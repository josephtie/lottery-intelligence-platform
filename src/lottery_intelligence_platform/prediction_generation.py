"""Automatic prospective prediction generation — cohort-driven.

The prospective cohort (`research.prospective_cohort_versions` + members) is a
versioned manifest: which models, on which draw types, with which parameters
and seed. Changing the cohort creates a new audited version, never edits the
old one.

Every (target, member) combination gets an explicit coverage row:
GENERATED / MISSING / FAILED / INELIGIBLE — absent predictions are traceable,
never silent.

Picks are computed strictly from draws whose scheduled_date < the target
date; the settlement lock (`created_at < result_observed_at`) is the second
anti-leakage barrier.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Mapping
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.predictions import record_prediction
from lottery_intelligence_platform.scheduler import emit_event

DEFAULT_COHORT_CODE = "prospective_turbo_v1"
DEFAULT_COHORT_DEFINITION: dict[str, Any] = {
    "game": "loto_bonheur",
    "pick_count": 2,
    "stake": 100,
    "number_range": [1, 90],
    "numbers_picked_per_draw": 5,
    "primary_metrics": ["hit_rate", "turbo_2_hit_rate", "net_profit", "roi"],
    "reference_model": "null_model_benchmark",
    "exclusion_criteria": (
        "draw types with fewer than 30 historical draws remain eligible but "
        "must be reported under low-power"
    ),
    "start_date": "2026-10-04",
    "notes": (
        "Cohort sealed before prospective scoring begins; any membership or "
        "parameter change requires a new audited cohort_version."
    ),
}
GENERATOR_CODES: tuple[str, ...] = (
    "null_model_benchmark",
    "top_k_frequency",
    "rolling_frequency",
    "bayesian_shrinkage",
)
DEFAULT_PICK_COUNT = 2
ROLLING_WINDOW = 200
BAYES_ALPHA = 5.0
BAYES_MU = 5 / 90
FALLBACK_ACTIVITY_DAYS = 7


@dataclass(frozen=True, slots=True)
class CohortMember:
    cohort_member_id: UUID
    model_version_id: UUID
    model_code: str
    draw_type_id: UUID | None
    parameters: Mapping[str, Any]
    seed: int | None


@dataclass(frozen=True, slots=True)
class GenerationResult:
    cohort_version_id: UUID | None
    targets: int
    created: int
    reused: int
    failed: int
    ineligible: int
    by_model: dict[str, int]


def _stable_seed(*parts: object) -> int:
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big")


# ---------------------------------------------------------------------------
# Cohort manifest
# ---------------------------------------------------------------------------

def ensure_default_cohort(connection: Any) -> UUID:
    """Register the sealed v1 prospective cohort. Idempotent via
    UNIQUE(cohort_id, definition_sha256)."""
    sha = hashlib.sha256(
        repr(sorted(DEFAULT_COHORT_DEFINITION.items())).encode()
    ).hexdigest()
    with connection.transaction():
        row = connection.execute(
            """INSERT INTO research.prospective_cohorts (cohort_id, code, display_name)
               VALUES (%s, %s, 'Prospective Turbo cohort v1')
               ON CONFLICT (code) DO NOTHING
               RETURNING cohort_id""",
            (uuid4(), DEFAULT_COHORT_CODE),
        ).fetchone()
        cohort_id = row[0] if row else connection.execute(
            "SELECT cohort_id FROM research.prospective_cohorts WHERE code = %s",
            (DEFAULT_COHORT_CODE,),
        ).fetchone()[0]
        row = connection.execute(
            """SELECT cohort_version_id FROM research.prospective_cohort_versions
               WHERE cohort_id = %s AND definition_sha256 = %s""",
            (cohort_id, sha),
        ).fetchone()
        if row is not None:
            return row[0]
        cohort_version_id = uuid4()
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM research.prospective_cohort_versions WHERE cohort_id = %s",
            (cohort_id,),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO research.prospective_cohort_versions
               (cohort_version_id, cohort_id, version, definition, definition_sha256,
                effective_from)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                cohort_version_id, cohort_id, version,
                Jsonb(DEFAULT_COHORT_DEFINITION), sha,
                date.fromisoformat(DEFAULT_COHORT_DEFINITION["start_date"]),
            ),
        )
        for code in GENERATOR_CODES:
            model_version_id = connection.execute(
                """SELECT model_version_id FROM research.model_versions
                   WHERE code = %s ORDER BY version DESC LIMIT 1""",
                (code,),
            ).fetchone()
            if model_version_id is None:
                continue
            seed = (
                _stable_seed(code, "prospective")
                if code == "null_model_benchmark"
                else None
            )
            connection.execute(
                """INSERT INTO research.prospective_cohort_members
                   (cohort_member_id, cohort_version_id, model_version_id,
                    draw_type_id, parameters, seed)
                   VALUES (%s, %s, %s, NULL, %s, %s)""",
                (
                    uuid4(), cohort_version_id, model_version_id[0],
                    Jsonb({"pick_count": DEFAULT_PICK_COUNT}), seed,
                ),
            )
    return cohort_version_id


def load_cohort(connection: Any, cohort_version_id: UUID) -> tuple[CohortMember, ...]:
    rows = connection.execute(
        """SELECT m.cohort_member_id, m.model_version_id, mv.code,
                  m.draw_type_id, m.parameters, m.seed
           FROM research.prospective_cohort_members m
           JOIN research.model_versions mv ON mv.model_version_id = m.model_version_id
           WHERE m.cohort_version_id = %s AND m.status = 'ACTIVE'
           ORDER BY mv.code""",
        (cohort_version_id,),
    ).fetchall()
    return tuple(
        CohortMember(r[0], r[1], r[2], r[3], r[4] or {}, r[5]) for r in rows
    )


def _cohort_definition(connection: Any, cohort_version_id: UUID) -> dict[str, Any]:
    row = connection.execute(
        "SELECT definition FROM research.prospective_cohort_versions WHERE cohort_version_id = %s",
        (cohort_version_id,),
    ).fetchone()
    return row[0] if row else {}


# ---------------------------------------------------------------------------
# Pickers — training data strictly before the target date
# ---------------------------------------------------------------------------

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
        numbers = numbers[: limit * 5]
    counts: dict[int, int] = {}
    for number in numbers:
        counts[number] = counts.get(number, 0) + 1
    return counts


def _top_k(counts: dict[int, int], k: int, score: Callable[[int], float]) -> list[int]:
    ranked = sorted(range(1, 91), key=lambda n: (-score(n), n))
    return sorted(ranked[:k])


def pick_null(
    connection: Any, draw_type_id: UUID, target: date,
    params: Mapping[str, Any], seed: int | None,
) -> list[int]:
    rng = random.Random(
        _stable_seed(seed or "null_model_benchmark", str(draw_type_id), target)
    )
    return sorted(rng.sample(range(1, 91), int(params.get("pick_count", DEFAULT_PICK_COUNT))))


def pick_top_k(
    connection: Any, draw_type_id: UUID, target: date,
    params: Mapping[str, Any], seed: int | None,
) -> list[int]:
    counts = _train_counts(connection, draw_type_id, target)
    return _top_k(counts, int(params.get("pick_count", DEFAULT_PICK_COUNT)),
                  lambda n: float(counts.get(n, 0)))


def pick_rolling(
    connection: Any, draw_type_id: UUID, target: date,
    params: Mapping[str, Any], seed: int | None,
) -> list[int]:
    counts = _train_counts(
        connection, draw_type_id, target,
        limit=int(params.get("window_draws", ROLLING_WINDOW)),
    )
    return _top_k(counts, int(params.get("pick_count", DEFAULT_PICK_COUNT)),
                  lambda n: float(counts.get(n, 0)))


def pick_bayesian(
    connection: Any, draw_type_id: UUID, target: date,
    params: Mapping[str, Any], seed: int | None,
) -> list[int]:
    counts = _train_counts(connection, draw_type_id, target)
    alpha = float(params.get("alpha", BAYES_ALPHA))
    n = sum(counts.values()) / 5 if counts else 0
    return _top_k(
        counts, int(params.get("pick_count", DEFAULT_PICK_COUNT)),
        lambda num: (counts.get(num, 0) + BAYES_MU * alpha) / (n + alpha),
    )


PICKERS: dict[str, Callable[[Any, UUID, date, Mapping[str, Any], int | None], list[int]]] = {
    "null_model_benchmark": pick_null,
    "top_k_frequency": pick_top_k,
    "rolling_frequency": pick_rolling,
    "bayesian_shrinkage": pick_bayesian,
}


# ---------------------------------------------------------------------------
# Targets and generation
# ---------------------------------------------------------------------------

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


def _coverage(
    connection: Any, *,
    draw_type_id: UUID, scheduled_date: date, draw_id: UUID | None,
    member: CohortMember, cohort_version_id: UUID,
    status: str, reason: str | None = None, prediction_id: UUID | None = None,
) -> None:
    connection.execute(
        """INSERT INTO research.prediction_coverage
               (coverage_id, draw_type_id, scheduled_date, draw_id,
                model_version_id, cohort_version_id, status, reason, prediction_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (draw_type_id, scheduled_date, model_version_id, cohort_version_id)
           DO UPDATE SET status = EXCLUDED.status, reason = EXCLUDED.reason,
                         prediction_id = COALESCE(EXCLUDED.prediction_id,
                                                  prediction_coverage.prediction_id),
                         draw_id = COALESCE(prediction_coverage.draw_id, EXCLUDED.draw_id),
                         recorded_at = CURRENT_TIMESTAMP""",
        (
            uuid4(), draw_type_id, scheduled_date, draw_id,
            member.model_version_id, cohort_version_id, status, reason, prediction_id,
        ),
    )


def _reconcile_coverage(connection: Any, cohort_version_id: UUID, effective_from: date) -> int:
    """Heal coverage gaps so every cohort pair has an explicit ledger row.

    Two cases, both idempotent:
    - predictions matching an active cohort member but lacking a coverage row
      (recorded before the ledger existed, or a failed coverage write) are
      linked back as GENERATED/reconciled;
    - settled/validated draws inside the cohort window whose model pair never
      produced a prediction nor a coverage row are marked MISSING, so silent
      absence is impossible.
    """
    healed = connection.execute(
        """INSERT INTO research.prediction_coverage
               (coverage_id, draw_type_id, scheduled_date, draw_id,
                model_version_id, cohort_version_id, status, reason, prediction_id)
           SELECT gen_random_uuid(), p.draw_type_id, p.scheduled_date,
                  p.target_draw_id, p.model_version_id, %s, 'GENERATED',
                  'reconciled: prediction predates coverage ledger',
                  p.prediction_id
           FROM research.predictions p
           JOIN research.prospective_cohort_members m
             ON m.model_version_id = p.model_version_id
            AND m.cohort_version_id = %s
            AND m.status = 'ACTIVE'
            AND (m.draw_type_id IS NULL OR m.draw_type_id = p.draw_type_id)
           LEFT JOIN research.prediction_coverage cov
             ON cov.draw_type_id = p.draw_type_id
            AND cov.scheduled_date = p.scheduled_date
            AND cov.model_version_id = p.model_version_id
            AND cov.cohort_version_id = %s
           WHERE cov.coverage_id IS NULL
           ON CONFLICT (draw_type_id, scheduled_date, model_version_id, cohort_version_id)
           DO NOTHING""",
        (cohort_version_id, cohort_version_id, cohort_version_id),
    )
    connection.execute(
        """INSERT INTO research.prediction_coverage
               (coverage_id, draw_type_id, scheduled_date, draw_id,
                model_version_id, cohort_version_id, status, reason)
           SELECT gen_random_uuid(), d.draw_type_id, d.scheduled_date, d.draw_id,
                  m.model_version_id, %s, 'MISSING',
                  'draw settled before generation evaluated this pair'
           FROM core.draws d
           JOIN research.prospective_cohort_members m
             ON m.cohort_version_id = %s
            AND m.status = 'ACTIVE'
            AND (m.draw_type_id IS NULL OR m.draw_type_id = d.draw_type_id)
           LEFT JOIN research.prediction_coverage cov
             ON cov.draw_type_id = d.draw_type_id
            AND cov.scheduled_date = d.scheduled_date
            AND cov.model_version_id = m.model_version_id
            AND cov.cohort_version_id = %s
           WHERE cov.coverage_id IS NULL
             AND d.scheduled_date >= %s
             AND d.scheduled_date <= CURRENT_DATE
             AND d.status IN ('FROZEN', 'SETTLED')
           ON CONFLICT (draw_type_id, scheduled_date, model_version_id, cohort_version_id)
           DO NOTHING""",
        (cohort_version_id, cohort_version_id, cohort_version_id, effective_from),
    )
    return healed.rowcount or 0


def generate_predictions(
    connection: Any,
    *,
    cohort_code: str = DEFAULT_COHORT_CODE,
    today: date | None = None,
) -> GenerationResult:
    """Record one prediction per (target, active cohort member).

    Idempotent via the predictions unique key; every outcome lands in
    research.prediction_coverage.
    """
    today = today or date.today()
    cohort = connection.execute(
        "SELECT cohort_id FROM research.prospective_cohorts WHERE code = %s",
        (cohort_code,),
    ).fetchone()
    if cohort is None:
        return GenerationResult(None, 0, 0, 0, 0, 0, {})
    cohort_version_id, effective_from = connection.execute(
        """SELECT cohort_version_id, effective_from
           FROM research.prospective_cohort_versions
           WHERE cohort_id = %s ORDER BY version DESC LIMIT 1""",
        (cohort[0],),
    ).fetchone()
    definition = _cohort_definition(connection, cohort_version_id)
    members = load_cohort(connection, cohort_version_id)
    _reconcile_coverage(connection, cohort_version_id, effective_from)
    targets = _targets(connection, today)
    dataset_version_id = _latest_dataset_version(connection)
    stake = float(definition.get("stake", 100))

    created = reused = failed = ineligible = 0
    by_model: dict[str, int] = {}
    for draw_type_id, scheduled_date, draw_id in targets:
        covered_any = False
        for member in members:
            if member.draw_type_id is not None and member.draw_type_id != draw_type_id:
                _coverage(
                    connection, draw_type_id=draw_type_id, scheduled_date=scheduled_date,
                    draw_id=draw_id, member=member, cohort_version_id=cohort_version_id,
                    status="INELIGIBLE", reason="draw_type not in member scope",
                )
                ineligible += 1
                continue
            picker = PICKERS.get(member.model_code)
            covered_any = True
            if picker is None:
                _coverage(
                    connection, draw_type_id=draw_type_id, scheduled_date=scheduled_date,
                    draw_id=draw_id, member=member, cohort_version_id=cohort_version_id,
                    status="FAILED", reason=f"no picker for model {member.model_code}",
                )
                failed += 1
                continue
            try:
                numbers = picker(connection, draw_type_id, scheduled_date,
                                 member.parameters, member.seed)
                if not numbers:
                    raise ValueError("picker returned no candidates")
                prediction = record_prediction(
                    connection,
                    model_version_id=member.model_version_id,
                    draw_type_id=draw_type_id,
                    scheduled_date=scheduled_date,
                    predicted_numbers=numbers,
                    dataset_version_id=dataset_version_id,
                    parameters={
                        **dict(member.parameters),
                        "generator": member.model_code,
                        "cohort_version_id": str(cohort_version_id),
                        "seed": member.seed,
                    },
                    stake=stake,
                )
            except Exception as exc:  # noqa: BLE001 - one member must not kill the batch
                _coverage(
                    connection, draw_type_id=draw_type_id, scheduled_date=scheduled_date,
                    draw_id=draw_id, member=member, cohort_version_id=cohort_version_id,
                    status="FAILED", reason=str(exc)[:500],
                )
                emit_event(
                    connection, "PREDICTION_GENERATION_FAILED",
                    {"draw_type_id": str(draw_type_id), "date": str(scheduled_date),
                     "model": member.model_code, "error": str(exc)[:500]},
                )
                failed += 1
                continue
            _coverage(
                connection, draw_type_id=draw_type_id, scheduled_date=scheduled_date,
                draw_id=draw_id, member=member, cohort_version_id=cohort_version_id,
                status="GENERATED", prediction_id=prediction.prediction_id,
            )
            by_model[member.model_code] = by_model.get(member.model_code, 0) + 1
            if prediction.created:
                created += 1
            else:
                reused += 1
        if not covered_any:
            emit_event(
                connection, "TARGET_WITHOUT_COHORT",
                {"draw_type_id": str(draw_type_id), "date": str(scheduled_date)},
            )
    return GenerationResult(
        cohort_version_id, len(targets), created, reused, failed, ineligible, by_model
    )
