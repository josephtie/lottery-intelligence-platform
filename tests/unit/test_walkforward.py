import unittest
from datetime import date

from lottery_intelligence_platform.walkforward import generate_windows


class WindowGenerationTests(unittest.TestCase):
    def test_expanding_windows_have_disjoint_test_periods(self):
        windows = generate_windows(
            date(2020, 11, 1), date(2026, 10, 3),
            {"mode": "expanding", "min_train_days": 730, "test_days": 182, "step_days": 182},
        )
        self.assertGreater(len(windows), 1)
        for index, window in enumerate(windows):
            self.assertEqual(window.ordinal, index + 1)
            self.assertEqual(window.train_start, date(2020, 11, 1))
            self.assertLess(window.train_end, window.test_start)
            self.assertLessEqual(window.test_start, window.test_end)
            if index:
                self.assertGreater(window.test_start, windows[index - 1].test_end)
        self.assertLessEqual(windows[-1].test_end, date(2026, 10, 3))

    def test_sliding_windows_move_train_start(self):
        windows = generate_windows(
            date(2020, 11, 1), date(2026, 10, 3),
            {"mode": "sliding", "min_train_days": 30, "train_days": 365,
             "test_days": 90, "step_days": 90},
        )
        self.assertGreater(len(windows), 1)
        starts = {window.train_start for window in windows}
        self.assertGreater(len(starts), 1)
        for window in windows:
            self.assertGreaterEqual(window.train_start, date(2020, 11, 1))

    def test_validation_segment_is_strictly_between(self):
        windows = generate_windows(
            date(2020, 11, 1), date(2024, 11, 1),
            {"mode": "expanding", "min_train_days": 365,
             "validation_days": 90, "test_days": 90, "step_days": 90},
        )
        for window in windows:
            self.assertGreater(window.validation_start, window.train_end)
            self.assertGreater(window.test_start, window.validation_end)

    def test_empty_when_history_too_short(self):
        windows = generate_windows(
            date(2026, 1, 1), date(2026, 6, 30),
            {"mode": "expanding", "min_train_days": 730, "test_days": 182},
        )
        self.assertEqual(windows, ())

    def test_sliding_requires_train_days(self):
        with self.assertRaises(ValueError):
            generate_windows(
                date(2020, 1, 1), date(2026, 1, 1),
                {"mode": "sliding", "min_train_days": 100, "test_days": 30},
            )


if __name__ == "__main__":
    unittest.main()
