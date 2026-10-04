from __future__ import annotations

import random
from typing import Callable, Sequence, TypeVar

T = TypeVar("T")


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    ordered = sorted(values)
    if not 0 <= q <= 1:
        raise ValueError("q must be in [0, 1]")
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def bootstrap_ci(
    statistic: Callable[[list[T]], float],
    items: Sequence[T],
    *,
    resamples: int,
    seed: int,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    if resamples < 1:
        raise ValueError("resamples must be positive")
    if not items:
        raise ValueError("items cannot be empty")
    point = statistic(list(items))
    rng = random.Random(seed)
    n = len(items)
    estimates = []
    for _ in range(resamples):
        sample = [items[rng.randrange(n)] for _ in range(n)]
        estimates.append(statistic(sample))
    return point, percentile(estimates, alpha / 2), percentile(estimates, 1 - alpha / 2)


def paired_bootstrap_difference(
    items_a: Sequence[float],
    items_b: Sequence[float],
    *,
    resamples: int,
    seed: int,
    alpha: float = 0.05,
) -> dict[str, float]:
    if len(items_a) != len(items_b) or not items_a:
        raise ValueError("paired series must be non-empty and equally sized")
    differences = [a - b for a, b in zip(items_a, items_b)]
    point = sum(differences) / len(differences)
    rng = random.Random(seed)
    n = len(differences)
    estimates = []
    for _ in range(resamples):
        total = 0.0
        for _ in range(n):
            total += differences[rng.randrange(n)]
        estimates.append(total / n)
    return {
        "point_difference": point,
        "ci_low": percentile(estimates, alpha / 2),
        "ci_high": percentile(estimates, 1 - alpha / 2),
        "fraction_below_zero": sum(1 for e in estimates if e < 0) / resamples,
    }


def paired_block_bootstrap_difference(
    items_a: Sequence[float],
    items_b: Sequence[float],
    *,
    block_size: int,
    resamples: int,
    seed: int,
    alpha: float = 0.05,
) -> dict[str, float]:
    if len(items_a) != len(items_b) or not items_a:
        raise ValueError("paired series must be non-empty and equally sized")
    if block_size < 1:
        raise ValueError("block_size must be positive")
    differences = [a - b for a, b in zip(items_a, items_b)]
    n = len(differences)
    point = sum(differences) / n
    if block_size >= n:
        block_size = n
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        total = 0.0
        filled = 0
        while filled < n:
            start = rng.randrange(n - block_size + 1) if block_size < n else 0
            take = min(block_size, n - filled)
            total += sum(differences[start:start + take])
            filled += take
        estimates.append(total / n)
    return {
        "point_difference": point,
        "ci_low": percentile(estimates, alpha / 2),
        "ci_high": percentile(estimates, 1 - alpha / 2),
        "fraction_below_zero": sum(1 for e in estimates if e < 0) / resamples,
        "block_size": block_size,
    }
