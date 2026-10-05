"""M10 — Coverage optimizer.

Given a budget of `tickets` grids of `pick_size` numbers, build a portfolio
maximizing coverage: distinct numbers covered uniformly (each number appears
~ tickets*pick_size/90 times) and distinct pairs maximized. Compared against
random portfolios of the same size (seeded baseline).

Honest limit: better coverage of the combination space does NOT increase the
probability of winning — it spreads risk across tickets.
"""

from __future__ import annotations

import random
from itertools import combinations
from typing import Any

POPULATION = 90


def _greedy_ticket(
    covered: list[int], used_pairs: set[tuple[int, int]],
    rng: random.Random, pick_size: int,
) -> list[int]:
    """Pick `pick_size` numbers: minimize per-number coverage count, then
    avoid pairs already used."""
    order = sorted(range(1, POPULATION + 1), key=lambda n: (covered[n - 1], rng.random()))
    # greedy build: add least-covered number that creates the fewest reused pairs
    ticket: list[int] = []
    candidates = order
    for _ in range(pick_size):
        best, best_key = None, None
        for n in candidates:
            reused = sum(1 for m in ticket if (min(n, m), max(n, m)) in used_pairs)
            key = (covered[n - 1], reused, rng.random())
            if best_key is None or key < best_key:
                best, best_key = n, key
        ticket.append(best)
        candidates = [c for c in candidates if c != best]
    for n in ticket:
        covered[n - 1] += 1
    for a, b in combinations(sorted(ticket), 2):
        used_pairs.add((a, b))
    return sorted(ticket)


def _portfolio_metrics(tickets: list[list[int]]) -> dict[str, Any]:
    covered = [0] * POPULATION
    pairs: set[tuple[int, int]] = set()
    for t in tickets:
        for n in t:
            covered[n - 1] += 1
        pairs.update(combinations(sorted(t), 2))
    appearances = [c for c in covered]
    mean_app = sum(appearances) / POPULATION
    var_app = sum((a - mean_app) ** 2 for a in appearances) / POPULATION
    return {
        "distinct_numbers": sum(1 for c in covered if c > 0),
        "distinct_pairs": len(pairs),
        "appearances_mean": mean_app,
        "appearances_stdev": var_app ** 0.5,
        "appearances_min": min(appearances),
        "appearances_max": max(appearances),
    }


def coverage_portfolio(
    *,
    tickets: int,
    pick_size: int = 2,
    baselines: int = 100,
    seed: int = 0,
) -> dict[str, Any]:
    """Greedy balanced portfolio + comparison vs `baselines` random portfolios."""
    if tickets < 1 or pick_size < 1:
        raise ValueError("tickets and pick_size must be positive")
    rng = random.Random(seed)
    covered = [0] * POPULATION
    used_pairs: set[tuple[int, int]] = set()
    portfolio = [
        _greedy_ticket(covered, used_pairs, rng, pick_size)
        for _ in range(tickets)
    ]
    metrics = _portfolio_metrics(portfolio)

    # null baseline: uniform random tickets, same count/size
    baseline_pairs: list[float] = []
    baseline_stdev: list[float] = []
    brng = random.Random(seed + 1)
    for _ in range(baselines):
        random_portfolio = [
            sorted(brng.sample(range(1, POPULATION + 1), pick_size))
            for _ in range(tickets)
        ]
        m = _portfolio_metrics(random_portfolio)
        baseline_pairs.append(m["distinct_pairs"])
        baseline_stdev.append(m["appearances_stdev"])
    return {
        "tickets": tickets,
        "pick_size": pick_size,
        "portfolio": portfolio,
        "metrics": metrics,
        "random_baseline": {
            "portfolios": baselines,
            "distinct_pairs_mean": sum(baseline_pairs) / baselines,
            "distinct_pairs_max": max(baseline_pairs),
            "appearances_stdev_mean": sum(baseline_stdev) / baselines,
        },
        "disclaimer": (
            "La couverture répartit le risque entre les tickets ; elle "
            "n'augmente pas la probabilité de gain de chaque grille."
        ),
    }
