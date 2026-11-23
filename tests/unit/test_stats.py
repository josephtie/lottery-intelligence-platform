import unittest
from datetime import date

from lottery_intelligence_platform.stats import (
    benjamini_hochberg,
    chi_square_homogeneity,
    chi_square_sf,
    chi_square_uniform,
)


class ChiSquareTests(unittest.TestCase):
    def test_known_critical_values(self):
        self.assertAlmostEqual(chi_square_sf(3.841, 1), 0.05, places=3)
        self.assertAlmostEqual(chi_square_sf(6.635, 1), 0.01, places=3)
        self.assertAlmostEqual(chi_square_sf(0.0, 5), 1.0, places=6)

    def test_high_statistic_is_significant(self):
        p_value = chi_square_sf(168.7, 89)
        self.assertLess(p_value, 0.001)

    def test_uniform_counts_statistic(self):
        statistic, df, expected = chi_square_uniform([10, 10, 10, 10])
        self.assertEqual(statistic, 0.0)
        self.assertEqual(df, 3)
        self.assertEqual(expected, 10.0)

    def test_homogeneity_identical_samples_is_zero(self):
        statistic, df = chi_square_homogeneity([10, 20, 30], [10, 20, 30])
        self.assertEqual(statistic, 0.0)
        self.assertEqual(df, 2)

    def test_homogeneity_detects_shift(self):
        statistic, _ = chi_square_homogeneity([100, 10, 10], [10, 10, 100])
        self.assertGreater(statistic, 50)


class BenjaminiHochbergTests(unittest.TestCase):
    def test_controls_false_discovery_rate(self):
        flags = benjamini_hochberg([0.001, 0.02, 0.20, 0.5], 0.05)
        self.assertEqual(flags, [True, True, False, False])

    def test_nothing_significant(self):
        flags = benjamini_hochberg([0.4, 0.6, 0.8], 0.05)
        self.assertEqual(flags, [False, False, False])

    def test_alpha_must_be_in_range(self):
        with self.assertRaises(ValueError):
            benjamini_hochberg([0.01], 0.0)


if __name__ == "__main__":
    unittest.main()
