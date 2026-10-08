"""Structure Map — null behaviour, leakage, ordering, FDR, reproducibility."""
from __future__ import annotations

import datetime
import random
import unittest

from lottery_intelligence_platform import structure_map as sm


def _uniform_hist(n: int, seed: int = 42, k: int = 5) -> list[list[int]]:
    rng = random.Random(seed)
    return [rng.sample(range(1, 91), k) for _ in range(n)]


def _dated(hist: list[list[int]], start: datetime.date = datetime.date(2024, 1, 1)):
    return [(start + datetime.timedelta(days=i), d) for i, d in enumerate(hist)]


class TestNullC(unittest.TestCase):
    def test_preserves_draw_size_and_marginals(self):
        # skewed history: number 1 in every draw
        hist = [[1] + random.Random(i).sample(range(2, 91), 4)
                for i in range(60)]
        rng = random.Random(0)
        syn = sm.structural_null(hist, rng, 3)
        self.assertEqual(len(syn), 3)
        for h in syn:
            self.assertEqual(len(h), 60)
            self.assertTrue(all(len(d) == 5 and len(set(d)) == 5
                                for d in h))
            # marginal of number 1 must stay near 1.0, never 5/90
            freq1 = sum(1 for d in h if 1 in d) / len(h)
            self.assertGreater(freq1, 0.8)

    def test_deterministic_given_seed(self):
        hist = _uniform_hist(50)
        a = sm.structural_null(hist, random.Random(9), 1)
        b = sm.structural_null(hist, random.Random(9), 1)
        self.assertEqual(a, b)

    def test_destroys_temporal_dependence(self):
        # planted A(t)->A(t+1) should NOT survive NULL C resampling
        from lottery_intelligence_platform.calling_image import (
            evaluate_edges)
        hist = _uniform_hist(200, seed=3)
        for t in range(199):
            if 7 in hist[t] and 7 not in hist[t + 1]:
                hist[t + 1][0] = 7
        row_obs = evaluate_edges(hist, [(7, 7)], horizon=1)["edges"][0]
        syn = sm.structural_null(hist, random.Random(5), 1)[0]
        row_nul = evaluate_edges(syn, [(7, 7)], horizon=1)["edges"][0]
        # observed: deterministic self-chain (p_cond ~1); NULL C keeps the
        # inflated marginal but must break the conditional dependence
        self.assertGreater(row_obs["p_cond"], 0.9)
        self.assertLess(row_nul["lift"], row_obs["lift"] * 0.8)


class TestStatusLadder(unittest.TestCase):
    def test_ladder(self):
        self.assertEqual(sm._status(None), sm.NO_SIGNAL)
        self.assertEqual(sm._status(0.4), sm.NO_SIGNAL)
        self.assertEqual(sm._status(0.01), sm.INTERESTING)
        self.assertEqual(sm._status(0.01, oos_ok=False), sm.UNSTABLE)
        self.assertEqual(sm._status(0.01, oos_ok=True), sm.ROBUST)
        self.assertEqual(
            sm._status(0.01, oos_ok=True, prospective_ok=True),
            sm.VALIDATED)
        # VALIDATED never reachable on in-sample alone
        self.assertNotEqual(sm._status(0.0), sm.VALIDATED)


class TestFrequencyWindows(unittest.TestCase):
    def test_planted_hot_number_flagged(self):
        hist = _uniform_hist(120, seed=1)
        for d in hist[-30:]:
            d[0] = 42
        res = sm.frequency_windows(hist)
        hits = [r for r in res["top"] if r["number"] == 42]
        self.assertTrue(any(r["significant"] for r in hits))
        self.assertLess(res["min_q"], 0.05)

    def test_no_lookahead_baseline(self):
        # if the window itself leaked into the baseline, a number that ONLY
        # appears in the window would have p0=5/90-ish and a mild z;
        # with a strict-past baseline p0 is near zero => large z.
        hist = _uniform_hist(100, seed=2)
        for d in hist[-30:]:
            d[0] = 55
        res = sm.frequency_windows(hist, windows=(30,))
        row = next(r for r in res["top"] if r["number"] == 55)
        self.assertEqual(row["observed"], 30)
        self.assertGreater(row["z"], 5)

    def test_noise_mostly_clean(self):
        res = sm.frequency_windows(_uniform_hist(300, seed=11))
        self.assertLessEqual(res["significant"], 5)


class TestAutocorrelation(unittest.TestCase):
    def test_planted_self_transition(self):
        hist = _uniform_hist(300, seed=4)
        rng = random.Random(0)
        for t in range(299):
            if 7 in hist[t] and rng.random() < 0.6:
                hist[t + 1][0] = 7
        res = sm.autocorrelation(hist, lags=(1, 2), permutations=0)
        self.assertGreater(res["significant"], 0)
        self.assertTrue(any(r["a"] == 7 and r["b"] == 7
                            for r in res["top"]))

    def test_noise_no_signal(self):
        res = sm.autocorrelation(_uniform_hist(300, seed=8), lags=(1,),
                                 permutations=0)
        self.assertEqual(res["significant"], 0)


class TestTransitionMatrix(unittest.TestCase):
    def test_discovers_planted_edge_without_grid(self):
        # 3 -> 77 is NOT a calling edge nor an image edge
        from lottery_intelligence_platform.calling_image import (
            CALLING_EDGES, IMAGE_EDGES)
        self.assertNotIn(77, CALLING_EDGES.get(3, ()))
        self.assertNotIn(77, IMAGE_EDGES.get(3, ()))
        hist = _uniform_hist(300, seed=5)
        rng = random.Random(0)
        for t in range(299):
            # strong enough to survive BH over ~8000 pairs
            if 3 in hist[t] and 77 not in hist[t + 1] \
                    and rng.random() < 0.85:
                hist[t + 1][1] = 77
        res = sm.transition_matrix(hist, permutations=0)
        self.assertGreater(res["significant"], 0)
        edge = next((r for r in res["top"]
                     if r["a"] == 3 and r["b"] == 77), None)
        self.assertIsNotNone(edge)
        self.assertGreater(edge["lift"], 2)

    def test_noise_overlap_keys(self):
        res = sm.transition_matrix(_uniform_hist(150, seed=6),
                                   permutations=0)
        self.assertEqual(res["significant"], 0)
        self.assertEqual(res["calling_overlap"], 0)
        self.assertIn("per_lag", res)


class TestPositional(unittest.TestCase):
    def test_positions_kept_separate(self):
        res = sm.positional_structure(_uniform_hist(200, seed=9),
                                      permutations=20)
        self.assertEqual(len(res["position_uniformity"]), 5)
        self.assertEqual(len(res["persistence"]), 25)
        keys = {(r["from_pos"], r["to_pos"]) for r in res["persistence"]}
        self.assertEqual(len(keys), 25)

    def test_planted_positional_bias(self):
        hist = _uniform_hist(300, seed=7)
        for d in hist:          # position 0 almost always 80
            d[0] = 80
        res = sm.positional_structure(hist, permutations=20)
        row = next(r for r in res["position_uniformity"]
                   if r["position"] == 1)
        self.assertTrue(row["significant"])


class TestRunsDelay(unittest.TestCase):
    def test_delay_is_past_only(self):
        # delay d counts draws since last appearance — a number present at
        # t contributes delay 0 only if seen at t-1, never future info.
        hist = [[1, 2, 3, 4, 5]] * 10
        res = sm.runs_delay(hist, null_c_simulations=10, seed=0)
        zero = [r for r in res["delay_top"] if r["delay_bucket"] == "0-0"]
        self.assertTrue(all(r["rate"] == 1.0 for r in zero))

    def test_runs_detected(self):
        hist = _uniform_hist(200, seed=12)
        for t in range(50, 90):          # number 9 in 40 consecutive draws
            hist[t][2] = 9
        res = sm.runs_delay(hist, null_c_simulations=30, seed=0)
        row = next(r for r in res["runs_top"] if r["number"] == 9)
        self.assertGreaterEqual(row["runs_ge3"], 1)


class TestChangePointSeasonality(unittest.TestCase):
    def test_planted_regime_change(self):
        # Monthly aggregation is intentionally conservative: with ~6
        # periods a mid-series break yields a large statistic but weak
        # permutation power.  We assert *detection* (right boundary),
        # not proof — per the detection/proof distinction.
        hist_a = _uniform_hist(90, seed=20)
        rng = random.Random(21)
        hist_b = [[rng.choice(range(1, 20)) for _ in range(5)]
                  for _ in range(90)]
        dated = _dated(hist_a + hist_b, datetime.date(2024, 1, 1))
        res = sm.change_point_family(dated, permutations=200, seed=0)
        self.assertIsNotNone(res["detail"])
        self.assertEqual(res["detail"]["split_index"], 3)
        self.assertLess(res["min_q"], 0.2)

    def test_seasonality_shape(self):
        res = sm.seasonality(_dated(_uniform_hist(140, seed=30)))
        self.assertEqual(res["n_tests"], 2)
        self.assertIn("weekday_table", res)


class TestCrossGame(unittest.TestCase):
    def _days(self, n_days: int, seed: int = 40):
        rng = random.Random(seed)
        day_games = {}
        for i in range(n_days):
            d = datetime.date(2025, 1, 1) + datetime.timedelta(days=i)
            day_games[d] = [
                (1, "GameA", rng.sample(range(1, 91), 5)),
                (2, "GameB", rng.sample(range(1, 91), 5)),
                (3, "GameC", rng.sample(range(1, 91), 5)),
            ]
        return day_games

    def test_ordering_by_sequence(self):
        # input order scrambled — output must follow scheduled_sequence
        day_games = self._days(20)
        for d in day_games:
            day_games[d] = list(reversed(day_games[d]))
        res = sm.cross_game(day_games, permutations=50, seed=0)
        pairs = {(r["from"], r["to"]) for r in res["pairs"]}
        self.assertIn(("GameA", "GameB"), pairs)
        self.assertIn(("GameB", "GameC"), pairs)
        self.assertNotIn(("GameB", "GameA"), pairs)

    def test_planted_overlap(self):
        day_games = self._days(60)
        for d, games in day_games.items():
            games[1] = (2, "GameB", list(games[0][2][:3]) +
                        random.Random(hash(d) & 0xFFFF).sample(
                            range(1, 91), 2))
        res = sm.cross_game(day_games, permutations=100, seed=0)
        pair = next(r for r in res["pairs"]
                    if r["from"] == "GameA" and r["to"] == "GameB")
        self.assertGreater(pair["overlap_mean"],
                           pair["overlap_expected"] * 2)
        self.assertLess(pair["q_fdr"], 0.05)

    def test_noise(self):
        res = sm.cross_game(self._days(60, seed=55),
                            permutations=50, seed=1)
        self.assertEqual(res["significant"], 0)


class TestBuildMap(unittest.TestCase):
    def test_shape_and_reproducibility(self):
        hist = _uniform_hist(150, seed=60)
        dated = _dated(hist)
        a = sm.build_structure_map(hist, dated=dated, permutations=40,
                                   seed=1, light=True)
        b = sm.build_structure_map(hist, dated=dated, permutations=40,
                                   seed=1, light=True)
        self.assertEqual(a["verdict"], b["verdict"])
        self.assertEqual([s["min_q"] for s in a["statuses"]],
                         [s["min_q"] for s in b["statuses"]])
        families = {s["family"] for s in a["statuses"]}
        self.assertTrue({"frequency", "autocorrelation", "position",
                         "runs_delay", "change_point", "seasonality",
                         "calling_image"} <= families)
        self.assertIn(a["verdict"], sm._STATUS_ORDER)

    def test_light_skips_transition(self):
        res = sm.build_structure_map(_uniform_hist(80, seed=70),
                                     permutations=10, seed=0, light=True)
        self.assertNotIn("transition", res["families"])


if __name__ == "__main__":
    unittest.main()
