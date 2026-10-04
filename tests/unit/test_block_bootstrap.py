import unittest

from lottery_intelligence_platform.uncertainty import (
    paired_block_bootstrap_difference,
)


class TestPairedBlockBootstrap(unittest.TestCase):
    def test_deterministic_with_same_seed(self):
        a = [float(v) for v in range(60)]
        b = [float(v) * 0.9 for v in range(60)]
        first = paired_block_bootstrap_difference(
            a, b, block_size=10, resamples=100, seed=3
        )
        second = paired_block_bootstrap_difference(
            a, b, block_size=10, resamples=100, seed=3
        )
        self.assertEqual(first, second)

    def test_identical_series_span_zero(self):
        a = [1.0, -1.0, 2.0, -2.0] * 25
        result = paired_block_bootstrap_difference(
            a, a, block_size=5, resamples=50, seed=7
        )
        self.assertEqual(result["point_difference"], 0.0)
        self.assertEqual(result["ci_low"], 0.0)
        self.assertEqual(result["ci_high"], 0.0)

    def test_clear_separation_detected(self):
        a = [0.2] * 40
        b = [0.8] * 40
        result = paired_block_bootstrap_difference(
            a, b, block_size=5, resamples=50, seed=7
        )
        self.assertLess(result["ci_high"], 0.0)
        self.assertEqual(result["block_size"], 5)

    def test_block_size_capped_at_series_length(self):
        a = [1.0, 2.0]
        b = [0.5, 1.0]
        result = paired_block_bootstrap_difference(
            a, b, block_size=10, resamples=20, seed=1
        )
        self.assertEqual(result["block_size"], 2)

    def test_validation(self):
        with self.assertRaises(ValueError):
            paired_block_bootstrap_difference([], [], block_size=5, resamples=5, seed=1)
        with self.assertRaises(ValueError):
            paired_block_bootstrap_difference([1.0], [1.0, 2.0], block_size=5, resamples=5, seed=1)
        with self.assertRaises(ValueError):
            paired_block_bootstrap_difference([1.0], [1.0], block_size=0, resamples=5, seed=1)

    def test_block_preserves_structure_narrower_than_iid_like(self):
        # A series with strong local agreement should get a tight interval
        # under block resampling because blocks keep neighbouring diffs together.
        a = []
        b = []
        for block_index in range(10):
            value = 0.1 if block_index % 2 else 0.9
            a.extend([value] * 5)
            b.extend([0.5] * 5)
        result = paired_block_bootstrap_difference(
            a, b, block_size=5, resamples=100, seed=2
        )
        self.assertNotEqual(result["ci_low"], result["ci_high"])


if __name__ == "__main__":
    unittest.main()
