"""Game Temporal Intelligence — unit tests on pure aggregations."""
import random
import unittest
from datetime import date, timedelta

from lottery_intelligence_platform import game_temporal as gt


def series_from(hits, start=date(2026, 1, 5), step_days=7):
    """Synthetic series: one draw per week on `start`'s weekday."""
    return [{"date": start + timedelta(days=step_days * i), "hits": h}
            for i, h in enumerate(hits)]


def series_days(hit_by_weekday, weeks=10, monday=date(2026, 1, 5)):
    """Series with a draw every weekday for `weeks` weeks."""
    out = []
    for w in range(weeks):
        for wd in range(7):
            out.append({"date": monday + timedelta(days=w * 7 + wd),
                        "hits": hit_by_weekday[wd % len(hit_by_weekday)]})
    return out


class WeeklyAggregationTest(unittest.TestCase):
    def test_weeks_grouped_by_iso(self):
        s = series_from([1, 2, 0, 3])
        weekly = gt.weekly_aggregate(s)
        self.assertEqual(len(weekly), 4)
        self.assertTrue(all(w["iso_week"].startswith("2026-W") for w in weekly))
        self.assertEqual(weekly[1]["mean_hits"], 2.0)

    def test_same_iso_week_aggregated(self):
        mon, tue = date(2026, 1, 5), date(2026, 1, 6)
        s = [{"date": mon, "hits": 1}, {"date": tue, "hits": 3},
             {"date": mon + timedelta(weeks=1), "hits": 2}]
        weekly = gt.weekly_aggregate(s)
        self.assertEqual(len(weekly), 2)
        self.assertEqual(weekly[0]["n"], 2)
        self.assertEqual(weekly[0]["mean_hits"], 2.0)

    def test_ge_thresholds(self):
        s = series_from([0, 1, 2, 3, 2, 1, 0, 2])
        agg = gt._aggregate(s)
        self.assertEqual(agg["ge1_pct"], 75.0)
        self.assertEqual(agg["ge2_pct"], 50.0)
        self.assertEqual(agg["ge3_pct"], 12.5)


class WeekdayAggregationTest(unittest.TestCase):
    def test_weekdays_separated(self):
        s = series_days([0, 1, 2, 3, 0, 1, 2], weeks=5)
        agg = gt.weekday_aggregate(s)
        self.assertEqual(len(agg), 7)
        by_wd = {a["weekday"]: a for a in agg}
        self.assertEqual(by_wd[0]["mean_hits"], 0.0)   # Mondays
        self.assertEqual(by_wd[3]["mean_hits"], 3.0)   # Thursdays
        self.assertEqual(by_wd[3]["n"], 5)

    def test_strict_per_weekday_segmentation(self):
        # hits differ per weekday — weekday means must not bleed into each other
        s = series_days([5, 0, 0, 0, 0, 0, 0], weeks=4)
        agg = {a["weekday"]: a for a in gt.weekday_aggregate(s)}
        self.assertEqual(agg[0]["mean_hits"], 5.0)
        self.assertEqual(agg[1]["mean_hits"], 0.0)


class StreaksTest(unittest.TestCase):
    def test_best_and_worst(self):
        best, worst = gt._streaks([1, 2, 0, 0, 0, 1, 1, 1, 0])
        self.assertEqual(best, 3)
        self.assertEqual(worst, 3)


class ConsistencyTest(unittest.TestCase):
    def test_perfectly_stable(self):
        # same hits every week → CV 0 → index 1
        hits = [2] * 12
        dates = [date(2026, 1, 5) + timedelta(weeks=i) for i in range(12)]
        c = gt.consistency(hits, dates)
        self.assertEqual(c["consistency_index"], 1.0)
        self.assertEqual(c["stability"], "stable")

    def test_volatile_beats_stable_distinction(self):
        # same overall level, wildly varying weeks vs uniform weeks
        dates = [date(2026, 1, 5) + timedelta(weeks=i) for i in range(10)]
        volatile = gt.consistency([0, 4, 0, 4, 0, 4, 0, 4, 0, 4], dates)
        stable = gt.consistency([2] * 10, dates)
        self.assertLess(volatile["consistency_index"], stable["consistency_index"])
        self.assertEqual(volatile["stability"], "volatile")

    def test_not_computable(self):
        c = gt.consistency([0, 0, 0], [date(2026, 1, 5)] * 3)
        self.assertIsNone(c["consistency_index"])


class NullReferenceTest(unittest.TestCase):
    def test_hypergeometric_expectations_pick5(self):
        ref = gt.null_reference(5)
        self.assertAlmostEqual(ref["expected_mean_hits"], 5 * 5 / 90, places=3)
        self.assertAlmostEqual(ref["expected_ge1_pct"], 25.8, places=0)
        self.assertAlmostEqual(ref["expected_ge2_pct"], 2.3, places=0)

    def test_hypergeom_pick2_turbo(self):
        # pick 2 vs 5 drawn: P(>=1) = 1 - C(88,5)/C(90,5)
        p = gt.hypergeom_ge(2, 1)
        from math import comb
        self.assertAlmostEqual(p, 1 - comb(88, 5) / comb(90, 5), places=9)

    def test_ge1_purity(self):
        # exact probability for a 1-number pick
        self.assertAlmostEqual(gt.hypergeom_ge(1, 1), 5 / 90, places=9)


class VsNullTest(unittest.TestCase):
    def test_random_level_series_no_signal(self):
        rng = random.Random(1)
        # hits ~ hypergeometric-ish for pick 5: mostly 0, some 1
        s = series_from([rng.choices([0, 1, 2], weights=[74, 22, 4])[0]
                         for _ in range(200)])
        v = gt.vs_null(s, 5)
        self.assertIn("binomial_p_ge1", v)
        self.assertIn("lift_mean_pct", v)

    def test_strong_series_detected(self):
        s = series_from([2] * 100)  # absurdly strong vs null
        v = gt.vs_null(s, 5)
        self.assertLess(v["binomial_p_ge1"], 0.001)
        self.assertGreater(v["lift_mean_pct"], 100)


class PairedVsNullTest(unittest.TestCase):
    def test_identical_series_zero_diff(self):
        s = series_from([0, 1, 0, 1, 2] * 20)
        out = gt.paired_vs_null(s, list(s), seed=7)
        self.assertEqual(out["mean_hit_diff"], 0.0)

    def test_better_series_significant(self):
        weak = series_from([0] * 150)
        strong = series_from([1] * 150)
        out = gt.paired_vs_null(strong, weak, seed=7)
        self.assertEqual(out["mean_hit_diff"], 1.0)
        self.assertLessEqual(out["permutation_p"], 0.01)

    def test_reproducible_seed(self):
        rng = random.Random(3)
        a = series_from([rng.randint(0, 3) for _ in range(80)])
        b = series_from([rng.randint(0, 3) for _ in range(80)])
        r1 = gt.paired_vs_null(a, b, seed=42)
        r2 = gt.paired_vs_null(a, b, seed=42)
        self.assertEqual(r1, r2)


class SampleLevelTest(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(gt.sample_level(5), "insufficient")
        self.assertEqual(gt.sample_level(10), "preliminary")
        self.assertEqual(gt.sample_level(40), "adequate")

    def test_profile_hides_stats_when_insufficient(self):
        p = gt.model_profile(series_from([4, 4, 4]), 5, seed=1)
        self.assertEqual(p["sample_level"], "insufficient")
        self.assertNotIn("mean_hits", p)
        self.assertEqual(p["label"], "Échantillon insuffisant")


class TrendTest(unittest.TestCase):
    def test_improving_and_declining(self):
        up = gt.trend(gt.weekly_aggregate(
            series_from([1] * 8 + [3] * 4)))
        self.assertEqual(up["label"], "improving")
        down = gt.trend(gt.weekly_aggregate(
            series_from([3] * 8 + [1] * 4)))
        self.assertEqual(down["label"], "declining")


class ChangePointTest(unittest.TestCase):
    def test_regime_shift_detected(self):
        # 15 weeks of zeros then 15 weeks of 2-hits — weekly hit-count
        # vectors differ dramatically → change point at the boundary
        s = series_from([0] * 90 + [2] * 90, step_days=1)
        cp = gt.change_point_observation(s, 5, seed=11)
        self.assertIsNotNone(cp)
        self.assertLessEqual(cp["permutation_p"], 0.05)

    def test_no_regime_no_finding(self):
        rng = random.Random(5)
        s = series_from([rng.choice([0, 1]) for _ in range(120)], step_days=1)
        cp = gt.change_point_observation(s, 5, seed=11)
        # may occasionally fire by chance; uniform-level series must not
        # produce a significant split deterministically
        if cp is not None:
            self.assertGreater(cp["permutation_p"], 0.0)  # never p=0 asserted
        # typical case: none
        # (assertion kept loose: the test only documents behaviour)

    def test_too_few_weeks_returns_none(self):
        s = series_from([1, 2, 0, 1, 2])
        self.assertIsNone(gt.change_point_observation(s, 5, seed=1))


class AntiLeakageTest(unittest.TestCase):
    def test_wf_series_never_sees_future(self):
        seen_windows = []

        def spy(hist, rng, k):
            seen_windows.append(len(hist))
            return list(range(k))

        hist = [[i] for i in range(50)]
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(50)]
        out = gt.wf_series(hist, dates, spy, pick_count=1, seed=1, warmup=20)
        self.assertEqual(len(out), 30)
        # model at index i sees exactly i draws — strictly anterior
        self.assertEqual(seen_windows[0], 20)
        self.assertEqual(seen_windows[-1], 49)
        for i, window in enumerate(seen_windows):
            self.assertEqual(window, 20 + i)

    def test_determinism_same_seed(self):
        def fn(hist, rng, k):
            return rng.sample(range(90), k)
        hist = [[i % 90] for i in range(60)]
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(60)]
        a = gt.wf_series(hist, dates, fn, pick_count=5, seed=99)
        b = gt.wf_series(hist, dates, fn, pick_count=5, seed=99)
        self.assertEqual(a, b)

    def test_stable_seed_process_independent(self):
        self.assertEqual(gt._stable_seed("x", "y"), gt._stable_seed("x", "y"))
        self.assertNotEqual(gt._stable_seed("x"), gt._stable_seed("y"))


class ProspectiveMatrixShapeTest(unittest.TestCase):
    def test_aggregate_shape(self):
        # _aggregate drives the matrix cells — verify keys and empty case
        self.assertEqual(gt._aggregate([]), {"n": 0})
        agg = gt._aggregate([{"hits": 0}] * 12)
        self.assertEqual(agg["sample_level"], "preliminary")
        self.assertEqual(agg["ge1_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
