import hashlib
import os
import unittest
from contextlib import contextmanager
from uuid import uuid4

import psycopg

from lottery_intelligence_platform.ingestion import ingest_payload
from lottery_intelligence_platform.raw import RawObjectRef, raw_object_key

TEST_DATABASE_URL = os.getenv("LOTTERY_TEST_DATABASE_URL")


class RollbackProbe(Exception):
    pass


class FakeRawObjectStore:
    def __init__(self, failure=None):
        self.failure = failure
        self.objects = {}

    def put(self, payload, content_type="application/octet-stream"):
        if self.failure:
            raise self.failure
        digest = hashlib.sha256(payload).hexdigest()
        reference = RawObjectRef(digest, raw_object_key(digest), len(payload), content_type)
        self.objects.setdefault(reference.object_key, payload)
        return reference


@contextmanager
def rollback_transaction(connection):
    try:
        with connection.transaction():
            yield
            raise RollbackProbe
    except RollbackProbe:
        pass


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class CollectionIngestionTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def create_source(self):
        source_id = uuid4()
        self.connection.execute(
            "INSERT INTO ingestion.sources (source_id, code, display_name, source_kind) VALUES (%s, %s, %s, 'MANUAL')",
            (source_id, f"integration-{source_id.hex}", "Integration test"),
        )
        return source_id

    def ingest(self, source_id, store, payload=b"source payload"):
        return ingest_payload(
            self.connection,
            store,
            source_id=source_id,
            collector_name="integration-test",
            collector_version="1",
            payload=payload,
            content_type="application/json",
            response_status=200,
            external_identifiers={"external_draw_id": "test-1"},
        )

    def test_duplicate_payloads_share_raw_object_and_keep_collection_events(self):
        with rollback_transaction(self.connection):
            source_id = self.create_source()
            store = FakeRawObjectStore()
            first = self.ingest(source_id, store)
            second = self.ingest(source_id, store)

            self.assertEqual(first.raw_object_id, second.raw_object_id)
            self.assertEqual(first.raw_object.sha256, second.raw_object.sha256)
            self.assertEqual(
                self.connection.execute(
                    "SELECT count(*) FROM ingestion.raw_objects WHERE sha256 = %s",
                    (first.raw_object.sha256,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                self.connection.execute(
                    "SELECT count(*) FROM ingestion.collection_events WHERE collection_run_id IN (%s, %s)",
                    (first.collection_run_id, second.collection_run_id),
                ).fetchone()[0],
                2,
            )
            self.assertEqual(
                self.connection.execute(
                    "SELECT count(*) FROM ingestion.ingestion_events WHERE collection_event_id IN (%s, %s)",
                    (first.collection_event_id, second.collection_event_id),
                ).fetchone()[0],
                2,
            )

    def test_storage_failure_is_recorded_without_a_raw_object(self):
        with rollback_transaction(self.connection):
            source_id = self.create_source()
            with self.assertRaises(OSError):
                self.ingest(source_id, FakeRawObjectStore(OSError("temporary storage failure")))

            run = self.connection.execute(
                "SELECT collection_run_id FROM ingestion.collection_runs WHERE source_id = %s",
                (source_id,),
            ).fetchone()
            self.assertIsNotNone(run)
            event = self.connection.execute(
                "SELECT event_type, raw_object_id FROM ingestion.collection_events WHERE collection_run_id = %s",
                (run[0],),
            ).fetchone()
            self.assertEqual(event, ("RAW_STORAGE_ERROR", None))
            self.assertEqual(
                self.connection.execute(
                    "SELECT status FROM ingestion.collection_runs WHERE collection_run_id = %s",
                    (run[0],),
                ).fetchone()[0],
                "FAILED",
            )

    def test_metadata_conflict_is_recorded_and_does_not_overwrite_raw_object(self):
        with rollback_transaction(self.connection):
            source_id = self.create_source()
            payload = b"consistent bytes"
            digest = hashlib.sha256(payload).hexdigest()
            object_key = raw_object_key(digest)
            raw_object_id = uuid4()
            self.connection.execute(
                """INSERT INTO ingestion.raw_objects
                   (raw_object_id, sha256, object_key, byte_size, media_type)
                   VALUES (%s, %s, %s, %s, %s)""",
                (raw_object_id, digest, object_key, len(payload) + 1, "application/json"),
            )

            with self.assertRaises(RuntimeError):
                self.ingest(source_id, FakeRawObjectStore(), payload)

            self.assertEqual(
                self.connection.execute(
                    "SELECT byte_size FROM ingestion.raw_objects WHERE raw_object_id = %s",
                    (raw_object_id,),
                ).fetchone()[0],
                len(payload) + 1,
            )
            self.assertEqual(
                self.connection.execute(
                    """SELECT event_type FROM ingestion.collection_events WHERE collection_run_id = (
                        SELECT collection_run_id FROM ingestion.collection_runs WHERE source_id = %s
                    )""",
                    (source_id,),
                ).fetchone()[0],
                "REGISTRATION_ERROR",
            )


if __name__ == "__main__":
    unittest.main()
