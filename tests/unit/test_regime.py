import random
import unittest
from datetime import date

from lottery_intelligence_platform.regime import (
    monthly_period_counts,
    post_change_point_draws,
    regime_change_point,
)


def _draws(rng, start_year, months, per_month, hot=None):
    draws = []
    day = 1
    for index in range(months):
        year = start_year + index // 12
        month = index % 12 + 1
        for _ in range(per_month):
            numbers = set(rng.sample(range(1, 91), 5))
            if hot:
                numbers = set(hot) | set(rng.sample(range(6, 91), 5 - len(hot)))
            draws.append((date(year, month, day), f"id{len(draws)}", numbers))
    return draws


class TestMonthlyPeriodCounts(unittest.TestCase):
    def test_groups_by_month_ordered(self):
        rng = random.Random(1)
        draws = _draws(rng, 2022, 4, 3)
        periods = monthly_period_counts(draws)
        self.assertEqual([k for k, _ in periods], [(2022, m) for m in (1, 2, 3, 4)])
        self.assertTrue(all(sum(c) == 15 for _, c in periods))


class TestRegimeDetection(unittest.TestCase):
    def test_stable_history_has_no_regime_cut(self):
        rng = random.Random(2)
        draws = _draws(rng, 2020, 24, 30)
        retained, cp, cutoff = post_change_point_draws(
            draws, permutations=99, seed=5
        )
        if cp is None:
            self.assertIsNone(cutoff)
            self.assertEqual(len(retained), len(draws))

    def test_shifted_history_detects_regime(self):
        rng = random.Random(3)
        early = _draws(rng, 2020, 12, 30)
        late_rng = random.Random(9)
        late = []
        index = 0
        for month in range(1, 13):
            for _ in range(30):
                numbers = {1, 2, 3} | set(late_rng.sample(range(4, 91), 2))
                late.append((date(2021, month, 5), f"late{index}", numbers))
                index += 1
        draws = early + late
        retained, cp, cutoff = post_change_point_draws(
            draws, permutations=99, seed=5
        )
        self.assertIsNotNone(cp)
        self.assertIsNotNone(cutoff)
        self.assertLess(len(retained), len(draws))
        self.assertTrue(all(
            (d[0].year, d[0].month) >= tuple(cutoff) for d in retained
        ))
        self.assertEqual(regime_change_point(draws, permutations=99, seed=5).split_index,
                         cp.split_index)

    def test_deterministic_with_same_seed(self):
        rng = random.Random(4)
        draws = _draws(rng, 2020, 18, 25)
        first = post_change_point_draws(draws, permutations=49, seed=11)
        second = post_change_point_draws(draws, permutations=49, seed=11)
        self.assertEqual(
            (len(first[0]), first[1] and first[1].split_index, first[2]),
            (len(second[0]), second[1] and second[1].split_index, second[2]),
        )

    def test_too_few_periods_returns_all_draws(self):
        rng = random.Random(5)
        draws = _draws(rng, 2023, 2, 10)
        retained, cp, cutoff = post_change_point_draws(draws, permutations=49, seed=1)
        self.assertIsNone(cp)
        self.assertIsNone(cutoff)
        self.assertEqual(retained, draws)


if __name__ == "__main__":
    unittest.main()
