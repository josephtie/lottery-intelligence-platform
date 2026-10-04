from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.research import ResearchError


@dataclass(frozen=True, slots=True)
class Prediction:
    prediction_id: UUID
    status: str
    created: bool


def record_prediction(
    connection: Any,
    *,
    model_version_id: UUID | str,
    draw_type_id: UUID | str,
    scheduled_date: date,
    predicted_numbers: Sequence[int],
    strategy_version_id: UUID | str | None = None,
) -> Prediction:
    numbers = sorted(set(int(n) for n in predicted_numbers))
    if not numbers:
        raise ValueError("predicted_numbers cannot be empty")
    if len(numbers) != len(predicted_numbers):
        raise ValueError("predicted_numbers must be distinct")
    if any(n < 1 or n > 90 for n in numbers):
        raise ValueError("predicted numbers must be in [1, 90]")
    if scheduled_date < date.today():
        raise ValueError("prospective predictions must target today or a future date")

    with connection.transaction():
        connection.execute(
            "SELECT 1 FROM catalog.draw_types WHERE draw_type_id = %s",
            (draw_type_id,),
        ).fetchone() or (_ for _ in ()).throw(
            ResearchError("draw_type_id does not exist")
        )
        connection.execute(
            "SELECT 1 FROM research.model_versions WHERE model_version_id = %s",
            (model_version_id,),
        ).fetchone() or (_ for _ in ()).throw(
            ResearchError("model_version_id does not exist")
        )
        inserted = connection.execute(
            """INSERT INTO research.predictions
               (prediction_id, model_version_id, strategy_version_id, draw_type_id,
                scheduled_date, predicted_numbers)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (model_version_id, draw_type_id, scheduled_date, predicted_numbers)
               DO NOTHING
               RETURNING prediction_id, status""",
            (uuid4(), model_version_id, strategy_version_id, draw_type_id,
             scheduled_date, numbers),
        ).fetchone()
        if inserted:
            return Prediction(inserted[0], inserted[1], True)
        existing = connection.execute(
            """SELECT prediction_id, status FROM research.predictions
               WHERE model_version_id = %s AND draw_type_id = %s
                 AND scheduled_date = %s AND predicted_numbers = %s::INTEGER[]""",
            (model_version_id, draw_type_id, scheduled_date, numbers),
        ).fetchone()
        return Prediction(existing[0], existing[1], False)


def score_predictions(
    connection: Any,
    *,
    scheduled_date_before: date | None = None,
) -> dict[str, int]:
    date_filter = "AND p.scheduled_date < %s" if scheduled_date_before else ""
    params = (scheduled_date_before,) if scheduled_date_before else ()
    pending = connection.execute(
        f"""SELECT p.prediction_id, p.draw_type_id, p.scheduled_date,
                   p.predicted_numbers, p.created_at
            FROM research.predictions p
            WHERE p.status = 'PENDING' {date_filter}
            ORDER BY p.created_at""",
        params,
    ).fetchall()

    scored = invalidated = skipped = 0
    with connection.transaction():
        for prediction_id, draw_type_id, scheduled_date, numbers, created_at in pending:
            candidate = connection.execute(
                """SELECT dv.draw_version_id, dv.result_observed_at
                   FROM core.draws d
                   JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
                   WHERE d.draw_type_id = %s AND d.scheduled_date = %s
                     AND dv.validation_status = 'VALID'
                     AND EXISTS (
                         SELECT 1 FROM core.draw_numbers dn
                         WHERE dn.draw_version_id = dv.draw_version_id
                           AND dn.number_role = 'WINNING'
                     )
                   ORDER BY dv.version_number DESC
                   LIMIT 1""",
                (draw_type_id, scheduled_date),
            ).fetchone()
            if candidate is None:
                skipped += 1
                continue
            draw_version_id, result_observed_at = candidate
            if created_at >= result_observed_at:
                connection.execute(
                    "UPDATE research.predictions SET status = 'INVALID' WHERE prediction_id = %s",
                    (prediction_id,),
                )
                invalidated += 1
                continue
            winning = {
                row[0] for row in connection.execute(
                    """SELECT number FROM core.draw_numbers
                       WHERE draw_version_id = %s AND number_role = 'WINNING'""",
                    (draw_version_id,),
                ).fetchall()
            }
            hits = len(set(numbers) & winning)
            connection.execute(
                """INSERT INTO research.prediction_scores
                   (prediction_score_id, prediction_id, draw_version_id, hits, details)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (prediction_id) DO NOTHING""",
                (
                    uuid4(), prediction_id, draw_version_id, hits,
                    Jsonb({
                        "predicted_numbers": sorted(set(numbers)),
                        "winning_numbers": sorted(winning),
                        "predicted_at": created_at.isoformat(),
                        "result_observed_at": result_observed_at.isoformat(),
                    }),
                ),
            )
            connection.execute(
                "UPDATE research.predictions SET status = 'SCORED' WHERE prediction_id = %s",
                (prediction_id,),
            )
            scored += 1
    return {"scored": scored, "invalidated": invalidated, "skipped_pending_draw": skipped}
