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
GENERATION_HORIZON_DAYS = 7
WEEKDAY_INFERENCE_DAYS = 56


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


def _history(
    connection: Any, draw_type_id: UUID, before: date
) -> list[list[int]]:
    """Chronological winning-number lists (latest VALID version per draw),
    position-ordered — the `hist` input of the legacy lab models."""
    rows = connection.execute(
        """SELECT d.scheduled_date, dn.number
           FROM core.draws d
           JOIN LATERAL (
               SELECT draw_version_id FROM core.draw_versions
               WHERE draw_id = d.draw_id AND validation_status = 'VALID'
               ORDER BY version_number DESC LIMIT 1
           ) v ON true
           JOIN core.draw_numbers dn
             ON dn.draw_version_id = v.draw_version_id
            AND dn.number_role = 'WINNING'
           WHERE d.draw_type_id = %s AND d.scheduled_date < %s
           ORDER BY d.scheduled_date, dn.position""",
        (draw_type_id, before),
    ).fetchall()
    hist: list[list[int]] = []
    current: list[int] = []
    current_date = None
    for draw_date, number in rows:
        if draw_date != current_date:
            if current:
                hist.append(current)
            current, current_date = [number], draw_date
        else:
            current.append(number)
    if current:
        hist.append(current)
    return hist


# ---------------------------------------------------------------------------
# Lab pickers — deterministic cores live in lab_models.py (shared with the
# matrix evaluation); these wrappers just load history and seed the rng.
# ---------------------------------------------------------------------------

from lottery_intelligence_platform import (calling_image, lab_models,
                                           meta_ensemble)
from lottery_intelligence_platform.digital_root_picker import (
    pick_digital_root_turbo,
    pick_digital_root_turbo_v2,
)

# Hist-functions available to cohort pickers: the ported lab models plus the
# CALLING_IMAGE and META_ENSEMBLE families (same (hist, rng, k) interface).
_HIST_REGISTRY: dict[str, Any] = {
    **lab_models.HIST_MODELS,
    **calling_image.CALLING_IMAGE_MODELS,
    **meta_ensemble.META_ENSEMBLE_MODELS,
}


def _rng(seed: int | None, code: str, draw_type_id: UUID, target: date) -> random.Random:
    return random.Random(_stable_seed(seed or code, str(draw_type_id), target))


def _lab_picker(
    code: str, *,
    stochastic: bool,
) -> Callable[[Any, UUID, date, Mapping[str, Any], int | None], list[int]]:
    """Adapt a lab_models hist-function to the cohort picker signature."""
    fn = _HIST_REGISTRY[code]

    def pick(
        connection: Any, draw_type_id: UUID, target: date,
        params: Mapping[str, Any], seed: int | None,
    ) -> list[int]:
        k = int(params.get("pick_count", DEFAULT_PICK_COUNT))
        hist = _history(connection, draw_type_id, target)
        rng = _rng(seed, code, draw_type_id, target) if stochastic else random.Random(0)
        return fn(hist, rng, k)

    return pick


pick_hot_frequency_v1 = _lab_picker("hot_frequency_v1", stochastic=False)
pick_cold_delay_v1 = _lab_picker("cold_delay_v1", stochastic=False)
pick_frequency_delay_v1 = _lab_picker("frequency_delay_v1", stochastic=False)
pick_pair_frequency_v1 = _lab_picker("pair_frequency_v1", stochastic=False)
pick_balanced_v1 = _lab_picker("balanced_v1", stochastic=False)
pick_bayesian_v1 = _lab_picker("bayesian_v1", stochastic=True)
pick_monte_carlo_v1 = _lab_picker("monte_carlo_v1", stochastic=True)
pick_ensemble_v1 = _lab_picker("ensemble_v1", stochastic=False)
pick_calling_numbers = _lab_picker("calling_numbers", stochastic=False)
pick_image_numbers = _lab_picker("image_numbers", stochastic=False)
pick_calling_image = _lab_picker("calling_image", stochastic=False)
pick_calling_image_position = _lab_picker("calling_image_position", stochastic=False)
pick_meta_consensus_count = _lab_picker("meta_consensus_count", stochastic=False)
pick_meta_consensus_family = _lab_picker("meta_consensus_family", stochastic=False)



PICKERS: dict[str, Callable[[Any, UUID, date, Mapping[str, Any], int | None], list[int]]] = {
    "null_model_benchmark": pick_null,
    "top_k_frequency": pick_top_k,
    "rolling_frequency": pick_rolling,
    "bayesian_shrinkage": pick_bayesian,
    "random": pick_null,
    "hot_frequency_v1": pick_hot_frequency_v1,
    "cold_delay_v1": pick_cold_delay_v1,
    "frequency_delay_v1": pick_frequency_delay_v1,
    "pair_frequency_v1": pick_pair_frequency_v1,
    "balanced_v1": pick_balanced_v1,
    "bayesian_v1": pick_bayesian_v1,
    "monte_carlo_v1": pick_monte_carlo_v1,
    "ensemble_v1": pick_ensemble_v1,
    "calling_numbers": pick_calling_numbers,
    "image_numbers": pick_image_numbers,
    "calling_image": pick_calling_image,
    "calling_image_position": pick_calling_image_position,
    "meta_consensus_count": pick_meta_consensus_count,
    "meta_consensus_family": pick_meta_consensus_family,
    "digital_root_turbo": pick_digital_root_turbo,
    "digital_root_turbo_v2": pick_digital_root_turbo_v2,
}

LAB_GENERATOR_CODES: tuple[str, ...] = tuple(
    code for code in PICKERS if code not in GENERATOR_CODES
)

# Families used when registering the lab models into research.model_versions.
LAB_MODEL_FAMILIES: dict[str, str] = {
    "random": "BENCHMARK",
    "hot_frequency_v1": "PREDICTIVE",
    "cold_delay_v1": "PREDICTIVE",
    "frequency_delay_v1": "PREDICTIVE",
    "pair_frequency_v1": "PREDICTIVE",
    "balanced_v1": "PREDICTIVE",
    "bayesian_v1": "PREDICTIVE",
    "monte_carlo_v1": "PREDICTIVE",
    "ensemble_v1": "PREDICTIVE",
    # research.model_versions.family is a coarse enum (CHECK constraint);
    # the CALLING_IMAGE grouping lives in the codes, the picker registry and
    # the catalog — at the DB level these are predictive candidates.
    "calling_numbers": "PREDICTIVE",
    "image_numbers": "PREDICTIVE",
    "calling_image": "PREDICTIVE",
    "calling_image_position": "PREDICTIVE",
    # Meta-ensemble: deterministic consensus over the lab pickers.
    "meta_consensus_count": "ENSEMBLE",
    "meta_consensus_family": "ENSEMBLE",
    # Digital Root Turbo: temporary relation-based predictions
    "digital_root_turbo": "PREDICTIVE",
    "digital_root_turbo_v2": "PREDICTIVE",
}
_STOCHASTIC_CODES = {"random", "bayesian_v1", "monte_carlo_v1"}
CALLING_IMAGE_CODES = frozenset(calling_image.CALLING_IMAGE_MODELS)


def register_lab_cohort(
    connection: Any, *, cohort_code: str = DEFAULT_COHORT_CODE
) -> dict[str, Any]:
    """Extend the prospective cohort with the lab models (audited new version).

    Registers model_versions for every picker code missing one, then creates a
    new cohort_version containing all ACTIVE members of the latest version plus
    the new lab models. Cohort content is append-only: the old version is
    untouched, generation simply reads the latest version.
    """
    from lottery_intelligence_platform.models import register_model_version

    cohort = connection.execute(
        "SELECT cohort_id FROM research.prospective_cohorts WHERE code = %s",
        (cohort_code,),
    ).fetchone()
    if cohort is None:
        raise RuntimeError(f"cohort {cohort_code} not found — run generation first")
    cohort_id = cohort[0]
    latest = connection.execute(
        """SELECT cohort_version_id, definition FROM research.prospective_cohort_versions
           WHERE cohort_id = %s ORDER BY version DESC LIMIT 1""",
        (cohort_id,),
    ).fetchone()
    old_version_id, definition = latest

    registered: list[str] = []
    model_ids: dict[str, UUID] = {}
    for code in PICKERS:
        if code in GENERATOR_CODES:
            row = connection.execute(
                "SELECT model_version_id FROM research.model_versions WHERE code = %s ORDER BY version DESC LIMIT 1",
                (code,),
            ).fetchone()
            if row:
                model_ids[code] = row[0]
            continue
        mv = register_model_version(
            connection, code=code,
            family=LAB_MODEL_FAMILIES.get(code, "PREDICTIVE"),
            definition={
                "picker": code, "pick_count": DEFAULT_PICK_COUNT,
                "source": (
                    "calling_image.py grid/image hypothesis"
                    if code in CALLING_IMAGE_CODES
                    else "lottery-statistics-expert models/models.py"
                ),
                "stochastic": code in _STOCHASTIC_CODES,
            },
        )
        model_ids[code] = mv.model_version_id
        if mv.created:
            registered.append(code)
    if not registered:
        return {"registered": [], "cohort_version_created": False}

    with connection.transaction():
        existing_members = connection.execute(
            """SELECT model_version_id, draw_type_id, parameters, seed
               FROM research.prospective_cohort_members
               WHERE cohort_version_id = %s AND status = 'ACTIVE'""",
            (old_version_id,),
        ).fetchall()
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM research.prospective_cohort_versions WHERE cohort_id = %s",
            (cohort_id,),
        ).fetchone()[0]
        new_definition = {
            **dict(definition),
            "models": sorted(model_ids),
            "notes": (
                "v2: lab cohort — deterministic + stochastic pickers ported "
                "from lottery-statistics-expert; prospective evaluation vs "
                "null_model_benchmark unchanged."
            ),
        }
        sha = hashlib.sha256(
            repr(sorted(new_definition.items())).encode()
        ).hexdigest()
        new_version_id = uuid4()
        connection.execute(
            """INSERT INTO research.prospective_cohort_versions
               (cohort_version_id, cohort_id, version, definition, definition_sha256,
                effective_from)
               VALUES (%s, %s, %s, %s, %s, CURRENT_DATE + 1)""",
            (new_version_id, cohort_id, version, Jsonb(new_definition), sha),
        )
        for mv_id, dt_id, params, s in existing_members:
            connection.execute(
                """INSERT INTO research.prospective_cohort_members
                   (cohort_member_id, cohort_version_id, model_version_id,
                    draw_type_id, parameters, seed)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (uuid4(), new_version_id, mv_id, dt_id,
                 Jsonb(params) if params is not None else None, s),
            )
        for code in registered:
            seed = (
                _stable_seed(code, "prospective")
                if code in _STOCHASTIC_CODES
                else None
            )
            connection.execute(
                """INSERT INTO research.prospective_cohort_members
                   (cohort_member_id, cohort_version_id, model_version_id,
                    draw_type_id, parameters, seed)
                   VALUES (%s, %s, %s, NULL, %s, %s)""",
                (uuid4(), new_version_id, model_ids[code],
                 Jsonb({"pick_count": DEFAULT_PICK_COUNT}), seed),
            )
    return {
        "registered": registered,
        "cohort_version_created": True,
        "cohort_version_id": str(new_version_id),
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
    over the horizon, unioned with per-type weekday projections so a draw that
    only appears on the official schedule hours before happening is still
    covered by a prediction recorded well in advance."""
    horizon = today + timedelta(days=GENERATION_HORIZON_DAYS)
    rows = connection.execute(
        """SELECT draw_type_id, scheduled_date, draw_id FROM core.draws
           WHERE status IN ('SCHEDULED', 'EXPECTED')
             AND scheduled_date >= %s AND scheduled_date <= %s
             AND NOT EXISTS (
                 SELECT 1 FROM core.draw_versions dv
                 WHERE dv.draw_id = draws.draw_id AND dv.validation_status = 'VALID'
             )
           ORDER BY scheduled_date""",
        (today, horizon),
    ).fetchall()
    targets: dict[tuple[UUID, date], tuple[UUID, date, UUID | None]] = {
        (r[0], r[1]): (r[0], r[1], r[2]) for r in rows
    }
    # Fallback projection: each recently-active type's observed draw weekdays
    # over the horizon — a weekly type gets one target, a daily type gets
    # seven. Pairs already covered by an EXPECTED draw are skipped.
    projected = connection.execute(
        """WITH active AS (
               SELECT DISTINCT draw_type_id FROM core.draws
               WHERE scheduled_date >= %s AND status IN ('FROZEN', 'SETTLED')
           ),
           weekdays AS (
               SELECT draw_type_id,
                      array_agg(DISTINCT extract(isodow FROM scheduled_date)::int) AS dows
               FROM core.draws
               WHERE scheduled_date >= %s AND status IN ('FROZEN', 'SETTLED')
               GROUP BY draw_type_id
           )
           SELECT w.draw_type_id, gs::date
           FROM weekdays w
           JOIN active a ON a.draw_type_id = w.draw_type_id
           CROSS JOIN LATERAL generate_series(%s::date, %s::date, '1 day') gs
           WHERE extract(isodow FROM gs)::int = ANY(w.dows)
           ORDER BY gs, w.draw_type_id""",
        (
            today - timedelta(days=FALLBACK_ACTIVITY_DAYS),
            today - timedelta(days=WEEKDAY_INFERENCE_DAYS),
            today + timedelta(days=1), horizon,
        ),
    ).fetchall()
    for draw_type_id, scheduled_date in projected:
        targets.setdefault((draw_type_id, scheduled_date), (draw_type_id, scheduled_date, None))
    return sorted(targets.values(), key=lambda t: (t[1], str(t[0])))


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
