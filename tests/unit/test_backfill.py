import unittest
from datetime import date

from lottery_intelligence_platform.backfill import (
    EARLIEST_RESULTS_DATE,
    BackfillResult,
    BackfillWindow,
    subtract_calendar_months,
)


class BackfillWindowTests(unittest.TestCase):
    def test_rolling_six_months_from_october_uses_seven_monthly_buckets(self):
        window = BackfillWindow.trailing_months(6, through=date(2026, 10, 3))

        self.assertEqual(window.start_date, date(2026, 4, 3))
        self.assertEqual(window.end_date, date(2026, 10, 3))
        self.assertEqual(window.month_years(), (
            "avril 2026", "mai 2026", "juin 2026", "juillet 2026",
            "août 2026", "septembre 2026", "octobre 2026",
        ))

    def test_subtract_months_clamps_to_last_day_of_shorter_month(self):
        self.assertEqual(subtract_calendar_months(date(2024, 8, 31), 6), date(2024, 2, 29))
        self.assertEqual(subtract_calendar_months(date(2026, 10, 3), 6), date(2026, 4, 3))

    def test_window_boundaries_are_inclusive(self):
        window = BackfillWindow(date(2026, 4, 3), date(2026, 10, 3))

        self.assertFalse(window.contains(date(2026, 4, 2)))
        self.assertTrue(window.contains(date(2026, 4, 3)))
        self.assertTrue(window.contains(date(2026, 10, 3)))
        self.assertFalse(window.contains(date(2026, 10, 4)))

    def test_complete_official_archive_window_has_72_monthly_buckets(self):
        window = BackfillWindow.available_history(through=date(2026, 10, 3))

        self.assertEqual(window.start_date, EARLIEST_RESULTS_DATE)
        self.assertEqual(window.end_date, date(2026, 10, 3))
        self.assertEqual(len(window.month_years()), 72)
        self.assertEqual(window.month_years()[0], "novembre 2020")

    def test_invalid_windows_and_month_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            BackfillWindow(date(2026, 10, 4), date(2026, 10, 3))
        with self.assertRaises(ValueError):
            subtract_calendar_months(date(2026, 10, 3), 0)
        with self.assertRaises(ValueError):
            BackfillWindow.available_history(through=date(2020, 10, 31))


if __name__ == "__main__":
    unittest.main()
