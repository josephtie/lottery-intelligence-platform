import math
import unittest

from lottery_intelligence_platform.dependence import (
    PAIR_INCLUSION_PROBABILITY,
    binomial_right_tail,
    pair_counts,
    pair_dependence_tests,
)


class TestPairProbability(unittest.TestCase):
    def test_pair_inclusion_probability(self):
        expected = math.comb(88, 3) / math.comb(90, 5)
        self.assertAlmostEqual(PAIR_INCLUSION_PROBABILITY, expected)
        self.assertAlmostEqual(PAIR_INCLUSION_PROBABILITY, 20 / 8010)


class TestPairCounts(unittest.TestCase):
    def test_counts_all_pairs_per_draw(self):
        counts = pair_counts([{1, 2, 3}, {1, 2, 4}])
        self.assertEqual(counts[(1, 2)], 2)
        self.assertEqual(counts[(1, 3)], 1)
        self.assertEqual(counts[(2, 4)], 1)
        self.assertNotIn((3, 4), counts)


class TestBinomialTail(unittest.TestCase):
    def test_edges(self):
        self.assertEqual(binomial_right_tail(10, 0.5, 0), 1.0)
        self.assertEqual(binomial_right_tail(10, 0.5, 11), 0.0)

    def test_known_value(self):
        # P[X >= 8] for Binomial(10, 0.5) = (45 + 10 + 1) / 1024
        self.assertAlmostEqual(binomial_right_tail(10, 0.5, 8), 56 / 1024)

    def test_rare_event(self):
        self.assertAlmostEqual(binomial_right_tail(5, 0.1, 5), 1e-5, places=10)

    def test_tail_decreases_with_k(self):
        values = [binomial_right_tail(1000, 0.0025, k) for k in (8, 10, 12)]
        self.assertGreater(values[0], values[1])
        self.assertGreater(values[1], values[2])


class TestPairDependenceTests(unittest.TestCase):
    def test_empty_draws(self):
        self.assertEqual(pair_dependence_tests([]), [])

    def test_uniform_draws_flag_nothing_extreme(self):
        import random
        rng = random.Random(7)
        draws = [set(rng.sample(range(1, 91), 5)) for _ in range(400)]
        results = pair_dependence_tests(draws)
        self.assertTrue(all(r["p_value"] > 1e-9 for r in results))

    def test_planted_pair_is_detected(self):
        draws = [{1, 2, 50, 60, 70} for _ in range(30)]
        draws += [{10, 20, 30, 40, 80} for _ in range(20)]
        results = pair_dependence_tests(draws)
        self.assertEqual(results[0]["pair"], (1, 2))
        self.assertEqual(results[0]["observed"], 30)
        self.assertLess(results[0]["p_value"], 1e-20)

    def test_only_pairs_above_expected_returned(self):
        draws = [{1, 2, 3, 4, 5}]
        results = pair_dependence_tests(draws)
        expected = PAIR_INCLUSION_PROBABILITY
        self.assertTrue(all(r["observed"] > expected for r in results))


if __name__ == "__main__":
    unittest.main()
