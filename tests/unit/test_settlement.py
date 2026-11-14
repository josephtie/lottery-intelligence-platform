import unittest

from lottery_intelligence_platform.scheduler import _backoff_seconds
from lottery_intelligence_platform.settlement import (
    DEFAULT_TURBO_STAKE,
    positional_hit_counts,
    turbo_settlement,
)

MULTIPLIERS = {"2": 2400, "3": 800, "4": 400, "5": 240}
WINNING = [31, 46, 7, 12, 88]


class PositionalHitCountsTests(unittest.TestCase):
    def test_counts_within_prefixes(self):
        counts = positional_hit_counts([31, 12], WINNING)
        self.assertEqual(counts["first_1"], 1)
        self.assertEqual(counts["first_2"], 1)
        self.assertEqual(counts["first_4"], 2)
        self.assertEqual(counts["first_5"], 2)

    def test_no_hits(self):
        counts = positional_hit_counts([1, 2], WINNING)
        self.assertTrue(all(v == 0 for v in counts.values()))


class TurboSettlementTests(unittest.TestCase):
    def test_positional_hit_pays(self):
        result = turbo_settlement([31, 46], WINNING, stake=100, multipliers=MULTIPLIERS)
        self.assertTrue(result["turbo_2"]["hit"])
        self.assertEqual(result["turbo_2"]["payout"], 240_000)
        self.assertEqual(result["turbo_2"]["net"], 239_900)
        self.assertEqual(result["turbo_2"]["positions"], 2)
        self.assertEqual(result["turbo_2"]["multiplier"], 2400)

    def test_later_position_only(self):
        # 7 is position 3: wins turbo_3/4/5 but not turbo_2 with pick {46,7}
        result = turbo_settlement([46, 7], WINNING, stake=100, multipliers=MULTIPLIERS)
        self.assertFalse(result["turbo_2"]["hit"])
        self.assertEqual(result["turbo_2"]["net"], -100)
        self.assertTrue(result["turbo_3"]["hit"])
        self.assertEqual(result["turbo_3"]["payout"], 80_000)
        self.assertTrue(result["turbo_4"]["hit"])
        self.assertEqual(result["turbo_4"]["payout"], 40_000)
        self.assertTrue(result["turbo_5"]["hit"])
        self.assertEqual(result["turbo_5"]["payout"], 24_000)

    def test_miss_loses_stake(self):
        result = turbo_settlement([1, 2], WINNING, stake=100, multipliers=MULTIPLIERS)
        for variant in ("turbo_2", "turbo_3", "turbo_4", "turbo_5"):
            self.assertFalse(result[variant]["hit"])
            self.assertEqual(result[variant]["payout"], 0)
            self.assertEqual(result[variant]["net"], -100)
            self.assertEqual(result[variant]["roi"], -1)

    def test_subset_semantics_not_anywhere(self):
        # both numbers are winners but one is at position 5 -> turbo_2 fails
        result = turbo_settlement([31, 88], WINNING, stake=100, multipliers=MULTIPLIERS)
        self.assertFalse(result["turbo_2"]["hit"])
        self.assertTrue(result["turbo_5"]["hit"])

    def test_roi_on_win(self):
        result = turbo_settlement([31, 46], WINNING, stake=DEFAULT_TURBO_STAKE, multipliers=MULTIPLIERS)
        self.assertAlmostEqual(result["turbo_2"]["roi"], 2399.0)


class BackoffTests(unittest.TestCase):
    def test_exponential_backoff(self):
        self.assertEqual(_backoff_seconds(0), 30)
        self.assertEqual(_backoff_seconds(1), 60)
        self.assertEqual(_backoff_seconds(3), 240)


if __name__ == "__main__":
    unittest.main()
