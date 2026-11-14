import os
import unittest
from contextlib import contextmanager
from datetime import date

import psycopg

from lottery_intelligence_platform.evaluation import (
    run_scoped_frequency_evaluation,
    temporal_scopes,
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
class TemporalEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)
        self.dataset_version_id = self.connection.execute(
            "SELECT dataset_version_id FROM datasets.dataset_versions ORDER BY created_at LIMIT 1"
        ).fetchone()[0]

    def tearDown(self):
        self.connection.close()

    def test_scopes_partition_members_without_overlap(self):
        with rollback_transaction(self.connection):
            scopes = temporal_scopes(
                self.connection,
                dataset_version_id=self.dataset_version_id,
                train_end=date(2024, 12, 31),
                validation_end=date(2025, 12, 31),
            )
            total = self.connection.execute(
                "SELECT count(*) FROM datasets.dataset_members WHERE dataset_version_id = %s",
                (self.dataset_version_id,),
            ).fetchone()[0]

            self.assertEqual([scope.scope for scope in scopes], ["TRAIN", "VALIDATION", "OUT_OF_SAMPLE"])
            self.assertEqual(sum(scope.member_count for scope in scopes), total)
            self.assertLessEqual(scopes[0].last_date, date(2024, 12, 31))
            self.assertGreater(scopes[1].first_date, date(2024, 12, 31))
            self.assertLessEqual(scopes[1].last_date, date(2025, 12, 31))
            self.assertGreater(scopes[2].first_date, date(2025, 12, 31))
            with self.assertRaises(ValueError):
                temporal_scopes(
                    self.connection,
                    dataset_version_id=self.dataset_version_id,
                    train_end=date(2025, 12, 31),
                    validation_end=date(2024, 12, 31),
                )

    def test_scoped_evaluation_records_run_per_scope(self):
        with rollback_transaction(self.connection):
            result = run_scoped_frequency_evaluation(
                self.connection,
                dataset_version_id=self.dataset_version_id,
                train_end=date(2025, 12, 31),
                validation_end=date(2026, 6, 30),
            )
            runs = self.connection.execute(
                """SELECT scope, status FROM research.experiment_runs
                   WHERE experiment_id = %s ORDER BY run_number""",
                (result["experiment_id"],),
            ).fetchall()
            metric_scopes = self.connection.execute(
                """SELECT DISTINCT metric_scope FROM research.experiment_metrics
                   WHERE experiment_id = %s""",
                (result["experiment_id"],),
            ).fetchall()

            self.assertEqual([run[0] for run in runs], ["TRAIN", "VALIDATION", "OUT_OF_SAMPLE"])
            self.assertTrue(all(run[1] == "COMPLETED" for run in runs))
            self.assertEqual(
                {row[0] for row in metric_scopes},
                {"TRAIN", "VALIDATION", "OUT_OF_SAMPLE"},
            )


if __name__ == "__main__":
    unittest.main()
