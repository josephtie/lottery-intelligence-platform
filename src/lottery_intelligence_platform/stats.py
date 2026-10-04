from __future__ import annotations

import math
from typing import Sequence

_ITERATIONS = 200
_EPSILON = 1e-14


def regularized_gamma_q(a: float, x: float) -> float:
    if a <= 0 or x < 0:
        raise ValueError("a must be positive and x non-negative")
    if x == 0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gamma_series_p(a, x)
    return _gamma_fraction_q(a, x)


def chi_square_sf(statistic: float, degrees_of_freedom: int | float) -> float:
    if statistic < 0:
        raise ValueError("chi-square statistic cannot be negative")
    if degrees_of_freedom <= 0:
        raise ValueError("degrees_of_freedom must be positive")
    return regularized_gamma_q(degrees_of_freedom / 2.0, statistic / 2.0)


def _gamma_series_p(a: float, x: float) -> float:
    term = 1.0 / a
    total = term
    ap = a
    for _ in range(_ITERATIONS):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) < abs(total) * _EPSILON:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_fraction_q(a: float, x: float) -> float:
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b if b != 0 else tiny
    h = d
    for i in range(1, _ITERATIONS + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPSILON:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def benjamini_hochberg(p_values: Sequence[float], alpha: float) -> list[bool]:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    indexed = sorted(enumerate(p_values), key=lambda item: item[1])
    significant = [False] * len(p_values)
    m = len(indexed)
    threshold_rank = 0
    for rank, (_, p_value) in enumerate(indexed, start=1):
        if p_value <= rank / m * alpha:
            threshold_rank = rank
    for rank, (index, _) in enumerate(indexed, start=1):
        if rank <= threshold_rank:
            significant[index] = True
    return significant


def chi_square_uniform(observed: Sequence[int]) -> tuple[float, int, float]:
    if not observed:
        raise ValueError("observed cannot be empty")
    expected = sum(observed) / len(observed)
    if expected <= 0:
        raise ValueError("observed counts sum to zero")
    statistic = sum((value - expected) ** 2 / expected for value in observed)
    df = len(observed) - 1
    return statistic, df, expected


def chi_square_homogeneity(
    sample_a: Sequence[int], sample_b: Sequence[int]
) -> tuple[float, int]:
    if len(sample_a) != len(sample_b) or not sample_a:
        raise ValueError("samples must be non-empty and equally sized")
    total_a = sum(sample_a)
    total_b = sum(sample_b)
    if total_a == 0 or total_b == 0:
        raise ValueError("samples cannot be empty")
    total = total_a + total_b
    statistic = 0.0
    for count_a, count_b in zip(sample_a, sample_b):
        column_total = count_a + count_b
        if column_total == 0:
            continue
        expected_a = column_total * total_a / total
        expected_b = column_total * total_b / total
        statistic += (count_a - expected_a) ** 2 / expected_a
        statistic += (count_b - expected_b) ** 2 / expected_b
    return statistic, len(sample_a) - 1
