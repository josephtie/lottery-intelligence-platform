import os
import unittest
from contextlib import contextmanager
from datetime import date

import psycopg

from lottery_intelligence_platform.strategy_lab import (
    ensure_turbo_payout_rule,
    evaluate_strategy_window,
    register_strategy,
    register_strategy_version,
    transition_strategy_version,
)
from lottery_intelligence_platform.walkforward import (
    materialize_windows,
    register_evaluation_plan,
    run_walkforward_evaluation,
)

TEST_DATABASE_URL = os.getenv("LOTTERY_TEST_DATABASE_URL")
DATASET_VERSION = "a370db21-39d5-43c6-a614-574e70233efc"
EXISTING_PLAN = "3d17e2a7-bfd4-4dc5-b89c-57e2059bdaeb"


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
class WalkForwardAndStrategyTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def test_walkforward_resume_is_idempotent(self):
        with rollback_transaction(self.connection):
            first = run_walkforward_evaluation(
                self.connection,
                dataset_version_id=DATASET_VERSION,
                evaluation_plan_id=EXISTING_PLAN,
            )
            second = run_walkforward_evaluation(
                self.connection,
                dataset_version_id=DATASET_VERSION,
                evaluation_plan_id=EXISTING_PLAN,
            )
            run_count = self.connection.execute(
                "SELECT count(*) FROM research.experiment_runs WHERE experiment_id = %s",
                (second["experiment_id"],),
            ).fetchone()[0]
            self.assertEqual(first["experiment_id"], second["experiment_id"])
            self.assertEqual(run_count, 8)
            self.assertTrue(all(window["skipped"] for window in second["windows"]))

    def test_small_plan_materializes_windows_deterministically(self):
        with rollback_transaction(self.connection):
            definition = {
                "mode": "expanding", "min_train_days": 730,
                "test_days": 1000, "step_days": 1000,
            }
            plan = register_evaluation_plan(
                self.connection, code="test_plan_small", definition=definition,
            )
            first = materialize_windows(
                self.connection,
                evaluation_plan_id=plan.evaluation_plan_id,
                dataset_version_id=DATASET_VERSION,
                definition=definition,
            )
            second = materialize_windows(
                self.connection,
                evaluation_plan_id=plan.evaluation_plan_id,
                dataset_version_id=DATASET_VERSION,
                definition=definition,
            )
            self.assertEqual(first, second)
            self.assertEqual(len(first), 2)

    def test_strategy_registry_and_economic_evaluation(self):
        with rollback_transaction(self.connection):
            context = self.connection.execute(
                """SELECT gv.game_id, gv.game_version_id, s.source_id
                   FROM catalog.game_versions gv, ingestion.sources s
                   WHERE s.code = 'lotobonheur_official' LIMIT 1"""
            ).fetchone()
            payout_rule_version_id = ensure_turbo_payout_rule(
                self.connection,
                game_id=context[0], game_version_id=context[1], source_id=context[2],
            )
            strategy_id = register_strategy(
                self.connection,
                code="test_turbo_topn",
                display_name="Test Turbo top-N",
            )
            version = register_strategy_version(
                self.connection,
                strategy_id=strategy_id,
                game_id=context[0],
                game_version_id=context[1],
                payout_rule_version_id=payout_rule_version_id,
                dataset_version_id=DATASET_VERSION,
                definition={
                    "selection": {"method": "top_k_frequency", "source": "train_window"},
                    "bet": {"kind": "turbo", "numbers_picked": 3, "stake": 100},
                },
            )
            same = register_strategy_version(
                self.connection,
                strategy_id=strategy_id,
                game_id=context[0],
                game_version_id=context[1],
                payout_rule_version_id=payout_rule_version_id,
                dataset_version_id=DATASET_VERSION,
                definition={
                    "selection": {"method": "top_k_frequency", "source": "train_window"},
                    "bet": {"kind": "turbo", "numbers_picked": 3, "stake": 100},
                },
            )
            transition_strategy_version(
                self.connection,
                strategy_version_id=version.strategy_version_id,
                new_status="BACKTESTED",
                reason="test transition",
            )
            window_id = self.connection.execute(
                """SELECT evaluation_window_id FROM research.evaluation_windows
                   WHERE evaluation_plan_id = %s ORDER BY ordinal LIMIT 1""",
                (EXISTING_PLAN,),
            ).fetchone()[0]
            results = evaluate_strategy_window(
                self.connection,
                strategy_version_id=version.strategy_version_id,
                evaluation_window_id=window_id,
            )
            evaluate_strategy_window(
                self.connection,
                strategy_version_id=version.strategy_version_id,
                evaluation_window_id=window_id,
            )
            rows = self.connection.execute(
                """SELECT count(*), min(draws_evaluated), max(hit_count)
                   FROM research.economic_evaluations
                   WHERE strategy_version_id = %s""",
                (version.strategy_version_id,),
            ).fetchone()
            events = self.connection.execute(
                """SELECT previous_status, new_status FROM research.strategy_version_status_events
                   WHERE strategy_version_id = %s ORDER BY occurred_at""",
                (version.strategy_version_id,),
            ).fetchall()

            self.assertEqual(same.strategy_version_id, version.strategy_version_id)
            self.assertFalse(same.created)
            self.assertGreater(len(results), 0)
            self.assertEqual(rows[0], len(results))
            self.assertTrue(all(r["draws_evaluated"] > 1 for r in results))
            self.assertGreater(rows[1], 1)
            self.assertEqual([(e[0], e[1]) for e in events], [(None, "DRAFT"), ("DRAFT", "BACKTESTED")])


if __name__ == "__main__":
    unittest.main()
