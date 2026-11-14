from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.frequency_baseline import NUMBERS_PER_DRAW
from lottery_intelligence_platform.research import ResearchError, canonical_sha256
from lottery_intelligence_platform.walkforward import _number_counts_by_type
from lottery_intelligence_platform.frequency_baseline import NUMBERS_MIN

EVALUATOR_VERSION = "v2-individual-draws"


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    strategy_version_id: UUID
    strategy_id: UUID
    version: int
    definition_sha256: str
    status: str
    created: bool


def ensure_turbo_payout_rule(
    connection: Any,
    *,
    game_id: UUID,
    game_version_id: UUID,
    source_id: UUID,
) -> UUID:
    rule_definition = {
        "kind": "fixed_multiplier",
        "bet": "all_selected_numbers_must_match",
        "payout_multipliers": {"2": 2400, "3": 800, "4": 400, "5": 240},
        "verification_status": "UNVERIFIED",
        "note": "Turbo multipliers from project specification; must be confirmed against the official rules before any economic conclusion.",
    }
    with connection.transaction():
        rule_id = uuid4()
        inserted = connection.execute(
            """INSERT INTO catalog.payout_rules (payout_rule_id, game_id, code, display_name)
               VALUES (%s, %s, 'turbo_fixed_odds', 'Loto Bonheur Turbo fixed odds')
               ON CONFLICT (game_id, code) DO NOTHING
               RETURNING payout_rule_id""",
            (rule_id, game_id),
        ).fetchone()
        payout_rule_id = inserted[0] if inserted else connection.execute(
            "SELECT payout_rule_id FROM catalog.payout_rules WHERE game_id = %s AND code = 'turbo_fixed_odds'",
            (game_id,),
        ).fetchone()[0]
        version_id = uuid4()
        inserted = connection.execute(
            """INSERT INTO catalog.payout_rule_versions
               (payout_rule_version_id, payout_rule_id, game_id, game_version_id, version,
                effective_from, currency_code, rule_definition, source_id, source_url,
                source_observed_at)
               VALUES (%s, %s, %s, %s, 'provisional-turbo-2026-10', DATE '2020-11-01',
                'XOF', %s, %s, 'https://www.lonaci.ci/loto_bonheur/', CURRENT_TIMESTAMP)
               ON CONFLICT (payout_rule_id, version) DO NOTHING
               RETURNING payout_rule_version_id""",
            (version_id, payout_rule_id, game_id, game_version_id, Jsonb(rule_definition), source_id),
        ).fetchone()
        if inserted:
            return inserted[0]
        existing = connection.execute(
            """SELECT payout_rule_version_id, rule_definition FROM catalog.payout_rule_versions
               WHERE payout_rule_id = %s AND version = 'provisional-turbo-2026-10'""",
            (payout_rule_id,),
        ).fetchone()
        if existing[1] != rule_definition:
            raise ResearchError("stored provisional turbo payout rule differs from this definition")
        return existing[0]


def ensure_turbo_position_payout_rule(
    connection: Any,
    *,
    game_id: UUID,
    game_version_id: UUID,
    source_id: UUID,
) -> UUID:
    rule_definition = {
        "kind": "fixed_multiplier",
        "bet": "selected_numbers_within_first_k_positions",
        "numbers_picked": 2,
        "positions_by_variant": {"turbo_2": 2, "turbo_3": 3, "turbo_4": 4, "turbo_5": 5},
        "payout_multipliers": {"2": 2400, "3": 800, "4": 400, "5": 240},
        "verification_status": "VERIFIED_OFFICIAL",
        "note": (
            "Official LONACI rules page: 'Choisissez 2 numeros et predisez dans "
            "quelle position ils seront tires.' Turbo k requires both numbers "
            "among the first k drawn. Expected return is ~0.60 for all variants."
        ),
    }
    with connection.transaction():
        inserted_rule = connection.execute(
            """INSERT INTO catalog.payout_rules (payout_rule_id, game_id, code, display_name)
               VALUES (%s, %s, 'turbo_fixed_odds', 'Loto Bonheur Turbo fixed odds')
               ON CONFLICT (game_id, code) DO NOTHING
               RETURNING payout_rule_id""",
            (uuid4(), game_id),
        ).fetchone()
        payout_rule_id = inserted_rule[0] if inserted_rule else connection.execute(
            "SELECT payout_rule_id FROM catalog.payout_rules WHERE game_id = %s AND code = 'turbo_fixed_odds'",
            (game_id,),
        ).fetchone()[0]
        version_id = uuid4()
        inserted = connection.execute(
            """INSERT INTO catalog.payout_rule_versions
               (payout_rule_version_id, payout_rule_id, game_id, game_version_id, version,
                effective_from, currency_code, rule_definition, source_id, source_url,
                source_observed_at)
               VALUES (%s, %s, %s, %s, 'official-turbo-position-2026-10', DATE '2020-11-01',
                'XOF', %s, %s, 'https://www.lonaci.ci/loto_bonheur/', CURRENT_TIMESTAMP)
               ON CONFLICT (payout_rule_id, version) DO NOTHING
               RETURNING payout_rule_version_id""",
            (version_id, payout_rule_id, game_id, game_version_id, Jsonb(rule_definition), source_id),
        ).fetchone()
        if inserted:
            return inserted[0]
        existing = connection.execute(
            """SELECT payout_rule_version_id, rule_definition FROM catalog.payout_rule_versions
               WHERE payout_rule_id = %s AND version = 'official-turbo-position-2026-10'""",
            (payout_rule_id,),
        ).fetchone()
        if existing[1] != rule_definition:
            raise ResearchError("stored official turbo payout rule differs from this definition")
        return existing[0]


def register_strategy(
    connection: Any,
    *,
    code: str,
    display_name: str,
) -> UUID:
    if not code.strip() or not display_name.strip():
        raise ValueError("strategy code and display_name cannot be empty")
    strategy_id = uuid4()
    inserted = connection.execute(
        """INSERT INTO research.strategies (strategy_id, code, display_name)
           VALUES (%s, %s, %s)
           ON CONFLICT (code) DO NOTHING
           RETURNING strategy_id""",
        (strategy_id, code, display_name),
    ).fetchone()
    if inserted:
        return inserted[0]
    existing = connection.execute(
        "SELECT strategy_id, display_name FROM research.strategies WHERE code = %s",
        (code,),
    ).fetchone()
    if existing is None or existing[1] != display_name:
        raise ResearchError("existing strategy code has a different display name")
    return existing[0]


def register_strategy_version(
    connection: Any,
    *,
    strategy_id: UUID | str,
    game_id: UUID | str,
    game_version_id: UUID | str,
    payout_rule_version_id: UUID | str,
    definition: Mapping[str, Any],
    dataset_version_id: UUID | str | None = None,
    experiment_id: UUID | str | None = None,
    code_version: str | None = None,
) -> StrategyVersion:
    from lottery_intelligence_platform.dataset_repository import workspace_code_version

    definition_sha = canonical_sha256(definition)
    code_version = code_version or workspace_code_version()
    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"strategy:{strategy_id}",),
        )
        existing = connection.execute(
            """SELECT strategy_version_id, version, status FROM research.strategy_versions
               WHERE strategy_id = %s AND definition_sha256 = %s""",
            (strategy_id, definition_sha),
        ).fetchone()
        if existing:
            return StrategyVersion(existing[0], UUID(str(strategy_id)), existing[1], definition_sha, existing[2], False)
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM research.strategy_versions WHERE strategy_id = %s",
            (strategy_id,),
        ).fetchone()[0]
        strategy_version_id = uuid4()
        connection.execute(
            """INSERT INTO research.strategy_versions
               (strategy_version_id, strategy_id, version, game_version_id, game_id,
                payout_rule_version_id, dataset_version_id, experiment_id,
                code_version, definition, definition_sha256)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                strategy_version_id, strategy_id, version, game_version_id, game_id,
                payout_rule_version_id, dataset_version_id, experiment_id,
                code_version, Jsonb(dict(definition)), definition_sha,
            ),
        )
        connection.execute(
            """INSERT INTO research.strategy_version_status_events
               (status_event_id, strategy_version_id, previous_status, new_status, reason)
               VALUES (%s, %s, NULL, 'DRAFT', 'strategy version registered')""",
            (uuid4(), strategy_version_id),
        )
        return StrategyVersion(strategy_version_id, UUID(str(strategy_id)), version, definition_sha, "DRAFT", True)


def transition_strategy_version(
    connection: Any,
    *,
    strategy_version_id: UUID | str,
    new_status: str,
    reason: str,
    evidence: Mapping[str, Any] | None = None,
) -> None:
    valid = {"DRAFT", "BACKTESTED", "OOS_EVALUATED", "PROSPECTIVE", "REJECTED", "RETIRED"}
    if new_status not in valid:
        raise ValueError(f"new_status must be one of {sorted(valid)}")
    with connection.transaction():
        current = connection.execute(
            "SELECT status FROM research.strategy_versions WHERE strategy_version_id = %s FOR UPDATE",
            (strategy_version_id,),
        ).fetchone()
        if current is None:
            raise ResearchError("strategy_version_id does not exist")
        connection.execute(
            "UPDATE research.strategy_versions SET status = %s WHERE strategy_version_id = %s",
            (new_status, strategy_version_id),
        )
        connection.execute(
            """INSERT INTO research.strategy_version_status_events
               (status_event_id, strategy_version_id, previous_status, new_status, reason, evidence)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (uuid4(), strategy_version_id, current[0], new_status, reason, Jsonb(dict(evidence or {}))),
        )


def _top_numbers(train_counts: list[int], count: int) -> set[int]:
    return {
        index + NUMBERS_MIN
        for index, _ in sorted(enumerate(train_counts), key=lambda item: (-item[1], item[0]))[:count]
    }


def evaluate_strategy_window(
    connection: Any,
    *,
    strategy_version_id: UUID | str,
    evaluation_window_id: UUID | str,
) -> list[dict[str, Any]]:
    with connection.transaction():
        context = connection.execute(
            """SELECT sv.definition, prv.rule_definition, w.dataset_version_id,
                      w.train_start, w.train_end, w.test_start, w.test_end
               FROM research.strategy_versions sv
               JOIN catalog.payout_rule_versions prv
                 ON prv.payout_rule_version_id = sv.payout_rule_version_id
               JOIN research.evaluation_windows w ON w.evaluation_window_id = %s
               WHERE sv.strategy_version_id = %s""",
            (evaluation_window_id, strategy_version_id),
        ).fetchone()
        if context is None:
            raise ResearchError("strategy_version_id or evaluation_window_id not found")
        definition, payout_rules, dataset_version_id, train_start, train_end, test_start, test_end = context

        bet = definition["bet"]
        numbers_picked = int(bet["numbers_picked"])
        stake = Decimal(str(bet["stake"]))
        multiplier = Decimal(str(payout_rules["payout_multipliers"][str(numbers_picked)]))

        train_counts = _number_counts_by_type(
            connection, dataset_version_id, train_start, train_end
        )
        rows = connection.execute(
            """SELECT dt.draw_type_id, dt.display_name, dv.draw_version_id, dn.number
               FROM datasets.dataset_members m
               JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
               JOIN core.draws d ON d.draw_id = dv.draw_id
               JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
               JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
               WHERE m.dataset_version_id = %s AND dn.number_role = 'WINNING'
                 AND d.scheduled_date BETWEEN %s AND %s
               ORDER BY d.scheduled_date, dt.display_name, dv.draw_version_id, dn.position""",
            (dataset_version_id, test_start, test_end),
        ).fetchall()

        positions = bet.get("positions")

        draws: dict[Any, tuple[str, list[int]]] = {}
        draw_type_ids: dict[str, Any] = {}
        for draw_type_id, draw_type, draw_version_id, number in rows:
            draw_type_ids[draw_type] = draw_type_id
            draws.setdefault(draw_version_id, (draw_type, []))[1].append(number)

        results = []
        for draw_type in sorted(draw_type_ids):
            if draw_type not in train_counts:
                continue
            pick = _top_numbers(train_counts[draw_type], numbers_picked)
            equity = Decimal(0)
            peak = Decimal(0)
            max_drawdown = Decimal(0)
            losing_streak = 0
            longest_losing_streak = 0
            hits = 0
            evaluated = 0
            for _, (name, winning) in draws.items():
                if name != draw_type:
                    continue
                evaluated += 1
                if positions:
                    won = pick <= set(winning[: int(positions)])
                else:
                    won = pick <= set(winning)
                payout = stake * multiplier if won else Decimal(0)
                equity += payout - stake
                hits += int(won)
                losing_streak = 0 if won else losing_streak + 1
                longest_losing_streak = max(longest_losing_streak, losing_streak)
                peak = max(peak, equity)
                max_drawdown = max(max_drawdown, peak - equity)
            if evaluated == 0:
                continue
            stake_total = stake * evaluated
            payout_total = stake_total + equity
            roi = float(equity / stake_total)
            details = {
                "draw_type": draw_type,
                "numbers_picked": numbers_picked,
                "stake_per_draw": float(stake),
                "payout_multiplier": float(multiplier),
                "payout_rule_verification": payout_rules.get("verification_status", "UNSPECIFIED"),
                "selection": sorted(pick),
                "positions": int(positions) if positions else None,
                "window_scope": "OUT_OF_SAMPLE",
            }
            connection.execute(
                """INSERT INTO research.economic_evaluations
                   (economic_evaluation_id, strategy_version_id, evaluation_window_id,
                    draw_type_id, scope, draws_evaluated, stake_total, payout_total,
                    net_result, roi, max_drawdown, longest_losing_streak, hit_count, details,
                    evaluator_version)
                   VALUES (%s, %s, %s, %s, 'OUT_OF_SAMPLE', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (strategy_version_id, evaluation_window_id, scope, draw_type_id, evaluator_version)
                   DO NOTHING""",
                (
                    uuid4(), strategy_version_id, evaluation_window_id,
                    draw_type_ids[draw_type], evaluated, stake_total, payout_total,
                    equity, roi, max_drawdown, longest_losing_streak, hits,
                    Jsonb(details), EVALUATOR_VERSION,
                ),
            )
            results.append({
                "draw_type": draw_type,
                "draws_evaluated": evaluated,
                "hits": hits,
                "net_result": float(equity),
                "roi": roi,
                "max_drawdown": float(max_drawdown),
                "longest_losing_streak": longest_losing_streak,
            })
    return results
