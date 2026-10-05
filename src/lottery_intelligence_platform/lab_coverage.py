"""M10 — Coverage Laboratory v2.

Builds a portfolio of `tickets` grids of `pick_size` numbers maximizing
combinatorial coverage: a first pass produces mutually disjoint tickets
(perfect matching over the 1..90 pool, optimal when k*tickets <= 90), then a
rejection-sampling pass recycles numbers while minimizing pair overlap.

Economic rules are NEVER hardcoded: the payout rule is resolved from
``catalog.payout_rule_versions`` (explicit `rule_version` selection) and the
win/settlement convention matches ``settlement.py`` — a ticket wins iff all
its numbers fall among the first `positions` drawn numbers of the official
Turbo variant (positional rule, ordered draw).

``probability_at_least_one_win`` is the headline metric:

- EXACT when computable — either tickets have size >= positions (win =
  equality, so distinct tickets / C(90, positions)), or the covered-number
  union is small enough to enumerate the winning subsets that land in it
  (hypergeometric decomposition over m = |W ∩ union|, then fraction of
  m-subsets containing a ticket).
- MONTE_CARLO otherwise, with an explicit seed, a configurable simulation
  count and a Wilson 95% interval. Monte-Carlo estimates are always labelled
  as approximations.

Honest limit, kept visible in every response: coverage reshapes the risk
across tickets — it changes P(at least one win) and variance, never the
expected value. EV_portfolio = n_tickets * EV_ticket, always.
"""

from __future__ import annotations

import math
import random
from itertools import combinations
from typing import Any

POPULATION = 90
RULE_CODE = "turbo_fixed_odds"
EXACT_ENUM_MAX = 200_000


class CoverageRuleError(ValueError):
    pass


def _comb(n: int, k: int) -> int:
    return math.comb(n, k) if 0 <= k <= n else 0


def resolve_payout_rule(
    connection: Any, rule_version: str | None = None,
) -> dict[str, Any]:
    """Load the payout rule definition from catalog.payout_rule_versions.

    `rule_version` selects the version explicitly; when omitted the most
    recently effective VERIFIED_OFFICIAL version is used. No odds, stake or
    win convention is defined here — everything comes from the catalog row.
    """
    if rule_version:
        row = connection.execute(
            """SELECT prv.version, prv.rule_definition
               FROM catalog.payout_rule_versions prv
               JOIN catalog.payout_rules pr ON pr.payout_rule_id = prv.payout_rule_id
               WHERE pr.code = %s AND prv.version = %s""",
            (RULE_CODE, rule_version),
        ).fetchone()
        if row is None:
            raise CoverageRuleError(
                f"payout rule version not found: {RULE_CODE}/{rule_version}")
    else:
        row = connection.execute(
            """SELECT prv.version, prv.rule_definition
               FROM catalog.payout_rule_versions prv
               JOIN catalog.payout_rules pr ON pr.payout_rule_id = prv.payout_rule_id
               WHERE pr.code = %s
                 AND prv.rule_definition->>'verification_status' = 'VERIFIED_OFFICIAL'
               ORDER BY prv.effective_from DESC NULLS LAST, prv.created_at DESC
               LIMIT 1""",
            (RULE_CODE,),
        ).fetchone()
        if row is None:
            raise CoverageRuleError(
                f"no verified payout rule version for {RULE_CODE}")
    version, definition = row
    definition = dict(definition)
    positions = definition.get("positions_by_variant") or {}
    multipliers = definition.get("payout_multipliers") or {}
    if not positions or not multipliers:
        raise CoverageRuleError(
            f"payout rule {RULE_CODE}/{version} lacks positions_by_variant "
            "or payout_multipliers")
    return {
        "code": RULE_CODE,
        "version": version,
        "verification_status": definition.get("verification_status"),
        "positions_by_variant": {k: int(v) for k, v in positions.items()},
        "payout_multipliers": {str(k): float(v) for k, v in multipliers.items()},
    }


# ---------------------------------------------------------------- portfolio
def _optimized_portfolio(
    n_tickets: int, pick_size: int, rng: random.Random,
) -> list[tuple[int, ...]]:
    """Pass 1: mutually disjoint k-subsets of a shuffled pool (guarantees zero
    pair overlap while k*len(tickets) <= 90). Pass 2: rejection sampling that
    accepts the candidate sharing the fewest already-covered pairs."""
    pool = list(range(1, POPULATION + 1))
    rng.shuffle(pool)
    tickets: list[tuple[int, ...]] = []
    i = 0
    while len(tickets) < n_tickets and i + pick_size <= len(pool):
        tickets.append(tuple(sorted(pool[i:i + pick_size])))
        i += pick_size

    if pick_size >= 2:
        covered_pairs: set[tuple[int, int]] = {
            pair for t in tickets for pair in combinations(t, 2)}
    else:
        covered_pairs = set()
    covered_numbers = {n for t in tickets for n in t}

    def collision(cand: tuple[int, ...]) -> int:
        if pick_size >= 2:
            return sum(1 for pair in combinations(cand, 2)
                       if pair in covered_pairs)
        return sum(1 for n in cand if n in covered_numbers)

    guard = n_tickets * 40
    while len(tickets) < n_tickets and guard > 0:
        guard -= 1
        best, best_overlap = None, None
        for _ in range(30):
            cand = tuple(sorted(rng.sample(range(1, POPULATION + 1), pick_size)))
            overlap = collision(cand)
            if overlap == 0:
                best = cand
                break
            if best_overlap is None or overlap < best_overlap:
                best, best_overlap = cand, overlap
        if best is None:
            break
        tickets.append(best)
        if pick_size >= 2:
            covered_pairs.update(combinations(best, 2))
        covered_numbers.update(best)
    return tickets


def _random_portfolio(
    n_tickets: int, pick_size: int, rng: random.Random,
) -> list[tuple[int, ...]]:
    return [tuple(sorted(rng.sample(range(1, POPULATION + 1), pick_size)))
            for _ in range(n_tickets)]


# ------------------------------------------------------------------ metrics
def _metrics(tickets: list[tuple[int, ...]]) -> dict[str, Any]:
    covered = [0] * POPULATION
    pairs: dict[tuple[int, int], int] = {}
    for t in tickets:
        for n in t:
            covered[n - 1] += 1
        for pair in combinations(t, 2):
            pairs[pair] = pairs.get(pair, 0) + 1
    mean_app = sum(covered) / POPULATION
    var_app = sum((c - mean_app) ** 2 for c in covered) / POPULATION
    overlaps = sum(c - 1 for c in pairs.values())
    return {
        "distinct_numbers": sum(1 for c in covered if c > 0),
        "distinct_pairs": len(pairs),
        "pair_overlaps": overlaps,
        "pair_overlap_mean": overlaps / len(tickets) if tickets else 0.0,
        "appearances_mean": mean_app,
        "appearances_stdev": var_app ** 0.5,
        "appearances_min": min(covered),
        "appearances_max": max(covered),
    }


# ------------------------------------------------------- P(>=1 winning grid)
def _wilson(wins: int, n: int) -> list[float]:
    z = 1.959963984540054
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [max(0.0, center - half), min(1.0, center + half)]


def _wins_zone(
    drawn_sorted: tuple[int, ...], pick_size: int,
    ticket_set: frozenset[tuple[int, ...]],
) -> bool:
    """Ticket wins iff it is a subset of the `positions` drawn numbers.
    Sorted-tuple comparison — combinations of sorted input are sorted."""
    return any(c in ticket_set
               for c in combinations(drawn_sorted, pick_size))


def probability_at_least_one_win(
    tickets: list[tuple[int, ...]], positions: int, *,
    seed: int = 0, mc_sims: int = 20_000,
) -> dict[str, Any]:
    """P(at least one ticket wins) under the positional rule:
    W = uniform `positions`-subset of 1..90; a ticket wins iff ticket ⊆ W.

    Returns method EXACT or MONTE_CARLO (labelled approximation, Wilson CI).
    """
    if not tickets:
        raise ValueError("empty portfolio")
    pick_size = len(tickets[0])
    ticket_set = frozenset(tuple(sorted(t)) for t in tickets)
    total_ways = _comb(POPULATION, positions)

    if pick_size > positions:
        return {"value": 0.0, "method": "EXACT",
                "detail": "pick_size > positions: no ticket can fit the win zone"}
    if pick_size == positions:
        value = len(ticket_set) / total_ways
        return {"value": value, "method": "EXACT",
                "detail": "win = ticket equals the win zone: "
                          f"{len(ticket_set)} distinct / C(90,{positions})"}

    union = sorted({n for t in ticket_set for n in t})
    u = len(union)
    enum_cost = sum(_comb(u, m) for m in range(pick_size, min(positions, u) + 1))
    if enum_cost <= EXACT_ENUM_MAX:
        p_any = 0.0
        for m in range(pick_size, min(positions, u) + 1):
            p_m = _comb(u, m) * _comb(POPULATION - u, positions - m) / total_ways
            wins = sum(
                1 for combo in combinations(union, m)
                if any(c in ticket_set for c in combinations(combo, pick_size))
            )
            p_any += p_m * wins / _comb(u, m)
        return {"value": p_any, "method": "EXACT",
                "detail": f"hypergeometric decomposition over |W ∩ union|, "
                          f"union={u} numbers, {enum_cost} subsets enumerated"}

    rng = random.Random(seed)
    wins = sum(
        1 for _ in range(mc_sims)
        if _wins_zone(
            tuple(sorted(rng.sample(range(1, POPULATION + 1), positions))),
            pick_size, ticket_set)
    )
    p_hat = wins / mc_sims
    return {"value": p_hat, "method": "MONTE_CARLO", "mc_sims": mc_sims,
            "mc_seed": seed, "ci95_wilson": _wilson(wins, mc_sims),
            "detail": f"approximation Monte-Carlo ({mc_sims} tirages simulés, "
                      f"seed={seed}) — pas une probabilité exacte"}


# ------------------------------------------------------------------ economics
def _economics(
    n_tickets: int, stake: float, positions: int, pick_size: int,
    multiplier: float,
) -> dict[str, Any]:
    """Same conventions as settlement: gross = stake * multiplier on a win,
    net = gross - stake. EV_portfolio = n * EV_ticket regardless of coverage.
    """
    p_win = _comb(positions, pick_size) / _comb(POPULATION, pick_size)
    ev_ticket = p_win * stake * multiplier - stake
    stake_total = n_tickets * stake
    return {
        "p_win_per_ticket": p_win,
        "gross_payout_per_win": stake * multiplier,
        "stake_total": stake_total,
        "ev_per_ticket": ev_ticket,
        "ev_portfolio": ev_ticket * n_tickets,
        "expected_loss": -ev_ticket * n_tickets,
        "rtp": p_win * multiplier,
    }


# ------------------------------------------------------------------ main API
def coverage_laboratory(
    *,
    rule: dict[str, Any],
    budget_fcfa: float | None = None,
    tickets: int | None = None,
    stake: float = 100.0,
    pick_size: int = 2,
    variant: str = "turbo_2",
    seed: int = 0,
    baselines: int = 100,
    mc_sims: int = 20_000,
) -> dict[str, Any]:
    """Optimized vs random ticket portfolios under a catalog payout rule."""
    if stake <= 0:
        raise ValueError("stake must be positive")
    if not 1 <= pick_size <= 90:
        raise ValueError("pick_size must be in 1..90")
    if variant not in rule["positions_by_variant"]:
        raise ValueError(f"unknown variant for rule {rule['code']}: {variant}")
    if tickets is None:
        if budget_fcfa is None:
            raise ValueError("budget_fcfa or tickets is required")
        tickets = int(budget_fcfa // stake)
    if tickets < 1:
        raise ValueError("budget below one stake unit (tickets = 0)")

    positions = rule["positions_by_variant"][variant]
    multiplier = rule["payout_multipliers"][str(positions)]
    stake_total = tickets * stake

    rng = random.Random(seed)
    optimized = _optimized_portfolio(tickets, pick_size, rng)
    p_any_opt = probability_at_least_one_win(
        optimized, positions, seed=seed + 7, mc_sims=mc_sims)

    brng = random.Random(seed + 1)
    baseline_sims = max(1_000, min(mc_sims, 5_000))
    pairs_list, num_list, ov_list, stdev_list, p_any_list = [], [], [], [], []
    for b in range(baselines):
        portfolio = _random_portfolio(tickets, pick_size, brng)
        m = _metrics(portfolio)
        pairs_list.append(m["distinct_pairs"])
        num_list.append(m["distinct_numbers"])
        ov_list.append(m["pair_overlap_mean"])
        stdev_list.append(m["appearances_stdev"])
        p_any_list.append(probability_at_least_one_win(
            portfolio, positions, seed=seed + 10_000 + b,
            mc_sims=baseline_sims)["value"])
    pairs_list.sort()

    opt_metrics = _metrics(optimized)
    eco = _economics(tickets, stake, positions, pick_size, multiplier)
    mean_pairs = sum(pairs_list) / baselines

    return {
        "budget_fcfa": budget_fcfa,
        "stake_unit": stake,
        "stake_total": stake_total,
        "remainder_fcfa": (budget_fcfa - stake_total)
                          if budget_fcfa is not None else None,
        "tickets": tickets,
        "pick_size": pick_size,
        "variant": variant,
        "win_zone_positions": positions,
        "payout_rule": {
            "code": rule["code"], "version": rule["version"],
            "verification_status": rule["verification_status"],
            "payout_multiplier": multiplier,
        },
        "optimized": {
            "portfolio": [list(t) for t in optimized],
            "metrics": opt_metrics,
            "probability_at_least_one_win": p_any_opt,
            "economics": eco,
        },
        "random_baseline": {
            "portfolios": baselines,
            "distinct_pairs_mean": mean_pairs,
            "distinct_pairs_max": pairs_list[-1],
            "distinct_pairs_p90": pairs_list[int(baselines * 0.9)],
            "distinct_numbers_mean": sum(num_list) / baselines,
            "pair_overlap_mean": sum(ov_list) / baselines,
            "appearances_stdev_mean": sum(stdev_list) / baselines,
            "p_at_least_one_mean": sum(p_any_list) / baselines,
            "p_at_least_one_max": max(p_any_list),
        },
        "comparison": {
            "distinct_pairs_vs_random_pct": (
                (opt_metrics["distinct_pairs"] / mean_pairs - 1) * 100
                if mean_pairs else None),
            "p_at_least_one_vs_random": (
                p_any_opt["value"] - sum(p_any_list) / baselines),
        },
        "disclaimer": (
            "Une meilleure couverture peut augmenter la probabilité d'obtenir "
            "au moins un gain, mais ne crée pas nécessairement un avantage "
            "économique. L'EV dépend des règles du jeu et reste inchangée par "
            "une simple réorganisation des tickets lorsque les tickets "
            "individuels ont la même espérance."
        ),
    }
