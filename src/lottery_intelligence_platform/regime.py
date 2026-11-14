from __future__ import annotations

from typing import Any, Sequence

from lottery_intelligence_platform.drift import ChangePoint, detect_change_point
from lottery_intelligence_platform.models import NUMBER_COUNT


def monthly_period_counts(
    draws: Sequence[tuple[Any, Any, set[int]]],
) -> list[tuple[tuple[int, int], list[int]]]:
    buckets: dict[tuple[int, int], list[int]] = {}
    for scheduled_date, _, numbers in draws:
        key = (scheduled_date.year, scheduled_date.month)
        bucket = buckets.setdefault(key, [0] * NUMBER_COUNT)
        for number in numbers:
            bucket[number - 1] += 1
    return [(key, buckets[key]) for key in sorted(buckets)]


def regime_change_point(
    draws: Sequence[tuple[Any, Any, set[int]]],
    *,
    permutations: int,
    seed: int,
    alpha: float = 0.05,
) -> ChangePoint | None:
    periods = [(key, counts) for key, counts in monthly_period_counts(draws) if sum(counts) > 0]
    result = detect_change_point(
        [counts for _, counts in periods], permutations=permutations, seed=seed
    )
    if result is None or result.permutation_p > alpha:
        return None
    return result


def post_change_point_draws(
    draws: Sequence[tuple[Any, Any, set[int]]],
    *,
    permutations: int,
    seed: int,
    alpha: float = 0.05,
) -> tuple[list[tuple[Any, Any, set[int]]], ChangePoint | None, tuple[int, int] | None]:
    periods = [(key, counts) for key, counts in monthly_period_counts(draws) if sum(counts) > 0]
    if len(periods) < 3:
        return list(draws), None, None
    result = detect_change_point(
        [counts for _, counts in periods], permutations=permutations, seed=seed
    )
    if result is None or result.permutation_p > alpha:
        return list(draws), None, None
    cutoff_period = periods[result.split_index][0]
    retained = [
        draw for draw in draws
        if (draw[0].year, draw[0].month) >= cutoff_period
    ]
    return retained, result, cutoff_period
