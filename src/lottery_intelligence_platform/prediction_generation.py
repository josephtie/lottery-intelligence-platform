"""Automatic prospective prediction generation.

Targets: real draws (status EXPECTED/SCHEDULED) when the schedule is known,
otherwise a conservative fallback — draw types with recent activity get
predictions for tomorrow only.

Each generator is a registered model_version; picks are computed strictly
from draws whose scheduled_date < the target date (no look-ahead).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable
from uuid import UUID

from lottery_intelligence_platform.predictions import record_prediction

GENERATOR_CODES: tuple[str, ...] = (
    "null_model_benchmark",
    "top_k_frequency",
    "rolling_frequency",
    "bayesian_shrinkage",
)
PICK_COUNT = 2
ROLLING_WINDOW = 200
BAYES_ALPHA = 5.0
BAYES_MU = 5 / 90
FALLBACK_ACTIVITY_DAYS = 7


@dataclass(frozen=True, slots=True)
class GenerationResult:
    targets: int
    created: int
    reused: int
    by_model: dict[str, int]


def _stable_seed(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big")


def _train_counts(
    connection: Any, draw_type_id: UUID, before: date, *, limit: int | None = None
) -> dict[int, int]:
    """WINNING-number counts for a draw type over draws before `before`."""
    rows = connection.execute(
        """SELECT dn.number
           FROM core.draws d
           JOIN core.draw_versions dv
             ON dv.draw_id = d.draw_id AND dv.validation_status = 'VALID'
           JOIN core.draw_numbers dn
             ON dn.draw_version_id = dv.draw_version_id AND dn.number_role = 'WINNING'
           WHERE d.draw_type_id = %s AND d.scheduled_date < %s
           ORDER BY d.scheduled_date DESC""",
        (draw_type_id, before),
    ).fetchall()
    numbers = [row[0] for row in rows]
    if limit is not None:
        # `limit` counts draws, not numbers: 5 numbers per draw.
        numbers = numbers[: limit * 5]
    counts: dict[int, int] = {}
    for number in numbers:
        counts[number] = counts.get(number, 0) + 1
    return counts


def _top_k(counts: dict[int, int], k: int, score: Callable[[int], float]) -> list[int]:
    ranked = sorted(range(1, 91), key=lambda n: (-score(n), n))
    return sorted(ranked[:k])


def pick_null(connection: Any, draw_type_id: UUID, target: date) -> list[int]:
    rng = random.Random(_stable_seed("null_model_benchmark", str(draw_type_id), target))
    return sorted(rng.sample(range(1, 91), PICK_COUNT))


def pick_top_k(connection: Any, draw_type_id: UUID, target: date) -> list[int]:
    counts = _train_counts(connection, draw_type_id, target)
    return _top_k(counts, PICK_COUNT, lambda n: float(counts.get(n, 0)))


def pick_rolling(connection: Any, draw_type_id: UUID, target: date) -> list[int]:
    counts = _train_counts(connection, draw_type_id, target, limit=ROLLING_WINDOW)
    return _top_k(counts, PICK_COUNT, lambda n: float(counts.get(n, 0)))


def pick_bayesian(connection: Any, draw_type_id: UUID, target: date) -> list[int]:
    counts = _train_counts(connection, draw_type_id, target)
    n = sum(counts.values()) / 5 if counts else 0
    return _top_k(
        counts, PICK_COUNT,
        lambda num: (counts.get(num, 0) + BAYES_MU * BAYES_ALPHA) / (n + BAYES_ALPHA),
    )


PICKERS: dict[str, Callable[[Any, UUID, date], list[int]]] = {
    "null_model_benchmark": pick_null,
    "top_k_frequency": pick_top_k,
    "rolling_frequency": pick_rolling,
    "bayesian_shrinkage": pick_bayesian,
}


def _model_version_ids(connection: Any, codes: tuple[str, ...]) -> dict[str, UUID]:
    rows = connection.execute(
        """SELECT DISTINCT ON (code) code, model_version_id
           FROM research.model_versions WHERE code = ANY(%s)
           ORDER BY code, version DESC""",
        (list(codes),),
    ).fetchall()
    return {code: mv for code, mv in rows}


def _latest_dataset_version(connection: Any) -> UUID | None:
    row = connection.execute(
        "SELECT dataset_version_id FROM datasets.dataset_versions ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def _targets(connection: Any, today: date) -> list[tuple[UUID, date, UUID | None]]:
    """(draw_type_id, scheduled_date, draw_id|None) — scheduled/expected draws
    first; fallback: recently active types for tomorrow."""
    rows = connection.execute(
        """SELECT draw_type_id, scheduled_date, draw_id FROM core.draws
           WHERE status IN ('SCHEDULED', 'EXPECTED')
             AND scheduled_date >= %s AND scheduled_date <= %s
             AND NOT EXISTS (
                 SELECT 1 FROM core.draw_versions dv
                 WHERE dv.draw_id = draws.draw_id AND dv.validation_status = 'VALID'
             )
           ORDER BY scheduled_date""",
        (today, today + timedelta(days=7)),
    ).fetchall()
    if rows:
        return [(r[0], r[1], r[2]) for r in rows]
    tomorrow = today + timedelta(days=1)
    fallback = connection.execute(
        """SELECT DISTINCT draw_type_id FROM core.draws
           WHERE scheduled_date >= %s AND status IN ('FROZEN', 'SETTLED')
             AND draw_type_id IN (
                 SELECT DISTINCT draw_type_id FROM core.draws
                 WHERE scheduled_date = %s OR scheduled_date = %s
             )""",
        (today - timedelta(days=FALLBACK_ACTIVITY_DAYS), today - timedelta(days=1), today),
    ).fetchall()
    return [(r[0], tomorrow, None) for r in fallback]


def generate_predictions(
    connection: Any,
    *,
    today: date | None = None,
    stake: float = 100.0,
) -> GenerationResult:
    """Record one prediction per (generator, target draw). Idempotent via the
    predictions unique key."""
    today = today or date.today()
    targets = _targets(connection, today)
    model_ids = _model_version_ids(connection, GENERATOR_CODES)
    dataset_version_id = _latest_dataset_version(connection)
    created = reused = 0
    by_model: dict[str, int] = {code: 0 for code in GENERATOR_CODES}
    for draw_type_id, scheduled_date, _draw_id in targets:
        for code in GENERATOR_CODES:
            model_version_id = model_ids.get(code)
            if model_version_id is None:
                continue
            numbers = PICKERS[code](connection, draw_type_id, scheduled_date)
            result = record_prediction(
                connection,
                model_version_id=model_version_id,
                draw_type_id=draw_type_id,
                scheduled_date=scheduled_date,
                predicted_numbers=numbers,
                dataset_version_id=dataset_version_id,
                parameters={"pick_count": PICK_COUNT, "generator": code},
                stake=stake,
            )
            by_model[code] += 1
            if result.created:
                created += 1
            else:
                reused += 1
    return GenerationResult(len(targets), created, reused, by_model)
