from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID

from lottery_intelligence_platform.model_evaluation import (
    _draws_in_range,
    _draws_ordered_in_range,
    _stable_seed,
)
from lottery_intelligence_platform.models import NUMBER_COUNT, register_model_version
from lottery_intelligence_platform.research import (
    complete_experiment,
    create_experiment,
    create_hypothesis,
    finish_run,
    record_finding,
    record_metric,
    start_run,
)
from lottery_intelligence_platform.strategy_lab import _top_numbers
from lottery_intelligence_platform.uncertainty import paired_bootstrap_difference

MODEL_CODES = (
    "turbo_strategy_simulator",
    "payout_sensitivity",
    "portfolio_risk",
    "strategy_benchmark",
)

MODEL_SPECS = {
    "turbo_strategy_simulator": {
        "family": "STRATEGY",
        "definition": {"kind": "per_draw_bet_ledger", "evaluator": "v3-risk"},
        "hypothesis": {
            "code": "turbo_strategy_economic_advantage",
            "title": "Turbo strategy beats an equivalent random strategy economically",
            "statement": (
                "A top-k frequency Turbo strategy produces a higher net result than "
                "an equivalent random selection strategy on strictly posterior draws "
                "under identical stake and payout assumptions."
            ),
        },
    },
    "payout_sensitivity": {
        "family": "STRATEGY",
        "definition": {"kind": "multiplier_scenario_grid", "basis": "breakeven"},
        "hypothesis": {
            "code": "payout_assumption_sensitivity",
            "title": "Profitability conclusions are robust to payout interpretation",
            "statement": (
                "The sign of the strategy's net result is unchanged across plausible "
                "payout multiplier interpretations; a conclusion that flips with the "
                "multiplier is rejected as a profit claim."
            ),
        },
    },
    "portfolio_risk": {
        "family": "STRATEGY",
        "definition": {
            "kind": "bet_ledger_risk",
            "bankroll_stakes": 100,
            "ruin_paths": 500,
        },
        "hypothesis": {
            "code": "portfolio_ruin_risk_quantified",
            "title": "Ruin risk is quantified under explicit bankroll assumptions",
            "statement": (
                "Drawdown, losing streaks, outcome variance and ruin probability are "
                "reported per draw type under an explicit starting bankroll expressed "
                "in stake units."
            ),
        },
    },
    "strategy_benchmark": {
        "family": "BENCHMARK",
        "definition": {"kind": "random_equivalent", "selection": "seeded_uniform"},
        "hypothesis": {
            "code": "strategy_outperforms_random_equivalent",
            "title": "The frequency strategy outperforms its random equivalent",
            "statement": (
                "Paired per-draw net results of the frequency strategy exceed those "
                "of seeded random picks using the same stake and payout rule."
            ),
        },
    },
}


@dataclass(frozen=True, slots=True)
class Bet:
    hit: bool
    net: float


def simulate_turbo_bets(
    test_number_sets: Sequence[set[int]],
    pick: set[int],
    *,
    stake: float,
    multiplier: float,
) -> list[Bet]:
    return [
        Bet(hit=pick <= numbers, net=(stake * multiplier - stake) if pick <= numbers else -stake)
        for numbers in test_number_sets
    ]


def equity_risk(
    bets: Sequence[Bet], *, stake: float, bankroll_stakes: float
) -> dict[str, float]:
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    streak = 0
    longest = 0
    nets = []
    for bet in bets:
        nets.append(bet.net)
        equity += bet.net
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        streak = 0 if bet.hit else streak + 1
        longest = max(longest, streak)
    mean = sum(nets) / len(nets)
    variance = sum((n - mean) ** 2 for n in nets) / len(nets)
    bankroll_peak = peak + bankroll_stakes * stake
    return {
        "max_drawdown": max_drawdown,
        "max_drawdown_bankroll_pct": max_drawdown / bankroll_peak if bankroll_peak else None,
        "longest_losing_streak": longest,
        "net_per_bet_mean": mean,
        "net_per_bet_variance": variance,
    }


def ruin_probability(
    bets: Sequence[Bet],
    *,
    bankroll: float,
    paths: int,
    seed: int,
) -> float:
    if not bets:
        raise ValueError("bets cannot be empty")
    nets = [bet.net for bet in bets]
    rng = random.Random(seed)
    ruined = 0
    for _ in range(paths):
        balance = bankroll
        for _ in range(len(nets)):
            balance += nets[rng.randrange(len(nets))]
            if balance <= 0:
                ruined += 1
                break
    return ruined / paths


def breakeven_multiplier(bets: Sequence[Bet]) -> float | None:
    hits = sum(1 for bet in bets if bet.hit)
    if hits == 0:
        return None
    return len(bets) / hits


def evaluate_strategy_risk(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    evaluation_plan_id: UUID | str,
    numbers_picked: int = 2,
    stake: float = 100.0,
    positions: int | None = None,
    payout_multipliers: dict[int, float] | None = None,
    bankroll_stakes: float = 100.0,
    ruin_paths: int = 500,
    bootstrap_resamples: int = 199,
) -> dict[str, Any]:
    multipliers = payout_multipliers or {2: 2400, 3: 800, 4: 400, 5: 240}
    multiplier = multipliers[numbers_picked]

    model_ids = {}
    for code in MODEL_CODES:
        spec = MODEL_SPECS[code]
        definition = dict(spec["definition"])
        definition["numbers_picked"] = numbers_picked
        definition["stake"] = stake
        if positions:
            definition["positions"] = positions
        if code in {"turbo_strategy_simulator", "strategy_benchmark"}:
            definition["multiplier"] = multiplier
            definition["multiplier_verification"] = (
                "VERIFIED_OFFICIAL" if positions else "UNVERIFIED"
            )
        model = register_model_version(
            connection, code=code, family=spec["family"], definition=definition
        )
        model_ids[code] = model

    windows = connection.execute(
        """SELECT evaluation_window_id, ordinal, train_start, train_end, test_start, test_end
           FROM research.evaluation_windows
           WHERE evaluation_plan_id = %s AND dataset_version_id = %s
           ORDER BY ordinal""",
        (evaluation_plan_id, dataset_version_id),
    ).fetchall()
    if not windows:
        raise ValueError("no materialized windows for this plan and dataset")
    plan = connection.execute(
        "SELECT code, version FROM research.evaluation_plans WHERE evaluation_plan_id = %s",
        (evaluation_plan_id,),
    ).fetchone()

    experiment_ids = {}
    hypotheses = {}
    for code, model in model_ids.items():
        spec = MODEL_SPECS[code]
        hypothesis = create_hypothesis(
            connection,
            code=spec["hypothesis"]["code"],
            title=spec["hypothesis"]["title"],
            statement=spec["hypothesis"]["statement"],
        )
        hypotheses[code] = hypothesis
        experiment_ids[code] = create_experiment(
            connection,
            hypothesis_id=hypothesis.hypothesis_id,
            dataset_version_id=dataset_version_id,
            model_version_id=model.model_version_id,
            configuration={
                "analysis": "turbo_strategy_risk",
                "model_code": code,
                "model_version": model.version,
                "evaluation_plan_code": plan[0],
                "evaluation_plan_version": plan[1],
                "numbers_picked": numbers_picked,
                "stake": stake,
                "positions": positions,
                "multiplier_verification": (
                    "VERIFIED_OFFICIAL" if positions else "UNVERIFIED"
                ),
            },
        ).experiment_id

    window_summaries = []
    benchmark_cells: list[dict[str, Any]] = []
    sensitivity_cells: list[dict[str, Any]] = []
    with connection.transaction():
        for window in windows:
            window_id, ordinal, train_start, train_end, test_start, test_end = window
            draws_by_type = (
                _draws_ordered_in_range(connection, dataset_version_id, train_start, test_end)
                if positions
                else _draws_in_range(connection, dataset_version_id, train_start, test_end)
            )
            run_ids = {
                code: start_run(
                    connection,
                    experiment_id=experiment_ids[code],
                    scope="OUT_OF_SAMPLE",
                    details={"window_ordinal": ordinal},
                ).experiment_run_id
                for code in MODEL_CODES
            }
            for run_id in run_ids.values():
                connection.execute(
                    "UPDATE research.experiment_runs SET evaluation_window_id = %s WHERE experiment_run_id = %s",
                    (window_id, run_id),
                )

            for draw_type in sorted(draws_by_type):
                draws = draws_by_type[draw_type]
                train_draws = [d for d in draws if d[0] <= train_end]
                test_draws = [d for d in draws if test_start <= d[0] <= test_end]
                if not train_draws or not test_draws:
                    continue
                train_counts = [0] * NUMBER_COUNT
                for _, _, numbers in train_draws:
                    for number in numbers:
                        train_counts[number - 1] += 1
                pick = _top_numbers(train_counts, numbers_picked)
                test_number_sets = [
                    set(numbers[:positions]) if positions else set(numbers)
                    for _, _, numbers in test_draws
                ]

                strategy_bets = simulate_turbo_bets(
                    test_number_sets, pick, stake=stake, multiplier=multiplier
                )
                rng = random.Random(_stable_seed("random_strategy", draw_type, ordinal))
                random_bets: list[Bet] = []
                for winning in test_number_sets:
                    random_pick = set(rng.sample(range(1, NUMBER_COUNT + 1), numbers_picked))
                    hit = random_pick <= winning
                    random_bets.append(Bet(hit=hit, net=(stake * multiplier - stake) if hit else -stake))

                benchmark_diff = paired_bootstrap_difference(
                    [b.net for b in strategy_bets],
                    [b.net for b in random_bets],
                    resamples=bootstrap_resamples,
                    seed=_stable_seed("strategy_vs_random", draw_type, ordinal),
                )
                benchmark_cells.append({"draw_type": draw_type, **benchmark_diff})

                hits = sum(1 for b in strategy_bets if b.hit)
                breakeven = breakeven_multiplier(strategy_bets)
                scenarios = {
                    "provisional": multiplier,
                    "half_breakeven": breakeven * 0.5 if breakeven else None,
                    "breakeven": breakeven,
                    "double_breakeven": breakeven * 2 if breakeven else None,
                }
                scenario_nets = {
                    name: (hits * stake * m - stake * len(test_number_sets)) if m else None
                    for name, m in scenarios.items()
                }
                risk = equity_risk(
                    strategy_bets, stake=stake, bankroll_stakes=bankroll_stakes
                )
                ruin = ruin_probability(
                    strategy_bets,
                    bankroll=bankroll_stakes * stake,
                    paths=ruin_paths,
                    seed=_stable_seed("ruin", draw_type, ordinal),
                )
                sensitivity_cells.append({
                    "draw_type": draw_type,
                    "breakeven": breakeven,
                    "provisional_net": scenario_nets["provisional"],
                    "fair_net": scenario_nets["breakeven"],
                })

                shared = {
                    "draw_type": draw_type,
                    "window_ordinal": ordinal,
                    "numbers_picked": numbers_picked,
                    "positions": positions,
                    "stake": stake,
                    "test_draws": len(test_number_sets),
                    "hits": hits,
                }
                record_metric(
                    connection,
                    experiment_id=experiment_ids["turbo_strategy_simulator"],
                    experiment_run_id=run_ids["turbo_strategy_simulator"],
                    metric_name="simulated_net_result",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=sum(b.net for b in strategy_bets),
                    details={
                        **shared, "multiplier": multiplier,
                        "payout_rule_verification": (
                            "VERIFIED_OFFICIAL" if positions else "UNVERIFIED"
                        ),
                        "selection": sorted(pick),
                        "roi": sum(b.net for b in strategy_bets) / (stake * len(test_number_sets)),
                        "metric_kind": "strategy_simulation",
                    },
                )
                record_metric(
                    connection,
                    experiment_id=experiment_ids["strategy_benchmark"],
                    experiment_run_id=run_ids["strategy_benchmark"],
                    metric_name="net_advantage_vs_random",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=benchmark_diff["point_difference"],
                    details={
                        **shared, "multiplier": multiplier,
                        "random_hits": sum(1 for b in random_bets if b.hit),
                        "ci_low": benchmark_diff["ci_low"],
                        "ci_high": benchmark_diff["ci_high"],
                        "metric_kind": "strategy_benchmark",
                    },
                )
                record_metric(
                    connection,
                    experiment_id=experiment_ids["payout_sensitivity"],
                    experiment_run_id=run_ids["payout_sensitivity"],
                    metric_name="breakeven_multiplier",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=breakeven,
                    details={
                        **shared,
                        "scenarios": scenario_nets,
                        "provisional_multiplier": multiplier,
                        "sign_flips_under_fair_odds": (
                            scenario_nets["provisional"] > 0
                            and (scenario_nets["breakeven"] or 0) <= 0
                        ) if breakeven else True,
                        "metric_kind": "payout_sensitivity",
                    },
                )
                record_metric(
                    connection,
                    experiment_id=experiment_ids["portfolio_risk"],
                    experiment_run_id=run_ids["portfolio_risk"],
                    metric_name="portfolio_risk",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=risk["max_drawdown_bankroll_pct"],
                    details={
                        **shared, "multiplier": multiplier,
                        "bankroll_stakes": bankroll_stakes,
                        "ruin_probability": ruin,
                        "ruin_paths": ruin_paths,
                        **risk,
                        "metric_kind": "portfolio_risk",
                    },
                )
            for run_id in run_ids.values():
                finish_run(connection, experiment_run_id=run_id)
            window_summaries.append({"ordinal": ordinal})

    for experiment_id in experiment_ids.values():
        complete_experiment(connection, experiment_id=experiment_id)

    fav = sum(1 for c in benchmark_cells if c["ci_low"] > 0)
    adv = sum(1 for c in benchmark_cells if c["ci_high"] < 0)
    record_finding(
        connection,
        hypothesis_id=hypotheses["strategy_benchmark"].hypothesis_id,
        experiment_id=experiment_ids["strategy_benchmark"],
        conclusion=(
            f"Frequency strategy beat the random equivalent in {fav}/"
            f"{len(benchmark_cells)} cells and lost in {adv}."
        ),
        status="SUPPORTED" if fav > adv and fav / max(1, len(benchmark_cells)) > 0.1
        else "REJECTED" if adv > fav and adv / max(1, len(benchmark_cells)) > 0.1
        else "INCONCLUSIVE",
        evidence={"cells": len(benchmark_cells), "favorable": fav, "adverse": adv},
    )
    flips = sum(1 for c in sensitivity_cells
                if c["breakeven"] is None
                or (c["provisional_net"] > 0 and (c["fair_net"] or 0) <= 0))
    record_finding(
        connection,
        hypothesis_id=hypotheses["payout_sensitivity"].hypothesis_id,
        experiment_id=experiment_ids["payout_sensitivity"],
        conclusion=(
            f"Net-result sign depends on the unverified multiplier in "
            f"{flips}/{len(sensitivity_cells)} cells; no profitability claim "
            f"stands under fair-odds assumptions."
        ),
        status="REJECTED" if flips / max(1, len(sensitivity_cells)) > 0.5 else "INCONCLUSIVE",
        evidence={"cells": len(sensitivity_cells), "sign_flip_cells": flips},
    )
    verification_note = (
        "under the official positional payout rule"
        if positions else
        "while payout rules remain UNVERIFIED"
    )
    for code in ("turbo_strategy_simulator", "portfolio_risk"):
        record_finding(
            connection,
            hypothesis_id=hypotheses[code].hypothesis_id,
            experiment_id=experiment_ids[code],
            conclusion=(
                f"Descriptive risk and simulation metrics recorded per window and "
                f"draw type {verification_note}."
            ),
            status="INCONCLUSIVE",
            evidence={"descriptive": True},
        )
    return {
        "experiments": {c: str(e) for c, e in experiment_ids.items()},
        "windows": window_summaries,
    }
