from __future__ import annotations

import math
from collections import deque
from typing import Any, Sequence
from uuid import UUID

from lottery_intelligence_platform.calibration import (
    clip_probability,
    expected_calibration_error,
    probability_predictions,
    reliability_bins,
)
from lottery_intelligence_platform.frequency_baseline import NUMBERS_MIN
from lottery_intelligence_platform.model_evaluation import (
    SELECTION_MODEL_CODES,
    _draws_in_range,
    _stable_seed,
    register_candidate_models,
)
from lottery_intelligence_platform.models import NUMBER_COUNT
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

CALIBRATION_HYPOTHESIS_CODE = "probability_calibration_benchmark"
CALIBRATION_HYPOTHESIS_TITLE = "Models produce calibrated probabilities beating the null benchmark"
CALIBRATION_HYPOTHESIS_STATEMENT = (
    "Per-number occurrence probabilities predicted from training frequencies are "
    "calibrated and achieve a lower Brier score than the uniform null benchmark "
    "on strictly posterior draws."
)


def _draw_brier(predictions: Sequence[float], winning: set[int]) -> float:
    total = 0.0
    for index, p in enumerate(predictions):
        y = 1.0 if index + NUMBERS_MIN in winning else 0.0
        total += (p - y) ** 2
    return total / len(predictions)


def _draw_log_loss(predictions: Sequence[float], winning: set[int]) -> float:
    total = 0.0
    for index, p in enumerate(predictions):
        clipped = clip_probability(p)
        if index + NUMBERS_MIN in winning:
            total -= math.log(clipped)
        else:
            total -= math.log(1 - clipped)
    return total / len(predictions)


def evaluate_calibration_walkforward(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    evaluation_plan_id: UUID | str,
    bh_alpha: float = 0.05,
    bootstrap_resamples: int = 499,
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
    plan = connection.execute(
        "SELECT code, version FROM research.evaluation_plans WHERE evaluation_plan_id = %s",
        (evaluation_plan_id,),
    ).fetchone()

    hypothesis = create_hypothesis(
        connection,
        code=CALIBRATION_HYPOTHESIS_CODE,
        title=CALIBRATION_HYPOTHESIS_TITLE,
        statement=CALIBRATION_HYPOTHESIS_STATEMENT,
    )
    experiment_ids = {}
    for code in SELECTION_MODEL_CODES:
        experiment = create_experiment(
            connection,
            hypothesis_id=hypothesis.hypothesis_id,
            dataset_version_id=dataset_version_id,
            model_version_id=models[code].model_version_id,
            configuration={
                "analysis": "probability_calibration",
                "model_code": code,
                "model_version": models[code].version,
                "evaluation_plan_code": plan[0],
                "evaluation_plan_version": plan[1],
            },
        )
        experiment_ids[code] = experiment.experiment_id

    window_summaries = []
    all_advantage_cells = []
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
                for code in SELECTION_MODEL_CODES
            }
            for run_id in run_ids.values():
                connection.execute(
                    "UPDATE research.experiment_runs SET evaluation_window_id = %s WHERE experiment_run_id = %s",
                    (window_id, run_id),
                )

            advantage_cells = []
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

                cell_scores: dict[str, dict[str, Any]] = {}
                for code in SELECTION_MODEL_CODES:
                    definition = model_definitions[code]
                    if definition.get("kind") == "rolling_train_frequency":
                        history: deque[set[int]] = deque(
                            (numbers for _, _, numbers in train_draws),
                            maxlen=int(definition["window_draws"]),
                        )
                        briers, log_losses, all_preds, all_outcomes = [], [], [], []
                        for _, _, numbers in test_draws:
                            rolling_counts = [0] * NUMBER_COUNT
                            for past in history:
                                for number in past:
                                    rolling_counts[number - NUMBERS_MIN] += 1
                            preds = probability_predictions(
                                code, rolling_counts, len(history), definition
                            )
                            briers.append(_draw_brier(preds, numbers))
                            log_losses.append(_draw_log_loss(preds, numbers))
                            all_preds.extend(preds)
                            all_outcomes.extend(1 if index + NUMBERS_MIN in numbers else 0
                                                for index in range(NUMBER_COUNT))
                            history.append(numbers)
                    else:
                        preds = probability_predictions(
                            code, train_counts, len(train_draws), definition
                        )
                        briers = [_draw_brier(preds, numbers) for _, _, numbers in test_draws]
                        log_losses = [_draw_log_loss(preds, numbers) for _, _, numbers in test_draws]
                        all_preds = preds * len(test_draws)
                        all_outcomes = [
                            y for _, _, numbers in test_draws
                            for y in (1 if index + NUMBERS_MIN in numbers else 0
                                      for index in range(NUMBER_COUNT))
                        ]
                    reliability = reliability_bins(all_preds, all_outcomes, bins=10)
                    cell_scores[code] = {
                        "briers": briers,
                        "log_losses": log_losses,
                        "brier": sum(briers) / len(briers),
                        "log_loss": sum(log_losses) / len(log_losses),
                        "mean_predicted": sum(all_preds) / len(all_preds),
                        "reliability": reliability,
                        "ece": expected_calibration_error(reliability, len(all_outcomes)),
                    }

                for code in SELECTION_MODEL_CODES:
                    if code == "null_model_benchmark":
                        continue
                    diff = paired_bootstrap_difference(
                        cell_scores[code]["briers"],
                        cell_scores["null_model_benchmark"]["briers"],
                        resamples=bootstrap_resamples,
                        seed=_stable_seed("brier_advantage", code, draw_type, ordinal),
                    )
                    cell = {
                        "draw_type": draw_type,
                        "window_ordinal": ordinal,
                        "model_code": code,
                        **diff,
                    }
                    advantage_cells.append(cell)
                    all_advantage_cells.append(cell)
                    cell_scores[code]["advantage"] = diff

                for code in SELECTION_MODEL_CODES:
                    scores = cell_scores[code]
                    details = {
                        "draw_type": draw_type,
                        "model_code": code,
                        "calibration_version": "v2",
                        "mean_predicted": scores["mean_predicted"],
                        "expected_rate": 5 / 90,
                        "reliability_bins": scores["reliability"],
                        "ece": scores["ece"],
                        "train_draws": len(train_draws),
                        "test_draws": len(test_draws),
                        "metric_kind": "calibration",
                    }
                    if "advantage" in scores:
                        details["brier_advantage_vs_null"] = scores["advantage"]
                    record_metric(
                        connection,
                        experiment_id=experiment_ids[code],
                        experiment_run_id=run_ids[code],
                        metric_name="brier_score",
                        metric_scope="OUT_OF_SAMPLE",
                        metric_value=scores["brier"],
                        details=details,
                    )
                    record_metric(
                        connection,
                        experiment_id=experiment_ids[code],
                        experiment_run_id=run_ids[code],
                        metric_name="log_loss",
                        metric_scope="OUT_OF_SAMPLE",
                        metric_value=scores["log_loss"],
                        details={
                            "draw_type": draw_type,
                            "model_code": code,
                            "calibration_version": "v2",
                            "test_draws": len(test_draws),
                            "metric_kind": "calibration",
                        },
                    )
                    record_metric(
                        connection,
                        experiment_id=experiment_ids[code],
                        experiment_run_id=run_ids[code],
                        metric_name="expected_calibration_error",
                        metric_scope="OUT_OF_SAMPLE",
                        metric_value=scores["ece"],
                        details={
                            "draw_type": draw_type,
                            "model_code": code,
                            "calibration_version": "v2",
                            "test_draws": len(test_draws),
                            "metric_kind": "calibration",
                        },
                    )
            for run_id in run_ids.values():
                finish_run(connection, experiment_run_id=run_id)
            window_summaries.append({"ordinal": ordinal, "cells": len(advantage_cells)})

    for experiment_id in experiment_ids.values():
        complete_experiment(connection, experiment_id=experiment_id)
    for code, experiment_id in experiment_ids.items():
        cells = [cell for cell in all_advantage_cells if cell["model_code"] == code]
        favorable = sum(1 for cell in cells if cell["ci_high"] < 0)
        adverse = sum(1 for cell in cells if cell["ci_low"] > 0)
        if not cells:
            continue
        conclusion = (
            f"{favorable}/{len(cells)} cells beat the null benchmark on Brier score "
            f"(bootstrap 95% CI); {adverse}/{len(cells)} cells are worse."
        )
        if favorable / len(cells) > 0.1 and favorable > adverse:
            status = "SUPPORTED"
        elif adverse / len(cells) > 0.1 and adverse > favorable:
            status = "REJECTED"
        else:
            status = "INCONCLUSIVE"
        record_finding(
            connection,
            hypothesis_id=hypothesis.hypothesis_id,
            experiment_id=experiment_id,
            conclusion=conclusion,
            status=status,
            evidence={
                "model_code": code,
                "cells": len(cells),
                "favorable_cells": favorable,
                "adverse_cells": adverse,
                "bootstrap_resamples": bootstrap_resamples,
                "calibration_version": "v2",
            },
        )
    return {"experiments": {c: str(e) for c, e in experiment_ids.items()}, "windows": window_summaries}
