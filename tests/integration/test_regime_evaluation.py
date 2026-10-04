import os
import unittest
from contextlib import contextmanager

import psycopg

from lottery_intelligence_platform.regime_evaluation import (
    evaluate_dependence_and_regime,
)
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
class RegimeEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def test_dependence_and_regime_metrics_are_recorded(self):
        with rollback_transaction(self.connection):
            definition = {
                "mode": "expanding",
                "min_train_days": 365,
                "test_days": 1800,
                "step_days": 1800,
            }
            plan = register_evaluation_plan(
                self.connection, code="test_regime_plan", definition=definition,
            )
            materialize_windows(
                self.connection,
                evaluation_plan_id=plan.evaluation_plan_id,
                dataset_version_id=DATASET_VERSION,
                definition=definition,
            )
            result = evaluate_dependence_and_regime(
                self.connection,
                dataset_version_id=DATASET_VERSION,
                evaluation_plan_id=plan.evaluation_plan_id,
                change_point_permutations=49,
                bootstrap_resamples=49,
            )
            dependence_id = result["experiments"]["conditional_dependence"]
            regime_id = result["experiments"]["regime_aware"]

            names = {
                r[0] for r in self.connection.execute(
                    "SELECT DISTINCT metric_name FROM research.experiment_metrics WHERE experiment_id = %s",
                    (dependence_id,),
                )
            }
            self.assertEqual(names, {"significant_pair_count"})

            regime_rows = self.connection.execute(
                """SELECT details->>'train_draws_full', details->>'train_draws_regime',
                          details->>'cutoff_period', details->>'change_point_detected'
                   FROM research.experiment_metrics
                   WHERE experiment_id = %s""",
                (regime_id,),
            ).fetchall()
            self.assertTrue(regime_rows)
            for full, regime, cutoff, detected in regime_rows:
                self.assertLessEqual(int(regime), int(full))
                if detected == "true":
                    self.assertIsNotNone(cutoff)

            rows = self.connection.execute(
                "SELECT status FROM research.findings WHERE experiment_id IN (%s, %s)",
                (dependence_id, regime_id),
            ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertTrue(
                {r[0] for r in rows} <= {"SUPPORTED", "REJECTED", "INCONCLUSIVE"}
            )


if __name__ == "__main__":
    unittest.main()
