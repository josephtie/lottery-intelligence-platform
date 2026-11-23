from __future__ import annotations

import math
import random
from typing import Callable, Sequence, TypeVar

from lottery_intelligence_platform.frequency_baseline import NUMBERS_PER_DRAW

T = TypeVar("T")


def match_pmf(pick_k: int, drawn: int = NUMBERS_PER_DRAW, population: int = 90) -> list[float]:
    if pick_k < 1 or pick_k > population:
        raise ValueError("pick_k out of range")
    total = math.comb(population, drawn)
    return [
        math.comb(pick_k, m) * math.comb(population - pick_k, drawn - m) / total
        for m in range(0, min(pick_k, drawn) + 1)
    ]


def match_moments(
    pick_k: int, drawn: int = NUMBERS_PER_DRAW, population: int = 90
) -> tuple[float, float]:
    mean = drawn * pick_k / population
    variance = (
        drawn
        * (pick_k / population)
        * (1 - pick_k / population)
        * (population - drawn)
        / (population - 1)
    )
    return mean, variance


def normal_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def mean_matches_test(
    observed_mean: float, draws: int, pick_k: int
) -> tuple[float, float, float, float]:
    if draws < 1:
        raise ValueError("draws must be positive")
    mean, variance = match_moments(pick_k)
    if variance == 0:
        return 0.0, 1.0, mean, variance
    z = (observed_mean - mean) / math.sqrt(variance / draws)
    return z, 2 * normal_sf(abs(z)), mean, variance


def permutation_p_value(
    items: Sequence[T],
    statistic: Callable[[list[T]], float],
    *,
    permutations: int,
    seed: int,
) -> tuple[float, float]:
    if permutations < 1:
        raise ValueError("permutations must be positive")
    observed = statistic(list(items))
    rng = random.Random(seed)
    extreme = 0
    for _ in range(permutations):
        shuffled = list(items)
        rng.shuffle(shuffled)
        if statistic(shuffled) >= observed:
            extreme += 1
    return (extreme + 1) / (permutations + 1), observed
