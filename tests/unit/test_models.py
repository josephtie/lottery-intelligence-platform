import math
import unittest

from lottery_intelligence_platform.models import (
    select_bayesian_shrinkage,
    select_top_frequency,
    select_uniform_reference,
    selection_model_for,
)
from lottery_intelligence_platform.null_model import (
    match_moments,
    match_pmf,
    mean_matches_test,
    permutation_p_value,
)


class SelectionModelTests(unittest.TestCase):
    def test_top_frequency_uses_deterministic_tie_break(self):
        counts = [0] * 90
        counts[41] = 10
        counts[7] = 10
        counts[88] = 5
        pick = select_top_frequency(counts, 3)
        self.assertEqual(pick, {8, 42, 89})

    def test_symmetric_shrinkage_preserves_ranking(self):
        counts = [3, 0, 7, 7, 1] + [0] * 85
        self.assertEqual(
            select_bayesian_shrinkage(counts, 3, alpha=5.0),
            select_top_frequency(counts, 3),
        )

    def test_null_reference_is_seeded_and_stable(self):
        first = select_uniform_reference(10, seed=2026)
        second = select_uniform_reference(10, seed=2026)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 10)
        self.assertTrue(all(1 <= n <= 90 for n in first))

    def test_unknown_model_rejected(self):
        with self.assertRaises(ValueError):
            selection_model_for("does_not_exist", {})


class NullModelTests(unittest.TestCase):
    def test_match_pmf_sums_to_one(self):
        pmf = match_pmf(10)
        self.assertAlmostEqual(sum(pmf), 1.0, places=12)
        self.assertEqual(len(pmf), 6)

    def test_match_moments(self):
        mean, variance = match_moments(10)
        self.assertAlmostEqual(mean, 5 * 10 / 90)
        self.assertAlmostEqual(
            variance,
            5 * (10 / 90) * (1 - 10 / 90) * (90 - 5) / (90 - 1),
        )

    def test_mean_matches_test_flags_extremes(self):
        mean, variance = match_moments(10)
        draws = 1000
        observed = mean + 3 * math.sqrt(variance / draws)
        z, p_two_sided, _, _ = mean_matches_test(observed, draws, 10)
        self.assertAlmostEqual(z, 3.0, places=6)
        self.assertLess(p_two_sided, 0.01)

    def test_permutation_p_value_is_seeded(self):
        items = [1, 2, 3, 4, 5, 6, 7, 8]
        stat = lambda values: values[0]
        first = permutation_p_value(items, stat, permutations=99, seed=7)
        second = permutation_p_value(items, stat, permutations=99, seed=7)
        self.assertEqual(first, second)
        self.assertEqual(first[1], 1.0)


if __name__ == "__main__":
    unittest.main()
