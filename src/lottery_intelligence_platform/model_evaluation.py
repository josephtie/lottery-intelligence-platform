from __future__ import annotations

import hashlib
from collections import deque
from typing import Any
from uuid import UUID

from lottery_intelligence_platform.drift import detect_change_point
from lottery_intelligence_platform.frequency_baseline import NUMBERS_MIN
from lottery_intelligence_platform.models import (
    ModelVersion,
    NUMBER_COUNT,
    register_model_version,
    selection_model_for,
)
from lottery_intelligence_platform.null_model import mean_matches_test
from lottery_intelligence_platform.research import (
    complete_experiment,
    create_experiment,
    finish_run,
    record_metric,
    start_run,
)
from lottery_intelligence_platform.stats import benjamini_hochberg

SELECTION_MODEL_CODES = {
    "null_model_benchmark",
    "top_k_frequency",
    "rolling_frequency",
    "bayesian_shrinkage",
}


def register_candidate_models(connection: Any) -> dict[str, ModelVersion]:
    candidates = {
        "null_model_benchmark": ("BENCHMARK", {"kind": "uniform_random_pick", "seed": 2026}),
        "top_k_frequency": ("BASELINE", {"kind": "expanding_train_frequency"}),
        "rolling_frequency": ("PREDICTIVE", {"kind": "rolling_train_frequency", "window_draws": 200}),
        "bayesian_shrinkage": ("PREDICTIVE", {"kind": "dirichlet_shrinkage", "alpha": 5.0}),
        "distribution_drift": ("STATISTICAL_TEST", {"kind": "max_homogeneity_scan", "block": "month"}),
    }
    return {
        code: register_model_version(connection, code=code, family=family, definition=definition)
        for code, (family, definition) in candidates.items()
    }


def _stable_seed(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(part) for part in parts).encode("utf-8"))
    return int.from_bytes(digest.digest()[:4], "big")


def _draws_in_range(
    connection: Any,
    dataset_version_id: UUID | str,
    start_date,
    end_date,
) -> dict[str, list[tuple[Any, Any, set[int]]]]:
    rows = connection.execute(
        """SELECT dt.display_name, d.scheduled_date, dv.draw_version_id, dn.number
           FROM datasets.dataset_members m
           JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
           JOIN core.draws d ON d.draw_id = dv.draw_id
           JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
           JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
           WHERE m.dataset_version_id = %s AND dn.number_role = 'WINNING'
             AND d.scheduled_date BETWEEN %s AND %s
           ORDER BY dt.display_name, d.scheduled_date, dv.draw_version_id, dn.position""",
        (dataset_version_id, start_date, end_date),
    ).fetchall()
    by_draw: dict[Any, tuple[str, Any, set[int]]] = {}
    for draw_type, scheduled_date, draw_version_id, number in rows:
        entry = by_draw.setdefault(draw_version_id, (draw_type, scheduled_date, set()))
        entry[2].add(number)
    by_type: dict[str, list[tuple[Any, Any, set[int]]]] = {}
    for draw_version_id, (draw_type, scheduled_date, numbers) in by_draw.items():
        by_type.setdefault(draw_type, []).append((scheduled_date, draw_version_id, numbers))
    return by_type


def _draws_ordered_in_range(
    connection: Any,
    dataset_version_id: UUID | str,
    start_date,
    end_date,
) -> dict[str, list[tuple[Any, Any, list[int]]]]:
    rows = connection.execute(
        """SELECT dt.display_name, d.scheduled_date, dv.draw_version_id, dn.number
           FROM datasets.dataset_members m
           JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
           JOIN core.draws d ON d.draw_id = dv.draw_id
           JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
           JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
           WHERE m.dataset_version_id = %s AND dn.number_role = 'WINNING'
             AND d.scheduled_date BETWEEN %s AND %s
           ORDER BY dt.display_name, d.scheduled_date, dv.draw_version_id, dn.position""",
        (dataset_version_id, start_date, end_date),
    ).fetchall()
    by_draw: dict[Any, tuple[str, Any, list[int]]] = {}
    for draw_type, scheduled_date, draw_version_id, number in rows:
        entry = by_draw.setdefault(draw_version_id, (draw_type, scheduled_date, []))
        entry[2].append(number)
    by_type: dict[str, list[tuple[Any, Any, list[int]]]] = {}
    for draw_version_id, (draw_type, scheduled_date, numbers) in by_draw.items():
        by_type.setdefault(draw_type, []).append((scheduled_date, draw_version_id, numbers))
    return by_type


def evaluate_models_walkforward(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    evaluation_plan_id: UUID | str,
    top_k: int = 10,
    bh_alpha: float = 0.05,
    change_point_permutations: int = 499,
) -> dict[str, Any]:
    models = register_candidate_models(connection)
    model_definitions = {
        code: connection.execute(
            "SELECT definition FROM research.model_versions WHERE model_version_id = %s",
            (model.model_version_id,),
        ).fetchone()[0]
        for code, model in models.items()
    }
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
    hypothesis = connection.execute(
        "SELECT hypothesis_id FROM research.hypotheses WHERE code = %s",
        ("walkforward_frequency_stability_and_selection",),
    ).fetchone()

    experiment_ids: dict[str, Any] = {}
    for code, model in models.items():
        experiment = create_experiment(
            connection,
            hypothesis_id=hypothesis[0],
            dataset_version_id=dataset_version_id,
            model_version_id=model.model_version_id,
            configuration={
                "analysis": "walkforward_model_comparison",
                "model_code": code,
                "model_version": model.version,
                "evaluation_plan_code": plan[0],
                "evaluation_plan_version": plan[1],
                "top_k": top_k,
            },
        )
        experiment_ids[code] = experiment.experiment_id

    window_summaries: list[dict[str, Any]] = []
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
                    details={
                        "window_ordinal": ordinal,
                        "train_start": train_start.isoformat(),
                        "train_end": train_end.isoformat(),
                        "test_start": test_start.isoformat(),
                        "test_end": test_end.isoformat(),
                    },
                ).experiment_run_id
                for code in models
            }
            for run_id in run_ids.values():
                connection.execute(
                    "UPDATE research.experiment_runs SET evaluation_window_id = %s WHERE experiment_run_id = %s",
                    (window_id, run_id),
                )

            cell_p_values: list[float] = []
            cells: list[dict[str, Any]] = []
            for draw_type in sorted(draws_by_type):
                draws = draws_by_type[draw_type]
                train_draws = [d for d in draws if d[0] <= train_end]
                test_draws = [d for d in draws if test_start <= d[0] <= test_end]
                if not train_draws or not test_draws:
                    continue
                train_counts = [0] * NUMBER_COUNT
                for _, _, numbers in train_draws:
                    for number in numbers:
                        train_counts[number - NUMBERS_MIN] += 1

                for code in SELECTION_MODEL_CODES:
                    model = models[code]
                    definition = model_definitions[code]
                    selector = selection_model_for(code, definition)
                    if definition.get("kind") == "rolling_train_frequency":
                        history: deque[set[int]] = deque(
                            (numbers for _, _, numbers in train_draws),
                            maxlen=int(definition["window_draws"]),
                        )
                        matches = []
                        for _, _, numbers in test_draws:
                            rolling_counts = [0] * NUMBER_COUNT
                            for past in history:
                                for number in past:
                                    rolling_counts[number - NUMBERS_MIN] += 1
                            pick = selector(rolling_counts, top_k)
                            matches.append(len(pick & numbers))
                            history.append(numbers)
                    else:
                        pick = selector(train_counts, top_k)
                        matches = [len(pick & numbers) for _, _, numbers in test_draws]
                    observed_mean = sum(matches) / len(matches)
                    z, p_value, expected_mean, _ = mean_matches_test(
                        observed_mean, len(matches), top_k
                    )
                    cell_p_values.append(p_value)
                    cells.append({
                        "draw_type": draw_type,
                        "model_code": code,
                        "model_version_id": str(model.model_version_id),
                        "observed_mean_matches": observed_mean,
                        "expected_mean_matches": expected_mean,
                        "z": z,
                        "p_value": p_value,
                        "draws_evaluated": len(matches),
                        "coverage_lift": observed_mean / expected_mean,
                        "run_id": run_ids[code],
                    })

            significant = benjamini_hochberg(cell_p_values, bh_alpha)
            for cell, flag in zip(cells, significant):
                cell["lift_significant_bh"] = bool(flag)

            for cell in cells:
                record_metric(
                    connection,
                    experiment_id=experiment_ids[cell["model_code"]],
                    experiment_run_id=cell["run_id"],
                    metric_name="coverage_lift",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=cell["coverage_lift"],
                    details={
                        "draw_type": cell["draw_type"],
                        "model_code": cell["model_code"],
                        "model_version_id": cell["model_version_id"],
                        "observed_mean_matches": cell["observed_mean_matches"],
                        "expected_mean_matches": cell["expected_mean_matches"],
                        "z": cell["z"],
                        "p_value": cell["p_value"],
                        "lift_significant_bh": cell["lift_significant_bh"],
                        "draws_evaluated": cell["draws_evaluated"],
                        "metric_kind": "predictive",
                    },
                )

            for draw_type in sorted(draws_by_type):
                monthly: dict[str, list[int]] = {}
                order: list[str] = []
                for scheduled_date, _, numbers in draws_by_type[draw_type]:
                    key = f"{scheduled_date.year:04d}-{scheduled_date.month:02d}"
                    if key not in monthly:
                        monthly[key] = [0] * NUMBER_COUNT
                        order.append(key)
                    for number in numbers:
                        monthly[key][number - NUMBERS_MIN] += 1
                change_point = detect_change_point(
                    [monthly[key] for key in order],
                    permutations=change_point_permutations,
                    seed=_stable_seed(draw_type, ordinal),
                )
                if change_point is None:
                    continue
                record_metric(
                    connection,
                    experiment_id=experiment_ids["distribution_drift"],
                    experiment_run_id=run_ids["distribution_drift"],
                    metric_name="change_point_statistic",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=change_point.statistic,
                    details={
                        "draw_type": draw_type,
                        "window_ordinal": ordinal,
                        "split_month": order[change_point.split_index],
                        "degrees_of_freedom": change_point.degrees_of_freedom,
                        "permutation_p": change_point.permutation_p,
                        "permutations": change_point_permutations,
                        "test": "max_homogeneity_scan_with_block_permutation",
                        "metric_kind": "distribution",
                    },
                )

            for run_id in run_ids.values():
                finish_run(connection, experiment_run_id=run_id)
            window_summaries.append({
                "ordinal": ordinal,
                "cells": len(cells),
                "significant_lifts": sum(c["lift_significant_bh"] for c in cells),
            })

    for experiment_id in experiment_ids.values():
        complete_experiment(connection, experiment_id=experiment_id)
    return {
        "experiments": {code: str(eid) for code, eid in experiment_ids.items()},
        "windows": window_summaries,
    }
