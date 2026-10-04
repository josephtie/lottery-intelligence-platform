import hashlib
import os
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timezone
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from lottery_intelligence_platform.collectors.lotobonheur import (
    CollectedBatch,
    ResultObservation,
    ScheduleObservation,
)
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
class DrawRegistryTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def create_context(self, draw_names=("Moaye",)):
        game_id, game_version_id, source_id = uuid4(), uuid4(), uuid4()
        self.connection.execute(
            "INSERT INTO catalog.games (game_id, code, display_name, country_code, timezone_name) VALUES (%s, %s, %s, 'CI', 'Africa/Abidjan')",
            (game_id, f"registry-{game_id.hex}", "Loto Bonheur test"),
        )
        self.connection.execute(
            """INSERT INTO catalog.game_versions
               (game_version_id, game_id, version, effective_from, rules)
               VALUES (%s, %s, 'test-1', %s, %s)""",
            (game_version_id, game_id, date(2026, 1, 1), Jsonb({
                "number_min": 1,
                "number_max": 90,
                "numbers_per_draw": 5,
                "duplicates_allowed": False,
            })),
        )
        draw_type_ids = {}
        for name in draw_names:
            draw_type_id = uuid4()
            code = "".join(character.lower() if character.isalnum() else "_" for character in name).strip("_")
            self.connection.execute(
                "INSERT INTO catalog.draw_types (draw_type_id, game_version_id, code, display_name, rules) VALUES (%s, %s, %s, %s, %s)",
                (draw_type_id, game_version_id, code, name, Jsonb({"session_name": name})),
            )
            draw_type_ids[name] = draw_type_id
        self.connection.execute(
            "INSERT INTO ingestion.sources (source_id, code, display_name, source_kind) VALUES (%s, %s, %s, 'OFFICIAL')",
            (source_id, f"registry-source-{game_id.hex}", "Loto Bonheur test source"),
        )
        return game_id, game_version_id, source_id, draw_type_ids

    def create_receipt(self, source_id, payload):
        return ingest_payload(
            self.connection,
            FakeRawObjectStore(),
            source_id=source_id,
            collector_name="draw-registry-test",
            collector_version="1",
            payload=payload,
            content_type="application/json",
            response_status=200,
        )

    def test_schedule_versions_are_idempotent_and_external_ids_are_separate(self):
        with rollback_transaction(self.connection):
            game_id, game_version_id, source_id, draw_types = self.create_context()
            receipt = self.create_receipt(source_id, b'{"schedule":1}')
            observation = ScheduleObservation(
                external_draw_id="759368",
                external_event_id="404",
                draw_name="Moaye",
                group_date=date(2026, 10, 3),
                source_datetime="2026-10-03T15:55:00Z",
                scheduled_at=datetime(2026, 10, 3, 15, 55, tzinfo=timezone.utc),
                source_timezone="UTC",
                end_time="15H55",
                is_single_set=False,
                preview="Moaye - Sam.15H55",
                source_data={"name": "Moaye", "id": "759368", "eventId": "404"},
            )
            batch = CollectedBatch((receipt,), ValidationReport("PASSED", (observation,), ()))
            registry = DrawRegistry(
                self.connection,
                game_id=game_id,
                game_version_id=game_version_id,
                source_id=source_id,
                draw_type_ids_by_name=draw_types,
            )

            first = registry.register_schedule_batch(batch)
            second = registry.register_schedule_batch(batch)

            self.assertTrue(first[0].created)
            self.assertFalse(second[0].created)
            self.assertEqual(first[0].draw_id, second[0].draw_id)
            self.assertEqual(
                self.connection.execute(
                    "SELECT status FROM core.draws WHERE draw_id = %s", (first[0].draw_id,)
                ).fetchone()[0],
                "EXPECTED",
            )
            self.assertEqual(
                self.connection.execute(
                    "SELECT external_draw_id, external_event_id FROM core.draw_external_ids WHERE draw_id = %s",
                    (first[0].draw_id,),
                ).fetchone(),
                ("759368", "404"),
            )
            self.assertEqual(
                self.connection.execute(
                    "SELECT count(*) FROM core.draw_schedule_versions WHERE draw_id = %s",
                    (first[0].draw_id,),
                ).fetchone()[0],
                1,
            )

    def test_result_is_frozen_with_ordered_numbers_and_repeated_result_is_idempotent(self):
        with rollback_transaction(self.connection):
            game_id, game_version_id, source_id, draw_types = self.create_context()
            receipt = self.create_receipt(source_id, b'{"result":1}')
            observation = ResultObservation(
                draw_date=date(2026, 10, 3),
                draw_name="Moaye",
                result_group="standardDraws",
                winning_numbers=(33, 42, 39, 38, 2),
                machine_numbers=(58, 49, 19, 54, 27),
                source_date="samedi 03/10",
                source_data={"drawName": "Moaye"},
            )
            batch = CollectedBatch((receipt,), ValidationReport("PASSED", (observation,), ()))
            registry = DrawRegistry(
                self.connection,
                game_id=game_id,
                game_version_id=game_version_id,
                source_id=source_id,
                draw_type_ids_by_name=draw_types,
            )

            first = registry.register_result_batch(batch)[0]
            second = registry.register_result_batch(batch)[0]

            self.assertEqual(first.status, "FROZEN")
            self.assertTrue(first.created)
            self.assertEqual(second.status, "UNCHANGED")
            self.assertFalse(second.created)
            self.assertEqual(first.draw_version_id, second.draw_version_id)
            self.assertEqual(
                self.connection.execute(
                    "SELECT status, canonical_draw_version_id FROM core.draws WHERE draw_id = %s",
                    (first.draw_id,),
                ).fetchone(),
                ("FROZEN", first.draw_version_id),
            )
            self.assertEqual(
                self.connection.execute(
                    "SELECT number FROM core.draw_numbers WHERE draw_version_id = %s AND number_role = 'WINNING' ORDER BY position",
                    (first.draw_version_id,),
                ).fetchall(),
                [(33,), (42,), (39,), (38,), (2,)],
            )
            self.assertEqual(
                self.connection.execute(
                    "SELECT result_metadata->>'result_group' FROM core.draw_versions WHERE draw_version_id = %s",
                    (first.draw_version_id,),
                ).fetchone()[0],
                "standardDraws",
            )

    def test_changed_result_creates_conflict_version_without_replacing_canonical(self):
        with rollback_transaction(self.connection):
            game_id, game_version_id, source_id, draw_types = self.create_context()
            registry = DrawRegistry(
                self.connection,
                game_id=game_id,
                game_version_id=game_version_id,
                source_id=source_id,
                draw_type_ids_by_name=draw_types,
            )
            first_observation = ResultObservation(
                date(2026, 10, 3), "Moaye", "standardDraws", (1, 2, 3, 4, 5), None,
                "samedi 03/10", {"drawName": "Moaye", "numbers": [1, 2, 3, 4, 5]},
            )
            first_batch = CollectedBatch(
                (self.create_receipt(source_id, b'{"result":1}'),),
                ValidationReport("PASSED", (first_observation,), ()),
            )
            canonical = registry.register_result_batch(first_batch)[0]
            changed_observation = ResultObservation(
                date(2026, 10, 3), "Moaye", "standardDraws", (1, 2, 3, 4, 6), None,
                "samedi 03/10", {"drawName": "Moaye", "numbers": [1, 2, 3, 4, 6]},
            )
            changed_batch = CollectedBatch(
                (self.create_receipt(source_id, b'{"result":2}'),),
                ValidationReport("PASSED", (changed_observation,), ()),
            )

            changed = registry.register_result_batch(changed_batch)[0]

            self.assertEqual(changed.status, "CONFLICT")
            self.assertNotEqual(changed.draw_version_id, canonical.draw_version_id)
            self.assertEqual(changed.canonical_draw_version_id, canonical.draw_version_id)
            self.assertEqual(
                self.connection.execute(
                    "SELECT status, canonical_draw_version_id FROM core.draws WHERE draw_id = %s",
                    (canonical.draw_id,),
                ).fetchone(),
                ("CORRECTED", canonical.draw_version_id),
            )
            self.assertEqual(
                self.connection.execute(
                    "SELECT validation_status FROM core.draw_versions WHERE draw_version_id = %s",
                    (changed.draw_version_id,),
                ).fetchone()[0],
                "CONFLICT",
            )
            self.assertEqual(
                self.connection.execute(
                    "SELECT count(*) FROM core.draw_corrections WHERE new_draw_version_id = %s",
                    (changed.draw_version_id,),
                ).fetchone()[0],
                1,
            )


if __name__ == "__main__":
    unittest.main()
