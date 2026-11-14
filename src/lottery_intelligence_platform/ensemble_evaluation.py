from __future__ import annotations

from typing import Any
from uuid import UUID

from lottery_intelligence_platform.calibration import probability_predictions
from lottery_intelligence_platform.calibration_evaluation import _draw_brier
from lottery_intelligence_platform.model_evaluation import (
    _draws_in_range,
    _stable_seed,
)
from lottery_intelligence_platform.models import (
    NUMBER_COUNT,
    register_model_version,
    select_uniform_reference,
)
from lottery_intelligence_platform.regime import post_change_point_draws
from lottery_intelligence_platform.research import (
    complete_experiment,
    create_experiment,
    create_hypothesis,
    finish_run,
    record_finding,
    record_metric,
    start_run,
)
from lottery_intelligence_platform.uncertainty import paired_bootstrap_difference

ENSEMBLE_MODEL_CODE = "ensemble_ablation"
ENSEMBLE_MODEL_DEFINITION = {
    "kind": "probability_mixture",
    "components": ["expanding", "bayesian", "rolling", "regime"],
    "regime": {"kind": "regime_conditioned_frequency", "alpha": 0.05},
}
ENSEMBLE_HYPOTHESIS_CODE = "ensemble_probability_advantage"
ENSEMBLE_HYPOTHESIS = {
    "code": "ensemble_probability_advantage",
    "title": "A probability mixture beats its best component",
    "statement": (
        "A uniform mixture of component probability predictors achieves a lower "
        "out-of-sample Brier score than the best single component and the null "
        "benchmark; each component contributes measurably via leave-one-out ablation."
    ),
}

RANKING_MODEL_CODE = "candidate_ranking"
RANKING_MODEL_DEFINITION = {
    "kind": "ensemble_top_k_ranking",
    "top_k": 10,
    "benchmark": "uniform_reference",
}
RANKING_HYPOTHESIS = {
    "code": "candidate_ranking_advantage",
    "title": "Ensemble ranking covers more winning numbers than random ranking",
    "statement": (
        "The ensemble's top-K number ranking covers more of the drawn numbers on "
        "strictly posterior draws than a uniform random reference ranking."
    ),
}

COMPONENT_CODES = ("expanding", "bayesian", "rolling", "regime")
TOP_K = 10


def _component_predictions(
    draws: list[tuple[Any, Any, set[int]]],
    train_draws: list[tuple[Any, Any, set[int]]],
    test_draws: list[tuple[Any, Any, set[int]]],
    *,
    change_point_permutations: int,
    seed: int,
) -> dict[str, list[list[float]]]:
    train_counts = [0] * NUMBER_COUNT
    for _, _, numbers in train_draws:
        for number in numbers:
            train_counts[number - 1] += 1
    regime_draws, _, _ = post_change_point_draws(
        train_draws, permutations=change_point_permutations, seed=seed
    )
    regime_counts = [0] * NUMBER_COUNT
    for _, _, numbers in regime_draws:
        for number in numbers:
            regime_counts[number - 1] += 1

    expanding_preds = probability_predictions(
        "top_k_frequency", train_counts, len(train_draws), {}
    )
    bayesian_preds = probability_predictions(
        "bayesian_shrinkage", train_counts, len(train_draws), {"alpha": 5.0}
    )
    regime_preds = probability_predictions(
        "top_k_frequency", regime_counts, len(regime_draws), {}
    )

    from collections import deque
    history: deque[set[int]] = deque(
        (numbers for _, _, numbers in train_draws), maxlen=200
    )
    predictions: dict[str, list[list[float]]] = {code: [] for code in COMPONENT_CODES}
    rolling_counts = [0] * NUMBER_COUNT
    for past in history:
        for number in past:
            rolling_counts[number - 1] += 1
    rolling_n = len(history)
    for _, _, numbers in test_draws:
        predictions["expanding"].append(expanding_preds)
        predictions["bayesian"].append(bayesian_preds)
        predictions["regime"].append(regime_preds)
        predictions["rolling"].append(
            probability_predictions("rolling_frequency", rolling_counts, rolling_n, {})
        )
        if rolling_n >= 200:
            removed = history.popleft()
            for number in removed:
                rolling_counts[number - 1] -= 1
        else:
            rolling_n += 1
        history.append(numbers)
        for number in numbers:
            rolling_counts[number - 1] += 1
    return predictions


def _mixture(variant_components: list[list[list[float]]]) -> list[list[float]]:
    n = len(variant_components[0])
    size = len(variant_components[0][0])
    mixed = []
    for index in range(n):
        row = [0.0] * size
        for component in variant_components:
            source = component[index]
            for j in range(size):
                row[j] += source[j]
        factor = 1 / len(variant_components)
        mixed.append([value * factor for value in row])
    return mixed


def evaluate_ensemble_and_ranking(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    evaluation_plan_id: UUID | str,
    change_point_permutations: int = 99,
    bootstrap_resamples: int = 99,
) -> dict[str, Any]:
    ensemble_model = register_model_version(
        connection, code=ENSEMBLE_MODEL_CODE, family="ENSEMBLE",
        definition=ENSEMBLE_MODEL_DEFINITION,
    )
    ranking_model = register_model_version(
        connection, code=RANKING_MODEL_CODE, family="PREDICTIVE",
        definition=RANKING_MODEL_DEFINITION,
    )
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
    for code, model, spec in (
        (ENSEMBLE_MODEL_CODE, ensemble_model, ENSEMBLE_HYPOTHESIS),
        (RANKING_MODEL_CODE, ranking_model, RANKING_HYPOTHESIS),
    ):
        hypothesis = create_hypothesis(
            connection, code=spec["code"], title=spec["title"], statement=spec["statement"]
        )
        hypotheses[code] = hypothesis
        experiment_ids[code] = create_experiment(
            connection,
            hypothesis_id=hypothesis.hypothesis_id,
            dataset_version_id=dataset_version_id,
            model_version_id=model.model_version_id,
            configuration={
                "analysis": "ensemble_ablation_and_ranking",
                "model_code": code,
                "model_version": model.version,
                "evaluation_plan_code": plan[0],
                "evaluation_plan_version": plan[1],
            },
        ).experiment_id

    window_summaries = []
    ensemble_cells: list[dict[str, Any]] = []
    ranking_cells: list[dict[str, Any]] = []
    with connection.transaction():
        for window in windows:
            window_id, ordinal, train_start, train_end, test_start, test_end = window
            draws_by_type = _draws_in_range(
                connection, dataset_version_id, train_start, test_end
            )
            run_ids = {
                code: start_run(
                    connection,
                    experiment_id=experiment_ids[code],
                    scope="OUT_OF_SAMPLE",
                    details={"window_ordinal": ordinal},
                ).experiment_run_id
                for code in experiment_ids
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
                test_number_sets = [numbers for _, _, numbers in test_draws]

                components = _component_predictions(
                    draws, train_draws, test_draws,
                    change_point_permutations=change_point_permutations,
                    seed=_stable_seed("ensemble_cp", draw_type, ordinal),
                )
                component_briers = {
                    code: [
                        _draw_brier(component[index], numbers)
                        for index, numbers in enumerate(test_number_sets)
                    ]
                    for code, component in components.items()
                }
                null_briers = [
                    _draw_brier([5 / 90] * NUMBER_COUNT, numbers)
                    for numbers in test_number_sets
                ]

                full_mixture = _mixture(list(components.values()))
                variants: dict[str, list[list[float]]] = {"full": full_mixture}
                for left_out in COMPONENT_CODES:
                    variants[f"minus_{left_out}"] = _mixture([
                        component for code, component in components.items()
                        if code != left_out
                    ])
                variant_briers = {
                    name: [
                        _draw_brier(pred, numbers)
                        for pred, numbers in zip(source, test_number_sets)
                    ]
                    for name, source in variants.items()
                }

                best_single = min(
                    component_briers, key=lambda c: sum(component_briers[c])
                )
                vs_best = paired_bootstrap_difference(
                    variant_briers["full"], component_briers[best_single],
                    resamples=bootstrap_resamples,
                    seed=_stable_seed("ens_vs_best", draw_type, ordinal),
                )
                vs_null = paired_bootstrap_difference(
                    variant_briers["full"], null_briers,
                    resamples=bootstrap_resamples,
                    seed=_stable_seed("ens_vs_null", draw_type, ordinal),
                )
                ablations = {}
                for left_out in COMPONENT_CODES:
                    ablations[left_out] = paired_bootstrap_difference(
                        variant_briers[f"minus_{left_out}"], variant_briers["full"],
                        resamples=bootstrap_resamples,
                        seed=_stable_seed("ablation", left_out, draw_type, ordinal),
                    )

                ensemble_cells.append({
                    "draw_type": draw_type,
                    "vs_best": vs_best, "vs_null": vs_null,
                })
                record_metric(
                    connection,
                    experiment_id=experiment_ids[ENSEMBLE_MODEL_CODE],
                    experiment_run_id=run_ids[ENSEMBLE_MODEL_CODE],
                    metric_name="ensemble_brier",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=sum(variant_briers["full"]) / len(variant_briers["full"]),
                    details={
                        "draw_type": draw_type,
                        "window_ordinal": ordinal,
                        "best_single_component": best_single,
                        "advantage_vs_best_single": vs_best,
                        "advantage_vs_null": vs_null,
                        "ablation_contributions": {
                            code: ablations[code] for code in COMPONENT_CODES
                        },
                        "component_briers": {
                            code: sum(b) / len(b)
                            for code, b in component_briers.items()
                        },
                        "test_draws": len(test_draws),
                        "metric_kind": "ensemble",
                    },
                )

                # --- candidate ranking: ensemble top-K vs random reference ---
                # Ranking uses predictions for the first test draw, which depend
                # only on training history (the rolling component has not yet
                # consumed any test outcome).
                ensemble_ranked = [
                    index + 1 for index, _ in sorted(
                        enumerate(full_mixture[0]),
                        key=lambda item: (-item[1], item[0]),
                    )
                ][:TOP_K]
                null_picks = select_uniform_reference(
                    TOP_K, seed=_stable_seed("rank_null", draw_type, ordinal)
                )
                ens_set = set(ensemble_ranked)
                ens_hits = [len(numbers & ens_set) for numbers in test_number_sets]
                null_hits = [len(numbers & null_picks) for numbers in test_number_sets]
                ranking_diff = paired_bootstrap_difference(
                    ens_hits, null_hits,
                    resamples=bootstrap_resamples,
                    seed=_stable_seed("rank_adv", draw_type, ordinal),
                )
                expected = TOP_K * 5 / 90
                ranking_cells.append({"draw_type": draw_type, **ranking_diff})
                record_metric(
                    connection,
                    experiment_id=experiment_ids[RANKING_MODEL_CODE],
                    experiment_run_id=run_ids[RANKING_MODEL_CODE],
                    metric_name="candidate_ranking_hits",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=sum(ens_hits) / len(ens_hits),
                    details={
                        "draw_type": draw_type,
                        "window_ordinal": ordinal,
                        "top_k": TOP_K,
                        "expected_hits_uniform": expected,
                        "coverage_lift": (sum(ens_hits) / len(ens_hits)) / expected,
                        "advantage_vs_null": ranking_diff,
                        "test_draws": len(test_draws),
                        "metric_kind": "ranking",
                    },
                )
            for run_id in run_ids.values():
                finish_run(connection, experiment_run_id=run_id)
            window_summaries.append({"ordinal": ordinal})

    for experiment_id in experiment_ids.values():
        complete_experiment(connection, experiment_id=experiment_id)

    vs_best_fav = sum(1 for c in ensemble_cells if c["vs_best"]["ci_high"] < 0)
    vs_best_adv = sum(1 for c in ensemble_cells if c["vs_best"]["ci_low"] > 0)
    vs_null_fav = sum(1 for c in ensemble_cells if c["vs_null"]["ci_high"] < 0)
    vs_null_adv = sum(1 for c in ensemble_cells if c["vs_null"]["ci_low"] > 0)
    total = max(1, len(ensemble_cells))
    record_finding(
        connection,
        hypothesis_id=hypotheses[ENSEMBLE_MODEL_CODE].hypothesis_id,
        experiment_id=experiment_ids[ENSEMBLE_MODEL_CODE],
        conclusion=(
            f"Ensemble beat best component in {vs_best_fav}/{total} cells "
            f"(worse in {vs_best_adv}); vs null: {vs_null_fav} better, "
            f"{vs_null_adv} worse."
        ),
        status="SUPPORTED" if vs_best_fav > vs_best_adv and vs_best_fav / total > 0.1
        else "REJECTED" if vs_null_adv > vs_null_fav and vs_null_adv / total > 0.1
        else "INCONCLUSIVE",
        evidence={
            "cells": len(ensemble_cells),
            "vs_best_favorable": vs_best_fav, "vs_best_adverse": vs_best_adv,
            "vs_null_favorable": vs_null_fav, "vs_null_adverse": vs_null_adv,
        },
    )
    rank_fav = sum(1 for c in ranking_cells if c["ci_low"] > 0)
    rank_adv = sum(1 for c in ranking_cells if c["ci_high"] < 0)
    record_finding(
        connection,
        hypothesis_id=hypotheses[RANKING_MODEL_CODE].hypothesis_id,
        experiment_id=experiment_ids[RANKING_MODEL_CODE],
        conclusion=(
            f"Ensemble top-{TOP_K} covered more winners than random in "
            f"{rank_fav}/{len(ranking_cells)} cells (fewer in {rank_adv})."
        ),
        status="SUPPORTED" if rank_fav > rank_adv and rank_fav / max(1, len(ranking_cells)) > 0.1
        else "REJECTED" if rank_adv > rank_fav and rank_adv / max(1, len(ranking_cells)) > 0.1
        else "INCONCLUSIVE",
        evidence={
            "cells": len(ranking_cells),
            "favorable": rank_fav, "adverse": rank_adv,
        },
    )
    return {
        "experiments": {c: str(e) for c, e in experiment_ids.items()},
        "windows": window_summaries,
    }
