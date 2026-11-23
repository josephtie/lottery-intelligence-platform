import os
import unittest
from contextlib import contextmanager

import psycopg

from lottery_intelligence_platform.calibration import probability_predictions
from lottery_intelligence_platform.calibration_evaluation import (
    evaluate_calibration_walkforward,
)
from lottery_intelligence_platform.frequency_baseline import NUMBERS_MIN
from lottery_intelligence_platform.model_evaluation import _draws_in_range
from lottery_intelligence_platform.models import NUMBER_COUNT
from lottery_intelligence_platform.walkforward import (
    materialize_windows,
    register_evaluation_plan,
)

TEST_DATABASE_URL = os.getenv("LOTTERY_TEST_DATABASE_URL")
DATASET_VERSION = "a370db21-39d5-43c6-a614-574e70233efc"


class RollbackProbe(Exception):
    pass


@contextmanager
def rollback_transaction(connection):
    try:
        with connection.transaction():
            yield
            raise RollbackProbe
    except RollbackProbe:
        pass


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class CalibrationEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def _single_window_plan(self):
        definition = {
            "mode": "expanding",
            "min_train_days": 365,
            "test_days": 1800,
            "step_days": 1800,
        }
        plan = register_evaluation_plan(
            self.connection,
            code="test_calibration_plan",
            definition=definition,
        )
        materialize_windows(
            self.connection,
            evaluation_plan_id=plan.evaluation_plan_id,
            dataset_version_id=DATASET_VERSION,
            definition=definition,
        )
        return plan.evaluation_plan_id

    def test_calibration_metrics_and_findings_are_recorded(self):
        with rollback_transaction(self.connection):
            plan_id = self._single_window_plan()
            result = evaluate_calibration_walkforward(
                self.connection,
                dataset_version_id=DATASET_VERSION,
                evaluation_plan_id=plan_id,
                bootstrap_resamples=49,
            )
            experiment_id = result["experiments"]["top_k_frequency"]
            metric_names = {
                row[0] for row in self.connection.execute(
                    "SELECT DISTINCT metric_name FROM research.experiment_metrics WHERE experiment_id = %s",
                    (experiment_id,),
                ).fetchall()
            }
            self.assertEqual(
                metric_names,
                {"brier_score", "log_loss", "expected_calibration_error"},
            )
            versions = self.connection.execute(
                "SELECT DISTINCT details->>'calibration_version' FROM research.experiment_metrics WHERE experiment_id = %s",
                (experiment_id,),
            ).fetchall()
            self.assertEqual(versions, [("v2",)])
            finding = self.connection.execute(
                "SELECT status FROM research.findings WHERE experiment_id = %s",
                (experiment_id,),
            ).fetchone()
            self.assertIn(finding[0], {"SUPPORTED", "REJECTED", "INCONCLUSIVE"})

    def test_stored_predictions_match_train_only_recomputation(self):
        with rollback_transaction(self.connection):
            plan_id = self._single_window_plan()
            result = evaluate_calibration_walkforward(
                self.connection,
                dataset_version_id=DATASET_VERSION,
                evaluation_plan_id=plan_id,
                bootstrap_resamples=49,
            )
            experiment_id = result["experiments"]["top_k_frequency"]
            row = self.connection.execute(
                """SELECT m.details->>'draw_type', m.details->>'mean_predicted',
                          m.details->>'train_draws', w.train_start, w.train_end,
                          w.test_start, w.test_end
                   FROM research.experiment_metrics m
                   JOIN research.experiment_runs r ON r.experiment_run_id = m.experiment_run_id
                   JOIN research.evaluation_windows w ON w.evaluation_window_id = r.evaluation_window_id
                   WHERE m.experiment_id = %s AND m.metric_name = 'brier_score'
                   ORDER BY m.experiment_metric_id LIMIT 1""",
                (experiment_id,),
            ).fetchone()
            draw_type, mean_predicted, train_draws, train_start, train_end, test_start, test_end = row
            draws = _draws_in_range(
                self.connection, DATASET_VERSION, train_start, test_end
            )[draw_type]
            train = [d for d in draws if d[0] <= train_end]
            self.assertEqual(len(train), int(train_draws))
            counts = [0] * NUMBER_COUNT
            for _, _, numbers in train:
                for number in numbers:
                    counts[number - NUMBERS_MIN] += 1
            preds = probability_predictions(
                "top_k_frequency", counts, len(train),
                {"kind": "expanding_train_frequency"},
            )
            self.assertAlmostEqual(sum(preds) / len(preds), float(mean_predicted), places=9)

    def test_null_experiment_records_no_advantage(self):
        with rollback_transaction(self.connection):
            plan_id = self._single_window_plan()
            result = evaluate_calibration_walkforward(
                self.connection,
                dataset_version_id=DATASET_VERSION,
                evaluation_plan_id=plan_id,
                bootstrap_resamples=49,
            )
            experiment_id = result["experiments"]["null_model_benchmark"]
            count = self.connection.execute(
                """SELECT count(*) FROM research.experiment_metrics
                   WHERE experiment_id = %s
                     AND details ? 'brier_advantage_vs_null'""",
                (experiment_id,),
            ).fetchone()[0]
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
