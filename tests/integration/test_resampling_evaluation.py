import os
import unittest
from contextlib import contextmanager

import psycopg

from lottery_intelligence_platform.resampling_evaluation import (
    evaluate_dependence_aware_resampling,
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
class ResamplingEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def test_block_bootstrap_metrics_and_finding_recorded(self):
        with rollback_transaction(self.connection):
            definition = {
                "mode": "expanding",
                "min_train_days": 365,
                "test_days": 1800,
                "step_days": 1800,
            }
            plan = register_evaluation_plan(
                self.connection, code="test_resampling_plan", definition=definition,
            )
            materialize_windows(
                self.connection,
                evaluation_plan_id=plan.evaluation_plan_id,
                dataset_version_id=DATASET_VERSION,
                definition=definition,
            )
            result = evaluate_dependence_aware_resampling(
                self.connection,
                dataset_version_id=DATASET_VERSION,
                evaluation_plan_id=plan.evaluation_plan_id,
                bootstrap_resamples=49,
            )
            rows = self.connection.execute(
                """SELECT details->>'iid_classification',
                          details->>'block_classification',
                          details->>'classification_changed'
                   FROM research.experiment_metrics
                   WHERE experiment_id = %s""",
                (result["experiment"],),
            ).fetchall()
            self.assertTrue(rows)
            for iid_class, block_class, changed in rows:
                self.assertIn(iid_class, {"better", "worse", "inconclusive"})
                self.assertIn(block_class, {"better", "worse", "inconclusive"})
                self.assertEqual(changed == "true", iid_class != block_class)
            finding = self.connection.execute(
                "SELECT status FROM research.findings WHERE experiment_id = %s",
                (result["experiment"],),
            ).fetchone()
            self.assertIn(finding[0], {"SUPPORTED", "REJECTED", "INCONCLUSIVE"})


if __name__ == "__main__":
    unittest.main()
