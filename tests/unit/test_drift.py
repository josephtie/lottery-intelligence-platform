import random
import unittest

from lottery_intelligence_platform.drift import detect_change_point


def _counts(rows):
    result = []
    rng = random.Random(7)
    for row in rows:
        counts = [0] * 90
        for number in row:
            counts[number] += 1
        result.append(counts)
    return result


class ChangePointTests(unittest.TestCase):
    def test_stable_series_is_not_flagged(self):
        rng = random.Random(1)
        periods = _counts([[rng.randint(0, 89) for _ in range(50)] for _ in range(12)])
        change_point = detect_change_point(periods, permutations=99, seed=42)
        self.assertIsNotNone(change_point)
        self.assertGreater(change_point.permutation_p, 0.05)

    def test_shifted_series_is_flagged_at_true_split(self):
        rng = random.Random(1)
        pool_high = list(range(10)) * 9 + list(range(10, 90))
        periods = _counts([
            [rng.choice(range(90) if index < 6 else pool_high) for _ in range(50)]
            for index in range(12)
        ])
        change_point = detect_change_point(periods, permutations=99, seed=42)
        self.assertEqual(change_point.split_index, 6)
        self.assertLessEqual(change_point.permutation_p, 0.02)

    def test_too_few_periods_returns_none(self):
        self.assertIsNone(detect_change_point([[1] * 90] * 2, permutations=99, seed=1))

    def test_result_is_deterministic(self):
        periods = _counts([[index % 90 for index in range(50)] for _ in range(8)])
        first = detect_change_point(periods, permutations=99, seed=99)
        second = detect_change_point(periods, permutations=99, seed=99)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
