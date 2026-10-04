import math
import unittest

from lottery_intelligence_platform.calibration import (
    EXPECTED_INCLUSION_RATE,
    brier_score,
    clip_probability,
    expected_calibration_error,
    log_loss,
    probability_predictions,
    reliability_bins,
)


class TestScoringRules(unittest.TestCase):
    def test_brier_score_perfect_forecaster(self):
        self.assertAlmostEqual(brier_score([1.0, 0.0, 1.0], [1, 0, 1]), 0.0)

    def test_brier_score_null_prediction(self):
        predictions = [0.5] * 4
        outcomes = [1, 0, 1, 0]
        self.assertAlmostEqual(brier_score(predictions, outcomes), 0.25)

    def test_log_loss_confident_correct(self):
        self.assertLess(log_loss([0.99], [1]), 0.02)

    def test_log_loss_confident_wrong_is_penalized_hard(self):
        self.assertGreater(log_loss([0.99], [0]), 4.0)

    def test_log_loss_clips_extremes(self):
        value = log_loss([1.0], [0])
        self.assertTrue(math.isfinite(value))
        self.assertGreater(value, 15.0)

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ValueError):
            brier_score([0.5], [1, 0])
        with self.assertRaises(ValueError):
            log_loss([], [])


class TestReliabilityBins(unittest.TestCase):
    def test_bins_cover_all_observations(self):
        predictions = [i / 100 for i in range(100)]
        outcomes = [1 if i > 60 else 0 for i in range(100)]
        bins = reliability_bins(predictions, outcomes, bins=10)
        self.assertEqual(sum(b["count"] for b in bins), 100)
        self.assertEqual(len(bins), 10)
        self.assertAlmostEqual(bins[-1]["observed_frequency"], 1.0)

    def test_ece_is_zero_for_perfect_calibration(self):
        bins = [
            {"mean_predicted": 0.2, "observed_frequency": 0.2, "count": 50},
            {"mean_predicted": 0.8, "observed_frequency": 0.8, "count": 50},
        ]
        self.assertAlmostEqual(expected_calibration_error(bins, 100), 0.0)

    def test_ece_weights_by_bucket_size(self):
        bins = [
            {"mean_predicted": 0.0, "observed_frequency": 1.0, "count": 10},
            {"mean_predicted": 0.5, "observed_frequency": 0.5, "count": 90},
        ]
        self.assertAlmostEqual(expected_calibration_error(bins, 100), 0.1)


class TestProbabilityPredictions(unittest.TestCase):
    def test_null_model_returns_inclusion_rate(self):
        preds = probability_predictions("null_model_benchmark", [0] * 90, 0, {})
        self.assertTrue(all(p == EXPECTED_INCLUSION_RATE for p in preds))
        self.assertAlmostEqual(sum(preds), 5.0)

    def test_predictions_sum_to_draw_size(self):
        counts = [10] * 90  # 900 selections over 180 draws = 5 per draw
        for code, definition in (
            ("top_k_frequency", {}),
            ("bayesian_shrinkage", {"alpha": 5.0}),
            ("rolling_frequency", {"window_draws": 200}),
        ):
            preds = probability_predictions(code, counts, 180, definition)
            self.assertAlmostEqual(sum(preds), 5.0, places=9)

    def test_shrinkage_pulls_toward_prior(self):
        counts = [50] + [0] * 89
        shrinkage = probability_predictions(
            "bayesian_shrinkage", counts, 100, {"alpha": 50.0}
        )
        self.assertLess(shrinkage[0], 0.5)
        self.assertGreater(shrinkage[0], EXPECTED_INCLUSION_RATE)

    def test_mle_prediction_without_prior_mass(self):
        preds = probability_predictions(
            "top_k_frequency", [10] + [0] * 89, 100, {"prior_draws": 0.0}
        )
        self.assertAlmostEqual(preds[0], 0.1)

    def test_predictions_are_clipped(self):
        preds = probability_predictions(
            "top_k_frequency", [500] + [0] * 89, 100, {"prior_draws": 0.0}
        )
        self.assertLess(preds[0], 1.0)

    def test_unknown_model_raises(self):
        with self.assertRaises(ValueError):
            probability_predictions("unknown", [0] * 90, 10, {})

    def test_negative_draws_raises(self):
        with self.assertRaises(ValueError):
            probability_predictions("null_model_benchmark", [0] * 90, -1, {})

    def test_clip_bounds(self):
        self.assertGreater(clip_probability(-5.0), 0.0)
        self.assertLess(clip_probability(5.0), 1.0)


if __name__ == "__main__":
    unittest.main()
