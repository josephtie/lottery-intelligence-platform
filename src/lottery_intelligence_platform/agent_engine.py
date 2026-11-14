"""Autonomous Agent Engine for Lottery Edge Lab.

This module implements the core autonomous agent system with individual
persistent memory, decision-making capabilities, and virtual capital management.

Agents can:
- Observe platform data via read-only API with strict temporal cutoffs
- Consult their memory before making decisions
- Formulate hypotheses and run experiments
- Select models, combine signals, or propose new strategies
- Choose markets, numbers, stakes, or NO_BET
- Seal decisions before draw time
- Learn from outcomes and update memory
- Evolve strategies and propose new agents
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb


class AgentError(RuntimeError):
    """Base exception for agent-related errors."""
    pass


class DecisionSealedError(AgentError):
    """Raised when attempting to modify a sealed decision."""
    pass


class CutoffViolationError(AgentError):
    """Raised when an operation violates temporal cutoff."""
    pass


class InsufficientCapitalError(AgentError):
    """Raised when an agent lacks sufficient capital for a bet."""
    pass


@dataclass(frozen=True, slots=True)
class Agent:
    """Core agent identity and configuration."""
    agent_id: UUID
    code: str
    display_name: str
    generation: int
    status: str
    mission: str
    specialties: list[str]
    objectives: list[str]
    preferred_methods: list[str]
    operational_level: str
    autonomy_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AgentCapital:
    """Virtual capital state for an agent."""
    capital_id: UUID
    agent_id: UUID
    initial_capital: Decimal
    current_capital: Decimal
    total_profit: Decimal
    total_loss: Decimal
    net_profit: Decimal
    roi: Decimal
    total_bets: int
    winning_bets: int
    losing_bets: int
    no_bet_count: int
    max_drawdown: Decimal
    max_drawdown_date: date | None
    peak_capital: Decimal
    peak_capital_date: date | None
    last_updated_at: datetime


@dataclass(frozen=True, slots=True)
class AgentDecision:
    """A sealed decision made by an agent."""
    decision_id: UUID
    agent_id: UUID
    draw_id: UUID
    draw_type_id: UUID
    decision_type: str
    selected_numbers: list[int]
    stake_amount: Decimal
    reasoning: str
    confidence_score: float
    hypothesis_ids: list[UUID]
    model_version_ids: list[UUID]
    strategy_version_ids: list[UUID]
    expected_outcome: dict[str, Any]
    risk_assessment: dict[str, Any]
    created_at: datetime
    sealed_at: datetime
    is_sealed: bool
    cutoff_respected: bool
    formula_id: UUID | None


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    """Outcome of a settled decision."""
    outcome_id: UUID
    decision_id: UUID
    draw_version_id: UUID
    winning_numbers: list[int]
    hit_count: int
    positional_hits: dict[str, Any]
    stake_returned: Decimal
    payout: Decimal
    net_result: Decimal
    outcome_type: str
    settlement_details: dict[str, Any]
    settled_at: datetime


def create_agent(
    connection: Any,
    *,
    code: str,
    display_name: str,
    mission: str,
    specialties: list[str] | None = None,
    objectives: list[str] | None = None,
    preferred_methods: list[str] | None = None,
    operational_level: str = "DECISION",
    autonomy_config: dict[str, Any] | None = None,
    initial_capital: Decimal = Decimal("100000.00"),
) -> Agent:
    """Create a new autonomous agent with virtual capital."""
    if not code.strip() or not display_name.strip() or not mission.strip():
        raise ValueError("agent code, display_name and mission cannot be empty")
    if operational_level not in {"DECISION", "RESEARCH", "EVOLUTION"}:
        raise ValueError("operational_level must be DECISION, RESEARCH or EVOLUTION")

    agent_id = uuid4()
    specialties = specialties or []
    objectives = objectives or []
    preferred_methods = preferred_methods or []
    autonomy_config = autonomy_config or {}

    with connection.transaction():
        # Create agent record
        connection.execute(
            """INSERT INTO edge_lab.agents
               (agent_id, code, display_name, generation, status, mission,
                specialties, objectives, preferred_methods, operational_level,
                autonomy_config)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                agent_id, code, display_name, 1, "ACTIVE", mission,
                Jsonb(specialties), Jsonb(objectives), Jsonb(preferred_methods),
                operational_level, Jsonb(autonomy_config),
            ),
        )

        # Create initial capital record
        capital_id = uuid4()
        connection.execute(
            """INSERT INTO edge_lab.agent_capital
               (capital_id, agent_id, initial_capital, current_capital,
                peak_capital, peak_capital_date)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (capital_id, agent_id, initial_capital, initial_capital, initial_capital, date.today()),
        )

        # Create initial identity memory record
        memory_id = uuid4()
        connection.execute(
            """INSERT INTO edge_lab.memory_identity
               (memory_id, agent_id, mission, specialties, objectives,
                preferred_methods, constraints, version_summary)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                memory_id, agent_id, mission,
                Jsonb(specialties), Jsonb(objectives), Jsonb(preferred_methods),
                Jsonb({}), f"Initial identity for generation 1 agent {code}",
            ),
        )

    return Agent(
        agent_id=agent_id,
        code=code,
        display_name=display_name,
        generation=1,
        status="ACTIVE",
        mission=mission,
        specialties=specialties,
        objectives=objectives,
        preferred_methods=preferred_methods,
        operational_level=operational_level,
        autonomy_config=autonomy_config,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def get_agent(connection: Any, agent_id: UUID | str) -> Agent | None:
    """Retrieve an agent by ID."""
    row = connection.execute(
        """SELECT agent_id, code, display_name, generation, status, mission,
                  specialties, objectives, preferred_methods, operational_level,
                  autonomy_config, created_at, updated_at
           FROM edge_lab.agents WHERE agent_id = %s""",
        (agent_id,),
    ).fetchone()

    if row is None:
        return None

    return Agent(
        agent_id=row[0],
        code=row[1],
        display_name=row[2],
        generation=row[3],
        status=row[4],
        mission=row[5],
        specialties=list(row[6]),
        objectives=list(row[7]),
        preferred_methods=list(row[8]),
        operational_level=row[9],
        autonomy_config=dict(row[10]),
        created_at=row[11],
        updated_at=row[12],
    )


def get_agent_capital(connection: Any, agent_id: UUID | str) -> AgentCapital | None:
    """Retrieve an agent's capital state."""
    row = connection.execute(
        """SELECT capital_id, agent_id, initial_capital, current_capital,
                  total_profit, total_loss, net_profit, roi, total_bets,
                  winning_bets, losing_bets, no_bet_count, max_drawdown,
                  max_drawdown_date, peak_capital, peak_capital_date, last_updated_at
           FROM edge_lab.agent_capital WHERE agent_id = %s""",
        (agent_id,),
    ).fetchone()

    if row is None:
        return None

    return AgentCapital(
        capital_id=row[0],
        agent_id=row[1],
        initial_capital=row[2],
        current_capital=row[3],
        total_profit=row[4],
        total_loss=row[5],
        net_profit=row[6],
        roi=row[7],
        total_bets=row[8],
        winning_bets=row[9],
        losing_bets=row[10],
        no_bet_count=row[11],
        max_drawdown=row[12],
        max_drawdown_date=row[13],
        peak_capital=row[14],
        peak_capital_date=row[15],
        last_updated_at=row[16],
    )


def record_reflection(
    connection: Any,
    *,
    agent_id: UUID | str,
    reflection_type: str,
    content: str,
    context: dict[str, Any] | None = None,
    action_taken: str | None = None,
    next_steps: list[str] | None = None,
) -> UUID:
    """Record an agent's reflection on its reasoning or performance."""
    valid_types = {"PRE_DECISION", "POST_SETTLEMENT", "PERIOD_REVIEW", "STRATEGY_REVIEW", "SELF_CRITIQUE"}
    if reflection_type not in valid_types:
        raise ValueError(f"reflection_type must be one of {valid_types}")
    if not content.strip():
        raise ValueError("reflection content cannot be empty")

    reflection_id = uuid4()
    context = context or {}
    next_steps = next_steps or []

    connection.execute(
        """INSERT INTO edge_lab.agent_reflections
           (reflection_id, agent_id, reflection_type, content, context,
            action_taken, next_steps)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (reflection_id, agent_id, reflection_type, content, Jsonb(context), action_taken, Jsonb(next_steps)),
    )

    return reflection_id


def make_decision(
    connection: Any,
    *,
    agent_id: UUID | str,
    draw_id: UUID | str,
    draw_type_id: UUID | str,
    decision_type: str,
    selected_numbers: list[int] | None = None,
    stake_amount: Decimal | None = None,
    reasoning: str,
    confidence_score: float,
    hypothesis_ids: list[UUID] | None = None,
    model_version_ids: list[UUID] | None = None,
    strategy_version_ids: list[UUID] | None = None,
    expected_outcome: dict[str, Any] | None = None,
    risk_assessment: dict[str, Any] | None = None,
    cutoff_at: datetime | None = None,
    formula_id: UUID | str | None = None,
) -> AgentDecision:
    """Make and seal a decision for an upcoming draw.

    This function enforces:
    - Temporal cutoff: no data after cutoff_at can be used
    - Capital validation: stake must not exceed available capital
    - Decision sealing: once created, decisions cannot be modified
    """
    if decision_type not in {"BET", "NO_BET"}:
        raise ValueError("decision_type must be BET or NO_BET")
    if not reasoning.strip():
        raise ValueError("reasoning cannot be empty")
    if not (0 <= confidence_score <= 1):
        raise ValueError("confidence_score must be between 0 and 1")

    if decision_type == "BET":
        if not selected_numbers or len(selected_numbers) == 0:
            raise ValueError("selected_numbers required for BET decisions")
        if stake_amount is None or stake_amount <= 0:
            raise ValueError("stake_amount must be positive for BET decisions")

        # Validate capital
        capital = get_agent_capital(connection, agent_id)
        if capital is None:
            raise AgentError("Agent capital record not found")
        if capital.current_capital < stake_amount:
            raise InsufficientCapitalError(
                f"Insufficient capital: {capital.current_capital} < {stake_amount}"
            )

    # Enforce temporal cutoff
    if cutoff_at is not None and datetime.now() > cutoff_at:
        raise CutoffViolationError("Current time exceeds cutoff time")

    decision_id = uuid4()
    hypothesis_ids = hypothesis_ids or []
    model_version_ids = model_version_ids or []
    strategy_version_ids = strategy_version_ids or []
    expected_outcome = expected_outcome or {}
    risk_assessment = risk_assessment or {}

    with connection.transaction():
        # Record pre-decision reflection
        record_reflection(
            connection,
            agent_id=agent_id,
            reflection_type="PRE_DECISION",
            content=reasoning,
            context={
                "draw_id": str(draw_id),
                "decision_type": decision_type,
                "selected_numbers": selected_numbers,
                "stake_amount": str(stake_amount),
                "confidence_score": confidence_score,
            },
        )

        # Create sealed decision
        now = datetime.now()
        connection.execute(
            """INSERT INTO edge_lab.agent_decisions
               (decision_id, agent_id, draw_id, draw_type_id, decision_type,
                selected_numbers, stake_amount, reasoning, confidence_score,
                hypothesis_ids, model_version_ids, strategy_version_ids,
                expected_outcome, risk_assessment, created_at, sealed_at,
                is_sealed, cutoff_respected, formula_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                decision_id, agent_id, draw_id, draw_type_id, decision_type,
                selected_numbers, stake_amount, reasoning, confidence_score,
                hypothesis_ids, model_version_ids, strategy_version_ids,
                Jsonb(expected_outcome), Jsonb(risk_assessment), now, now, True,
                cutoff_at is None or datetime.now() <= cutoff_at, formula_id,
            ),
        )

        # Update capital if it's a bet
        if decision_type == "BET":
            connection.execute(
                """UPDATE edge_lab.agent_capital
                   SET current_capital = current_capital - %s,
                       total_bets = total_bets + 1,
                       last_updated_at = CURRENT_TIMESTAMP
                   WHERE agent_id = %s""",
                (stake_amount, agent_id),
            )

    return AgentDecision(
        decision_id=decision_id,
        agent_id=UUID(str(agent_id)),
        draw_id=UUID(str(draw_id)),
        draw_type_id=UUID(str(draw_type_id)),
        decision_type=decision_type,
        selected_numbers=selected_numbers or [],
        stake_amount=stake_amount or Decimal("0"),
        reasoning=reasoning,
        confidence_score=confidence_score,
        hypothesis_ids=hypothesis_ids,
        model_version_ids=model_version_ids,
        strategy_version_ids=strategy_version_ids,
        expected_outcome=expected_outcome,
        risk_assessment=risk_assessment,
        created_at=now,
        sealed_at=now,
        is_sealed=True,
        cutoff_respected=cutoff_at is None or datetime.now() <= cutoff_at,
        formula_id=UUID(str(formula_id)) if formula_id else None,
    )


def settle_decision(
    connection: Any,
    *,
    decision_id: UUID | str,
    draw_version_id: UUID | str,
    winning_numbers: list[int],
    hit_count: int,
    positional_hits: dict[str, Any] | None = None,
    stake_returned: Decimal = Decimal("0"),
    payout: Decimal = Decimal("0"),
    settlement_details: dict[str, Any] | None = None,
) -> DecisionOutcome:
    """Settle a decision after the draw result is known.

    This function:
    - Records the outcome
    - Updates agent capital
    - Records post-settlement reflection trigger
    """
    outcome_id = uuid4()
    positional_hits = positional_hits or {}
    settlement_details = settlement_details or {}

    # Get the decision to calculate net result
    decision = connection.execute(
        """SELECT agent_id, decision_type, stake_amount
           FROM edge_lab.agent_decisions WHERE decision_id = %s""",
        (decision_id,),
    ).fetchone()

    if decision is None:
        raise AgentError("Decision not found")

    agent_id, decision_type, stake_amount = decision

    if decision_type == "NO_BET":
        net_result = Decimal("0")
        outcome_type = "NO_BET"
    else:
        net_result = payout - stake_amount
        outcome_type = "WIN" if net_result > 0 else "LOSS"

    with connection.transaction():
        # Record outcome
        connection.execute(
            """INSERT INTO edge_lab.decision_outcomes
               (outcome_id, decision_id, draw_version_id, winning_numbers,
                hit_count, positional_hits, stake_returned, payout, net_result,
                outcome_type, settlement_details, settled_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                outcome_id, decision_id, draw_version_id, winning_numbers,
                hit_count, Jsonb(positional_hits), stake_returned, payout,
                net_result, outcome_type, Jsonb(settlement_details), datetime.now(),
            ),
        )

        # Update capital
        if decision_type == "BET":
            if outcome_type == "WIN":
                connection.execute(
                    """UPDATE edge_lab.agent_capital
                       SET current_capital = current_capital + %s,
                           total_profit = total_profit + %s,
                           net_profit = net_profit + %s,
                           winning_bets = winning_bets + 1,
                           roi = (net_profit / initial_capital) * 100,
                           last_updated_at = CURRENT_TIMESTAMP
                       WHERE agent_id = %s""",
                    (payout, payout, net_result, agent_id),
                )
            else:
                connection.execute(
                    """UPDATE edge_lab.agent_capital
                       SET total_loss = total_loss + %s,
                           net_profit = net_profit + %s,
                           losing_bets = losing_bets + 1,
                           roi = (net_profit / initial_capital) * 100,
                           last_updated_at = CURRENT_TIMESTAMP
                       WHERE agent_id = %s""",
                    (stake_amount, net_result, agent_id),
                )

            # Update peak capital if new high
            connection.execute(
                """UPDATE edge_lab.agent_capital
                   SET peak_capital = GREATEST(peak_capital, current_capital),
                       peak_capital_date = CASE
                           WHEN current_capital >= peak_capital THEN CURRENT_DATE
                           ELSE peak_capital_date
                       END
                   WHERE agent_id = %s""",
                (agent_id,),
            )

            # Update max drawdown
            connection.execute(
                """UPDATE edge_lab.agent_capital
                   SET max_drawdown = GREATEST(
                       max_drawdown,
                       (peak_capital - current_capital) / peak_capital * 100
                   ),
                   max_drawdown_date = CASE
                       WHEN current_capital < peak_capital THEN CURRENT_DATE
                       ELSE max_drawdown_date
                   END
                   WHERE agent_id = %s""",
                (agent_id,),
            )
        else:
            connection.execute(
                """UPDATE edge_lab.agent_capital
                   SET no_bet_count = no_bet_count + 1,
                       last_updated_at = CURRENT_TIMESTAMP
                   WHERE agent_id = %s""",
                (agent_id,),
            )

    return DecisionOutcome(
        outcome_id=outcome_id,
        decision_id=UUID(str(decision_id)),
        draw_version_id=UUID(str(draw_version_id)),
        winning_numbers=winning_numbers,
        hit_count=hit_count,
        positional_hits=positional_hits,
        stake_returned=stake_returned,
        payout=payout,
        net_result=net_result,
        outcome_type=outcome_type,
        settlement_details=settlement_details,
        settled_at=datetime.now(),
    )


def list_active_agents(connection: Any) -> list[Agent]:
    """List all active agents."""
    rows = connection.execute(
        """SELECT agent_id, code, display_name, generation, status, mission,
                  specialties, objectives, preferred_methods, operational_level,
                  autonomy_config, created_at, updated_at
           FROM edge_lab.agents WHERE status = 'ACTIVE'
           ORDER BY code"""
    ).fetchall()

    return [
        Agent(
            agent_id=row[0],
            code=row[1],
            display_name=row[2],
            generation=row[3],
            status=row[4],
            mission=row[5],
            specialties=list(row[6]),
            objectives=list(row[7]),
            preferred_methods=list(row[8]),
            operational_level=row[9],
            autonomy_config=dict(row[10]),
            created_at=row[11],
            updated_at=row[12],
        )
        for row in rows
    ]


def get_agent_summary(connection: Any, agent_id: UUID | str) -> dict[str, Any] | None:
    """Get a comprehensive summary of an agent's state."""
    row = connection.execute(
        """SELECT * FROM edge_lab.agent_summary WHERE agent_id = %s""",
        (agent_id,),
    ).fetchone()

    if row is None:
        return None

    cols = [
        "agent_id", "code", "display_name", "generation", "status",
        "operational_level", "mission", "initial_capital", "current_capital",
        "net_profit", "roi", "total_bets", "winning_bets", "losing_bets",
        "no_bet_count", "max_drawdown", "experiments_count", "hypotheses_count",
        "successes_count", "failures_count", "last_reflection",
        "agent_created_at", "capital_updated_at",
    ]

    return dict(zip(cols, row))
