import unittest
from datetime import date
from uuid import uuid4

from lottery_intelligence_platform.backfill import BackfillResult, BackfillWindow, collect_result_window
from lottery_intelligence_platform.collectors.lotobonheur import (
    CollectedBatch,
    ResultObservation,
    SourceHTTPError,
)
from lottery_intelligence_platform.validation import ValidationReport


class FakeCollector:
    def __init__(self, fail_month=None):
        self.fail_month = fail_month
        self.calls = []

    def collect(self, connection, raw_store, *, source_id, month_year, date_from, date_to):
        self.calls.append((month_year, date_from, date_to))
        if month_year == self.fail_month:
            raise SourceHTTPError(503, "https://fixture.loto/api/results")
        observation = ResultObservation(
            draw_date=date_from,
            draw_name=f"draw-{month_year}",
            result_group="standardDraws",
            winning_numbers=(1, 2, 3, 4, 5),
            machine_numbers=None,
            source_date=date_from.strftime("%d/%m"),
            source_data={"drawName": f"draw-{month_year}"},
        )
        return CollectedBatch((), ValidationReport("PASSED", (observation,), ()))


class BackfillCollectionTests(unittest.TestCase):
    def test_collects_each_month_bucket_and_keeps_month_failures_visible(self):
        window = BackfillWindow(date(2026, 4, 3), date(2026, 10, 3))
        collector = FakeCollector(fail_month="juin 2026")
        pauses = []

        result = collect_result_window(
            collector,
            None,
            None,
            source_id=uuid4(),
            window=window,
            pause_seconds=0.25,
            sleeper=pauses.append,
        )

        self.assertEqual(
            [month for month, _, _ in collector.calls],
            ["avril 2026", "mai 2026", "juin 2026", "juillet 2026", "août 2026", "septembre 2026", "octobre 2026"],
        )
        self.assertTrue(all(start == window.start_date and end == window.end_date for _, start, end in collector.calls))
        self.assertEqual(result.failures[0].month_year, "juin 2026")
        self.assertEqual(len(result.observations), 6)
        self.assertFalse(result.is_complete)
        self.assertEqual(len(pauses), 6)

    def test_backfill_does_not_return_observations_outside_exact_window(self):
        window = BackfillWindow(date(2026, 4, 3), date(2026, 10, 3))
        batch = CollectedBatch((), ValidationReport("PASSED", (
            ResultObservation(date(2026, 4, 2), "before", "standardDraws", (1, 2, 3, 4, 5), None, "02/04", {}),
            ResultObservation(date(2026, 4, 3), "included", "standardDraws", (1, 2, 3, 4, 5), None, "03/04", {}),
            ResultObservation(date(2026, 10, 4), "after", "standardDraws", (1, 2, 3, 4, 5), None, "04/10", {}),
        ), ()))

        result = BackfillResult(window, (batch,), ())

        self.assertEqual([item.draw_name for item in result.observations], ["included"])
        self.assertTrue(result.is_complete)

    def test_coverage_deduplicates_month_overlap_by_draw_identity(self):
        observation = ResultObservation(
            date(2026, 10, 3), "Moaye", "standardDraws", (1, 2, 3, 4, 5), None, "03/10", {}
        )
        batches = tuple(
            CollectedBatch((), ValidationReport("PASSED", (observation,), ()))
            for _ in range(2)
        )
        result = BackfillResult(BackfillWindow(date(2026, 10, 1), date(2026, 10, 3)), batches, ())

        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.overlapping_observation_count, 1)
        self.assertEqual(result.coverage[0].observation_count, 1)
        self.assertTrue(result.is_complete)

    def test_conflicting_duplicate_draws_are_excluded_and_mark_window_incomplete(self):
        first = ResultObservation(
            date(2026, 10, 3), "Moaye", "standardDraws", (1, 2, 3, 4, 5), None, "03/10", {}
        )
        changed = ResultObservation(
            date(2026, 10, 3), "Moaye", "standardDraws", (6, 7, 8, 9, 10), None, "03/10", {}
        )
        batches = tuple(
            CollectedBatch((), ValidationReport("PASSED", (observation,), ()))
            for observation in (first, changed)
        )
        result = BackfillResult(BackfillWindow(date(2026, 10, 1), date(2026, 10, 3)), batches, ())

        self.assertEqual(result.observations, ())
        self.assertEqual(result.conflicting_observations, ((date(2026, 10, 3), "standardDraws", "Moaye"),))
        self.assertFalse(result.is_complete)


if __name__ == "__main__":
    unittest.main()
