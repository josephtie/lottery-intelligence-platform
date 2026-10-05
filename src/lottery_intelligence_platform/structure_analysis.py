"""Structure analysis — M04 null reference, M05 serial dependence, M06 change point.

All three answer "do the draws deviate from the reference rules of chance?"
using the same inputs: the chronological sequence of winning sets for one
draw type. Everything is computed on VALID versions only and is read-only.
"""

from __future__ import annotations

import math
import random
from typing import Any, Sequence

from lottery_intelligence_platform.drift import detect_change_point
from lottery_intelligence_platform.frequency_baseline import NUMBERS_PER_DRAW
from lottery_intelligence_platform.models import NUMBER_COUNT, NUMBERS_MIN
from lottery_intelligence_platform.null_model import normal_sf
from lottery_intelligence_platform.regime import monthly_period_counts

POPULATION = NUMBER_COUNT  # 90


def _chi_square_counts(counts: Sequence[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    expected = total / len(counts)
    return sum((c - expected) ** 2 / expected for c in counts)


def null_reference(
    draws: Sequence[set[int]],
    *,
    simulations: int = 199,
    seed: int = 0,
) -> dict[str, Any]:
    """M04 — compare observed statistics to simulated reference draws.

    Simulates `simulations` histories of the same length under the rules
    (uniform `NUMBERS_PER_DRAW`-of-`POPULATION`), computes each simulated
    chi-square frequency statistic, and returns where the observed value
    falls inside that reference distribution (empirical p-value).
    """
    n = len(draws)
    if n < 10:
        return {"insufficient": True, "draws": n}
    counts = [0] * POPULATION
    for numbers in draws:
        for number in numbers:
            counts[number - NUMBERS_MIN] += 1
    observed = _chi_square_counts(counts)
    rng = random.Random(seed)
    sims: list[float] = []
    for _ in range(simulations):
        sim_counts = [0] * POPULATION
        for _ in range(n):
            for number in rng.sample(range(POPULATION), NUMBERS_PER_DRAW):
                sim_counts[number] += 1
        sims.append(_chi_square_counts(sim_counts))
    extreme = sum(1 for s in sims if s >= observed)
    empirical_p = (extreme + 1) / (simulations + 1)
    sims.sort()
    return {
        "insufficient": False,
        "draws": n,
        "observed_chi_square": observed,
        "simulations": simulations,
        "simulated_median": sims[len(sims) // 2],
        "simulated_p05": sims[int(0.05 * len(sims))],
        "simulated_p95": sims[int(0.95 * len(sims))],
        "empirical_p": empirical_p,
        "compatible_with_chance": empirical_p >= 0.05,
    }


def serial_dependence(
    draws: Sequence[set[int]],
    *,
    permutations: int = 199,
    seed: int = 0,
) -> dict[str, Any]:
    """M05 — does draw t-1 carry information about draw t?

    Two complementary tests on consecutive draws (chronological order):

    1. Overlap test: |A_t ∩ A_{t-1}| vs the hypergeometric expectation
       (mean = K²/N). A permutation test shuffles the draw order to destroy
       any serial structure and gives an empirical p-value.
    2. Pooled transition independence: aggregate 2×2 counts
       (present/absent at t-1 × present/absent at t) over all numbers and
       consecutive pairs → chi-square independence, df = 1.
    """
    n = len(draws)
    if n < 20:
        return {"insufficient": True, "draws": n}
    ordered = [set(d) for d in draws]
    overlaps = [len(ordered[i] & ordered[i - 1]) for i in range(1, n)]
    k = NUMBERS_PER_DRAW
    expected = k * k / POPULATION
    variance = k * (k / POPULATION) * (1 - k / POPULATION) * (POPULATION - k) / (POPULATION - 1)
    observed_mean = sum(overlaps) / len(overlaps)
    z = ((observed_mean - expected) / math.sqrt(variance / len(overlaps))
         if variance else 0.0)

    rng = random.Random(seed)
    extreme = 0
    for _ in range(permutations):
        shuffled = ordered[:]
        rng.shuffle(shuffled)
        perm_mean = sum(
            len(shuffled[i] & shuffled[i - 1]) for i in range(1, n)
        ) / (n - 1)
        if abs(perm_mean - expected) >= abs(observed_mean - expected):
            extreme += 1
    permutation_p = (extreme + 1) / (permutations + 1)

    both = only_prev = only_curr = neither = 0
    for i in range(1, n):
        union = ordered[i] | ordered[i - 1]
        inter = len(ordered[i] & ordered[i - 1])
        both += inter
        only_prev += len(ordered[i - 1]) - inter
        only_curr += len(ordered[i]) - inter
        neither += POPULATION - len(union)
    total = both + only_prev + only_curr + neither
    row1, row2 = both + only_curr, only_prev + neither
    col1, col2 = both + only_prev, only_curr + neither
    chi2 = 0.0
    for obs, r, c in ((both, row1, col1), (only_curr, row1, col2),
                      (only_prev, row2, col1), (neither, row2, col2)):
        exp = r * c / total if total else 0.0
        if exp > 0:
            chi2 += (obs - exp) ** 2 / exp
    return {
        "insufficient": False,
        "draws": n,
        "consecutive_pairs": n - 1,
        "overlap_mean": observed_mean,
        "overlap_expected": expected,
        "overlap_z": z,
        "overlap_p_value": 2 * normal_sf(abs(z)),
        "overlap_permutation_p": permutation_p,
        "stay_rate": both / (both + only_curr) if (both + only_curr) else None,
        "enter_rate": both / (both + only_prev) if (both + only_prev) else None,
        "independence_chi2": chi2,
        "independence_p_value": math.erfc(math.sqrt(chi2 / 2)),  # chi2 sf, df=1
        "serial_dependence_detected": permutation_p < 0.05,
    }


def change_point(
    draws: Sequence[tuple[Any, set[int]]],
    *,
    permutations: int = 199,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """M06 — distribution break detection on monthly frequency counts.

    `draws` is a chronological sequence of (scheduled_date, numbers).
    A detected point is a *candidate* — rule changes, collection gaps or
    noise can produce the same signal; it never proves a regime change.
    """
    keyed = [(d, None, s) for d, s in draws]
    periods = [(key, counts) for key, counts in monthly_period_counts(keyed)
               if sum(counts) > 0]
    if len(periods) < 3:
        return {"insufficient": True, "months": len(periods)}
    result = detect_change_point(
        [counts for _, counts in periods], permutations=permutations, seed=seed)
    if result is None:
        return {"insufficient": True, "months": len(periods)}
    cutoff = periods[result.split_index][0]
    return {
        "insufficient": False,
        "months": len(periods),
        "candidate_split_period": f"{cutoff[0]:04d}-{cutoff[1]:02d}",
        "statistic": result.statistic,
        "degrees_of_freedom": result.degrees_of_freedom,
        "permutation_p": result.permutation_p,
        "change_detected": result.permutation_p <= alpha,
    }
