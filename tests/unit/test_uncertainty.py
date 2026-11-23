import unittest

from lottery_intelligence_platform.uncertainty import (
    bootstrap_ci,
    paired_bootstrap_difference,
    percentile,
)


class TestPercentile(unittest.TestCase):
    def test_median(self):
        self.assertAlmostEqual(percentile([1.0, 2.0, 3.0], 0.5), 2.0)

    def test_extremes(self):
        self.assertAlmostEqual(percentile([1.0, 2.0, 3.0], 0.0), 1.0)
        self.assertAlmostEqual(percentile([1.0, 2.0, 3.0], 1.0), 3.0)

    def test_invalid_q_raises(self):
        with self.assertRaises(ValueError):
            percentile([1.0], 1.5)
        with self.assertRaises(ValueError):
            percentile([], 0.5)


class TestBootstrapCi(unittest.TestCase):
    def test_deterministic_with_same_seed(self):
        items = list(range(100))
        stat = lambda xs: sum(xs) / len(xs)
        first = bootstrap_ci(stat, items, resamples=200, seed=7)
        second = bootstrap_ci(stat, items, resamples=200, seed=7)
        self.assertEqual(first, second)

    def test_interval_contains_point_estimate(self):
        items = [float(v) for v in range(50)]
        point, low, high = bootstrap_ci(
            lambda xs: sum(xs) / len(xs), items, resamples=200, seed=13
        )
        self.assertAlmostEqual(point, 24.5)
        self.assertLess(low, point)
        self.assertGreater(high, point)

    def test_constant_items_have_degenerate_interval(self):
        point, low, high = bootstrap_ci(
            lambda xs: sum(xs) / len(xs), [3.0] * 40, resamples=100, seed=1
        )
        self.assertEqual((point, low, high), (3.0, 3.0, 3.0))

    def test_empty_items_raise(self):
        with self.assertRaises(ValueError):
            bootstrap_ci(lambda xs: 0.0, [], resamples=10, seed=1)


class TestPairedBootstrapDifference(unittest.TestCase):
    def test_clearly_better_series(self):
        a = [0.1] * 30
        b = [0.5] * 30
        result = paired_bootstrap_difference(a, b, resamples=100, seed=3)
        self.assertLess(result["point_difference"], 0.0)
        self.assertLess(result["ci_high"], 0.0)
        self.assertAlmostEqual(result["fraction_below_zero"], 1.0)

    def test_matched_series_span_zero(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0] * 20
        result = paired_bootstrap_difference(a, a, resamples=100, seed=3)
        self.assertEqual(result["point_difference"], 0.0)
        self.assertEqual(result["ci_low"], 0.0)
        self.assertEqual(result["ci_high"], 0.0)

    def test_reproducible(self):
        a = list(range(40))
        b = [v * 1.1 for v in range(40)]
        first = paired_bootstrap_difference(a, b, resamples=150, seed=11)
        second = paired_bootstrap_difference(a, b, resamples=150, seed=11)
        self.assertEqual(first, second)

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ValueError):
            paired_bootstrap_difference([1.0], [1.0, 2.0], resamples=10, seed=1)


if __name__ == "__main__":
    unittest.main()
