import os
import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from uuid import uuid4

import psycopg

from lottery_intelligence_platform.predictions import (
    record_prediction,
    score_predictions,
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
class ProspectivePredictionTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)
        self.model_version_id = self.connection.execute(
            "SELECT model_version_id FROM research.model_versions LIMIT 1"
        ).fetchone()[0]
        self.draw_type_id, self.draw_date = self.connection.execute(
            """SELECT d.draw_type_id, d.scheduled_date FROM core.draws d
               WHERE EXISTS (
                   SELECT 1 FROM core.draw_versions dv
                   WHERE dv.draw_id = d.draw_id AND dv.validation_status = 'VALID'
               ) LIMIT 1"""
        ).fetchone()

    def tearDown(self):
        self.connection.close()

    def test_record_prediction_is_idempotent(self):
        with rollback_transaction(self.connection):
            future = date.today() + timedelta(days=365)
            first = record_prediction(
                self.connection,
                model_version_id=self.model_version_id,
                draw_type_id=self.draw_type_id,
                scheduled_date=future,
                predicted_numbers=[3, 17],
            )
            second = record_prediction(
                self.connection,
                model_version_id=self.model_version_id,
                draw_type_id=self.draw_type_id,
                scheduled_date=future,
                predicted_numbers=[3, 17],
            )
            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.prediction_id, second.prediction_id)

    def test_scoring_scores_and_invalidates_correctly(self):
        with rollback_transaction(self.connection):
            early_id = uuid4()
            late_id = uuid4()
            self.connection.execute(
                """INSERT INTO research.predictions
                   (prediction_id, model_version_id, draw_type_id, scheduled_date,
                    predicted_numbers, created_at)
                   VALUES (%s, %s, %s, %s, '{1,2}', '2000-01-01')""",
                (early_id, self.model_version_id, self.draw_type_id, self.draw_date),
            )
            self.connection.execute(
                """INSERT INTO research.predictions
                   (prediction_id, model_version_id, draw_type_id, scheduled_date,
                    predicted_numbers, created_at)
                   VALUES (%s, %s, %s, %s, '{1,3}', '2999-01-01')""",
                (late_id, self.model_version_id, self.draw_type_id, self.draw_date),
            )
            result = score_predictions(self.connection)
            self.assertGreaterEqual(result["scored"], 1)
            self.assertGreaterEqual(result["invalidated"], 1)

            scored = self.connection.execute(
                """SELECT p.status, s.hits FROM research.predictions p
                   JOIN research.prediction_scores s ON s.prediction_id = p.prediction_id
                   WHERE p.prediction_id = %s""",
                (early_id,),
            ).fetchone()
            self.assertEqual(scored[0], "SCORED")
            self.assertGreaterEqual(scored[1], 0)
            self.assertLessEqual(scored[1], 2)

            invalid = self.connection.execute(
                "SELECT status FROM research.predictions WHERE prediction_id = %s",
                (late_id,),
            ).fetchone()
            self.assertEqual(invalid[0], "INVALID")
            self.assertIsNone(
                self.connection.execute(
                    "SELECT 1 FROM research.prediction_scores WHERE prediction_id = %s",
                    (late_id,),
                ).fetchone()
            )

    def test_scoring_skips_draws_not_yet_recorded(self):
        with rollback_transaction(self.connection):
            missing_date = self.connection.execute(
                """SELECT max(scheduled_date) + interval '10 years'
                   FROM core.draws WHERE draw_type_id = %s""",
                (self.draw_type_id,),
            ).fetchone()[0].date()
            self.connection.execute(
                """INSERT INTO research.predictions
                   (prediction_id, model_version_id, draw_type_id, scheduled_date,
                    predicted_numbers, created_at)
                   VALUES (%s, %s, %s, %s, '{4,5}', '2000-01-01')""",
                (uuid4(), self.model_version_id, self.draw_type_id, missing_date),
            )
            result = score_predictions(self.connection)
            self.assertGreaterEqual(result["skipped_pending_draw"], 1)


if __name__ == "__main__":
    unittest.main()
