from __future__ import annotations

from typing import Any
from uuid import UUID

from lottery_intelligence_platform.calibration import probability_predictions
from lottery_intelligence_platform.calibration_evaluation import _draw_brier
from lottery_intelligence_platform.dependence import (
    PAIR_INCLUSION_PROBABILITY,
    binomial_right_tail,
    pair_dependence_tests,
)
from lottery_intelligence_platform.model_evaluation import (
    _draws_in_range,
    _stable_seed,
)
from lottery_intelligence_platform.models import NUMBER_COUNT, register_model_version
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
from lottery_intelligence_platform.stats import benjamini_hochberg
from lottery_intelligence_platform.uncertainty import paired_bootstrap_difference

DEPENDENCE_MODEL_CODE = "conditional_dependence"
REGIME_MODEL_CODE = "regime_aware"

DEPENDENCE_MODEL_DEFINITION = {
    "kind": "pair_cooccurrence",
    "pair_test": "binomial_right_tail",
    "correction": "benjamini_hochberg",
    "top_pairs": 10,
}
REGIME_MODEL_DEFINITION = {
    "kind": "regime_conditioned_frequency",
    "base": "top_k_frequency",
    "change_point_test": "monthly_permutation",
    "alpha": 0.05,
}

HYPOTHESES = {
    DEPENDENCE_MODEL_CODE: {
        "code": "pair_conditional_dependence",
        "title": "Number pairs co-occur beyond independence",
        "statement": (
            "Pairs of winning numbers co-occur in the same draw significantly more "
            "often than the independence baseline for a 5/90 game, and the pairs "
            "selected on training data retain an elevated hit rate out of sample."
        ),
    },
    REGIME_MODEL_CODE: {
        "code": "regime_aware_post_changepoint",
        "title": "Post-change-point history improves probability quality",
        "statement": (
            "For draw types where a distribution change-point is detected on training "
            "data, probabilities estimated from the post-change-point regime achieve a "
            "lower Brier score than probabilities estimated from the full history."
        ),
    },
}

TOP_PAIRS = 10


def evaluate_dependence_and_regime(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    evaluation_plan_id: UUID | str,
    change_point_permutations: int = 199,
    bootstrap_resamples: int = 199,
    bh_alpha: float = 0.05,
) -> dict[str, Any]:
    dependence_model = register_model_version(
        connection, code=DEPENDENCE_MODEL_CODE, family="STATISTICAL_TEST",
        definition=DEPENDENCE_MODEL_DEFINITION,
    )
    regime_model = register_model_version(
        connection, code=REGIME_MODEL_CODE, family="PREDICTIVE",
        definition=REGIME_MODEL_DEFINITION,
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
    for code, model in (
        (DEPENDENCE_MODEL_CODE, dependence_model),
        (REGIME_MODEL_CODE, regime_model),
    ):
        spec = HYPOTHESES[code]
        hypothesis = create_hypothesis(
            connection, code=spec["code"], title=spec["title"], statement=spec["statement"]
        )
        hypotheses[code] = hypothesis
        experiment = create_experiment(
            connection,
            hypothesis_id=hypothesis.hypothesis_id,
            dataset_version_id=dataset_version_id,
            model_version_id=model.model_version_id,
            configuration={
                "analysis": "conditional_dependence_and_regime",
                "model_code": code,
                "model_version": model.version,
                "evaluation_plan_code": plan[0],
                "evaluation_plan_version": plan[1],
            },
        )
        experiment_ids[code] = experiment.experiment_id

    window_summaries = []
    regime_cells: list[dict[str, Any]] = []
    dependence_cells: list[dict[str, Any]] = []
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
                train_number_sets = [numbers for _, _, numbers in train_draws]
                test_number_sets = [numbers for _, _, numbers in test_draws]

                # --- conditional dependence: pair co-occurrence ---
                pairs = pair_dependence_tests(train_number_sets)
                n_tested = len(pairs)
                significant = set()
                if pairs:
                    flags = benjamini_hochberg(
                        [p["p_value"] for p in pairs], alpha=bh_alpha
                    )
                    significant = {
                        pairs[i]["pair"] for i, flagged in enumerate(flags) if flagged
                    }
                top_pairs = {p["pair"] for p in pairs[:TOP_PAIRS]}
                expected_hits = len(test_number_sets) * TOP_PAIRS * PAIR_INCLUSION_PROBABILITY
                hits = sum(
                    1 for numbers in test_number_sets
                    if any(a in numbers and b in numbers for a, b in top_pairs)
                )
                oos_lift = hits / expected_hits if expected_hits else None
                oos_p = (
                    binomial_right_tail(
                        len(test_number_sets), TOP_PAIRS * PAIR_INCLUSION_PROBABILITY, hits
                    )
                    if top_pairs and hits > expected_hits else None
                )
                dependence_cells.append({
                    "draw_type": draw_type, "significant": len(significant),
                    "oos_lift": oos_lift, "oos_p": oos_p,
                })
                record_metric(
                    connection,
                    experiment_id=experiment_ids[DEPENDENCE_MODEL_CODE],
                    experiment_run_id=run_ids[DEPENDENCE_MODEL_CODE],
                    metric_name="significant_pair_count",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=float(len(significant)),
                    details={
                        "draw_type": draw_type,
                        "window_ordinal": ordinal,
                        "pairs_tested": n_tested,
                        "train_draws": len(train_draws),
                        "top_pairs": [list(p) for p in sorted(top_pairs)],
                        "oos_hits": hits,
                        "oos_expected_hits": expected_hits,
                        "oos_lift": oos_lift,
                        "oos_binomial_p": oos_p,
                        "metric_kind": "dependence",
                    },
                )

                # --- regime aware: post-change-point history ---
                regime_draws, change_point, cutoff_period = post_change_point_draws(
                    train_draws,
                    permutations=change_point_permutations,
                    seed=_stable_seed("regime_cp", draw_type, ordinal),
                )
                train_counts = [0] * NUMBER_COUNT
                for _, _, numbers in train_draws:
                    for number in numbers:
                        train_counts[number - 1] += 1
                regime_counts = [0] * NUMBER_COUNT
                for _, _, numbers in regime_draws:
                    for number in numbers:
                        regime_counts[number - 1] += 1
                base_preds = probability_predictions(
                    "top_k_frequency", train_counts, len(train_draws), {}
                )
                regime_preds = probability_predictions(
                    "top_k_frequency", regime_counts, len(regime_draws), {}
                )
                base_briers = [_draw_brier(base_preds, numbers) for numbers in test_number_sets]
                regime_briers = [_draw_brier(regime_preds, numbers) for numbers in test_number_sets]
                diff = paired_bootstrap_difference(
                    regime_briers, base_briers,
                    resamples=bootstrap_resamples,
                    seed=_stable_seed("regime_advantage", draw_type, ordinal),
                )
                regime_cells.append({
                    "draw_type": draw_type,
                    "change_point": change_point is not None,
                    **diff,
                })
                record_metric(
                    connection,
                    experiment_id=experiment_ids[REGIME_MODEL_CODE],
                    experiment_run_id=run_ids[REGIME_MODEL_CODE],
                    metric_name="regime_brier_advantage",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=diff["point_difference"],
                    details={
                        "draw_type": draw_type,
                        "window_ordinal": ordinal,
                        "change_point_detected": change_point is not None,
                        "cutoff_period": list(cutoff_period) if cutoff_period else None,
                        "permutation_p": change_point.permutation_p if change_point else None,
                        "statistic": change_point.statistic if change_point else None,
                        "train_draws_full": len(train_draws),
                        "train_draws_regime": len(regime_draws),
                        "ci_low": diff["ci_low"],
                        "ci_high": diff["ci_high"],
                        "metric_kind": "regime",
                    },
                )
            for run_id in run_ids.values():
                finish_run(connection, experiment_run_id=run_id)
            window_summaries.append({"ordinal": ordinal})

    for experiment_id in experiment_ids.values():
        complete_experiment(connection, experiment_id=experiment_id)

    favorable = sum(1 for c in regime_cells if c["ci_high"] < 0)
    adverse = sum(1 for c in regime_cells if c["ci_low"] > 0)
    detected = sum(1 for c in regime_cells if c["change_point"])
    record_finding(
        connection,
        hypothesis_id=hypotheses[REGIME_MODEL_CODE].hypothesis_id,
        experiment_id=experiment_ids[REGIME_MODEL_CODE],
        conclusion=(
            f"Change-points detected in {detected}/{len(regime_cells)} cells; "
            f"regime conditioning improved Brier in {favorable}/{len(regime_cells)} "
            f"cells and degraded it in {adverse}."
        ),
        status="SUPPORTED" if favorable > adverse and favorable / max(1, len(regime_cells)) > 0.1
        else "REJECTED" if adverse > favorable and adverse / max(1, len(regime_cells)) > 0.1
        else "INCONCLUSIVE",
        evidence={
            "cells": len(regime_cells), "change_points": detected,
            "favorable": favorable, "adverse": adverse,
        },
    )
    sig_cells = sum(1 for c in dependence_cells if c["significant"] > 0)
    lifted = sum(1 for c in dependence_cells if c["oos_lift"] and c["oos_lift"] > 1)
    record_finding(
        connection,
        hypothesis_id=hypotheses[DEPENDENCE_MODEL_CODE].hypothesis_id,
        experiment_id=experiment_ids[DEPENDENCE_MODEL_CODE],
        conclusion=(
            f"{sig_cells}/{len(dependence_cells)} cells show BH-significant pairs; "
            f"top-10 train pairs retain lift>1 OOS in {lifted}/{len(dependence_cells)} cells."
        ),
        status="INCONCLUSIVE" if 0 < sig_cells < len(dependence_cells) * 0.5
        else "REJECTED" if sig_cells == 0
        else "SUPPORTED",
        evidence={
            "cells": len(dependence_cells), "significant_cells": sig_cells,
            "oos_lifted_cells": lifted,
        },
    )
    return {
        "experiments": {c: str(e) for c, e in experiment_ids.items()},
        "windows": window_summaries,
    }
