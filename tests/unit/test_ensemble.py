import random
import unittest
from datetime import date

from lottery_intelligence_platform.ensemble_evaluation import (
    _component_predictions,
    _mixture,
)


def _make_draws(rng, n, start_year=2020):
    draws = []
    for index in range(n):
        draws.append((
            date(start_year + index // 300, index % 12 + 1, index % 28 + 1),
            f"d{index}",
            set(rng.sample(range(1, 91), 5)),
        ))
    return draws


class TestMixture(unittest.TestCase):
    def test_mixture_averages_components(self):
        components = [
            [[0.1, 0.2], [0.3, 0.4]],
            [[0.3, 0.4], [0.1, 0.2]],
        ]
        mixed = _mixture(components)
        self.assertAlmostEqual(mixed[0][0], 0.2)
        self.assertAlmostEqual(mixed[0][1], 0.3)
        self.assertAlmostEqual(mixed[1][0], 0.2)
        self.assertAlmostEqual(mixed[1][1], 0.3)

    def test_single_component_returns_copy(self):
        components = [[[0.05] * 90]]
        mixed = _mixture(components)
        self.assertEqual(mixed[0], [0.05] * 90)
        self.assertIsNot(mixed[0], components[0][0])


class TestComponentPredictions(unittest.TestCase):
    def test_all_components_return_90_predictions_per_draw(self):
        rng = random.Random(1)
        draws = _make_draws(rng, 120)
        predictions = _component_predictions(
            draws, draws[:80], draws[80:],
            change_point_permutations=9, seed=3,
        )
        self.assertEqual(set(predictions), {"expanding", "bayesian", "rolling", "regime"})
        for code, rows in predictions.items():
            self.assertEqual(len(rows), 40)
            for row in rows:
                self.assertEqual(len(row), 90)
                self.assertTrue(all(0 < p < 1 for p in row))

    def test_expanding_and_bayesian_are_constant_over_draws(self):
        rng = random.Random(2)
        draws = _make_draws(rng, 100)
        predictions = _component_predictions(
            draws, draws[:80], draws[80:], change_point_permutations=9, seed=3,
        )
        self.assertTrue(all(row is predictions["expanding"][0] for row in predictions["expanding"]))
        self.assertTrue(all(row is predictions["bayesian"][0] for row in predictions["bayesian"]))

    def test_predictions_do_not_depend_on_test_outcomes(self):
        rng = random.Random(3)
        draws_a = _make_draws(rng, 100)
        draws_b = list(draws_a[:80]) + [
            (d[0], d[1], {88, 89, 90, 85, 86} if i >= 80 else d[2])
            for i, d in enumerate(draws_a)
        ]
        first_a = _component_predictions(
            draws_a, draws_a[:80], draws_a[80:],
            change_point_permutations=9, seed=3,
        )
        first_b = _component_predictions(
            draws_b, draws_b[:80], draws_b[80:],
            change_point_permutations=9, seed=3,
        )
        for code in ("expanding", "bayesian", "regime", "rolling"):
            self.assertEqual(first_a[code][0], first_b[code][0])

    def test_rolling_updates_but_never_uses_current_draw(self):
        rng = random.Random(4)
        draws = _make_draws(rng, 100)
        predictions = _component_predictions(
            draws, draws[:80], draws[80:], change_point_permutations=9, seed=3,
        )
        self.assertNotEqual(predictions["rolling"][0], predictions["rolling"][-1])


if __name__ == "__main__":
    unittest.main()
