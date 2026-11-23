import hashlib
import os
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timezone
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from lottery_intelligence_platform.collectors.lotobonheur import CollectedBatch, ScheduleObservation
from lottery_intelligence_platform.draw_registry import DrawRegistry
from lottery_intelligence_platform.ingestion import ingest_payload
from lottery_intelligence_platform.raw import RawObjectRef, raw_object_key
from lottery_intelligence_platform.validation import ValidationReport

TEST_DATABASE_URL = os.getenv("LOTTERY_TEST_DATABASE_URL")


class RollbackProbe(Exception):
    pass


class FakeRawObjectStore:
    def put(self, payload, content_type="application/octet-stream"):
        digest = hashlib.sha256(payload).hexdigest()
        return RawObjectRef(digest, raw_object_key(digest), len(payload), content_type)


@contextmanager
def rollback_transaction(connection):
    try:
        with connection.transaction():
            yield
            raise RollbackProbe
    except RollbackProbe:
        pass


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class DrawTypeDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def test_official_draw_name_creates_reviewable_type_without_merging_names(self):
        with rollback_transaction(self.connection):
            game_id, game_version_id, source_id = uuid4(), uuid4(), uuid4()
            self.connection.execute(
                "INSERT INTO catalog.games (game_id, code, display_name, country_code, timezone_name) VALUES (%s, %s, %s, 'CI', 'Africa/Abidjan')",
                (game_id, f"type-discovery-{game_id.hex}", "Loto Bonheur test"),
            )
            self.connection.execute(
                """INSERT INTO catalog.game_versions
                   (game_version_id, game_id, version, effective_from, rules)
                   VALUES (%s, %s, 'test-v1', %s, %s)""",
                (game_version_id, game_id, date(2026, 1, 1), Jsonb({})),
            )
            self.connection.execute(
                "INSERT INTO ingestion.sources (source_id, code, display_name, source_kind) VALUES (%s, %s, %s, 'OFFICIAL')",
                (source_id, f"type-discovery-source-{game_id.hex}", "Loto Bonheur source"),
            )
            receipt = ingest_payload(
                self.connection,
                FakeRawObjectStore(),
                source_id=source_id,
                collector_name="schedule-test",
                collector_version="1",
                payload=b"schedule",
                response_status=200,
            )
            observation = ScheduleObservation(
                "draw-external-1", "event-1", "Moaye", date(2026, 10, 3),
                "2026-10-03T15:55:00Z", datetime(2026, 10, 3, 15, 55, tzinfo=timezone.utc),
                "UTC", "15H55", False, "Moaye", {"name": "Moaye"},
            )
            registry = DrawRegistry(
                self.connection,
                game_id=game_id,
                game_version_id=game_version_id,
                source_id=source_id,
                auto_create_draw_types=True,
            )

            result = registry.register_schedule_batch(
                CollectedBatch((receipt,), ValidationReport("PASSED", (observation,), ()))
            )
            draw_type = self.connection.execute(
                "SELECT display_name, rules FROM catalog.draw_types WHERE game_version_id = %s",
                (game_version_id,),
            ).fetchone()

            self.assertEqual(result[0].created, True)
            self.assertEqual(draw_type[0], "Moaye")
            self.assertEqual(draw_type[1]["modeling_eligibility"], "REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
