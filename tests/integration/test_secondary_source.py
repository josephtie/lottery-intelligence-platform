"""Integration tests for the independent-source import and reconciliation."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import psycopg

from lottery_intelligence_platform.secondary_source import (
    import_observations,
    reconcile,
)

TEST_DATABASE_URL = os.getenv("LOTTERY_TEST_DATABASE_URL")


class _MemoryStore:
    """Minimal RawObjectStore double: put() returns a content-addressed ref."""

    def __init__(self):
        self.objects = {}

    def put(self, payload, content_type="application/octet-stream"):
        import hashlib
        from lottery_intelligence_platform.raw import RawObjectRef, raw_object_key

        digest = hashlib.sha256(payload).hexdigest()
        key = raw_object_key(digest)
        self.objects[key] = payload
        return RawObjectRef(digest, key, len(payload), content_type)


def _canonical_numbers(connection, draw_date, type_code):
    """Same rule reconcile() applies: latest-created draw for (date, type)."""
    rows = connection.execute(
        """SELECT n.number FROM core.draw_numbers n
           JOIN core.draws d ON d.canonical_draw_version_id = n.draw_version_id
           JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
           WHERE n.number_role = 'WINNING' AND d.draw_id = (
               SELECT d2.draw_id FROM core.draws d2
               JOIN catalog.draw_types dt2 ON dt2.draw_type_id = d2.draw_type_id
               WHERE d2.scheduled_date = %s AND dt2.code = %s
               ORDER BY d2.created_at DESC LIMIT 1)
           ORDER BY n.position""",
        (draw_date, type_code),
    ).fetchall()
    return [r[0] for r in rows]


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class SecondarySourceIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)
        self.store = _MemoryStore()
        # Any real settled draw gives us ground truth to compare against.
        row = self.connection.execute(
            """SELECT d.scheduled_date, dt.display_name, dt.code
               FROM core.draws d
               JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
               WHERE d.status = 'SETTLED'
               ORDER BY d.scheduled_date DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            self.skipTest("no settled draw in test database")
        self.draw_date, self.draw_name, self.type_code = row
        self.winning = _canonical_numbers(
            self.connection, self.draw_date, self.type_code)

    def tearDown(self):
        self.connection.rollback()
        self.connection.close()

    def _write(self, records):
        fd, name = tempfile.mkstemp(suffix=".ndjson")
        with os.fdopen(fd, "w") as fh:
            for record in records:
                fh.write(json.dumps(record) + "\n")
        return Path(name)

    def _import_and_reconcile(self, records):
        result = import_observations(self.connection, self.store, self._write(records))
        counts = reconcile(self.connection)
        return result, counts

    def test_matching_observation_records_match(self):
        _, counts = self._import_and_reconcile([{
            "draw_date": str(self.draw_date),
            "draw_name": self.draw_name,
            "winning_numbers": self.winning,
        }])
        self.assertEqual(counts["MATCH"], 1)

    def test_divergent_observation_records_mismatch_and_alert(self):
        wrong = self.winning.copy()
        wrong[0] = 90 if wrong[0] != 90 else 1
        self._import_and_reconcile([{
            "draw_date": str(self.draw_date),
            "draw_name": self.draw_name,
            "winning_numbers": wrong,
        }])
        outcome = self.connection.execute(
            """SELECT outcome FROM ingestion.source_comparisons
               ORDER BY compared_at DESC LIMIT 1"""
        ).fetchone()[0]
        self.assertEqual(outcome, "MISMATCH")
        alert = self.connection.execute(
            "SELECT code, severity FROM ops.alerts ORDER BY raised_at DESC LIMIT 1"
        ).fetchone()
        self.assertEqual((alert[0], alert[1]), ("SOURCE_CONFLICT", "CRITICAL"))

    def test_unknown_date_records_missing_primary(self):
        _, counts = self._import_and_reconcile([{
            "draw_date": "1999-01-01",
            "draw_name": self.draw_name,
            "winning_numbers": self.winning,
        }])
        self.assertEqual(counts["MISSING_PRIMARY"], 1)

    def test_unknown_draw_name_records_unmatched(self):
        _, counts = self._import_and_reconcile([{
            "draw_date": str(self.draw_date),
            "draw_name": "Totally Invented Draw",
            "winning_numbers": [1, 2, 3, 4, 5],
        }])
        self.assertEqual(counts["UNMATCHED_NAME"], 1)

    def test_reimport_is_idempotent(self):
        records = [{
            "draw_date": str(self.draw_date),
            "draw_name": self.draw_name,
            "winning_numbers": self.winning,
        }]
        first, _ = self._import_and_reconcile(records)
        second = import_observations(self.connection, self.store, self._write(records))
        self.assertEqual(first["imported"], 1)
        self.assertEqual(second["skipped_existing"], 1)


if __name__ == "__main__":
    unittest.main()
