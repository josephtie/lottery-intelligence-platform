import json
import unittest
from datetime import date

from lottery_intelligence_platform.collectors.lotobonheur import (
    ResultValidationRules,
    extract_next_build_id,
    validate_results_payload,
    validate_schedule_payload,
)


class LotobonheurCollectorValidationTests(unittest.TestCase):
    def test_extracts_next_build_id_from_bootstrap_html(self):
        html = b'<html><script id="__NEXT_DATA__" type="application/json">{"buildId":"abc_123"}</script></html>'

        self.assertEqual(extract_next_build_id(html), "abc_123")

    def test_rejects_invalid_build_id(self):
        html = b'<script id="__NEXT_DATA__">{"buildId":"../bad"}</script>'

        with self.assertRaises(ValueError):
            extract_next_build_id(html)

    def test_validates_schedule_and_keeps_external_ids_separate(self):
        payload = {
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

        report = validate_schedule_payload(json.dumps(payload).encode())

        self.assertEqual(report.status, "PASSED")
        self.assertEqual(len(report.observations), 1)
        observation = report.observations[0]
        self.assertEqual(observation.external_draw_id, "759368")
        self.assertEqual(observation.external_event_id, "404")
        self.assertEqual(observation.draw_name, "Moaye")
        self.assertEqual(observation.scheduled_at.isoformat(), "2026-10-03T15:55:00+00:00")

    def test_schedule_count_mismatch_fails_validation(self):
        payload = {
            "pageProps": {
                "activeDrawsData": {
                    "status": "0",
                    "success": True,
                    "drawsNumber": 2,
                    "drawGroups": [],
                },
            },
        }

        report = validate_schedule_payload(json.dumps(payload).encode())

        self.assertEqual(report.status, "FAILED")
        self.assertEqual(report.issues[0]["issue_code"], "SCHEDULE_COUNT_MISMATCH")

    def test_result_parser_preserves_order_and_treats_placeholders_as_warning(self):
        payload = {
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
                        "standardDraws": [{
                            "drawName": "-",
                            "winningNumbers": ". - . - . - . - .",
                            "machineNumbers": ". - . - . - . - .",
                        }],
                    },
                }],
            }],
        }

        report = validate_results_payload(json.dumps(payload).encode(), "octobre 2026", ResultValidationRules(1, 90, 5))

        self.assertEqual(report.status, "WARNING")
        self.assertEqual(len(report.observations), 1)
        observation = report.observations[0]
        self.assertEqual(observation.winning_numbers, (33, 42, 39, 38, 2))
        self.assertEqual(observation.machine_numbers, (58, 49, 19, 54, 27))
        self.assertEqual(observation.result_group, "nightDraws")
        self.assertEqual(report.issues[0]["issue_code"], "UNAVAILABLE_DRAW")

    def test_invalid_winning_numbers_fail_validation_without_recording_draw(self):
        payload = {
            "status": "0",
            "success": True,
            "drawsResultsWeekly": [{
                "drawResultsDaily": [{
                    "date": "samedi 03/10",
                    "drawResults": {
                        "nightDraws": [{
                            "drawName": "Moaye",
                            "winningNumbers": "10 - 10 - 20 - 30 - 40",
                            "machineNumbers": ". - . - . - . - .",
                        }],
                        "standardDraws": [],
                    },
                }],
            }],
        }

        report = validate_results_payload(json.dumps(payload).encode(), "octobre 2026", ResultValidationRules(1, 90, 5))

        self.assertEqual(report.status, "FAILED")
        self.assertEqual(report.observations, ())
        self.assertIn("INVALID_WINNING_NUMBERS", {issue["issue_code"] for issue in report.issues})

    def test_rejects_results_from_an_unsuccessful_source_response(self):
        report = validate_results_payload(b'{"status":"-1","success":false}', "octobre 2026", ResultValidationRules(1, 90, 5))

        self.assertEqual(report.status, "FAILED")
        self.assertEqual(report.issues[0]["issue_code"], "RESULT_SOURCE_UNSUCCESSFUL")

    def test_result_window_filters_month_bucket_edges_and_keeps_raw_independent(self):
        payload = {
            "status": "0",
            "success": True,
            "drawsResultsWeekly": [{
                "drawResultsDaily": [
                    {"date": "jeudi 02/04", "drawResults": {"nightDraws": [{"drawName": "Moaye", "winningNumbers": "1 - 2 - 3 - 4 - 5", "machineNumbers": "6 - 7 - 8 - 9 - 10"}]}},
                    {"date": "vendredi 03/04", "drawResults": {"nightDraws": [{"drawName": "Moaye", "winningNumbers": "11 - 12 - 13 - 14 - 15", "machineNumbers": "16 - 17 - 18 - 19 - 20"}]}},
                    {"date": "samedi 03/10", "drawResults": {"nightDraws": [{"drawName": "Moaye", "winningNumbers": "21 - 22 - 23 - 24 - 25", "machineNumbers": "26 - 27 - 28 - 29 - 30"}]}},
                    {"date": "dimanche 04/10", "drawResults": {"nightDraws": [{"drawName": "Moaye", "winningNumbers": "31 - 32 - 33 - 34 - 35", "machineNumbers": "36 - 37 - 38 - 39 - 40"}]}},
                ],
            }],
        }

        report = validate_results_payload(
            json.dumps(payload).encode(),
            "octobre 2026",
            ResultValidationRules(1, 90, 5),
            date_from=date(2026, 4, 3),
            date_to=date(2026, 10, 3),
        )

        self.assertEqual(report.status, "PASSED")
        self.assertEqual([item.draw_date.isoformat() for item in report.observations], ["2026-04-03", "2026-10-03"])
        self.assertEqual(sum(issue["issue_code"] == "OUTSIDE_REQUESTED_WINDOW" for issue in report.issues), 2)


if __name__ == "__main__":
    unittest.main()
