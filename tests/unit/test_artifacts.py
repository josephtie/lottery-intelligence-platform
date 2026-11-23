import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import duckdb

from lottery_intelligence_platform.artifacts import (
    ArtifactConflict,
    LocalArtifactStore,
    manifest_key,
    parquet_key,
    write_parquet_rows,
)


class ArtifactTests(unittest.TestCase):
    def test_local_store_is_idempotent_and_rejects_conflicting_content(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))

            self.assertTrue(store.put_if_absent("objects/a", b"payload", "text/plain"))
            self.assertFalse(store.put_if_absent("objects/a", b"payload", "text/plain"))
            with self.assertRaises(ArtifactConflict):
                store.put_if_absent("objects/a", b"different", "text/plain")

    def test_parquet_export_is_deterministic_and_preserves_rows(self):
        draw_version_id = str(uuid4())
        draw_id = str(uuid4())
        row = {
            "draw_version_id": draw_version_id,
            "draw_id": draw_id,
            "scheduled_date": date(2026, 10, 3),
            "draw_name": "Moaye",
            "result_group": "Moaye",
            "number_role": "WINNING",
            "number_position": 1,
            "number_value": 42,
            "result_observed_at": datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc),
            "validated_at": datetime(2026, 10, 3, 16, 1, tzinfo=timezone.utc),
            "confirmed_at": datetime(2026, 10, 3, 16, 2, tzinfo=timezone.utc),
            "raw_object_sha256": "a" * 64,
            "dataset_version_id": str(uuid4()),
            "manifest_sha256": "b" * 64,
        }

        first = write_parquet_rows([row])
        second = write_parquet_rows([row])

        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as directory:
            parquet_path = Path(directory) / "numbers.parquet"
            parquet_path.write_bytes(first)
            stored = duckdb.execute(
                "SELECT draw_version_id::TEXT, draw_id::TEXT, number_role, number_position, number_value FROM read_parquet(?)",
                (str(parquet_path),),
            ).fetchone()
        self.assertEqual(stored, (draw_version_id, draw_id, "WINNING", 1, 42))

    def test_artifact_keys_are_versioned_and_content_addressed(self):
        version_id = str(uuid4())
        digest = "c" * 64

        self.assertEqual(
            manifest_key(version_id, digest),
            f"datasets/{version_id}/manifest-{digest}.json",
        )
        self.assertEqual(
            parquet_key(version_id, digest),
            f"datasets/{version_id}/draw_numbers-{digest}.parquet",
        )


if __name__ == "__main__":
    unittest.main()
