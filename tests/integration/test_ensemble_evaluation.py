import os
import unittest
from contextlib import contextmanager

import psycopg

from lottery_intelligence_platform.ensemble_evaluation import (
    evaluate_ensemble_and_ranking,
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
class EnsembleEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def test_ensemble_and_ranking_metrics_are_recorded(self):
        with rollback_transaction(self.connection):
            definition = {
                "mode": "expanding",
                "min_train_days": 365,
                "test_days": 1800,
                "step_days": 1800,
            }
            plan = register_evaluation_plan(
                self.connection, code="test_ensemble_plan", definition=definition,
            )
            materialize_windows(
                self.connection,
                evaluation_plan_id=plan.evaluation_plan_id,
                dataset_version_id=DATASET_VERSION,
                definition=definition,
            )
            result = evaluate_ensemble_and_ranking(
                self.connection,
                dataset_version_id=DATASET_VERSION,
                evaluation_plan_id=plan.evaluation_plan_id,
                change_point_permutations=19,
                bootstrap_resamples=19,
            )
            ensemble_id = result["experiments"]["ensemble_ablation"]
            ranking_id = result["experiments"]["candidate_ranking"]

            rows = self.connection.execute(
                """SELECT details->'ablation_contributions',
                          details->'component_briers',
                          details->'advantage_vs_null',
                          details->'best_single_component'
                   FROM research.experiment_metrics
                   WHERE experiment_id = %s""",
                (ensemble_id,),
            ).fetchall()
            self.assertTrue(rows)
            for ablations, briers, advantage, best in rows:
                self.assertEqual(
                    set(ablations), {"expanding", "bayesian", "rolling", "regime"}
                )
                self.assertIn(best, set(briers))
                self.assertIn("ci_low", advantage)

            ranking = self.connection.execute(
                """SELECT count(*), avg((details->>'coverage_lift')::float)
                   FROM research.experiment_metrics
                   WHERE experiment_id = %s""",
                (ranking_id,),
            ).fetchone()
            self.assertGreater(ranking[0], 0)
            self.assertGreater(ranking[1], 0)

            finding_count = self.connection.execute(
                "SELECT count(*) FROM research.findings WHERE experiment_id IN (%s, %s)",
                (ensemble_id, ranking_id),
            ).fetchone()[0]
            self.assertEqual(finding_count, 2)


if __name__ == "__main__":
    unittest.main()
