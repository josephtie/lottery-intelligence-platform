from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from lottery_intelligence_platform.research import (
    complete_experiment,
    create_experiment,
    create_hypothesis,
    finish_run,
    record_finding,
    record_metric,
    register_feature_version,
    start_run,
)

NUMBERS_MIN = 1
NUMBERS_MAX = 90
NUMBERS_PER_DRAW = 5

HYPOTHESIS_CODE = "winning_numbers_frequency_baseline"
HYPOTHESIS_TITLE = "Winning-number frequencies deviate from uniform"
HYPOTHESIS_STATEMENT = (
    "Within each draw type, the observed distribution of winning numbers differs "
    "from a uniform distribution over the valid number range by more than "
    "sampling noise."
)


@dataclass(frozen=True, slots=True)
class DrawTypeFrequency:
    draw_type: str
    draw_count: int
    selection_count: int
    chi_square: float
    degrees_of_freedom: int
    min_observed: int
    max_observed: int


def compute_winning_number_frequencies(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[DrawTypeFrequency, ...]:
    clauses = ["m.dataset_version_id = %s", "dn.number_role = 'WINNING'"]
    params: list[Any] = [dataset_version_id]
    if start_date is not None:
        clauses.append("d.scheduled_date >= %s")
        params.append(start_date)
    if end_date is not None:
        clauses.append("d.scheduled_date <= %s")
        params.append(end_date)
    rows = connection.execute(
        f"""SELECT dt.display_name, dn.number, count(*)
           FROM datasets.dataset_members m
           JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
           JOIN core.draws d ON d.draw_id = dv.draw_id
           JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
           JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
           WHERE {' AND '.join(clauses)}
           GROUP BY dt.display_name, dn.number
           ORDER BY dt.display_name, dn.number""",
        tuple(params),
    ).fetchall()

    by_type: dict[str, dict[int, int]] = {}
    for draw_type, number, count in rows:
        by_type.setdefault(draw_type, {})[number] = count

    results = []
    for draw_type, counts in sorted(by_type.items()):
        selection_count = sum(counts.values())
        draw_count = selection_count // NUMBERS_PER_DRAW
        expected = selection_count / (NUMBERS_MAX - NUMBERS_MIN + 1)
        observed = [counts.get(number, 0) for number in range(NUMBERS_MIN, NUMBERS_MAX + 1)]
        chi_square = sum((value - expected) ** 2 / expected for value in observed)
        results.append(DrawTypeFrequency(
            draw_type=draw_type,
            draw_count=draw_count,
            selection_count=selection_count,
            chi_square=chi_square,
            degrees_of_freedom=NUMBERS_MAX - NUMBERS_MIN,
            min_observed=min(observed),
            max_observed=max(observed),
        ))
    return tuple(results)


def run_frequency_baseline(
    connection: Any,
    *,
    dataset_version_id: UUID | str,
) -> dict[str, Any]:
    hypothesis = create_hypothesis(
        connection,
        code=HYPOTHESIS_CODE,
        title=HYPOTHESIS_TITLE,
        statement=HYPOTHESIS_STATEMENT,
    )
    feature_version = register_feature_version(
        connection,
        code="winning_number_counts",
        definition={
            "kind": "number_frequency",
            "number_role": "WINNING",
            "group_by": "draw_type",
            "number_range": [NUMBERS_MIN, NUMBERS_MAX],
        },
    )
    experiment = create_experiment(
        connection,
        hypothesis_id=hypothesis.hypothesis_id,
        dataset_version_id=dataset_version_id,
        feature_version_id=feature_version.feature_version_id,
        configuration={
            "analysis": "chi_square_frequency",
            "number_role": "WINNING",
            "numbers_per_draw": NUMBERS_PER_DRAW,
        },
    )
    frequencies = compute_winning_number_frequencies(
        connection, dataset_version_id=dataset_version_id
    )
    with connection.transaction():
        run = start_run(
            connection,
            experiment_id=experiment.experiment_id,
            scope="GLOBAL",
        )
        for frequency in frequencies:
            record_metric(
                connection,
                experiment_id=experiment.experiment_id,
                experiment_run_id=run.experiment_run_id,
                metric_name="chi_square_statistic",
                metric_scope="GLOBAL",
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
        complete_experiment(connection, experiment_id=experiment.experiment_id)
        record_finding(
            connection,
            hypothesis_id=hypothesis.hypothesis_id,
            experiment_id=experiment.experiment_id,
            conclusion=(
                "Descriptive frequency statistics computed per draw type; no "
                "significance verdict is recorded because historical rule "
                "effectivity is UNVERIFIED and the dataset is EXPLORATORY_ONLY."
            ),
            status="INCONCLUSIVE",
            evidence={
                "draw_types": len(frequencies),
                "max_chi_square": max((f.chi_square for f in frequencies), default=None),
                "min_draw_count": min((f.draw_count for f in frequencies), default=None),
                "dataset_status": "EXPLORATORY_ONLY",
            },
        )
    return {
        "hypothesis_id": str(hypothesis.hypothesis_id),
        "experiment_id": str(experiment.experiment_id),
        "run_id": str(run.experiment_run_id),
        "draw_types": len(frequencies),
        "metrics_recorded": len(frequencies),
        "finding_status": "INCONCLUSIVE",
    }
