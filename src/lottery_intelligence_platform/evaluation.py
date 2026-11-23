from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from lottery_intelligence_platform.frequency_baseline import (
    HYPOTHESIS_CODE,
    HYPOTHESIS_STATEMENT,
    HYPOTHESIS_TITLE,
    NUMBERS_PER_DRAW,
    compute_winning_number_frequencies,
)
from lottery_intelligence_platform.research import (
    complete_experiment,
    create_experiment,
    create_hypothesis,
    finish_run,
    record_finding,
    record_metric,
    start_run,
)


@dataclass(frozen=True, slots=True)
class TemporalScope:
    scope: str
    end_date: date | None
    member_count: int
    first_date: date | None
    last_date: date | None


def temporal_scopes(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    train_end: date,
    validation_end: date,
) -> tuple[TemporalScope, ...]:
    if train_end >= validation_end:
        raise ValueError("train_end must be before validation_end")
    rows = connection.execute(
        """SELECT CASE
                  WHEN d.scheduled_date <= %s THEN 'TRAIN'
                  WHEN d.scheduled_date <= %s THEN 'VALIDATION'
                  ELSE 'OUT_OF_SAMPLE' END AS scope,
                  count(*), min(d.scheduled_date), max(d.scheduled_date)
           FROM datasets.dataset_members m
           JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
           JOIN core.draws d ON d.draw_id = dv.draw_id
           WHERE m.dataset_version_id = %s
           GROUP BY 1""",
        (train_end, validation_end, dataset_version_id),
    ).fetchall()
    by_scope = {row[0]: row for row in rows}
    boundaries = {"TRAIN": train_end, "VALIDATION": validation_end, "OUT_OF_SAMPLE": None}
    return tuple(
        TemporalScope(
            scope=name,
            end_date=boundaries[name],
            member_count=row[1] if row else 0,
            first_date=row[2] if row else None,
            last_date=row[3] if row else None,
        )
        for name, row in (
            (scope, by_scope.get(scope))
            for scope in ("TRAIN", "VALIDATION", "OUT_OF_SAMPLE")
        )
    )


def _scope_start_date(scope: TemporalScope, previous: TemporalScope | None) -> date | None:
    if previous is None:
        return None
    return previous.end_date


def run_scoped_frequency_evaluation(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    train_end: date,
    validation_end: date,
) -> dict[str, Any]:
    scopes = temporal_scopes(
        connection,
        dataset_version_id=dataset_version_id,
        train_end=train_end,
        validation_end=validation_end,
    )
    hypothesis = create_hypothesis(
        connection,
        code=HYPOTHESIS_CODE,
        title=HYPOTHESIS_TITLE,
        statement=HYPOTHESIS_STATEMENT,
    )
    experiment = create_experiment(
        connection,
        hypothesis_id=hypothesis.hypothesis_id,
        dataset_version_id=dataset_version_id,
        configuration={
            "analysis": "chi_square_frequency",
            "number_role": "WINNING",
            "numbers_per_draw": NUMBERS_PER_DRAW,
            "temporal_split": {
                "train_end": train_end.isoformat(),
                "validation_end": validation_end.isoformat(),
            },
        },
    )

    scope_results: dict[str, dict[str, Any]] = {}
    with connection.transaction():
        previous: TemporalScope | None = None
        for scope in scopes:
            start_date = _scope_start_date(scope, previous)
            end_date = scope.end_date
            run = start_run(
                connection,
                experiment_id=experiment.experiment_id,
                scope=scope.scope,
                details={
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "member_count": scope.member_count,
                    "first_scheduled_date": scope.first_date.isoformat() if scope.first_date else None,
                    "last_scheduled_date": scope.last_date.isoformat() if scope.last_date else None,
                },
            )
            frequencies = compute_winning_number_frequencies(
                connection,
                dataset_version_id=dataset_version_id,
                start_date=date.fromordinal(start_date.toordinal() + 1) if start_date else None,
                end_date=end_date,
            )
            for frequency in frequencies:
                record_metric(
                    connection,
                    experiment_id=experiment.experiment_id,
                    experiment_run_id=run.experiment_run_id,
                    metric_name="chi_square_statistic",
                    metric_scope=scope.scope,
                    metric_value=frequency.chi_square,
                    details={
                        "draw_type": frequency.draw_type,
                        "draw_count": frequency.draw_count,
                        "selection_count": frequency.selection_count,
                        "degrees_of_freedom": frequency.degrees_of_freedom,
                        "min_observed": frequency.min_observed,
                        "max_observed": frequency.max_observed,
                    },
                )
            finish_run(connection, experiment_run_id=run.experiment_run_id)
            scope_results[scope.scope] = {
                "run_id": str(run.experiment_run_id),
                "member_count": scope.member_count,
                "draw_types": len(frequencies),
                "max_chi_square": max((f.chi_square for f in frequencies), default=None),
            }
            previous = scope
        complete_experiment(connection, experiment_id=experiment.experiment_id)
        record_finding(
            connection,
            hypothesis_id=hypothesis.hypothesis_id,
            experiment_id=experiment.experiment_id,
            conclusion=(
                "Scoped frequency evaluation completed across TRAIN, VALIDATION "
                "and OUT_OF_SAMPLE windows; verdict remains INCONCLUSIVE while "
                "rule effectivity is UNVERIFIED."
            ),
            status="INCONCLUSIVE",
            evidence={
                "dataset_status": "EXPLORATORY_ONLY",
                "scopes": scope_results,
            },
        )
    return {
        "hypothesis_id": str(hypothesis.hypothesis_id),
        "experiment_id": str(experiment.experiment_id),
        "experiment_created": experiment.created,
        "scopes": scope_results,
    }
