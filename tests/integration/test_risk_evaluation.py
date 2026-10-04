import os
import unittest
from contextlib import contextmanager

import psycopg

from lottery_intelligence_platform.risk_evaluation import evaluate_strategy_risk
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
class RiskEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def test_all_four_risk_families_record_metrics(self):
        with rollback_transaction(self.connection):
            definition = {
                "mode": "expanding",
                "min_train_days": 365,
                "test_days": 1800,
                "step_days": 1800,
            }
            plan = register_evaluation_plan(
                self.connection, code="test_risk_plan", definition=definition,
            )
            materialize_windows(
                self.connection,
                evaluation_plan_id=plan.evaluation_plan_id,
                dataset_version_id=DATASET_VERSION,
                definition=definition,
            )
            result = evaluate_strategy_risk(
                self.connection,
                dataset_version_id=DATASET_VERSION,
                evaluation_plan_id=plan.evaluation_plan_id,
                bootstrap_resamples=19,
                ruin_paths=19,
            )
            self.assertEqual(len(result["experiments"]), 4)
            expected_metrics = {
                "turbo_strategy_simulator": "simulated_net_result",
                "strategy_benchmark": "net_advantage_vs_random",
                "payout_sensitivity": "breakeven_multiplier",
                "portfolio_risk": "portfolio_risk",
            }
            for code, metric in expected_metrics.items():
                count = self.connection.execute(
                    """SELECT count(*) FROM research.experiment_metrics
                       WHERE experiment_id = %s AND metric_name = %s""",
                    (result["experiments"][code], metric),
                ).fetchone()[0]
                self.assertGreater(count, 0, f"missing metrics for {code}")

            unverified = self.connection.execute(
                """SELECT DISTINCT details->>'payout_rule_verification'
                   FROM research.experiment_metrics
                   WHERE experiment_id = %s""",
                (result["experiments"]["turbo_strategy_simulator"],),
            ).fetchall()
            self.assertEqual(unverified, [("UNVERIFIED",)])

            finding_count = self.connection.execute(
                "SELECT count(*) FROM research.findings WHERE experiment_id = ANY(%s)",
                (list(result["experiments"].values()),),
            ).fetchone()[0]
            self.assertEqual(finding_count, 4)


if __name__ == "__main__":
    unittest.main()
