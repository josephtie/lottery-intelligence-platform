from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.frequency_baseline import (
    NUMBERS_MAX,
    NUMBERS_MIN,
    NUMBERS_PER_DRAW,
)
from lottery_intelligence_platform.research import (
    ResearchError,
    canonical_sha256,
    complete_experiment,
    create_experiment,
    create_hypothesis,
    finish_run,
    record_finding,
    record_metric,
    start_run,
)
from lottery_intelligence_platform.stats import (
    benjamini_hochberg,
    chi_square_homogeneity,
    chi_square_sf,
    chi_square_uniform,
)

NUMBER_COUNT = NUMBERS_MAX - NUMBERS_MIN + 1

WF_HYPOTHESIS_CODE = "walkforward_frequency_stability_and_selection"
WF_HYPOTHESIS_TITLE = "Frequency structure is stable and exploitable out of sample"
WF_HYPOTHESIS_STATEMENT = (
    "Winning-number frequency structure measured on a training window persists "
    "into strictly posterior windows, and a frequency-based top-K selection "
    "covers more winning numbers than the uniform expectation."
)


@dataclass(frozen=True, slots=True)
class EvaluationPlan:
    evaluation_plan_id: UUID
    code: str
    version: int
    definition_sha256: str
    created: bool


@dataclass(frozen=True, slots=True)
class WindowSpec:
    ordinal: int
    train_start: date
    train_end: date
    validation_start: date | None
    validation_end: date | None
    test_start: date
    test_end: date


def generate_windows(
    first_date: date,
    last_date: date,
    definition: Mapping[str, Any],
) -> tuple[WindowSpec, ...]:
    mode = definition.get("mode", "expanding")
    if mode not in {"expanding", "sliding"}:
        raise ValueError("plan mode must be 'expanding' or 'sliding'")
    min_train_days = int(definition["min_train_days"])
    test_days = int(definition["test_days"])
    step_days = int(definition.get("step_days", test_days))
    validation_days = definition.get("validation_days")
    train_days = definition.get("train_days")
    if mode == "sliding" and train_days is None:
        raise ValueError("sliding mode requires train_days")
    if min_train_days < 1 or test_days < 1 or step_days < 1:
        raise ValueError("min_train_days, test_days and step_days must be positive")
    if validation_days is not None and int(validation_days) < 1:
        raise ValueError("validation_days must be positive when set")

    windows = []
    train_end = first_date + timedelta(days=min_train_days - 1)
    ordinal = 1
    while True:
        if mode == "sliding":
            train_start = train_end - timedelta(days=int(train_days) - 1)
            if train_start < first_date:
                train_start = first_date
        else:
            train_start = first_date
        if validation_days is not None:
            validation_start = train_end + timedelta(days=1)
            validation_end = validation_start + timedelta(days=int(validation_days) - 1)
            test_start = validation_end + timedelta(days=1)
        else:
            validation_start = validation_end = None
            test_start = train_end + timedelta(days=1)
        if test_start > last_date:
            break
        test_end = min(test_start + timedelta(days=test_days - 1), last_date)
        if train_end >= test_start or train_end > last_date:
            break
        windows.append(WindowSpec(
            ordinal=ordinal,
            train_start=train_start,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation_end,
            test_start=test_start,
            test_end=test_end,
        ))
        ordinal += 1
        train_end += timedelta(days=step_days)
    _assert_no_leakage(windows)
    return tuple(windows)


def _assert_no_leakage(windows: tuple[WindowSpec, ...]) -> None:
    previous_test_end: date | None = None
    for window in windows:
        if window.train_end >= window.test_start:
            raise ResearchError("leakage: train_end must precede test_start")
        if window.validation_start is not None:
            if not (window.train_end < window.validation_start <= window.validation_end):
                raise ResearchError("leakage: validation must strictly follow train")
            if window.test_start <= window.validation_end:
                raise ResearchError("leakage: test must strictly follow validation")
        if previous_test_end is not None and window.test_start <= previous_test_end:
            raise ResearchError("leakage: test windows must not overlap")
        previous_test_end = window.test_end


def register_evaluation_plan(
    connection: Any,
    *,
    code: str,
    definition: Mapping[str, Any],
) -> EvaluationPlan:
    if not code.strip():
        raise ValueError("plan code cannot be empty")
    if not isinstance(definition, Mapping):
        raise TypeError("plan definition must be a mapping")
    definition_sha = canonical_sha256(definition)
    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"evaluation_plan:{code}",),
        )
        existing = connection.execute(
            """SELECT evaluation_plan_id, version FROM research.evaluation_plans
               WHERE code = %s AND definition_sha256 = %s""",
            (code, definition_sha),
        ).fetchone()
        if existing:
            return EvaluationPlan(existing[0], code, existing[1], definition_sha, False)
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM research.evaluation_plans WHERE code = %s",
            (code,),
        ).fetchone()[0]
        plan_id = uuid4()
        connection.execute(
            """INSERT INTO research.evaluation_plans
               (evaluation_plan_id, code, version, definition, definition_sha256)
               VALUES (%s, %s, %s, %s, %s)""",
            (plan_id, code, version, Jsonb(dict(definition)), definition_sha),
        )
        return EvaluationPlan(plan_id, code, version, definition_sha, True)


def materialize_windows(
    connection: Any,
    *,
    evaluation_plan_id: UUID | str,
    dataset_version_id: UUID | str,
    definition: Mapping[str, Any],
) -> tuple[UUID, ...]:
    span = connection.execute(
        """SELECT min(d.scheduled_date), max(d.scheduled_date)
           FROM datasets.dataset_members m
           JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
           JOIN core.draws d ON d.draw_id = dv.draw_id
           WHERE m.dataset_version_id = %s""",
        (dataset_version_id,),
    ).fetchone()
    if span[0] is None:
        raise ResearchError("dataset version has no members")
    specs = generate_windows(span[0], span[1], definition)
    window_ids = []
    with connection.transaction():
        for spec in specs:
            counts = connection.execute(
                """SELECT count(*), count(*) FILTER (WHERE d.scheduled_date >= %s)
                   FROM datasets.dataset_members m
                   JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
                   JOIN core.draws d ON d.draw_id = dv.draw_id
                   WHERE m.dataset_version_id = %s AND d.scheduled_date <= %s""",
                (spec.test_start, dataset_version_id, spec.test_end),
            ).fetchone()
            window_id = uuid4()
            inserted = connection.execute(
                """INSERT INTO research.evaluation_windows
                   (evaluation_window_id, evaluation_plan_id, dataset_version_id, ordinal,
                    train_start, train_end, validation_start, validation_end,
                    test_start, test_end, member_count, test_member_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (evaluation_plan_id, dataset_version_id, ordinal)
                   DO NOTHING RETURNING evaluation_window_id""",
                (
                    window_id, evaluation_plan_id, dataset_version_id, spec.ordinal,
                    spec.train_start, spec.train_end, spec.validation_start,
                    spec.validation_end, spec.test_start, spec.test_end,
                    counts[0], counts[1],
                ),
            ).fetchone()
            if inserted is None:
                existing = connection.execute(
                    """SELECT evaluation_window_id, train_start, train_end, test_start, test_end
                       FROM research.evaluation_windows
                       WHERE evaluation_plan_id = %s AND dataset_version_id = %s AND ordinal = %s""",
                    (evaluation_plan_id, dataset_version_id, spec.ordinal),
                ).fetchone()
                if existing[1:] != (spec.train_start, spec.train_end, spec.test_start, spec.test_end):
                    raise ResearchError("stored evaluation window differs from regenerated spec")
                window_ids.append(existing[0])
            else:
                window_ids.append(inserted[0])
        stored = connection.execute(
            "SELECT count(*) FROM research.evaluation_windows WHERE evaluation_plan_id = %s AND dataset_version_id = %s",
            (evaluation_plan_id, dataset_version_id),
        ).fetchone()[0]
        if stored != len(specs):
            raise ResearchError("stored window count differs from regenerated plan")
    return tuple(window_ids)


def _number_counts_by_type(
    connection: Any,
    dataset_version_id: UUID | str,
    start_date: date,
    end_date: date,
) -> dict[str, list[int]]:
    rows = connection.execute(
        """SELECT dt.display_name, dn.number, count(*)
           FROM datasets.dataset_members m
           JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
           JOIN core.draws d ON d.draw_id = dv.draw_id
           JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
           JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
           WHERE m.dataset_version_id = %s AND dn.number_role = 'WINNING'
             AND d.scheduled_date BETWEEN %s AND %s
           GROUP BY dt.display_name, dn.number""",
        (dataset_version_id, start_date, end_date),
    ).fetchall()
    counts: dict[str, list[int]] = {}
    for draw_type, number, count in rows:
        counts.setdefault(draw_type, [0] * NUMBER_COUNT)[number - NUMBERS_MIN] = count
    return counts


def _test_draws_by_type(
    connection: Any,
    dataset_version_id: UUID | str,
    start_date: date,
    end_date: date,
) -> dict[str, list[set[int]]]:
    rows = connection.execute(
        """SELECT dt.display_name, dv.draw_version_id, dn.number
           FROM datasets.dataset_members m
           JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
           JOIN core.draws d ON d.draw_id = dv.draw_id
           JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
           JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
           WHERE m.dataset_version_id = %s AND dn.number_role = 'WINNING'
             AND d.scheduled_date BETWEEN %s AND %s
           ORDER BY d.scheduled_date, dv.draw_version_id, dn.position""",
        (dataset_version_id, start_date, end_date),
    ).fetchall()
    by_draw: dict[tuple[str, Any], set[int]] = {}
    for draw_type, draw_version_id, number in rows:
        by_draw.setdefault((draw_type, draw_version_id), set()).add(number)
    by_type: dict[str, list[set[int]]] = {}
    for (draw_type, _), numbers in by_draw.items():
        by_type.setdefault(draw_type, []).append(numbers)
    return by_type


def run_walkforward_evaluation(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    evaluation_plan_id: UUID | str,
    top_k: int = 10,
    bh_alpha: float = 0.05,
    min_expected_per_cell: float = 5.0,
) -> dict[str, Any]:
    if not NUMBERS_MIN <= top_k <= NUMBER_COUNT:
        raise ValueError("top_k out of range")
    windows = connection.execute(
        """SELECT evaluation_window_id, ordinal, train_start, train_end,
                  validation_start, validation_end, test_start, test_end
           FROM research.evaluation_windows
           WHERE evaluation_plan_id = %s AND dataset_version_id = %s
           ORDER BY ordinal""",
        (evaluation_plan_id, dataset_version_id),
    ).fetchall()
    if not windows:
        raise ResearchError("no materialized windows for this plan and dataset")
    plan = connection.execute(
        "SELECT code, version FROM research.evaluation_plans WHERE evaluation_plan_id = %s",
        (evaluation_plan_id,),
    ).fetchone()

    hypothesis = create_hypothesis(
        connection,
        code=WF_HYPOTHESIS_CODE,
        title=WF_HYPOTHESIS_TITLE,
        statement=WF_HYPOTHESIS_STATEMENT,
    )
    experiment = create_experiment(
        connection,
        hypothesis_id=hypothesis.hypothesis_id,
        dataset_version_id=dataset_version_id,
        configuration={
            "analysis": "walkforward_frequency",
            "evaluation_plan_code": plan[0],
            "evaluation_plan_version": plan[1],
            "top_k": top_k,
            "bh_alpha": bh_alpha,
            "min_expected_per_cell": min_expected_per_cell,
        },
    )

    evaluated_windows: list[dict[str, Any]] = []
    expected_matches = NUMBERS_PER_DRAW * top_k / NUMBER_COUNT
    with connection.transaction():
        for window in windows:
            window_id, ordinal, train_start, train_end, validation_start, validation_end, test_start, test_end = window
            existing_run = connection.execute(
                """SELECT experiment_run_id FROM research.experiment_runs
                   WHERE experiment_id = %s AND evaluation_window_id = %s""",
                (experiment.experiment_id, window_id),
            ).fetchone()
            if existing_run:
                evaluated_windows.append({"ordinal": ordinal, "run_id": str(existing_run[0]), "skipped": True})
                continue

            train_counts = _number_counts_by_type(connection, dataset_version_id, train_start, train_end)
            test_counts = _number_counts_by_type(connection, dataset_version_id, test_start, test_end)
            test_draws = _test_draws_by_type(connection, dataset_version_id, test_start, test_end)

            homogeneity_p_values: list[float] = []
            per_type: list[dict[str, Any]] = []
            for draw_type in sorted(set(train_counts) | set(test_counts)):
                train_observed = train_counts.get(draw_type, [0] * NUMBER_COUNT)
                test_observed = test_counts.get(draw_type, [0] * NUMBER_COUNT)
                train_total = sum(train_observed)
                test_total = sum(test_observed)
                if train_total == 0 or test_total == 0:
                    continue
                train_expected = train_total / NUMBER_COUNT
                test_expected = test_total / NUMBER_COUNT
                low_power = min(train_expected, test_expected) < min_expected_per_cell

                train_chi2, train_df, _ = chi_square_uniform(train_observed)
                test_chi2, _, _ = chi_square_uniform(test_observed)
                homogeneity_chi2, homogeneity_df = chi_square_homogeneity(train_observed, test_observed)
                homogeneity_p = chi_square_sf(homogeneity_chi2, homogeneity_df)
                homogeneity_p_values.append(homogeneity_p)

                top_numbers = {
                    index + NUMBERS_MIN
                    for index, _ in sorted(
                        enumerate(train_observed), key=lambda item: (-item[1], item[0])
                    )[:top_k]
                }
                draw_results = test_draws.get(draw_type, [])
                matches = [len(top_numbers & winning) for winning in draw_results]
                observed_mean = sum(matches) / len(matches) if matches else 0.0
                per_type.append({
                    "draw_type": draw_type,
                    "train_draws": train_total // NUMBERS_PER_DRAW,
                    "test_draws": test_total // NUMBERS_PER_DRAW,
                    "low_power": low_power,
                    "train_chi2": train_chi2,
                    "test_chi2": test_chi2,
                    "homogeneity_chi2": homogeneity_chi2,
                    "homogeneity_df": homogeneity_df,
                    "homogeneity_p": homogeneity_p,
                    "observed_mean_matches": observed_mean,
                    "expected_mean_matches": expected_matches,
                    "coverage_lift": observed_mean / expected_matches,
                    "draws_evaluated": len(matches),
                })
            significant = benjamini_hochberg(homogeneity_p_values, bh_alpha)
            for entry, is_significant in zip(per_type, significant):
                entry["non_stationary_bh"] = bool(is_significant)

            run = start_run(
                connection,
                experiment_id=experiment.experiment_id,
                scope="OUT_OF_SAMPLE",
                details={
                    "window_ordinal": ordinal,
                    "train_start": train_start.isoformat(),
                    "train_end": train_end.isoformat(),
                    "validation_start": validation_start.isoformat() if validation_start else None,
                    "validation_end": validation_end.isoformat() if validation_end else None,
                    "test_start": test_start.isoformat(),
                    "test_end": test_end.isoformat(),
                },
            )
            connection.execute(
                "UPDATE research.experiment_runs SET evaluation_window_id = %s WHERE experiment_run_id = %s",
                (window_id, run.experiment_run_id),
            )
            for entry in per_type:
                record_metric(
                    connection,
                    experiment_id=experiment.experiment_id,
                    experiment_run_id=run.experiment_run_id,
                    metric_name="train_chi_square",
                    metric_scope="TRAIN",
                    metric_value=entry["train_chi2"],
                    details={k: entry[k] for k in (
                        "draw_type", "train_draws", "low_power")},
                )
                record_metric(
                    connection,
                    experiment_id=experiment.experiment_id,
                    experiment_run_id=run.experiment_run_id,
                    metric_name="test_chi_square",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=entry["test_chi2"],
                    details={k: entry[k] for k in (
                        "draw_type", "test_draws", "low_power")},
                )
                record_metric(
                    connection,
                    experiment_id=experiment.experiment_id,
                    experiment_run_id=run.experiment_run_id,
                    metric_name="homogeneity_chi_square",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=entry["homogeneity_chi2"],
                    details={
                        "draw_type": entry["draw_type"],
                        "degrees_of_freedom": entry["homogeneity_df"],
                        "p_value": entry["homogeneity_p"],
                        "non_stationary_bh": entry["non_stationary_bh"],
                        "low_power": entry["low_power"],
                        "test": "two_sample_chi_square_homogeneity",
                    },
                )
                record_metric(
                    connection,
                    experiment_id=experiment.experiment_id,
                    experiment_run_id=run.experiment_run_id,
                    metric_name="coverage_lift",
                    metric_scope="OUT_OF_SAMPLE",
                    metric_value=entry["coverage_lift"],
                    details={
                        "draw_type": entry["draw_type"],
                        "top_k": top_k,
                        "observed_mean_matches": entry["observed_mean_matches"],
                        "expected_mean_matches": entry["expected_mean_matches"],
                        "draws_evaluated": entry["draws_evaluated"],
                        "metric_kind": "predictive",
                    },
                )
            finish_run(connection, experiment_run_id=run.experiment_run_id)
            evaluated_windows.append({
                "ordinal": ordinal,
                "run_id": str(run.experiment_run_id),
                "draw_types": len(per_type),
                "non_stationary_types": sum(e["non_stationary_bh"] for e in per_type),
                "mean_coverage_lift": (
                    sum(e["coverage_lift"] for e in per_type) / len(per_type)
                    if per_type else None
                ),
                "skipped": False,
            })

        experiment_status = connection.execute(
            "SELECT status FROM research.experiments WHERE experiment_id = %s",
            (experiment.experiment_id,),
        ).fetchone()[0]
        if experiment_status != "COMPLETED":
            complete_experiment(connection, experiment_id=experiment.experiment_id)
        existing_finding = connection.execute(
            "SELECT 1 FROM research.findings WHERE experiment_id = %s LIMIT 1",
            (experiment.experiment_id,),
        ).fetchone()
        if existing_finding is None:
            record_finding(
                connection,
                hypothesis_id=hypothesis.hypothesis_id,
                experiment_id=experiment.experiment_id,
                conclusion=(
                    "Walk-forward evaluation recorded per window and draw type; "
                    "INCONCLUSIVE pending verified rules. Negative and null "
                    "coverage_lift results are preserved as metrics."
                ),
                status="INCONCLUSIVE",
                evidence={
                    "dataset_status": "EXPLORATORY_ONLY",
                    "windows": evaluated_windows,
                },
            )
    return {
        "hypothesis_id": str(hypothesis.hypothesis_id),
        "experiment_id": str(experiment.experiment_id),
        "experiment_created": experiment.created,
        "windows": evaluated_windows,
    }
