"""Lab models operating on chronological winning-number history.

Ported faithfully from lottery-statistics-expert models/models.py, with the
pick count parameterised. `hist` is a list of number lists ordered by draw
date (past only — the caller enforces the temporal cut). `rng` is a seeded
random.Random for the stochastic models; deterministic ones ignore it.

    predict_*(hist, rng, k) -> sorted list of k numbers in 1..90
"""

from __future__ import annotations

import math
import random
from typing import Callable

MIN_NUM, MAX_NUM = 1, 90
POOL = list(range(MIN_NUM, MAX_NUM + 1))


def frequency(hist: list[list[int]]) -> dict[int, int]:
    freq: dict[int, int] = {}
    for nums in hist:
        for x in nums:
            freq[x] = freq.get(x, 0) + 1
    return freq


def delay(hist: list[list[int]]) -> dict[int, int]:
    """Draws since last appearance (n if never seen)."""
    last_seen: dict[int, int] = {}
    for idx, nums in enumerate(hist):
        for x in nums:
            last_seen[x] = idx
    n = len(hist)
    return {x: (n - 1 - last_seen[x]) if x in last_seen else n for x in POOL}


def gap_mean(hist: list[list[int]]) -> dict[int, float | None]:
    """Mean gap between successive appearances (None if < 2 appearances)."""
    gaps: dict[int, list[int]] = {}
    prev: dict[int, int] = {}
    for idx, nums in enumerate(hist):
        for x in nums:
            if x in prev:
                gaps.setdefault(x, []).append(idx - prev[x])
            prev[x] = idx
    return {x: (sum(gaps[x]) / len(gaps[x])) if gaps.get(x) else None for x in POOL}


def weighted_draw(
    rng: random.Random, weights: dict[int, float], k: int
) -> list[int]:
    """k numbers without replacement, weighted (urn model)."""
    pool = list(POOL)
    total = sum(weights[x] for x in pool)
    picked: list[int] = []
    for _ in range(min(k, len(pool))):
        r = rng.random() * total
        acc = 0.0
        for x in pool:
            acc += weights[x]
            if acc >= r:
                picked.append(x)
                pool.remove(x)
                total -= weights[x]
                break
    return picked


def predict_random(hist: list[list[int]], rng: random.Random, k: int) -> list[int]:
    return sorted(rng.sample(POOL, min(k, len(POOL))))


def predict_hot_frequency_v1(hist, rng, k):
    """Top-frequency pool (20), prefer numbers 'due' (delay > mean gap)."""
    freq = frequency(hist)
    pool = sorted(POOL, key=lambda x: (-freq.get(x, 0), x))[:20]
    d = delay(hist)
    gm = gap_mean(hist)
    due = [(x, d[x] - gm[x], freq.get(x, 0))
           for x in pool if gm[x] and d[x] > gm[x]]
    due.sort(key=lambda t: (-t[1], -t[2]))
    if len(due) >= k:
        return sorted(x for x, _, _ in due[:k])
    return sorted(pool[:k])


def predict_cold_delay_v1(hist, rng, k):
    freq = frequency(hist)
    d = delay(hist)
    ranked = sorted(POOL, key=lambda x: (-d[x], -freq.get(x, 0), x))
    return sorted(ranked[:k])


def predict_frequency_delay_v1(hist, rng, k):
    freq = frequency(hist)
    d = delay(hist)
    f_vals = [freq.get(x, 0) for x in POOL]
    d_vals = [d[x] for x in POOL]
    mf, md = sum(f_vals) / 90, sum(d_vals) / 90
    sf = math.sqrt(sum((v - mf) ** 2 for v in f_vals) / 90) or 1
    sd = math.sqrt(sum((v - md) ** 2 for v in d_vals) / 90) or 1
    score = {x: (freq.get(x, 0) - mf) / sf + (d[x] - md) / sd for x in POOL}
    return sorted(sorted(POOL, key=lambda x: (-score[x], x))[:k])


def predict_pair_frequency_v1(hist, rng, k):
    """Recency-decayed co-occurrence credit over the last 30 draws."""
    freq = frequency(hist)
    score: dict[int, float] = {}
    for offset, nums in enumerate(reversed(hist[-30:])):
        w = 1.0 / (1 + offset)
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                score[nums[i]] = score.get(nums[i], 0.0) + w
                score[nums[j]] = score.get(nums[j], 0.0) + w
    ranked = sorted(POOL, key=lambda x: (-score.get(x, 0), -freq.get(x, 0), x))
    return sorted(ranked[:k])


def predict_balanced_v1(hist, rng, k):
    """~60% hottest numbers + remaining slots filled by most overdue."""
    n_hot = max(1, round(k * 3 / 5)) if k >= 2 else k
    freq = frequency(hist)
    d = delay(hist)
    hot = sorted(POOL, key=lambda x: (-freq.get(x, 0), x))
    cold = sorted(POOL, key=lambda x: (-d[x], x))
    picks = hot[:n_hot]
    for x in cold:
        if len(picks) >= k:
            break
        if x not in picks:
            picks.append(x)
    return sorted(picks)


def predict_bayesian_v1(hist, rng, k):
    """Laplace-smoothed posterior then seeded weighted draw."""
    n = len(hist)
    per_draw = len(hist[0]) if hist else 5
    freq = frequency(hist)
    weights = {x: (freq.get(x, 0) + 1) / (per_draw * n + 90) for x in POOL}
    return sorted(weighted_draw(rng, weights, k))


def predict_monte_carlo_v1(hist, rng, k):
    """100 seeded simulations on recency-weighted frequency."""
    score: dict[int, float] = {}
    for offset, nums in enumerate(reversed(hist[-40:])):
        w = 1.0 / (1 + offset)
        for x in nums:
            score[x] = score.get(x, 0.0) + w
    weights = {x: score.get(x, 0.0) + 1 for x in POOL}
    sim_counts: dict[int, int] = {}
    sim_k = min(5, len(hist[0]) if hist else 5)
    for _ in range(100):
        for x in weighted_draw(rng, weights, sim_k):
            sim_counts[x] = sim_counts.get(x, 0) + 1
    ranked = sorted(POOL, key=lambda x: (-sim_counts.get(x, 0), x))
    return sorted(ranked[:k])


def predict_top_k(hist, rng, k):
    """Platform picker: top-k by all-time frequency."""
    freq = frequency(hist)
    return sorted(sorted(POOL, key=lambda x: (-freq.get(x, 0), x))[:k])


def predict_rolling(hist, rng, k, window: int = 200):
    """Platform picker: top-k by frequency over the last `window` draws."""
    return predict_top_k(hist[-window:], rng, k)


def predict_bayesian_shrinkage(hist, rng, k, alpha: float = 5.0, mu: float = 5 / 90):
    """Platform picker: posterior-mean ranking with shrinkage prior."""
    n = len(hist)
    freq = frequency(hist)
    per_draw = len(hist[0]) if hist else 5
    score = {x: (freq.get(x, 0) + mu * alpha) / (n + alpha) for x in POOL}
    return sorted(sorted(POOL, key=lambda x: (-score[x], x))[:k])


_DETERMINISTIC: tuple[Callable, ...] = (
    predict_hot_frequency_v1, predict_cold_delay_v1, predict_frequency_delay_v1,
    predict_pair_frequency_v1, predict_balanced_v1,
)


def predict_ensemble_v1(hist, rng, k):
    """Borda vote over the deterministic lab models."""
    borda: dict[int, int] = {}
    for fn in _DETERMINISTIC:
        for rank, x in enumerate(fn(hist, rng, k)):
            borda[x] = borda.get(x, 0) + (k * 2 - rank)
    ranked = sorted(POOL, key=lambda x: (-borda.get(x, 0), x))
    return sorted(ranked[:k])


# Model codes used in research.model_versions / cohort members.
HIST_MODELS: dict[str, Callable[[list[list[int]], random.Random, int], list[int]]] = {
    "random": predict_random,
    "hot_frequency_v1": predict_hot_frequency_v1,
    "cold_delay_v1": predict_cold_delay_v1,
    "frequency_delay_v1": predict_frequency_delay_v1,
    "pair_frequency_v1": predict_pair_frequency_v1,
    "balanced_v1": predict_balanced_v1,
    "bayesian_v1": predict_bayesian_v1,
    "monte_carlo_v1": predict_monte_carlo_v1,
    "ensemble_v1": predict_ensemble_v1,
}
