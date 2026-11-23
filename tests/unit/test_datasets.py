import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from lottery_intelligence_platform.datasets import (
    DatasetSnapshotManifest,
    compare_dataset_versions,
)


class DatasetManifestTests(unittest.TestCase):
    def setUp(self):
        self.first = str(uuid4())
        self.second = str(uuid4())
        self.cutoff = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)

    def manifest(self, draw_ids, cutoff=None, code_version="abc123"):
        return DatasetSnapshotManifest(
            draw_version_ids=tuple(draw_ids),
            cutoff_at=cutoff or self.cutoff,
            schema_version="1",
            code_version=code_version,
        )

    def test_hash_is_independent_of_member_input_order(self):
        left = self.manifest([self.first, self.second])
        right = self.manifest([self.second, self.first])

        self.assertEqual(left.sha256, right.sha256)
        self.assertEqual(left.draw_version_ids, right.draw_version_ids)

    def test_hash_changes_when_cutoff_or_code_changes(self):
        baseline = self.manifest([self.first])

        self.assertNotEqual(
            baseline.sha256,
            self.manifest([self.first], cutoff=self.cutoff + timedelta(seconds=1)).sha256,
        )
        self.assertNotEqual(baseline.sha256, self.manifest([self.first], code_version="def456").sha256)

    def test_duplicate_draw_versions_are_rejected(self):
        with self.assertRaises(ValueError):
            self.manifest([self.first, self.first])

    def test_naive_cutoff_is_rejected(self):
        with self.assertRaises(ValueError):
            self.manifest([self.first], cutoff=datetime(2026, 10, 3, 12, 0))

    def test_comparison_reports_added_and_removed_members(self):
        left = self.manifest([self.first])
        right = self.manifest([self.second])

        result = compare_dataset_versions(left, right)

        self.assertFalse(result["same_manifest"])
        self.assertEqual(result["added_draw_version_ids"], [self.second])
        self.assertEqual(result["removed_draw_version_ids"], [self.first])


if __name__ == "__main__":
    unittest.main()
