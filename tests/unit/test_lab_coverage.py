import math
import unittest
from itertools import combinations

import lottery_intelligence_platform.lab_coverage as lc


RULE = {
    "code": "turbo_fixed_odds",
    "version": "official-turbo-position-2026-10",
    "verification_status": "VERIFIED_OFFICIAL",
    "positions_by_variant": {"turbo_2": 2, "turbo_3": 3, "turbo_4": 4, "turbo_5": 5},
    "payout_multipliers": {"2": 2400.0, "3": 800.0, "4": 400.0, "5": 240.0},
}


def lab(**overrides):
    params = dict(rule=RULE, budget_fcfa=2000, stake=100, pick_size=2,
                  variant="turbo_5", seed=0, baselines=20, mc_sims=2000)
    params.update(overrides)
    return lc.coverage_laboratory(**params)


class OptimizedPortfolioTests(unittest.TestCase):
    def test_disjoint_tickets_when_pool_allows(self):
        # 20 tickets x 2 = 40 <= 90: first pass yields zero overlap
        tickets = lc._optimized_portfolio(20, 2, __import__("random").Random(0))
        numbers = [n for t in tickets for n in t]
        self.assertEqual(len(tickets), 20)
        self.assertEqual(len(set(numbers)), 40)
        self.assertEqual(lc._metrics(tickets)["pair_overlaps"], 0)

    def test_recycling_when_pool_exhausted(self):
        tickets = lc._optimized_portfolio(50, 2, __import__("random").Random(0))
        self.assertEqual(len(tickets), 50)
        m = lc._metrics(tickets)
        # numbers must be recycled (only 90 exist) but pair overlap stays low
        self.assertLessEqual(m["distinct_numbers"], 90)
        self.assertLess(m["pair_overlap_mean"], 1.0)

    def test_pick_size_five_disjoint_pass(self):
        tickets = lc._optimized_portfolio(18, 5, __import__("random").Random(0))
        numbers = [n for t in tickets for n in t]
        self.assertEqual(len(set(numbers)), 90)  # perfect partition

    def test_deterministic_same_seed(self):
        a = lc._optimized_portfolio(10, 2, __import__("random").Random(42))
        b = lc._optimized_portfolio(10, 2, __import__("random").Random(42))
        self.assertEqual(a, b)


class ProbabilityTests(unittest.TestCase):
    def test_exact_single_ticket_turbo2(self):
        r = lc.probability_at_least_one_win([(1, 2)], 2, seed=0)
        self.assertEqual(r["method"], "EXACT")
        self.assertAlmostEqual(r["value"], 1 / math.comb(90, 2))

    def test_exact_pick_equals_positions(self):
        tickets = [(1, 2), (3, 4), (5, 6)]
        r = lc.probability_at_least_one_win(tickets, 2, seed=0)
        self.assertEqual(r["method"], "EXACT")
        # win iff the 2-position zone equals a ticket: distinct / C(90,2)
        self.assertAlmostEqual(r["value"], 3 / math.comb(90, 2))

    def test_exact_pick_size_one(self):
        tickets = [(n,) for n in range(1, 11)]  # union = 10 numbers
        r = lc.probability_at_least_one_win(tickets, 5, seed=0)
        self.assertEqual(r["method"], "EXACT")
        expected = 1 - math.comb(80, 5) / math.comb(90, 5)
        self.assertAlmostEqual(r["value"], expected)

    def test_exact_small_universe_controlled(self):
        saved = lc.POPULATION
        try:
            lc.POPULATION = 10
            r = lc.probability_at_least_one_win(
                [(1, 2), (3, 4)], 3, seed=0, mc_sims=500)
            self.assertEqual(r["method"], "EXACT")
            # brute force: subsets of C(10,3)=120 containing {1,2} or {3,4}
            wins = sum(1 for c in combinations(range(1, 11), 3)
                       if {1, 2} <= set(c) or {3, 4} <= set(c))
            self.assertAlmostEqual(r["value"], wins / 120)
        finally:
            lc.POPULATION = saved

    def test_monte_carlo_reproducible_and_labelled(self):
        tickets = lc._optimized_portfolio(45, 2, __import__("random").Random(1))
        a = lc.probability_at_least_one_win(tickets, 5, seed=9, mc_sims=2000)
        b = lc.probability_at_least_one_win(tickets, 5, seed=9, mc_sims=2000)
        self.assertEqual(a["method"], "MONTE_CARLO")
        self.assertEqual(a, b)
        self.assertEqual(a["mc_sims"], 2000)
        self.assertEqual(a["mc_seed"], 9)
        self.assertEqual(len(a["ci95_wilson"]), 2)

    def test_impossible_when_pick_larger_than_zone(self):
        r = lc.probability_at_least_one_win([(1, 2, 3)], 2, seed=0)
        self.assertEqual(r["value"], 0.0)
        self.assertEqual(r["method"], "EXACT")

    def test_monte_carlo_consistent_with_exact(self):
        saved_pop, saved_max = lc.POPULATION, lc.EXACT_ENUM_MAX
        try:
            lc.POPULATION = 10
            tickets = [(1, 2), (3, 4), (5, 6)]
            lc.EXACT_ENUM_MAX = 200_000
            exact = lc.probability_at_least_one_win(tickets, 3, seed=0)
            self.assertEqual(exact["method"], "EXACT")
            lc.EXACT_ENUM_MAX = 0  # force the Monte-Carlo path
            mc = lc.probability_at_least_one_win(tickets, 3, seed=3,
                                                 mc_sims=40_000)
            self.assertEqual(mc["method"], "MONTE_CARLO")
            self.assertTrue(
                mc["ci95_wilson"][0] <= exact["value"] <= mc["ci95_wilson"][1],
                f"exact {exact['value']} outside MC CI {mc['ci95_wilson']}")
        finally:
            lc.POPULATION, lc.EXACT_ENUM_MAX = saved_pop, saved_max


class LaboratoryTests(unittest.TestCase):
    def test_budget_not_multiple_of_stake(self):
        r = lab(budget_fcfa=2150, stake=100)
        self.assertEqual(r["tickets"], 21)
        self.assertEqual(r["remainder_fcfa"], 50)
        self.assertEqual(r["stake_total"], 2100)

    def test_budget_below_stake_rejected(self):
        with self.assertRaises(ValueError):
            lab(budget_fcfa=50, stake=100)

    def test_single_ticket(self):
        r = lab(tickets=1, budget_fcfa=None)
        self.assertEqual(r["tickets"], 1)
        self.assertEqual(len(r["optimized"]["portfolio"]), 1)

    def test_pick_size_one(self):
        r = lab(pick_size=1, budget_fcfa=500)
        self.assertEqual(r["tickets"], 5)
        self.assertEqual(r["optimized"]["metrics"]["distinct_numbers"], 5)
        self.assertEqual(r["optimized"]["metrics"]["distinct_pairs"], 0)

    def test_pick_size_five(self):
        r = lab(pick_size=5, budget_fcfa=500)
        self.assertEqual(r["optimized"]["metrics"]["distinct_pairs"], 50)

    def test_ev_portfolio_equals_n_times_ev_ticket(self):
        r = lab(budget_fcfa=3000)
        eco = r["optimized"]["economics"]
        self.assertAlmostEqual(
            eco["ev_portfolio"], eco["ev_per_ticket"] * r["tickets"])
        # gross = stake * multiplier; net convention matches settlement
        self.assertEqual(eco["gross_payout_per_win"], 100 * 240.0)
        self.assertAlmostEqual(eco["expected_loss"], -eco["ev_portfolio"])

    def test_odds_come_from_rule_not_hardcoded(self):
        altered = dict(RULE, payout_multipliers={"5": 999.0})
        r = lab(rule=altered)
        self.assertEqual(r["payout_rule"]["payout_multiplier"], 999.0)
        self.assertEqual(r["optimized"]["economics"]["gross_payout_per_win"],
                         100 * 999.0)

    def test_same_seed_same_result(self):
        self.assertEqual(lab(seed=7), lab(seed=7))

    def test_random_baseline_compared(self):
        r = lab(budget_fcfa=3000)
        base = r["random_baseline"]
        self.assertEqual(base["portfolios"], 20)
        self.assertGreater(
            r["optimized"]["metrics"]["distinct_pairs"],
            base["distinct_pairs_mean"])
        self.assertIn("p_at_least_one_mean", base)
        self.assertIn("p_at_least_one_vs_random", r["comparison"])

    def test_rule_version_echoed_and_variant_resolved(self):
        r = lab(variant="turbo_3")
        self.assertEqual(r["payout_rule"]["version"],
                         "official-turbo-position-2026-10")
        self.assertEqual(r["win_zone_positions"], 3)
        self.assertEqual(r["payout_rule"]["payout_multiplier"], 800.0)

    def test_unknown_variant_rejected(self):
        with self.assertRaises(ValueError):
            lab(variant="turbo_9")


if __name__ == "__main__":
    unittest.main()
