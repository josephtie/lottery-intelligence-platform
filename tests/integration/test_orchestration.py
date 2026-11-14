import os
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from uuid import uuid4

import psycopg

from lottery_intelligence_platform.scheduler import (
    claim_next_run,
    complete_run,
    emit_event,
    enqueue_run,
    ensure_jobs,
    fail_run,
    run_due,
)
from lottery_intelligence_platform.settlement import (
    attempt_prediction_amendment,
    settle_draw,
)

TEST_DATABASE_URL = os.getenv("LOTTERY_TEST_DATABASE_URL")


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


def insert_prediction(connection, *, draw_type_id, scheduled_date, numbers,
                      created_at="2000-01-01", strategy_version_id=None, status="PENDING"):
    prediction_id = uuid4()
    connection.execute(
        """INSERT INTO research.predictions
           (prediction_id, model_version_id, strategy_version_id, draw_type_id,
            scheduled_date, predicted_numbers, created_at, status)
           VALUES (
               %s,
               (SELECT model_version_id FROM research.model_versions LIMIT 1),
               %s, %s, %s, %s, %s, %s)""",
        (prediction_id, strategy_version_id, draw_type_id, scheduled_date,
         numbers, created_at, status),
    )
    return prediction_id


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class SettlementPipelineTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)
        # Production state evolves (draws settle); build a synthetic FROZEN
        # draw per test inside its rollback transaction instead.
        row = self.connection.execute(
            """SELECT d.draw_type_id, d.game_version_id, d.game_id,
                      dv.source_id, dv.raw_object_id, d.scheduled_date
               FROM core.draws d
               JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
               WHERE dv.validation_status = 'VALID'
               ORDER BY d.scheduled_date DESC LIMIT 1"""
        ).fetchone()
        (self.draw_type_id, self.game_version_id, self.game_id,
         self.source_id, self.raw_object_id, self.base_date) = row
        self.draw_date = self.base_date + timedelta(days=3650)

    def tearDown(self):
        self.connection.close()

    def _new_draw(self, numbers=(10, 20, 30, 40, 50), status="FROZEN",
                  observed_at="2020-01-01", scheduled_date=None,
                  with_result=True):
        """Insert a synthetic draw + VALID version + ordered numbers.
        Must be called inside a rollback transaction."""
        draw_id = uuid4()
        self.connection.execute(
            """INSERT INTO core.draws
               (draw_id, game_id, game_version_id, draw_type_id,
                scheduled_date, scheduled_sequence, status)
               VALUES (%s, %s, %s, %s, %s, 9, %s)""",
            (draw_id, self.game_id, self.game_version_id, self.draw_type_id,
             scheduled_date or self.draw_date, status),
        )
        if not with_result:
            return draw_id, None
        version_id = uuid4()
        self.connection.execute(
            """INSERT INTO core.draw_versions
               (draw_version_id, draw_id, version_number, source_id, raw_object_id,
                payload_sha256, result_observed_at, validated_at, confirmed_at,
                validation_status)
               VALUES (%s, %s, 1, %s, %s, repeat('a', 64), %s, %s, %s, 'VALID')""",
            (version_id, draw_id, self.source_id, self.raw_object_id,
             observed_at, observed_at, observed_at),
        )
        for pos, num in enumerate(numbers, start=1):
            self.connection.execute(
                """INSERT INTO core.draw_numbers
                   (draw_version_id, number_role, position, number)
                   VALUES (%s, 'WINNING', %s, %s)""",
                (version_id, pos, num),
            )
        return draw_id, version_id

    # Spec 1/4/6: settlement is idempotent — a second run cannot double-settle.
    def test_double_settle_is_noop(self):
        with rollback_transaction(self.connection):
            self.draw_id, _ = self._new_draw()
            first = settle_draw(self.connection, self.draw_id)
            self.assertEqual(first.status, "SETTLED")
            second = settle_draw(self.connection, self.draw_id)
            self.assertEqual(second.status, "ALREADY_SETTLED")
            outcomes = self.connection.execute(
                "SELECT COUNT(*) FROM research.prediction_outcomes WHERE draw_id = %s",
                (self.draw_id,),
            ).fetchone()[0]
            third = settle_draw(self.connection, self.draw_id)
            self.assertEqual(third.status, "ALREADY_SETTLED")
            self.assertEqual(
                self.connection.execute(
                    "SELECT COUNT(*) FROM research.prediction_outcomes WHERE draw_id = %s",
                    (self.draw_id,),
                ).fetchone()[0],
                outcomes,
            )

    # Spec: PENDING -> LOCKED -> SCORED with real comparison + positional/turbo.
    def test_pending_prediction_locks_scores_with_outcome(self):
        with rollback_transaction(self.connection):
            self.draw_id, _ = self._new_draw(numbers=(31, 46, 7, 12, 88))
            prediction_id = insert_prediction(
                self.connection, draw_type_id=self.draw_type_id,
                scheduled_date=self.draw_date, numbers=[31, 46],
            )
            result = settle_draw(self.connection, self.draw_id)
            self.assertEqual(result.status, "SETTLED")
            self.assertGreaterEqual(result.predictions_locked, 1)
            self.assertGreaterEqual(result.predictions_scored, 1)

            row = self.connection.execute(
                """SELECT p.status, o.hit_count, o.positional_hits, o.metrics
                   FROM research.predictions p
                   JOIN research.prediction_outcomes o ON o.prediction_id = p.prediction_id
                   WHERE p.prediction_id = %s""",
                (prediction_id,),
            ).fetchone()
            self.assertEqual(row[0], "SCORED")
            self.assertEqual(row[1], 2)
            self.assertEqual(row[2]["first_2"], 2)
            turbo = row[3]["turbo"]
            self.assertTrue(turbo["turbo_2"]["hit"])
            self.assertEqual(turbo["turbo_2"]["multiplier"], 2400)
            self.assertEqual(turbo["turbo_5"]["multiplier"], 240)

    # Spec: a prediction created after the result was observed is INVALID.
    def test_late_prediction_invalidated_and_audited(self):
        with rollback_transaction(self.connection):
            self.draw_id, _ = self._new_draw()
            prediction_id = insert_prediction(
                self.connection, draw_type_id=self.draw_type_id,
                scheduled_date=self.draw_date, numbers=[1, 2],
                created_at="2999-01-01",
            )
            settle_draw(self.connection, self.draw_id)
            status = self.connection.execute(
                "SELECT status FROM research.predictions WHERE prediction_id = %s",
                (prediction_id,),
            ).fetchone()[0]
            self.assertEqual(status, "INVALID")
            audit = self.connection.execute(
                """SELECT outcome FROM ops.audit_events
                   WHERE entity_id = %s AND action = 'LATE_PREDICTION'""",
                (prediction_id,),
            ).fetchone()
            self.assertEqual(audit[0], "REJECTED")

    # Spec 3: no valid result -> no settlement.
    def test_draw_without_valid_result_is_skipped(self):
        with rollback_transaction(self.connection):
            new_draw_id, _ = self._new_draw(with_result=False)
            result = settle_draw(self.connection, new_draw_id)
            self.assertEqual(result.status, "NO_VALID_RESULT")
            self.assertEqual(
                self.connection.execute(
                    "SELECT status FROM core.draws WHERE draw_id = %s", (new_draw_id,)
                ).fetchone()[0],
                "FROZEN",
            )

    # Spec 5: modifying a LOCKED prediction is rejected and audited.
    def test_locked_prediction_amendment_rejected_audited(self):
        with rollback_transaction(self.connection):
            prediction_id = insert_prediction(
                self.connection, draw_type_id=self.draw_type_id,
                scheduled_date=self.draw_date,
                numbers=[5, 6],
            )
            self.connection.execute(
                """UPDATE research.predictions
                   SET status = 'LOCKED', locked_at = CURRENT_TIMESTAMP
                   WHERE prediction_id = %s""",
                (prediction_id,),
            )
            outcome = attempt_prediction_amendment(
                self.connection, prediction_id, actor="test", new_numbers=[9, 9],
            )
            self.assertEqual(outcome, "REJECTED")
            audit = self.connection.execute(
                """SELECT outcome FROM ops.audit_events
                   WHERE entity_id = %s AND action = 'AMEND_PREDICTION'""",
                (prediction_id,),
            ).fetchone()
            self.assertEqual(audit[0], "REJECTED")
            alert = self.connection.execute(
                """SELECT code FROM ops.alerts
                   WHERE entity_id = %s AND code = 'IMMUTABLE_PREDICTION_VIOLATION'""",
                (prediction_id,),
            ).fetchone()
            self.assertIsNotNone(alert)
            self.assertEqual(
                self.connection.execute(
                    "SELECT predicted_numbers FROM research.predictions WHERE prediction_id = %s",
                    (prediction_id,),
                ).fetchone()[0],
                [5, 6],
            )

    # Spec 9/10: a draw with no predictions and no strategy still settles.
    def test_draw_without_predictions_settles_cleanly(self):
        with rollback_transaction(self.connection):
            new_draw_id, _ = self._new_draw(numbers=(10, 20, 30, 40, 50))
            result = settle_draw(self.connection, new_draw_id)
            self.assertEqual(result.status, "SETTLED")
            self.assertEqual(result.predictions_scored, 0)

    # Spec 10: prediction without a strategy scores without strategy settlement.
    def test_prediction_without_strategy_no_strategy_settlement(self):
        with rollback_transaction(self.connection):
            self.draw_id, _ = self._new_draw()
            prediction_id = insert_prediction(
                self.connection, draw_type_id=self.draw_type_id,
                scheduled_date=self.draw_date, numbers=[70, 80],
            )
            settle_draw(self.connection, self.draw_id)
            self.assertEqual(
                self.connection.execute(
                    "SELECT status FROM research.predictions WHERE prediction_id = %s",
                    (prediction_id,),
                ).fetchone()[0],
                "SCORED",
            )
            self.assertIsNone(
                self.connection.execute(
                    "SELECT 1 FROM research.strategy_settlements WHERE prediction_id = %s",
                    (prediction_id,),
                ).fetchone()
            )

    # Spec 18: dataset_version containing draws on/after the target date
    # triggers LEAKAGE_DETECTED.
    def test_dataset_leakage_invalidates(self):
        with rollback_transaction(self.connection):
            # the settled draw sits at base_date; build a dataset_version that
            # already contains a member draw on/after the prediction target.
            self.draw_id, version_id = self._new_draw(scheduled_date=self.base_date)
            dataset_id = self.connection.execute(
                "SELECT dataset_id FROM datasets.datasets LIMIT 1"
            ).fetchone()[0]
            dataset_version_id = uuid4()
            self.connection.execute(
                """INSERT INTO datasets.dataset_versions
                   (dataset_version_id, dataset_id, version_number, cutoff_at,
                    schema_version, code_version, manifest, manifest_sha256)
                   VALUES (%s, %s, 9000, '2030-01-01', 'test', 'test', '{}',
                    repeat('c', 64))""",
                (dataset_version_id, dataset_id),
            )
            self.connection.execute(
                """INSERT INTO datasets.dataset_members
                   (dataset_version_id, draw_version_id, ordinal)
                   VALUES (%s, %s, 1)""",
                (dataset_version_id, version_id),
            )
            prediction_id = uuid4()
            self.connection.execute(
                """INSERT INTO research.predictions
                   (prediction_id, model_version_id, draw_type_id, scheduled_date,
                    predicted_numbers, created_at, dataset_version_id)
                   VALUES (
                       %s,
                       (SELECT model_version_id FROM research.model_versions LIMIT 1),
                       %s, %s, '{11,22}', '2000-01-01', %s)""",
                (prediction_id, self.draw_type_id, self.base_date, dataset_version_id),
            )
            settle_draw(self.connection, self.draw_id)
            self.assertEqual(
                self.connection.execute(
                    "SELECT status FROM research.predictions WHERE prediction_id = %s",
                    (prediction_id,),
                ).fetchone()[0],
                "INVALID",
            )
            self.assertIsNotNone(
                self.connection.execute(
                    "SELECT 1 FROM ops.alerts WHERE code = 'LEAKAGE_DETECTED' AND entity_id = %s",
                    (prediction_id,),
                ).fetchone()
            )


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class SchedulerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)
        ensure_jobs(self.connection)

    def tearDown(self):
        self.connection.close()

    # Spec: same idempotency key never creates two runs.
    def test_enqueue_idempotent(self):
        with rollback_transaction(self.connection):
            first = enqueue_run(self.connection, "settle_pending_draws", idempotency_key="t1")
            second = enqueue_run(self.connection, "settle_pending_draws", idempotency_key="t1")
            self.assertTrue(first[1])
            self.assertFalse(second[1])
            self.assertEqual(first[0], second[0])

    # Spec 2/8: a run that fails is retried, not lost.
    def test_failed_run_retries_and_recovers(self):
        with rollback_transaction(self.connection):
            run_id, _ = enqueue_run(
                self.connection, "daily_research_summary", idempotency_key="t2"
            )
            run = claim_next_run(self.connection, worker="w1")
            self.assertEqual(run.job_run_id, run_id)
            status = fail_run(self.connection, run_id, "boom")
            self.assertEqual(status, "RETRY_REQUIRED")
            # claimed run is not immediately re-claimed (backoff)
            self.assertIsNone(claim_next_run(self.connection, worker="w2"))
            self.connection.execute(
                "UPDATE ops.job_runs SET next_retry_at = CURRENT_TIMESTAMP - interval '1s' WHERE job_run_id = %s",
                (run_id,),
            )
            retried = claim_next_run(self.connection, worker="w2")
            self.assertEqual(retried.job_run_id, run_id)
            self.assertEqual(retried.retry_count, 1)
            complete_run(self.connection, run_id)
            self.assertEqual(
                self.connection.execute(
                    "SELECT status FROM ops.job_runs WHERE job_run_id = %s", (run_id,)
                ).fetchone()[0],
                "SUCCEEDED",
            )

    # Spec 6: run_due executes handlers; a crashing handler does not kill the worker.
    def test_run_due_survives_handler_crash(self):
        with rollback_transaction(self.connection):
            enqueue_run(self.connection, "daily_research_summary", idempotency_key="t3")
            counts = run_due(
                self.connection,
                {"daily_research_summary": lambda c, r: 1 / 0},
                max_runs=5,
            )
            self.assertEqual(counts["failed"], 1)
            self.assertIsNotNone(
                self.connection.execute(
                    """SELECT 1 FROM ops.job_events WHERE event_type = 'JOB_FAILED'
                       AND payload->>'code' = 'daily_research_summary'""",
                ).fetchone()
            )

    def test_run_due_executes_real_summary_handler(self):
        with rollback_transaction(self.connection):
            from lottery_intelligence_platform.orchestrator import handle_daily_research_summary

            enqueue_run(self.connection, "daily_research_summary", idempotency_key="t4")
            counts = run_due(
                self.connection,
                {"daily_research_summary": handle_daily_research_summary},
                max_runs=5,
            )
            self.assertEqual(counts["succeeded"], 1)
            event = self.connection.execute(
                """SELECT payload FROM ops.job_events
                   WHERE event_type = 'RESEARCH_SUMMARY'""",
            ).fetchone()
            self.assertIn("pending_predictions", event[0])


if __name__ == "__main__":
    unittest.main()
