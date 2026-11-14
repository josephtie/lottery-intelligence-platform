import os
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from uuid import uuid4

import psycopg

from lottery_intelligence_platform.prediction_generation import (
    GENERATOR_CODES,
    ensure_default_cohort,
    generate_predictions,
    pick_top_k,
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


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class PredictionGenerationTests(unittest.TestCase):
    def tearDown(self):
        self.connection.close()

    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)
        ensure_default_cohort(self.connection)

    def test_cohort_registration_is_idempotent(self):
        with rollback_transaction(self.connection):
            first = ensure_default_cohort(self.connection)
            second = ensure_default_cohort(self.connection)
            self.assertEqual(first, second)
            members = self.connection.execute(
                "SELECT COUNT(*) FROM research.prospective_cohort_members WHERE cohort_version_id = %s",
                (first,),
            ).fetchone()[0]
            self.assertEqual(members, len(GENERATOR_CODES))

    def test_generates_for_active_types_and_is_idempotent(self):
        with rollback_transaction(self.connection):
            result = generate_predictions(self.connection)
            self.assertGreaterEqual(result.targets, 1)
            self.assertGreaterEqual(result.created + result.reused, 1)
            for code in GENERATOR_CODES:
                self.assertGreaterEqual(result.by_model.get(code, 0), 1)
            # coverage rows exist for every attempted combination
            coverage = self.connection.execute(
                "SELECT COUNT(*) FROM research.prediction_coverage WHERE status = 'GENERATED'"
            ).fetchone()[0]
            self.assertGreaterEqual(coverage, sum(result.by_model.values()))

            second = generate_predictions(self.connection)
            self.assertEqual(second.created, 0)
            self.assertEqual(second.reused, result.created + result.reused)

    def test_missing_cohort_returns_empty(self):
        with rollback_transaction(self.connection):
            result = generate_predictions(self.connection, cohort_code="no_such_cohort")
            self.assertIsNone(result.cohort_version_id)
            self.assertEqual(result.created, 0)

    def test_picks_use_only_draws_before_target_date(self):
        with rollback_transaction(self.connection):
            draw_type_id, max_date = self.connection.execute(
                """SELECT draw_type_id, MAX(scheduled_date) FROM core.draws
                   GROUP BY draw_type_id ORDER BY 2 DESC LIMIT 1"""
            ).fetchone()
            target = max_date + timedelta(days=1)
            # Insert a fake future draw result that would corrupt picks if used.
            new_draw_id = uuid4()
            game_version_id, game_id = self.connection.execute(
                "SELECT game_version_id, game_id FROM core.draws WHERE draw_type_id = %s LIMIT 1",
                (draw_type_id,),
            ).fetchone()
            source_id, raw_object_id = self.connection.execute(
                """SELECT source_id, raw_object_id FROM core.draw_versions
                   WHERE draw_id = (SELECT draw_id FROM core.draws WHERE draw_type_id = %s LIMIT 1)""",
                (draw_type_id,),
            ).fetchone()
            self.connection.execute(
                """INSERT INTO core.draws (draw_id, game_id, game_version_id, draw_type_id,
                        scheduled_date, scheduled_sequence, status)
                   VALUES (%s, %s, %s, %s, %s, 9, 'FROZEN')""",
                (new_draw_id, game_id, game_version_id, draw_type_id, max_date),
            )
            version_id = uuid4()
            self.connection.execute(
                """INSERT INTO core.draw_versions
                   (draw_version_id, draw_id, version_number, source_id, raw_object_id,
                    payload_sha256, result_observed_at, validation_status)
                   VALUES (%s, %s, 99, %s, %s, repeat('b',64), '2000-01-01', 'VALID')""",
                (version_id, new_draw_id, source_id, raw_object_id),
            )
            for pos, num in enumerate([89, 90, 88, 87, 86], start=1):
                self.connection.execute(
                    """INSERT INTO core.draw_numbers
                       (draw_version_id, number_role, position, number)
                       VALUES (%s, 'WINNING', %s, %s)""",
                    (version_id, pos, num),
                )
            # picks for a target BEFORE the planted draw must ignore it entirely
            picks = pick_top_k(self.connection, draw_type_id, max_date, {"pick_count": 2}, None)
            expected = [
                r[0] for r in self.connection.execute(
                    """SELECT number FROM (
                           SELECT dn.number, COUNT(*) c FROM core.draws d
                           JOIN core.draw_versions dv ON dv.draw_id=d.draw_id AND dv.validation_status='VALID'
                           JOIN core.draw_numbers dn ON dn.draw_version_id=dv.draw_version_id AND dn.number_role='WINNING'
                           WHERE d.draw_type_id=%s AND d.scheduled_date < %s
                           GROUP BY dn.number) t
                       ORDER BY c DESC, number LIMIT 2""",
                    (draw_type_id, max_date),
                ).fetchall()
            ]
            self.assertEqual(sorted(picks), sorted(expected))
            self.assertEqual(
                picks,
                pick_top_k(self.connection, draw_type_id, max_date, {"pick_count": 2}, None),
            )

    def test_recorded_predictions_carry_versioning(self):
        with rollback_transaction(self.connection):
            generate_predictions(self.connection)
            row = self.connection.execute(
                """SELECT mv.code, p.parameters->>'pick_count', p.stake,
                          p.dataset_version_id IS NOT NULL,
                          p.parameters->>'cohort_version_id' IS NOT NULL
                   FROM research.predictions p
                   JOIN research.model_versions mv ON mv.model_version_id = p.model_version_id
                   WHERE p.parameters->>'generator' IS NOT NULL
                   LIMIT 1"""
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertIn(row[0], GENERATOR_CODES)
            self.assertEqual(row[1], "2")
            self.assertEqual(float(row[2]), 100.0)
            self.assertTrue(row[4])


if __name__ == "__main__":
    unittest.main()
