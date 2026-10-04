from __future__ import annotations

import math
from typing import Sequence

_EPSILON = 1e-7
EXPECTED_INCLUSION_RATE = 5 / 90


def clip_probability(p: float) -> float:
    return min(max(p, _EPSILON), 1 - _EPSILON)


def brier_score(predictions: Sequence[float], outcomes: Sequence[int]) -> float:
    if len(predictions) != len(outcomes) or not predictions:
        raise ValueError("predictions and outcomes must be non-empty and equally sized")
    return sum((p - y) ** 2 for p, y in zip(predictions, outcomes)) / len(predictions)


def log_loss(predictions: Sequence[float], outcomes: Sequence[int]) -> float:
    if len(predictions) != len(outcomes) or not predictions:
        raise ValueError("predictions and outcomes must be non-empty and equally sized")
    total = 0.0
    for p, y in zip(predictions, outcomes):
        clipped = clip_probability(p)
        total += y * math.log(clipped) + (1 - y) * math.log(1 - clipped)
    return -total / len(predictions)


def reliability_bins(
    predictions: Sequence[float],
    outcomes: Sequence[int],
    *,
    bins: int = 10,
) -> list[dict[str, float]]:
    if len(predictions) != len(outcomes) or not predictions:
        raise ValueError("predictions and outcomes must be non-empty and equally sized")
    ordered = sorted(zip(predictions, outcomes), key=lambda pair: pair[0])
    chunk = max(1, len(ordered) // bins)
    result = []
    for index in range(0, len(ordered), chunk):
        bucket = ordered[index:index + chunk]
        if not bucket:
            continue
        mean_pred = sum(p for p, _ in bucket) / len(bucket)
        observed = sum(y for _, y in bucket) / len(bucket)
        result.append({
            "mean_predicted": mean_pred,
            "observed_frequency": observed,
            "count": len(bucket),
        })
    return result


def expected_calibration_error(bins_: Sequence[dict[str, float]], n: int) -> float:
    if n <= 0:
        raise ValueError("n must be positive")
    return sum(
        bucket["count"] * abs(bucket["mean_predicted"] - bucket["observed_frequency"])
        for bucket in bins_
    ) / n


def probability_predictions(
    code: str,
    counts: Sequence[int],
    n_draws: int,
    definition: dict,
) -> list[float]:
    if n_draws < 0:
        raise ValueError("n_draws cannot be negative")
    if code == "null_model_benchmark":
        return [EXPECTED_INCLUSION_RATE] * len(counts)
    prior_draws = 1.0
    if code == "bayesian_shrinkage":
        prior_draws = float(definition.get("alpha", 5.0))
    elif code in {"top_k_frequency", "rolling_frequency"}:
        prior_draws = float(definition.get("prior_draws", 1.0))
    else:
        raise ValueError(f"no probability predictor for model: {code}")
    denominator = n_draws + prior_draws
    prior_mass = EXPECTED_INCLUSION_RATE * prior_draws
    return [
        clip_probability((count + prior_mass) / denominator)
        for count in counts
    ]
