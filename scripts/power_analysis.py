#!/usr/bin/env python3
"""Per-draw-type statistical power analysis.

Answers, for every draw type:
  1. uniformity: chi-square GOF p-value against the 90-number uniform, and the
     minimum detectable effect (Cohen's w) at alpha=0.05 / power=0.8 given the
     type's sample size;
  2. prospective: number of Turbo-2 predictions needed to detect a hit rate
     double the baseline 1/4005 with 80% power (normal approximation).

Pure stdlib statistics (regularized incomplete gamma + Poisson-mixture
noncentral chi-square) — no scipy dependency.

Usage: PYTHONPATH=src python scripts/power_analysis.py
"""

from __future__ import annotations

import math
import os
import sys

import psycopg

ITMAX = 200
EPS = 3.0e-12
FPMIN = 1.0e-300
K_CATEGORIES = 90
NUMBERS_PER_DRAW = 5
ALPHA = 0.05
TARGET_POWER = 0.80
TURBO2_BASELINE = 1.0 / 4005.0  # both picks inside first 2 positions


def _gammln(x: float) -> float:
    return math.lgamma(x)


def _gcf(a: float, x: float) -> float:
    b, c, d = x + 1.0 - a, 1.0 / FPMIN, 1.0 / (x + 1.0 - a + FPMIN)
    h = d
    for i in range(1, ITMAX + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < FPMIN:
            d = FPMIN
        c = b + an / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def gamma_p(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x)."""
    if x <= 0:
        return 0.0
    if x < a + 1.0:
        ap, total, delta = a, 1.0 / a, 1.0 / a
        for _ in range(ITMAX):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * EPS:
                break
        return total * math.exp(-x + a * math.log(x) - _gammln(a))
    return 1.0 - _gcf(a, x) * math.exp(-x + a * math.log(x) - _gammln(a))


def chi2_cdf(x: float, df: float) -> float:
    return gamma_p(df / 2.0, x / 2.0)


def chi2_ppf(p: float, df: float) -> float:
    lo, hi = 0.0, df + 10.0 * math.sqrt(2.0 * df) + 100.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if chi2_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def ncx2_cdf(x: float, df: float, lam: float) -> float:
    """Noncentral chi-square CDF as a Poisson mixture of central chi-squares."""
    if lam <= 0:
        return chi2_cdf(x, df)
    half = lam / 2.0
    # sum j around the Poisson mean for numerical stability
    log_w = -half
    j_start = max(0, int(half - 10.0 * math.sqrt(max(half, 1.0))))
    for j in range(j_start):
        log_w += math.log(half) - math.log(j + 1)
    total, j = 0.0, j_start
    while True:
        w = math.exp(log_w) if log_w > -745 else 0.0
        total += w * chi2_cdf(x, df + 2.0 * j)
        log_w += math.log(half) - math.log(j + 1)
        j += 1
        if j > j_start + 60 + 20 * math.sqrt(max(half, 1.0)) and w < 1e-12:
            break
        if j > 2000:
            break
    return min(total, 1.0)


def required_lambda(df: float, alpha: float, power: float) -> float:
    """Bisection: noncentrality giving `power` at the `alpha` critical value."""
    crit = chi2_ppf(1.0 - alpha, df)
    lo, hi = 0.0, 4.0 * df + 200.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if 1.0 - ncx2_cdf(crit, df, mid) < power:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def main() -> int:
    conninfo = os.environ.get(
        "LOTTERY_DB_DSN",
        "host=localhost port=5432 dbname=lottery_platform user=directus",
    )
    lam = required_lambda(K_CATEGORIES - 1, ALPHA, TARGET_POWER)

    # Turbo-2 prospective power: n to detect p = 2*p0 at alpha .05, power .8
    p0, p1 = TURBO2_BASELINE, 2.0 * TURBO2_BASELINE
    z_a, z_b = 1.6449, 0.8416  # one-sided .05 / .8
    n_turbo2 = math.ceil(
        ((z_a * math.sqrt(p0 * (1 - p0)) + z_b * math.sqrt(p1 * (1 - p1))) / (p1 - p0)) ** 2
    )

    print(f"{'draw_type':<22} {'draws':>6} {'numbers':>8} {'chi2':>8} "
          f"{'p_value':>8} {'w_obs':>7} {'w_mde':>7} {'years@MDE':>9}")
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            """SELECT dt.display_name, n.number, count(*)
               FROM core.draws d
               JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
               JOIN (SELECT DISTINCT ON (draw_id) draw_id, draw_version_id
                     FROM core.draw_versions ORDER BY draw_id, version_number DESC) v
                 ON v.draw_id = d.draw_id
               JOIN core.draw_numbers n ON n.draw_version_id = v.draw_version_id
                 AND n.number_role = 'WINNING'
               WHERE d.status IN ('FROZEN', 'SETTLED')
               GROUP BY dt.display_name, n.number
               ORDER BY dt.display_name"""
        ).fetchall()

    by_type: dict[str, dict[int, int]] = {}
    for name, number, cnt in rows:
        by_type.setdefault(name, {})[number] = cnt

    report = []
    for name in sorted(by_type):
        counts = by_type[name]
        total = sum(counts.values())
        n_draws = total // NUMBERS_PER_DRAW
        if total < NUMBERS_PER_DRAW:
            continue
        expected = total / K_CATEGORIES
        chi2 = sum((counts.get(k, 0) - expected) ** 2 / expected for k in range(1, K_CATEGORIES + 1))
        p_value = 1.0 - chi2_cdf(chi2, K_CATEGORIES - 1)
        w_obs = math.sqrt(chi2 / total)
        w_mde = math.sqrt(lam / total)
        # draws needed to detect w = 0.05: n = lam / w^2
        n_needed = lam / (0.05 ** 2) / NUMBERS_PER_DRAW
        report.append((name, n_draws, total, chi2, p_value, w_obs, w_mde, n_needed))

    for name, n_draws, total, chi2, p_value, w_obs, w_mde, n_needed in report:
        flag = " <-- SIG" if p_value < ALPHA else ""
        print(f"{name:<22} {n_draws:>6} {total:>8} {chi2:>8.1f} "
              f"{p_value:>8.4f} {w_obs:>7.4f} {w_mde:>7.4f} {n_needed:>9.0f}{flag}")

    print(f"\nrequired noncentrality (df={K_CATEGORIES-1}, a={ALPHA}, power={TARGET_POWER}): {lam:.1f}")
    print(f"draws needed to detect w=0.05 (5% relative deviation): {lam/(0.05**2)/NUMBERS_PER_DRAW:.0f}")
    print(f"Turbo-2 predictions needed to detect 2x baseline ({p0:.6f} -> {p1:.6f}): {n_turbo2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
