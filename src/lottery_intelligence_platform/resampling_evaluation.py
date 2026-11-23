from __future__ import annotations

from typing import Any
from uuid import UUID

from lottery_intelligence_platform.calibration import probability_predictions
from lottery_intelligence_platform.calibration_evaluation import _draw_brier
from lottery_intelligence_platform.model_evaluation import (
    _draws_in_range,
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
from lottery_intelligence_platform.uncertainty import (
    paired_block_bootstrap_difference,
    paired_bootstrap_difference,
)

MODEL_CODE = "dependence_aware_resampling"
MODEL_DEFINITION = {
    "kind": "block_bootstrap_comparison",
    "block_size": 20,
    "reference": "iid_paired_bootstrap",
}
HYPOTHESIS = {
    "code": "resampling_dependence_robustness",
    "title": "Bootstrap conclusions are robust to draw-level dependence",
    "statement": (
        "Confidence intervals for model-vs-null Brier differences do not change "
        "classification when observations are resampled in consecutive blocks "
        "instead of independently."
    ),
}

BLOCK_SIZE = 20
TARGET_MODEL = "top_k_frequency"


def evaluate_dependence_aware_resampling(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    evaluation_plan_id: UUID | str,
    block_size: int = BLOCK_SIZE,
    bootstrap_resamples: int = 199,
) -> dict[str, Any]:
    model = register_model_version(
        connection, code=MODEL_CODE, family="STATISTICAL_TEST",
        definition={**MODEL_DEFINITION, "block_size": block_size},
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
    hypothesis = create_hypothesis(
        connection,
        code=HYPOTHESIS["code"], title=HYPOTHESIS["title"],
        statement=HYPOTHESIS["statement"],
    )
    experiment = create_experiment(
        connection,
        hypothesis_id=hypothesis.hypothesis_id,
        dataset_version_id=dataset_version_id,
        model_version_id=model.model_version_id,
        configuration={
            "analysis": "dependence_aware_resampling",
            "model_code": MODEL_CODE,
            "model_version": model.version,
            "target_model": TARGET_MODEL,
            "evaluation_plan_code": plan[0],
            "evaluation_plan_version": plan[1],
            "block_size": block_size,
        },
    )

    window_summaries = []
    cells: list[dict[str, Any]] = []
    with connection.transaction():
        for window in windows:
            window_id, ordinal, train_start, train_end, test_start, test_end = window
            draws_by_type = _draws_in_range(
                connection, dataset_version_id, train_start, test_end
            )
            run_id = start_run(
                connection,
                experiment_id=experiment.experiment_id,
                scope="OUT_OF_SAMPLE",
                details={"window_ordinal": ordinal},
            ).experiment_run_id
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
                preds = probability_predictions(
                    TARGET_MODEL, train_counts, len(train_draws), {}
                )
                null_preds = [5 / 90] * NUMBER_COUNT
                model_briers = [
                    _draw_brier(preds, numbers) for _, _, numbers in test_draws
                ]
                null_briers = [
                    _draw_brier(null_preds, numbers) for _, _, numbers in test_draws
                ]
                iid = paired_bootstrap_difference(
                    model_briers, null_briers,
                    resamples=bootstrap_resamples,
                    seed=_stable_seed("iid_boot", draw_type, ordinal),
                )
                block = paired_block_bootstrap_difference(
                    model_briers, null_briers,
                    block_size=block_size,
                    resamples=bootstrap_resamples,
                    seed=_stable_seed("block_boot", draw_type, ordinal),
                )
                iid_class = (
                    "better" if iid["ci_high"] < 0
                    else "worse" if iid["ci_low"] > 0 else "inconclusive"
                )
                block_class = (
                    "better" if block["ci_high"] < 0
                    else "worse" if block["ci_low"] > 0 else "inconclusive"
                )
                changed = iid_class != block_class
                cells.append({
                    "draw_type": draw_type, "iid": iid_class,
                    "block": block_class, "changed": changed,
                })
                record_metric(
                    connection,
                    experiment_id=experiment.experiment_id,
                    experiment_run_id=run_id,
                    metric_name="block_vs_iid_advantage",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=block["point_difference"],
                    details={
                        "draw_type": draw_type,
                        "window_ordinal": ordinal,
                        "target_model": TARGET_MODEL,
                        "block_size": block_size,
                        "iid_ci": [iid["ci_low"], iid["ci_high"]],
                        "block_ci": [block["ci_low"], block["ci_high"]],
                        "iid_classification": iid_class,
                        "block_classification": block_class,
                        "classification_changed": changed,
                        "test_draws": len(test_draws),
                        "metric_kind": "dependence_aware_resampling",
                    },
                )
            finish_run(connection, experiment_run_id=run_id)
            window_summaries.append({"ordinal": ordinal})

    complete_experiment(connection, experiment_id=experiment.experiment_id)
    changed = sum(1 for c in cells if c["changed"])
    record_finding(
        connection,
        hypothesis_id=hypothesis.hypothesis_id,
        experiment_id=experiment.experiment_id,
        conclusion=(
            f"Block bootstrap (size {block_size}) changed the classification in "
            f"{changed}/{len(cells)} cells compared to iid resampling."
        ),
        status="SUPPORTED" if changed / max(1, len(cells)) <= 0.1 else "REJECTED",
        evidence={"cells": len(cells), "changed": changed, "block_size": block_size},
    )
    return {
        "experiment": str(experiment.experiment_id),
        "windows": window_summaries,
    }
