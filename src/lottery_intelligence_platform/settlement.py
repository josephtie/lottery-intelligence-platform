"""Per-draw settlement pipeline.

    DETECTED -> ... -> FROZEN -> LOCK predictions -> SETTLE predictions
        -> SETTLE turbo variants -> SETTLE strategies -> draw SETTLED

Every step is idempotent: re-running ``settle_draw`` on an already-settled
draw is a no-op; concurrent workers serialize on the draw row lock and on
the UNIQUE(prediction_id) outcome constraint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.scheduler import emit_event

DEFAULT_TURBO_STAKE = 100.0
TURBO_POSITIONS: dict[str, int] = {"turbo_2": 2, "turbo_3": 3, "turbo_4": 4, "turbo_5": 5}

IMUTABLE_VIOLATION = "IMMUTABLE_PREDICTION_VIOLATION"


@dataclass(frozen=True, slots=True)
class SettleResult:
    draw_id: UUID
    status: str
    predictions_locked: int
    predictions_scored: int
    predictions_invalidated: int
    strategy_settlements: int


def positional_hit_counts(predicted: Sequence[int], ordered_winning: Sequence[int]) -> dict[str, int]:
    """Number of predicted numbers found within the first k positions."""
    predicted_set = set(predicted)
    return {
        f"first_{k}": len(predicted_set & set(ordered_winning[:k]))
        for k in range(1, len(ordered_winning) + 1)
    }


def turbo_settlement(
    predicted: Sequence[int],
    ordered_winning: Sequence[int],
    *,
    stake: float,
    multipliers: Mapping[str, float],
    positions_by_variant: Mapping[str, int] = TURBO_POSITIONS,
) -> dict[str, dict[str, float | bool]]:
    """Positional Turbo evaluation for each variant.

    Hit = every predicted number appears among the first k drawn positions.
    """
    predicted_set = set(predicted)
    results: dict[str, dict[str, float | bool]] = {}
    for variant, k in positions_by_variant.items():
        first_k = set(ordered_winning[:k])
        hit = predicted_set <= first_k
        multiplier = float(multipliers.get(str(k), 0.0))
        payout = stake * multiplier if hit else 0.0
        results[variant] = {
            "hit": hit,
            "stake": stake,
            "payout": payout,
            "net": payout - stake,
            "roi": (payout - stake) / stake if stake else 0.0,
            "positions": k,
            "multiplier": multiplier,
        }
    return results


def _canonical_draw_version(connection: Any, draw_id: UUID) -> tuple[Any, ...] | None:
    return connection.execute(
        """SELECT dv.draw_version_id, dv.result_observed_at
           FROM core.draw_versions dv
           WHERE dv.draw_id = %s
             AND dv.validation_status = 'VALID'
             AND EXISTS (
                 SELECT 1 FROM core.draw_numbers dn
                 WHERE dn.draw_version_id = dv.draw_version_id
                   AND dn.number_role = 'WINNING'
             )
           ORDER BY dv.version_number DESC
           LIMIT 1""",
        (draw_id,),
    ).fetchone()


def _ordered_winning(connection: Any, draw_version_id: UUID) -> list[int]:
    return [
        row[0]
        for row in connection.execute(
            """SELECT number FROM core.draw_numbers
               WHERE draw_version_id = %s AND number_role = 'WINNING'
               ORDER BY position""",
            (draw_version_id,),
        ).fetchall()
    ]


def _audit_rejected(
    connection: Any,
    *,
    actor: str,
    action: str,
    entity_id: UUID | None,
    previous: Mapping[str, Any] | None,
    attempted: Mapping[str, Any] | None,
) -> None:
    connection.execute(
        """INSERT INTO ops.audit_events
               (audit_event_id, actor, action, entity_type, entity_id,
                previous_value, attempted_value, outcome)
           VALUES (%s, %s, %s, 'research.predictions', %s, %s, %s, 'REJECTED')""",
        (uuid4(), actor, action, entity_id,
         Jsonb(previous) if previous else None,
         Jsonb(attempted) if attempted else None),
    )


def _raise_alert(
    connection: Any,
    *,
    code: str,
    severity: str,
    entity_id: UUID | None = None,
    details: Mapping[str, Any] | None = None,
    dedupe_key: str | None = None,
    dedupe_window_seconds: int = 3600,
) -> None:
    """Insert an alert, deduplicated by (dedupe_key) within a time window."""
    key = dedupe_key or f"{code}:{entity_id}"
    exists = connection.execute(
        """SELECT 1 FROM ops.alerts
           WHERE dedupe_key = %s
             AND raised_at > CURRENT_TIMESTAMP - make_interval(secs => %s)
           LIMIT 1""",
        (key, dedupe_window_seconds),
    ).fetchone()
    if exists:
        return
    connection.execute(
        """INSERT INTO ops.alerts
               (alert_id, code, severity, entity_type, entity_id, details, dedupe_key)
           VALUES (%s, %s, %s, 'research.predictions', %s, %s, %s)""",
        (uuid4(), code, severity, entity_id, Jsonb(dict(details or {})), key),
    )


def _dataset_has_leakage(connection: Any, dataset_version_id: UUID, scheduled_date) -> bool:
    """True if the prediction's dataset contains draws on/after its target date."""
    row = connection.execute(
        """SELECT MAX(d.scheduled_date)
           FROM datasets.dataset_members m
           JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
           JOIN core.draws d ON d.draw_id = dv.draw_id
           WHERE m.dataset_version_id = %s""",
        (dataset_version_id,),
    ).fetchone()
    return bool(row and row[0] and row[0] >= scheduled_date)


def _payout_multipliers(
    connection: Any, strategy_version_id: UUID | None, draw_id: UUID
) -> Mapping[str, float]:
    """Resolve multipliers from the strategy's payout rule version, falling
    back to the rule in force on the draw date: highest effective_from that
    covers the draw's scheduled_date on its game_version, verified official
    rules preferred over provisional ones."""
    row = None
    if strategy_version_id is not None:
        row = connection.execute(
            """SELECT prv.rule_definition
               FROM research.strategy_versions sv
               JOIN catalog.payout_rule_versions prv
                 ON prv.payout_rule_version_id = sv.payout_rule_version_id
               WHERE sv.strategy_version_id = %s""",
            (strategy_version_id,),
        ).fetchone()
    if row is None:
        row = connection.execute(
            """SELECT prv.rule_definition
               FROM catalog.payout_rule_versions prv
               JOIN core.draws d ON d.game_version_id = prv.game_version_id
               WHERE d.draw_id = %s
                 AND prv.effective_from <= d.scheduled_date
                 AND (prv.effective_to IS NULL OR d.scheduled_date <= prv.effective_to)
               ORDER BY (prv.rule_definition->>'verification_status' = 'VERIFIED_OFFICIAL') DESC,
                        prv.effective_from DESC
               LIMIT 1""",
            (draw_id,),
        ).fetchone()
    if row is None:
        # Game-level fallback: the draw's game_version carries no rule (e.g.
        # synthetic or newly created version) — take the game's verified rule
        # covering the draw date, whatever version it was registered under.
        row = connection.execute(
            """SELECT prv.rule_definition
               FROM catalog.payout_rule_versions prv
               JOIN core.draws d ON d.game_id = prv.game_id
               WHERE d.draw_id = %s
                 AND prv.effective_from <= d.scheduled_date
                 AND (prv.effective_to IS NULL OR d.scheduled_date <= prv.effective_to)
               ORDER BY (prv.rule_definition->>'verification_status' = 'VERIFIED_OFFICIAL') DESC,
                        prv.effective_from DESC
               LIMIT 1""",
            (draw_id,),
        ).fetchone()
    if row is None:
        return {}
    definition = row[0]
    return definition.get("payout_multipliers", {})


def attempt_prediction_amendment(
    connection: Any,
    prediction_id: UUID,
    *,
    actor: str,
    new_numbers: Sequence[int],
) -> str:
    """Controlled amendment path: locked/scored/invalid predictions are
    rejected by the trigger; the attempt is audited and alerted.

    Returns 'REJECTED' or 'ALLOWED'.
    """
    previous = connection.execute(
        "SELECT status, predicted_numbers FROM research.predictions WHERE prediction_id = %s",
        (prediction_id,),
    ).fetchone()
    if previous is None:
        raise KeyError(f"unknown prediction: {prediction_id}")
    try:
        with connection.transaction():
            connection.execute(
                "UPDATE research.predictions SET predicted_numbers = %s WHERE prediction_id = %s",
                (sorted(set(int(n) for n in new_numbers)), prediction_id),
            )
    except Exception as exc:
        if "IMMUTABLE_PREDICTION_VIOLATION" not in str(exc):
            raise
        with connection.transaction():
            _audit_rejected(
                connection, actor=actor, action="AMEND_PREDICTION",
                entity_id=prediction_id,
                previous={"status": previous[0], "predicted_numbers": list(previous[1])},
                attempted={"predicted_numbers": sorted(set(int(n) for n in new_numbers))},
            )
            _raise_alert(
                connection, code="IMMUTABLE_PREDICTION_VIOLATION", severity="CRITICAL",
                entity_id=prediction_id,
                details={"actor": actor, "status": previous[0]},
            )
        return "REJECTED"
    with connection.transaction():
        connection.execute(
            """INSERT INTO ops.audit_events
                   (audit_event_id, actor, action, entity_type, entity_id,
                    previous_value, attempted_value, outcome)
               VALUES (%s, %s, 'AMEND_PREDICTION', 'research.predictions', %s, %s, %s, 'ALLOWED')""",
            (uuid4(), actor, prediction_id,
             Jsonb({"status": previous[0], "predicted_numbers": list(previous[1])}),
             Jsonb({"predicted_numbers": sorted(set(int(n) for n in new_numbers))})),
        )
    return "ALLOWED"


def settle_draw(
    connection: Any,
    draw_id: UUID,
    *,
    actor: str = "settle_predictions",
    job_run_id: UUID | None = None,
) -> SettleResult:
    """Run the full settlement cascade for one draw in a single transaction."""
    with connection.transaction():
        draw = connection.execute(
            """SELECT status, draw_type_id, scheduled_date FROM core.draws
               WHERE draw_id = %s FOR UPDATE""",
            (draw_id,),
        ).fetchone()
        if draw is None:
            raise KeyError(f"unknown draw: {draw_id}")
        status, draw_type_id, scheduled_date = draw
        if status == "SETTLED":
            return SettleResult(draw_id, "ALREADY_SETTLED", 0, 0, 0, 0)

        canonical = _canonical_draw_version(connection, draw_id)
        if canonical is None:
            emit_event(
                connection, "SETTLEMENT_SKIPPED",
                {"draw_id": str(draw_id), "reason": "no_valid_result"},
                job_run_id=job_run_id,
            )
            return SettleResult(draw_id, "NO_VALID_RESULT", 0, 0, 0, 0)
        draw_version_id, result_observed_at = canonical
        winning = _ordered_winning(connection, draw_version_id)

        # ---- LOCK STAGE ----------------------------------------------------
        locked = invalidated = 0
        pending = connection.execute(
            """SELECT prediction_id, created_at, dataset_version_id
               FROM research.predictions
               WHERE draw_type_id = %s AND scheduled_date = %s AND status = 'PENDING'
               ORDER BY created_at
               FOR UPDATE""",
            (draw_type_id, scheduled_date),
        ).fetchall()
        for prediction_id, created_at, dataset_version_id in pending:
            if created_at >= result_observed_at:
                connection.execute(
                    "UPDATE research.predictions SET status = 'INVALID' WHERE prediction_id = %s",
                    (prediction_id,),
                )
                _audit_rejected(
                    connection, actor=actor, action="LATE_PREDICTION",
                    entity_id=prediction_id,
                    previous={"status": "PENDING", "created_at": created_at.isoformat()},
                    attempted={"result_observed_at": result_observed_at.isoformat()},
                )
                invalidated += 1
                continue
            if dataset_version_id is not None and _dataset_has_leakage(
                connection, dataset_version_id, scheduled_date
            ):
                connection.execute(
                    "UPDATE research.predictions SET status = 'INVALID' WHERE prediction_id = %s",
                    (prediction_id,),
                )
                _raise_alert(
                    connection, code="LEAKAGE_DETECTED", severity="CRITICAL",
                    entity_id=prediction_id,
                    details={
                        "draw_id": str(draw_id),
                        "dataset_version_id": str(dataset_version_id),
                        "scheduled_date": str(scheduled_date),
                    },
                )
                invalidated += 1
                continue
            connection.execute(
                """UPDATE research.predictions
                   SET status = 'LOCKED', locked_at = CURRENT_TIMESTAMP,
                       target_draw_id = %s
                   WHERE prediction_id = %s""",
                (draw_id, prediction_id),
            )
            locked += 1

        # ---- SETTLE PREDICTIONS --------------------------------------------
        scored = 0
        to_settle = connection.execute(
            """SELECT prediction_id, predicted_numbers, strategy_version_id, stake,
                      created_at
               FROM research.predictions
               WHERE draw_type_id = %s AND scheduled_date = %s AND status = 'LOCKED'
               ORDER BY created_at
               FOR UPDATE""",
            (draw_type_id, scheduled_date),
        ).fetchall()
        settlements_by_strategy: dict[UUID, list[dict[str, Any]]] = {}
        multipliers = _payout_multipliers(
            connection, to_settle[0][2] if to_settle else None, draw_id
        )
        for prediction_id, predicted, strategy_version_id, stake, created_at in to_settle:
            effective_stake = float(stake) if stake is not None else DEFAULT_TURBO_STAKE
            turbo = (
                turbo_settlement(predicted, winning, stake=effective_stake, multipliers=multipliers)
                if multipliers
                else {}
            )
            outcome = {
                "positional_hits": positional_hit_counts(predicted, winning),
                "turbo": turbo,
            }
            inserted = connection.execute(
                """INSERT INTO research.prediction_outcomes
                       (outcome_id, prediction_id, draw_id, draw_version_id,
                        predicted_numbers, winning_numbers, hit_count,
                        positional_hits, metrics)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (prediction_id) DO NOTHING
                   RETURNING outcome_id""",
                (
                    uuid4(), prediction_id, draw_id, draw_version_id,
                    sorted(set(predicted)), winning, len(set(predicted) & set(winning)),
                    Jsonb(outcome["positional_hits"]),
                    Jsonb({"turbo": turbo, "stake": effective_stake}),
                ),
            ).fetchone()
            if inserted is not None:
                connection.execute(
                    """INSERT INTO research.prediction_scores
                           (prediction_score_id, prediction_id, draw_version_id, hits, details)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (prediction_id) DO NOTHING""",
                    (
                        uuid4(), prediction_id, draw_version_id,
                        len(set(predicted) & set(winning)),
                        Jsonb({
                            "predicted_numbers": sorted(set(predicted)),
                            "winning_numbers": winning,
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
            if strategy_version_id is not None:
                settlements_by_strategy.setdefault(strategy_version_id, []).append(
                    {"prediction_id": prediction_id, "turbo": turbo, "stake": effective_stake}
                )

        # ---- SETTLE STRATEGIES (REALIZED scope) ----------------------------
        strategy_rows = 0
        for strategy_version_id, items in settlements_by_strategy.items():
            for variant in TURBO_POSITIONS:
                total_stake = sum(item["stake"] for item in items)
                total_payout = sum(item["turbo"][variant]["payout"] for item in items) if items and items[0]["turbo"] else 0.0
                net = total_payout - total_stake
                connection.execute(
                    """INSERT INTO research.strategy_settlements
                           (settlement_id, strategy_version_id, draw_id, draw_version_id,
                            prediction_id, scope, variant, total_stake, total_payout,
                            net_profit, roi, metrics)
                       VALUES (%s, %s, %s, %s, %s, 'REALIZED', %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (strategy_version_id, draw_id, variant, scope) DO NOTHING""",
                    (
                        uuid4(), strategy_version_id, draw_id, draw_version_id,
                        items[0]["prediction_id"], variant, total_stake, total_payout,
                        net, net / total_stake if total_stake else None,
                        Jsonb({"predictions": len(items)}),
                    ),
                )
                strategy_rows += 1

        # ---- DRAW STATUS ----------------------------------------------------
        if status == "CONFIRMED":
            connection.execute(
                "UPDATE core.draws SET status = 'FROZEN' WHERE draw_id = %s", (draw_id,)
            )
            emit_event(connection, "DRAW_FROZEN", {"draw_id": str(draw_id)}, job_run_id=job_run_id)
            status = "FROZEN"
        if status == "FROZEN":
            connection.execute(
                "UPDATE core.draws SET status = 'SETTLED' WHERE draw_id = %s", (draw_id,)
            )
            emit_event(
                connection, "PREDICTIONS_SETTLED",
                {"draw_id": str(draw_id), "locked": locked, "scored": scored,
                 "invalidated": invalidated, "strategy_settlements": strategy_rows},
                job_run_id=job_run_id,
            )
            status = "SETTLED"

        return SettleResult(draw_id, status, locked, scored, invalidated, strategy_rows)


def settle_pending_draws(
    connection: Any,
    *,
    actor: str = "settle_predictions",
    job_run_id: UUID | None = None,
    limit: int = 500,
) -> dict[str, int]:
    """Settle every FROZEN/CONFIRMED draw that has a valid result and is not
    yet settled. Each draw settles in its own transaction so one bad draw
    cannot poison the batch."""
    draws = connection.execute(
        """SELECT draw_id FROM core.draws
           WHERE status IN ('FROZEN', 'CONFIRMED')
           ORDER BY scheduled_date
           LIMIT %s""",
        (limit,),
    ).fetchall()
    counts = {"settled": 0, "skipped": 0, "scored": 0, "invalidated": 0}
    for (draw_id,) in draws:
        result = settle_draw(connection, draw_id, actor=actor, job_run_id=job_run_id)
        if result.status == "SETTLED":
            counts["settled"] += 1
            counts["scored"] += result.predictions_scored
            counts["invalidated"] += result.predictions_invalidated
        else:
            counts["skipped"] += 1
    return counts
