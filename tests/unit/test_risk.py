import unittest

from lottery_intelligence_platform.risk_evaluation import (
    Bet,
    breakeven_multiplier,
    equity_risk,
    ruin_probability,
    simulate_turbo_bets,
)


class TestSimulateTurboBets(unittest.TestCase):
    def test_hit_and_miss_net(self):
        bets = simulate_turbo_bets(
            [{1, 2, 3, 4, 5}, {6, 7, 8, 9, 10}],
            {1, 2}, stake=100.0, multiplier=10.0,
        )
        self.assertEqual([b.hit for b in bets], [True, False])
        self.assertEqual([b.net for b in bets], [900.0, -100.0])

    def test_requires_full_subset(self):
        bets = simulate_turbo_bets([{1, 3, 4, 5, 6}], {1, 2}, stake=100.0, multiplier=10.0)
        self.assertFalse(bets[0].hit)


class TestEquityRisk(unittest.TestCase):
    def test_max_drawdown_and_streak(self):
        bets = [
            Bet(False, -1), Bet(False, -1), Bet(True, 9),
            Bet(False, -1), Bet(False, -1), Bet(False, -1),
        ]
        risk = equity_risk(bets, stake=1.0, bankroll_stakes=100.0)
        self.assertEqual(risk["max_drawdown"], 3.0)
        self.assertEqual(risk["longest_losing_streak"], 3)
        self.assertAlmostEqual(risk["net_per_bet_mean"], 4 / 6)

    def test_variance(self):
        bets = [Bet(True, 9), Bet(False, -1)] * 10
        risk = equity_risk(bets, stake=1.0, bankroll_stakes=100.0)
        self.assertAlmostEqual(risk["net_per_bet_mean"], 4.0)
        self.assertAlmostEqual(risk["net_per_bet_variance"], 25.0)


class TestBreakeven(unittest.TestCase):
    def test_no_hits_returns_none(self):
        self.assertIsNone(breakeven_multiplier([Bet(False, -1)] * 10))

    def test_breakeven_is_ratio(self):
        bets = [Bet(True, 99)] + [Bet(False, -1)] * 9
        self.assertAlmostEqual(breakeven_multiplier(bets), 10.0)


class TestRuinProbability(unittest.TestCase):
    def test_all_losing_is_certain_ruin(self):
        bets = [Bet(False, -1)] * 200
        self.assertEqual(
            ruin_probability(bets, bankroll=50, paths=50, seed=1), 1.0
        )

    def test_deterministic(self):
        bets = [Bet(True, 9)] + [Bet(False, -1)] * 9
        first = ruin_probability(bets, bankroll=20, paths=100, seed=4)
        second = ruin_probability(bets, bankroll=20, paths=100, seed=4)
        self.assertEqual(first, second)

    def test_bankroll_larger_than_stake_drain_never_ruins(self):
        bets = [Bet(False, -1)] * 50
        self.assertEqual(
            ruin_probability(bets, bankroll=60, paths=20, seed=1), 0.0
        )

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            ruin_probability([], bankroll=10, paths=5, seed=1)


if __name__ == "__main__":
    unittest.main()
