import unittest

from lottery_intelligence_platform.prediction_generation import _stable_seed, _top_k


class TopKTests(unittest.TestCase):
    def test_ranks_by_score_desc_number_asc(self):
        counts = {5: 10, 3: 10, 7: 20}
        picks = _top_k(counts, 2, lambda n: float(counts.get(n, 0)))
        self.assertEqual(picks, [3, 7])  # 7 top, tie 3<5

    def test_missing_numbers_score_zero(self):
        picks = _top_k({1: 5}, 2, lambda n: float(n == 1))
        self.assertEqual(picks, [1, 2])  # only 1 scores, 2 is smallest number


class StableSeedTests(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(_stable_seed("a", 1), _stable_seed("a", 1))
        self.assertNotEqual(_stable_seed("a", 1), _stable_seed("a", 2))


if __name__ == "__main__":
    unittest.main()
