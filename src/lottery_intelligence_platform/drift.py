from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class ChangePoint:
    split_index: int
    statistic: float
    degrees_of_freedom: int
    permutation_p: float


def _homogeneity_from_totals(
    left: Sequence[int], right: Sequence[int], total_left: int, total_right: int
) -> float:
    total = total_left + total_right
    statistic = 0.0
    for count_a, count_b in zip(left, right):
        column = count_a + count_b
        if column == 0:
            continue
        expected_a = column * total_left / total
        expected_b = column * total_right / total
        statistic += (count_a - expected_a) ** 2 / expected_a
        statistic += (count_b - expected_b) ** 2 / expected_b
    return statistic


def _best_split(series: list[list[int]]) -> tuple[int, float]:
    n_periods = len(series)
    n_columns = len(series[0])
    totals = [sum(column) for column in zip(*series)]
    prefix = [[0] * n_columns for _ in range(n_periods + 1)]
    for index, counts in enumerate(series):
        row = prefix[index]
        next_row = prefix[index + 1]
        running = 0
        for column, count in enumerate(counts):
            running += count
            next_row[column] = row[column] + count
        prefix[index + 1] = next_row
    period_totals = [sum(counts) for counts in series]
    grand_total = sum(period_totals)
    cumulative = 0
    best_index = -1
    best_statistic = 0.0
    for index in range(1, n_periods):
        cumulative += period_totals[index - 1]
        total_left = cumulative
        total_right = grand_total - cumulative
        if total_left == 0 or total_right == 0:
            continue
        left = prefix[index]
        right = [totals[c] - left[c] for c in range(n_columns)]
        statistic = _homogeneity_from_totals(left, right, total_left, total_right)
        if statistic > best_statistic:
            best_statistic, best_index = statistic, index
    return best_index, best_statistic


def detect_change_point(
    period_counts: Sequence[Sequence[int]],
    *,
    permutations: int,
    seed: int,
) -> ChangePoint | None:
    periods = [list(counts) for counts in period_counts if sum(counts) > 0]
    if len(periods) < 3 or permutations < 1:
        return None
    grand_total = sum(sum(counts) for counts in periods)
    nonempty = [sum(counts) > 0 for counts in periods]
    if not all(nonempty) or grand_total == 0:
        return None

    split_index, statistic = _best_split(periods)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(permutations):
        shuffled = list(periods)
        rng.shuffle(shuffled)
        _, perm_statistic = _best_split(shuffled)
        if perm_statistic >= statistic:
            extreme += 1
    p_value = (extreme + 1) / (permutations + 1)
    return ChangePoint(split_index, statistic, len(periods[0]) - 1, p_value)
