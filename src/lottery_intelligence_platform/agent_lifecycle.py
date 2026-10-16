"""Agent Lifecycle Management - Evolution and Generations.

This module implements agent evolution capabilities:
- Creating new agent versions with strategy changes
- Promoting strategies to new generations
- Proposing new specialized agents
- Comparing performance before/after changes
- Validating generation promotion criteria

Agents can evolve through three operational levels:
- Level 1 (DECISION): Choose models, numbers, market, stake, or NO_BET
- Level 2 (RESEARCH): Invent hypotheses, launch experiments, adjust parameters
- Level 3 (EVOLUTION): Create variants, propose new agents, reallocate capital
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.agent_memory import record_change, record_hypothesis


class LifecycleError(RuntimeError):
    """Base exception for lifecycle-related errors."""
    pass


class ValidationError(LifecycleError):
    """Raised when validation criteria are not met."""
    pass


@dataclass(frozen=True, slots=True)
class AgentVersion:
    """A version of an agent with its configuration changes."""
    agent_version_id: UUID
    agent_id: UUID
    version_number: int
    previous_version_id: UUID | None
    change_reason: str
    configuration_changes: dict[str, Any]
    performance_before: dict[str, Any] | None
    performance_after: dict[str, Any] | None
    validation_criteria: dict[str, Any]
    validation_status: str
    created_at: datetime


def create_agent_version(
    connection: Any,
    *,
    agent_id: UUID | str,
    change_reason: str,
    configuration_changes: dict[str, Any],
    performance_before: dict[str, Any] | None = None,
    validation_criteria: dict[str, Any] | None = None,
) -> AgentVersion:
    """Create a new version of an agent with configuration changes.

    This records the evolution of an agent's strategy or parameters.
    """
    if not change_reason.strip():
        raise ValueError("change_reason cannot be empty")

    validation_criteria = validation_criteria or {}

    with connection.transaction():
        # Get current version number
        current = connection.execute(
            """SELECT generation FROM edge_lab.agents WHERE agent_id = %s""",
            (agent_id,),
        ).fetchone()

        if current is None:
            raise LifecycleError("Agent not found")

        current_generation = current[0]
        new_version_number = current_generation + 1

        # Get previous version ID if exists
        previous = connection.execute(
            """SELECT agent_version_id FROM edge_lab.agent_versions
               WHERE agent_id = %s ORDER BY version_number DESC LIMIT 1""",
            (agent_id,),
        ).fetchone()

        previous_version_id = previous[0] if previous else None

        # Create version record
        agent_version_id = uuid4()
        connection.execute(
            """INSERT INTO edge_lab.agent_versions
               (agent_version_id, agent_id, version_number, previous_version_id,
                change_reason, configuration_changes, performance_before,
                validation_criteria, validation_status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                agent_version_id, agent_id, new_version_number, previous_version_id,
                change_reason, Jsonb(configuration_changes), Jsonb(performance_before or {}),
                Jsonb(validation_criteria), "PENDING",
            ),
        )

        # Record in change memory
        record_change(
            connection,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            change_type="GENERATION_PROMOTION",
            reason=change_reason,
            before_state=performance_before or {},
            after_state=configuration_changes,
            comparison_metrics={},
            decision_rationale=f"Creating version {new_version_number} based on {change_reason}",
        )

    return AgentVersion(
        agent_version_id=agent_version_id,
        agent_id=UUID(str(agent_id)),
        version_number=new_version_number,
        previous_version_id=previous_version_id,
        change_reason=change_reason,
        configuration_changes=configuration_changes,
        performance_before=performance_before,
        performance_after=None,
        validation_criteria=validation_criteria,
        validation_status="PENDING",
        created_at=datetime.now(),
    )


def validate_agent_version(
    connection: Any,
    *,
    agent_version_id: UUID | str,
    performance_after: dict[str, Any],
    validation_status: str,
) -> None:
    """Validate an agent version with performance data.

    This should be called after sufficient testing of the new version.
    """
    valid_statuses = {"PENDING", "VALIDATED", "REJECTED"}
    if validation_status not in valid_statuses:
        raise ValueError(f"validation_status must be one of {valid_statuses}")

    with connection.transaction():
        # Get the version record
        version = connection.execute(
            """SELECT agent_id, version_number, validation_criteria
               FROM edge_lab.agent_versions WHERE agent_version_id = %s""",
            (agent_version_id,),
        ).fetchone()

        if version is None:
            raise LifecycleError("Agent version not found")

        agent_id, version_number, validation_criteria = version

        # Check validation criteria if provided
        if validation_criteria and validation_status == "VALIDATED":
            # Basic check: ensure performance_after has the required metrics
            required_metrics = validation_criteria.get("required_metrics", [])
            for metric in required_metrics:
                if metric not in performance_after:
                    raise ValidationError(
                        f"Missing required metric for validation: {metric}"
                    )

        # Update version record
        connection.execute(
            """UPDATE edge_lab.agent_versions
               SET performance_after = %s, validation_status = %s
               WHERE agent_version_id = %s""",
            (Jsonb(performance_after), validation_status, agent_version_id),
        )

        # If validated, update the agent's generation
        if validation_status == "VALIDATED":
            connection.execute(
                """UPDATE edge_lab.agents
                   SET generation = %s, updated_at = CURRENT_TIMESTAMP
                   WHERE agent_id = %s""",
                (version_number, agent_id),
            )

            # Record identity memory for new generation
            connection.execute(
                """INSERT INTO edge_lab.memory_identity
                   (memory_id, agent_id, agent_version_id, mission, specialties,
                    objectives, preferred_methods, constraints, version_summary)
                   SELECT uuid_generate_v4(), a.agent_id, %s, a.mission, a.specialties,
                          a.objectives, a.preferred_methods, a.autonomy_config,
                          %s
                   FROM edge_lab.agents a
                   WHERE a.agent_id = %s""",
                (agent_version_id, f"Promoted to generation {version_number}", agent_id),
            )


def propose_new_agent(
    connection: Any,
    *,
    originating_agent_id: UUID | str,
    code: str,
    display_name: str,
    mission: str,
    specialties: list[str],
    objectives: list[str],
    preferred_methods: list[str],
    operational_level: str = "DECISION",
    autonomy_config: dict[str, Any] | None = None,
    justification: str,
    initial_capital: float = 100000.00,
) -> UUID:
    """Propose a new specialized agent.

    This creates a new agent based on insights from an existing agent.
    The new agent will start with its own capital and memory.
    """
    if not justification.strip():
        raise ValueError("justification cannot be empty")

    from lottery_intelligence_platform.agent_engine import create_agent

    # Create the new agent
    new_agent = create_agent(
        connection,
        code=code,
        display_name=display_name,
        mission=mission,
        specialties=specialties,
        objectives=objectives,
        preferred_methods=preferred_methods,
        operational_level=operational_level,
        autonomy_config=autonomy_config,
        initial_capital=initial_capital,
    )

    # Record a hypothesis about the new agent's potential
    record_hypothesis(
        connection,
        agent_id=originating_agent_id,
        code=f"new_agent_{code}",
        title=f"New agent {display_name} will outperform baseline",
        statement=f"Agent {display_name} with specialties {specialties} will achieve better performance than baseline",
        justification=justification,
        predicted_outcome={"expected_roi": 0.0},  # To be filled
        origin="SELF",
    )

    # Record the change in the originating agent's memory
    record_change(
        connection,
        agent_id=originating_agent_id,
        change_type="NEW_AGENT_PROPOSAL",
        reason=justification,
        before_state={},
        after_state={"new_agent_code": code, "new_agent_id": str(new_agent.agent_id)},
        comparison_metrics={},
        decision_rationale=f"Proposed new agent {display_name} based on {justification}",
    )

    return new_agent.agent_id


def upgrade_operational_level(
    connection: Any,
    *,
    agent_id: UUID | str,
    new_level: str,
    justification: str,
) -> None:
    """Upgrade an agent's operational level.

    This enables higher autonomy:
    - DECISION: Basic decision-making
    - RESEARCH: Can launch experiments
    - EVOLUTION: Can create variants and new agents
    """
    valid_levels = {"DECISION", "RESEARCH", "EVOLUTION"}
    if new_level not in valid_levels:
        raise ValueError(f"new_level must be one of {valid_levels}")

    if not justification.strip():
        raise ValueError("justification cannot be empty")

    # Get current level
    current = connection.execute(
        """SELECT operational_level FROM edge_lab.agents WHERE agent_id = %s""",
        (agent_id,),
    ).fetchone()

    if current is None:
        raise LifecycleError("Agent not found")

    current_level = current[0]

    # Validate progression (can't downgrade)
    level_order = {"DECISION": 1, "RESEARCH": 2, "EVOLUTION": 3}
    if level_order[new_level] <= level_order[current_level]:
        raise LifecycleError(
            f"Cannot downgrade or maintain same level: {current_level} -> {new_level}"
        )

    # Update agent
    connection.execute(
        """UPDATE edge_lab.agents
           SET operational_level = %s, updated_at = CURRENT_TIMESTAMP
           WHERE agent_id = %s""",
        (new_level, agent_id),
    )

    # Record the change
    record_change(
        connection,
        agent_id=agent_id,
        change_type="PARAMETER_ADJUSTMENT",
        reason=justification,
        before_state={"operational_level": current_level},
        after_state={"operational_level": new_level},
        comparison_metrics={},
        decision_rationale=f"Upgraded operational level from {current_level} to {new_level}: {justification}",
    )


def reallocate_capital(
    connection: Any,
    *,
    from_agent_id: UUID | str,
    to_agent_id: UUID | str,
    amount: float,
    justification: str,
) -> None:
    """Reallocate virtual capital between agents.

    This allows the system to shift resources to better-performing agents.
    """
    if amount <= 0:
        raise ValueError("amount must be positive")

    if not justification.strip():
        raise ValueError("justification cannot be empty")

    with connection.transaction():
        # Check source agent has sufficient capital
        source_capital = connection.execute(
            """SELECT current_capital FROM edge_lab.agent_capital WHERE agent_id = %s""",
            (from_agent_id,),
        ).fetchone()

        if source_capital is None:
            raise LifecycleError("Source agent capital record not found")

        if source_capital[0] < amount:
            raise LifecycleError(
                f"Insufficient capital in source agent: {source_capital[0]} < {amount}"
            )

        # Deduct from source
        connection.execute(
            """UPDATE edge_lab.agent_capital
               SET current_capital = current_capital - %s,
                   last_updated_at = CURRENT_TIMESTAMP
               WHERE agent_id = %s""",
            (amount, from_agent_id),
        )

        # Add to destination
        connection.execute(
            """UPDATE edge_lab.agent_capital
               SET current_capital = current_capital + %s,
                   initial_capital = initial_capital + %s,
                   last_updated_at = CURRENT_TIMESTAMP
               WHERE agent_id = %s""",
            (amount, amount, to_agent_id),
        )

        # Record changes in both agents' memory
        record_change(
            connection,
            agent_id=from_agent_id,
            change_type="CAPITAL_REALLOCATION",
            reason=justification,
            before_state={"capital": float(source_capital[0])},
            after_state={"capital": float(source_capital[0]) - amount, "reallocated": amount},
            comparison_metrics={},
            decision_rationale=f"Reallocated {amount} to agent {to_agent_id}: {justification}",
        )

        dest_capital = connection.execute(
            """SELECT current_capital FROM edge_lab.agent_capital WHERE agent_id = %s""",
            (to_agent_id,),
        ).fetchone()

        record_change(
            connection,
            agent_id=to_agent_id,
            change_type="CAPITAL_REALLOCATION",
            reason=justification,
            before_state={"capital": float(dest_capital[0]) - amount},
            after_state={"capital": float(dest_capital[0]), "received": amount},
            comparison_metrics={},
            decision_rationale=f"Received {amount} from agent {from_agent_id}: {justification}",
        )


def retire_agent(
    connection: Any,
    *,
    agent_id: UUID | str,
    reason: str,
) -> None:
    """Retire an agent from active duty.

    The agent's memory is preserved but it stops making new decisions.
    """
    if not reason.strip():
        raise ValueError("reason cannot be empty")

    connection.execute(
        """UPDATE edge_lab.agents
           SET status = 'RETIRED', updated_at = CURRENT_TIMESTAMP
           WHERE agent_id = %s""",
        (agent_id,),
    )

    # Record the change
    record_change(
        connection,
        agent_id=agent_id,
        change_type="OTHER",
        reason=reason,
        before_state={"status": "ACTIVE"},
        after_state={"status": "RETIRED"},
        comparison_metrics={},
        decision_rationale=f"Retired agent: {reason}",
    )


def get_agent_versions(
    connection: Any,
    agent_id: UUID | str,
) -> list[AgentVersion]:
    """Get all versions of an agent."""
    rows = connection.execute(
        """SELECT agent_version_id, agent_id, version_number, previous_version_id,
                  change_reason, configuration_changes, performance_before,
                  performance_after, validation_criteria, validation_status, created_at
           FROM edge_lab.agent_versions
           WHERE agent_id = %s
           ORDER BY version_number""",
        (agent_id,),
    ).fetchall()

    return [
        AgentVersion(
            agent_version_id=row[0],
            agent_id=row[1],
            version_number=row[2],
            previous_version_id=row[3],
            change_reason=row[4],
            configuration_changes=dict(row[5]),
            performance_before=dict(row[6]) if row[6] else None,
            performance_after=dict(row[7]) if row[7] else None,
            validation_criteria=dict(row[8]),
            validation_status=row[9],
            created_at=row[10],
        )
        for row in rows
    ]


def list_agents_by_performance(
    connection: Any,
    status: str | None = None,
    min_bets: int = 0,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List agents ranked by performance metrics."""
    if status:
        rows = connection.execute(
            """SELECT a.agent_id, a.code, a.display_name, a.generation, a.status,
                      a.operational_level, ac.current_capital, ac.net_profit, ac.roi,
                      ac.total_bets, ac.winning_bets, ac.losing_bets, ac.max_drawdown
               FROM edge_lab.agents a
               JOIN edge_lab.agent_capital ac ON ac.agent_id = a.agent_id
               WHERE a.status = %s AND ac.total_bets >= %s
               ORDER BY ac.roi DESC
               LIMIT %s""",
            (status, min_bets, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT a.agent_id, a.code, a.display_name, a.generation, a.status,
                      a.operational_level, ac.current_capital, ac.net_profit, ac.roi,
                      ac.total_bets, ac.winning_bets, ac.losing_bets, ac.max_drawdown
               FROM edge_lab.agents a
               JOIN edge_lab.agent_capital ac ON ac.agent_id = a.agent_id
               WHERE ac.total_bets >= %s
               ORDER BY ac.roi DESC
               LIMIT %s""",
            (min_bets, limit),
        ).fetchall()

    cols = [
        "agent_id", "code", "display_name", "generation", "status",
        "operational_level", "current_capital", "net_profit", "roi",
        "total_bets", "winning_bets", "losing_bets", "max_drawdown",
    ]

    return [dict(zip(cols, row)) for row in rows]
