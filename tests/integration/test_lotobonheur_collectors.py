import hashlib
import json
import os
import unittest
from contextlib import contextmanager
from uuid import uuid4

import psycopg

from lottery_intelligence_platform.collectors.http import HttpResponse
from lottery_intelligence_platform.collectors.lotobonheur import (
    LotobonheurResultCollector,
    LotobonheurScheduleCollector,
    ResultValidationRules,
)
from lottery_intelligence_platform.raw import RawObjectRef, raw_object_key

TEST_DATABASE_URL = os.getenv("LOTTERY_TEST_DATABASE_URL")


class RollbackProbe(Exception):
    pass


class FakeRawObjectStore:
    def put(self, payload, content_type="application/octet-stream"):
        digest = hashlib.sha256(payload).hexdigest()
        return RawObjectRef(digest, raw_object_key(digest), len(payload), content_type)


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, *, accept="application/json"):
        self.urls.append((url, accept))
        response = self.responses.pop(0)
        return HttpResponse(url, response.response_url, response.status_code, response.content_type, response.body)


def http_response(url, body, content_type="application/json", status=200):
    return HttpResponse(url, url, status, content_type, body)


@contextmanager
def rollback_transaction(connection):
    try:
        with connection.transaction():
            yield
            raise RollbackProbe
    except RollbackProbe:
        pass


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class LotobonheurCollectorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def create_source(self):
        source_id = uuid4()
        self.connection.execute(
            "INSERT INTO ingestion.sources (source_id, code, display_name, source_kind) VALUES (%s, %s, %s, 'OFFICIAL')",
            (source_id, f"collector-test-{source_id.hex}", "Loto Bonheur integration test"),
        )
        return source_id

    def test_schedule_collector_preserves_bootstrap_and_schedule_payloads(self):
        html = b'<script id="__NEXT_DATA__">{"buildId":"build_123"}</script>'
        schedule = {
            "pageProps": {
                "activeDrawsData": {
                    "status": "0",
                    "success": True,
                    "drawsNumber": 1,
                    "drawGroups": [{
                        "groupDate": "2026-10-03",
                        "draws": [{
                            "id": "759368",
                            "eventId": "404",
                            "name": "Moaye",
                            "endDateTime": "2026-10-03T15:55:00Z",
                            "endTime": "15H55",
                            "isSingleSet": False,
                            "preview": "Moaye - Sam.15H55",
                        }],
                    }],
                },
            },
        }
        schedule_bytes = json.dumps(schedule).encode()
        http = FakeHttpClient([
            http_response("https://fixture.loto/", html, "text/html; charset=utf-8"),
            http_response("https://fixture.loto/_next/data/build_123/index.json", schedule_bytes),
        ])

        with rollback_transaction(self.connection):
            source_id = self.create_source()
            result = LotobonheurScheduleCollector(
                http_client=http,
                base_url="https://fixture.loto",
            ).collect(self.connection, FakeRawObjectStore(), source_id=source_id)

            self.assertEqual(result.validation.status, "PASSED")
            self.assertEqual(len(result.validation.observations), 1)
            self.assertEqual(len(result.receipts), 2)
            self.assertEqual(self.connection.execute(
                "SELECT count(*) FROM ingestion.raw_objects WHERE raw_object_id IN (%s, %s)",
                tuple(receipt.raw_object_id for receipt in result.receipts),
            ).fetchone()[0], 2)
            self.assertEqual(self.connection.execute(
                "SELECT count(*) FROM ingestion.validation_events WHERE collection_run_id IN (%s, %s)",
                tuple(receipt.collection_run_id for receipt in result.receipts),
            ).fetchone()[0], 2)
            self.assertEqual(http.urls[1][0], "https://fixture.loto/_next/data/build_123/index.json")

    def test_result_collector_preserves_source_and_records_validation(self):
        result_payload = {
            "status": "0",
            "success": True,
            "drawsResultsWeekly": [{
                "drawResultsDaily": [{
                    "date": "samedi 03/10",
                    "drawResults": {
                        "nightDraws": [{
                            "drawName": "Digital Reveil 7h",
                            "winningNumbers": "33 - 42 - 39 - 38 - 02",
                            "machineNumbers": "58 - 49 - 19 - 54 - 27",
                        }],
                        "standardDraws": [],
                    },
                }],
            }],
        }
        payload = json.dumps(result_payload).encode()
        http = FakeHttpClient([http_response("https://fixture.loto/api/results", payload)])

        with rollback_transaction(self.connection):
            source_id = self.create_source()
            result = LotobonheurResultCollector(
                rules=ResultValidationRules(1, 90, 5),
                http_client=http,
                base_url="https://fixture.loto",
            ).collect(
                self.connection,
                FakeRawObjectStore(),
                source_id=source_id,
                month_year="octobre 2026",
            )

            self.assertEqual(result.validation.status, "PASSED")
            self.assertEqual(result.validation.observations[0].winning_numbers, (33, 42, 39, 38, 2))
            self.assertEqual(self.connection.execute(
                "SELECT count(*) FROM ingestion.validation_events WHERE collection_run_id = %s",
                (result.receipts[0].collection_run_id,),
            ).fetchone()[0], 1)
            metadata = self.connection.execute(
                "SELECT request_metadata FROM ingestion.collection_runs WHERE collection_run_id = %s",
                (result.receipts[0].collection_run_id,),
            ).fetchone()[0]
            self.assertEqual(metadata["month_year"], "octobre 2026")
            self.assertIn("monthYear=octobre+2026", http.urls[0][0])

    def test_http_error_creates_failure_event_without_raw_payload(self):
        http = FakeHttpClient([http_response("https://fixture.loto/api/results", b"unavailable", status=503)])

        with rollback_transaction(self.connection):
            source_id = self.create_source()
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                LotobonheurResultCollector(
                    rules=ResultValidationRules(1, 90, 5),
                    http_client=http,
                    base_url="https://fixture.loto",
                ).collect(
                    self.connection,
                    FakeRawObjectStore(),
                    source_id=source_id,
                    month_year="octobre 2026",
                )

            row = self.connection.execute(
                """SELECT r.status, e.event_type, e.raw_object_id
                   FROM ingestion.collection_runs r
                   JOIN ingestion.collection_events e USING (collection_run_id)
                   WHERE r.source_id = %s""",
                (source_id,),
            ).fetchone()
            self.assertEqual(row, ("FAILED", "HTTP_ERROR", None))


if __name__ == "__main__":
    unittest.main()
