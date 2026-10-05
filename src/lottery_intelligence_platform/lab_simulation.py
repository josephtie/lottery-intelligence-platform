"""M08 — Monte-Carlo strategy simulator.

Simulates bankroll paths for Turbo betting under the null (draws uniform —
every pick then hits with the same probability). Official LONACI rule: the
player picks 2 numbers; Turbo k wins if BOTH numbers land inside the first
k drawn positions. P(win) = C(k,2)/C(90,2) = k(k-1)/8010, which makes every
variant an ~0.60 expected-return bet.

Reports the distribution of what chance produces: final equity, ruin,
drawdown, losing streaks. Optional `hit_lift` scales the hit probability to
explore "what if a model truly overperformed by X%" — never demonstrated.

Honest framing: the simulator estimates *possible outcomes of a strategy*;
it cannot make the simulated numbers predictive.
"""

from __future__ import annotations

import random
from typing import Any

# Official verified multipliers (catalog.payout_rule_versions), keyed by
# Turbo variant = number of leading positions the 2 picked numbers must hit.
TURBO_MULTIPLIERS = {2: 2400.0, 3: 800.0, 4: 400.0, 5: 240.0}

PAIR_TOTAL = 90 * 89 // 2  # C(90,2) = 4005


def hit_probability(positions: int) -> float:
    """P(2 picked numbers both land among the first `positions` drawn)."""
    return positions * (positions - 1) / (2 * PAIR_TOTAL)


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, int(q * len(sorted_values))))
    return sorted_values[idx]


def simulate_bankroll(
    *,
    positions: int = 2,
    stake: float = 100.0,
    draws: int = 200,
    paths: int = 500,
    bankroll: float = 10_000.0,
    hit_lift: float = 1.0,
    seed: int = 0,
    multiplier: float | None = None,
) -> dict[str, Any]:
    """Simulate `paths` bankroll trajectories of `draws` Turbo bets.

    Each bet: `stake` on a 2-number pick, paid `stake * multiplier` when both
    numbers land in the first `positions` drawn. Hit probability is the
    theoretical rate (times optional `hit_lift`). Returns path summaries.
    """
    if positions not in TURBO_MULTIPLIERS and multiplier is None:
        raise ValueError(f"unknown Turbo variant: {positions}")
    mult = multiplier if multiplier is not None else TURBO_MULTIPLIERS[positions]
    p_win = min(1.0, hit_probability(positions) * hit_lift)
    win_net = stake * mult - stake
    rng = random.Random(seed)

    final_equities: list[float] = []
    max_drawdowns: list[float] = []
    longest_streaks: list[int] = []
    ruined = 0
    for _ in range(paths):
        balance = bankroll
        peak = balance
        max_dd = 0.0
        streak = longest = 0
        for _ in range(draws):
            if rng.random() < p_win:
                balance += win_net
                streak = 0
            else:
                balance -= stake
                streak += 1
                longest = max(longest, streak)
            peak = max(peak, balance)
            max_dd = max(max_dd, peak - balance)
            if balance <= 0:
                ruined += 1
                break
        final_equities.append(balance)
        max_drawdowns.append(max_dd)
        longest_streaks.append(longest)

    final_equities.sort()
    max_drawdowns.sort()
    longest_streaks.sort()
    n = len(final_equities)
    return {
        "variant": f"turbo_{positions}",
        "stake": stake,
        "multiplier": mult,
        "hit_probability": p_win,
        "hit_lift": hit_lift,
        "draws_per_path": draws,
        "paths": n,
        "initial_bankroll": bankroll,
        "expected_return_rate": mult * hit_probability(positions),
        "expected_value_per_bet": p_win * win_net - (1 - p_win) * stake,
        "final_equity": {
            "mean": sum(final_equities) / n,
            "median": _percentile(final_equities, 0.5),
            "p05": _percentile(final_equities, 0.05),
            "p95": _percentile(final_equities, 0.95),
        },
        "ruin_probability": ruined / n,
        "max_drawdown": {
            "median": _percentile(max_drawdowns, 0.5),
            "p95": _percentile(max_drawdowns, 0.95),
        },
        "longest_losing_streak": {
            "median": _percentile(longest_streaks, 0.5),
            "p95": _percentile(longest_streaks, 0.95),
        },
        "disclaimer": (
            "Simulation sous hypothèse de hasard uniforme : toute sélection "
            "de numéros a la même espérance (~60 % de retour). hit_lift > 1 "
            "explore le scénario où un modèle surperformerait réellement — "
            "jamais démontré à ce jour."
        ),
    }
