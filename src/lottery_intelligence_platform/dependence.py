from __future__ import annotations

import math
from itertools import combinations
from typing import Sequence

# P(two specific numbers both appear in a 5/90 draw) = C(88,3)/C(90,5)
PAIR_INCLUSION_PROBABILITY = 20 / 8010


def pair_counts(draws: Sequence[set[int]]) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for numbers in draws:
        for a, b in combinations(sorted(numbers), 2):
            counts[(a, b)] = counts.get((a, b), 0) + 1
    return counts


def _log_pmf_binomial(n: int, p: float, i: int) -> float:
    return (
        math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
        + i * math.log(p) + (n - i) * math.log1p(-p)
    )


def binomial_right_tail(n: int, p: float, k: int) -> float:
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    terms = []
    peak = _log_pmf_binomial(n, p, k)
    i = k
    while i <= n:
        term = _log_pmf_binomial(n, p, i)
        if term < peak - 40 and i > (n * p) + 5:
            break
        terms.append(term)
        i += 1
    total = terms[0]
    for term in terms[1:]:
        total = math.log(math.exp(total) + math.exp(term))
    return math.exp(total)


def pair_dependence_tests(
    draws: Sequence[set[int]],
    *,
    p0: float = PAIR_INCLUSION_PROBABILITY,
) -> list[dict[str, object]]:
    n = len(draws)
    if n == 0:
        return []
    expected = n * p0
    observed = pair_counts(draws)
    cache: dict[int, float] = {}
    results = []
    for (a, b), count in observed.items():
        if count <= expected:
            continue
        if count not in cache:
            cache[count] = binomial_right_tail(n, p0, count)
        results.append({
            "pair": (a, b),
            "observed": count,
            "expected": expected,
            "lift": count / expected,
            "p_value": cache[count],
        })
    results.sort(key=lambda r: r["p_value"])
    return results
