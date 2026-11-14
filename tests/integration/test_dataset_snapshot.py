import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from lottery_intelligence_platform.artifacts import LocalArtifactStore, export_dataset_artifact
from lottery_intelligence_platform.dataset_repository import create_dataset_snapshot

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
class DatasetSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def test_snapshot_is_idempotent_and_marks_unverified_history_exploratory(self):
        with rollback_transaction(self.connection):
            cutoff = datetime.now(timezone.utc) + timedelta(days=1)
            first = create_dataset_snapshot(
                self.connection,
                dataset_code="lotobonheur_archive_snapshot_test",
                display_name="Loto Bonheur archive snapshot test",
                cutoff_at=cutoff,
            )
            second = create_dataset_snapshot(
                self.connection,
                dataset_code="lotobonheur_archive_snapshot_test",
                display_name="Loto Bonheur archive snapshot test",
                cutoff_at=cutoff,
            )
            member_count = self.connection.execute(
                "SELECT count(*) FROM datasets.dataset_members WHERE dataset_version_id = %s",
                (first.dataset_version_id,),
            ).fetchone()[0]

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(second.dataset_version_id, first.dataset_version_id)
            self.assertEqual(member_count, len(first.manifest.draw_version_ids))
            self.assertIn("UNVERIFIED", first.manifest.historical_effectivity_statuses)
            self.assertEqual(first.manifest.modeling_eligibility, "EXPLORATORY_ONLY")

    def test_artifact_export_registers_verifiable_local_objects_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))
            with rollback_transaction(self.connection):
                cutoff = datetime.now(timezone.utc) + timedelta(days=1)
                snapshot = create_dataset_snapshot(
                    self.connection,
                    dataset_code="lotobonheur_archive_artifact_test",
                    display_name="Loto Bonheur archive artifact test",
                    cutoff_at=cutoff,
                )

                first = export_dataset_artifact(
                    self.connection,
                    store,
                    dataset_version_id=str(snapshot.dataset_version_id),
                    dataset_code="lotobonheur_archive_artifact_test",
                )
                second = export_dataset_artifact(
                    self.connection,
                    store,
                    dataset_version_id=str(snapshot.dataset_version_id),
                    dataset_code="lotobonheur_archive_artifact_test",
                )
                artifacts = self.connection.execute(
                    """SELECT artifact_type, sha256, object_key, row_count
                       FROM datasets.dataset_artifacts
                       WHERE dataset_version_id = %s
                       ORDER BY artifact_type""",
                    (snapshot.dataset_version_id,),
                ).fetchall()

            self.assertEqual(first, second)
            self.assertEqual(len(artifacts), 2)
            self.assertEqual(
                {row[0] for row in artifacts},
                {"DRAW_NUMBERS_PARQUET", "MANIFEST_JSON"},
            )
            by_type = {row[0]: row for row in artifacts}
            self.assertEqual(first[0].sha256, by_type["MANIFEST_JSON"][1])
            self.assertEqual(first[1].sha256, by_type["DRAW_NUMBERS_PARQUET"][1])
            self.assertTrue((Path(directory) / first[0].object_key.replace("/", "_")).exists())
            self.assertTrue((Path(directory) / first[1].object_key.replace("/", "_")).exists())
            self.assertEqual(first[0].row_count, len(snapshot.manifest.draw_version_ids))


if __name__ == "__main__":
    unittest.main()
