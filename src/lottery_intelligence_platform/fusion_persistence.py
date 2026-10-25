"""Persistance des agents de paris fusion dans edge_lab (capital virtuel durable).

Branche les profils de ``fusion_agents`` sur le moteur d'agents réel :
  * ``bootstrap`` crée les 8 agents dans ``edge_lab.agents`` (capital 100 000 F) ;
  * ``backfill`` rejoue l'historique : pour chaque tirage passé, chaque agent
    décide (walk-forward strict), scelle sa décision (``make_decision``) puis est
    réglé (``settle_decision``) — le capital est crédité/débité à chaque pari ;
  * idempotent : une décision déjà scellée pour (agent, tirage) est sautée.
"""

from __future__ import annotations

import random
from collections import OrderedDict
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

from lottery_intelligence_platform import agent_engine
from lottery_intelligence_platform import fusion_agents

INITIAL_CAPITAL = Decimal("100000.00")


def bootstrap(connection, *, initial_capital: Decimal = INITIAL_CAPITAL) -> dict[str, UUID]:
    """Crée les agents fusion manquants et retourne {code: agent_id}."""
    existing = {r[0]: r[1] for r in connection.execute(
        "SELECT code, agent_id FROM edge_lab.agents").fetchall()}
    ids: dict[str, UUID] = dict(existing)
    for profile in fusion_agents.FUSION_AGENT_PROFILES:
        if profile.code not in ids:
            agent = agent_engine.create_agent(
                connection,
                code=profile.code,
                display_name=profile.display_name,
                mission=profile.mission,
                specialties=list(profile.specialties),
                preferred_methods=list(profile.preferred_methods),
                operational_level="DECISION",
                initial_capital=initial_capital,
            )
            ids[profile.code] = agent.agent_id
    return ids


def load_settled_draws(
    connection, draw_type: str | None = None, limit: int | None = None
) -> list[tuple[UUID, UUID, UUID, list[int]]]:
    """Tirages réglés chronologiques : (draw_id, draw_type_id, draw_version_id, winning_numbers)."""
    where = "d.status = 'SETTLED'"
    params: list[Any] = []
    if draw_type:
        where += " AND dt.display_name = %s"
        params.append(draw_type)
    rows = connection.execute(
        f"""
        SELECT d.draw_id, d.draw_type_id, v.draw_version_id, n.number
        FROM core.draws d
        JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
        JOIN core.draw_versions v ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
        JOIN core.draw_numbers n ON n.draw_version_id = v.draw_version_id AND n.number_role = 'WINNING'
        WHERE {where}
        ORDER BY d.scheduled_date, d.scheduled_sequence, n.position
        """,
        params,
    ).fetchall()
    draws: "OrderedDict[tuple[UUID, UUID, UUID], list[int]]" = OrderedDict()
    for draw_id, draw_type_id, draw_version_id, num in rows:
        draws.setdefault((draw_id, draw_type_id, draw_version_id), []).append(num)
    result = [(k[0], k[1], k[2], sorted(nums)) for k, nums in draws.items()]
    if limit:
        result = result[-limit:]
    return result


def _has_decision(connection, agent_id: UUID, draw_id: UUID) -> bool:
    return connection.execute(
        "SELECT 1 FROM edge_lab.agent_decisions WHERE agent_id = %s AND draw_id = %s",
        (agent_id, draw_id),
    ).fetchone() is not None


def backfill(
    connection, *, draw_type: str | None = None, limit: int = 200,
    rng_seed: int = 20261003,
) -> dict[str, int]:
    """Rejoue l'historique pour chaque agent fusion (make_decision + settle_decision)."""
    ids = bootstrap(connection)
    profiles = {p.code: p for p in fusion_agents.FUSION_AGENT_PROFILES}
    draws = load_settled_draws(connection, draw_type, limit)
    rng = random.Random(rng_seed)
    history: list[list[int]] = []
    new = skipped = no_bet = 0
    for draw_id, draw_type_id, draw_version_id, winning in draws:
        for code, agent_id in ids.items():
            if _has_decision(connection, agent_id, draw_id):
                skipped += 1
                continue
            profile = profiles[code]
            d = fusion_agents.decide(profile, history, rng)
            if not d["selected_numbers"]:
                no_bet += 1
                continue
            hit = len(set(d["selected_numbers"]) & set(winning))
            settle = fusion_agents.settle_bet(
                d["bet_type"], d["selected_numbers"], winning, d["stake_amount"])
            payout = settle.get("total_gain", Decimal("0"))
            try:
                decision = agent_engine.make_decision(
                    connection,
                    agent_id=agent_id,
                    draw_id=draw_id,
                    draw_type_id=draw_type_id,
                    decision_type="BET",
                    selected_numbers=d["selected_numbers"],
                    stake_amount=d["stake_amount"],
                    reasoning=d["reasoning"],
                    confidence_score=d["confidence_score"],
                )
                agent_engine.settle_decision(
                    connection,
                    decision_id=decision.decision_id,
                    draw_version_id=draw_version_id,
                    winning_numbers=winning,
                    hit_count=hit,
                    payout=payout,
                )
                new += 1
            except agent_engine.InsufficientCapitalError:
                no_bet += 1
        history.append(winning)
    return {"draws": len(draws), "new": new, "skipped": skipped, "no_bet": no_bet}


def capital_summary(connection, agent_code: str) -> dict[str, Any] | None:
    """Lit le capital virtuel persisté d'un agent fusion depuis edge_lab."""
    row = connection.execute(
        """
        SELECT a.agent_id, a.code, a.display_name, a.generation, a.status,
               c.initial_capital, c.current_capital, c.net_profit, c.roi,
               c.total_bets, c.winning_bets, c.losing_bets, c.no_bet_count,
               c.max_drawdown
        FROM edge_lab.agents a
        JOIN edge_lab.agent_capital c ON c.agent_id = a.agent_id
        WHERE a.code = %s
        """,
        (agent_code,),
    ).fetchone()
    if row is None:
        return None
    keys = ["agent_id", "code", "display_name", "generation", "status",
            "initial_capital", "current_capital", "net_profit", "roi",
            "total_bets", "winning_bets", "losing_bets", "no_bet_count",
            "max_drawdown"]
    d = dict(zip(keys, row))
    for k in ("initial_capital", "current_capital", "net_profit", "roi", "max_drawdown"):
        if d.get(k) is not None and not isinstance(d[k], (int, float)):
            d[k] = float(d[k])
    return d
