"""Collective Memory System for Agent Collaboration.

This module implements the shared knowledge system where agents can:
- Publish validated findings to the collective
- Discover knowledge from other agents
- Adopt and validate knowledge from the collective
- Track proof levels and validation counts

The collective memory is distinct from individual memory:
- Individual memory: private experiences, parameters, hypotheses in progress
- Collective memory: reproducible experiments, refuted strategies, statistical traps,
  validated methods, best practices, warnings

All knowledge must indicate its origin, version, and proof level.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb


class CollectiveMemoryError(RuntimeError):
    """Base exception for collective memory errors."""
    pass


@dataclass(frozen=True, slots=True)
class CollectiveKnowledge:
    """A piece of shared knowledge in the collective memory."""
    knowledge_id: UUID
    code: str
    title: str
    knowledge_type: str
    content: str
    evidence: dict[str, Any]
    proof_level: str
    originating_agent_id: UUID
    originating_experiment_id: UUID | None
    version: int
    parent_knowledge_id: UUID | None
    validation_count: int
    rejection_count: int
    last_validated_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeAdoption:
    """An agent's adoption of a piece of collective knowledge."""
    adoption_id: UUID
    agent_id: UUID
    knowledge_id: UUID
    adoption_reason: str
    validation_status: str
    validation_results: dict[str, Any]
    adopted_at: datetime
    validated_at: datetime | None


def publish_knowledge(
    connection: Any,
    *,
    code: str,
    title: str,
    knowledge_type: str,
    content: str,
    evidence: dict[str, Any],
    originating_agent_id: UUID | str,
    originating_experiment_id: UUID | str | None = None,
    parent_knowledge_id: UUID | str | None = None,
    proof_level: str = "UNVERIFIED",
) -> CollectiveKnowledge:
    """Publish a piece of knowledge to the collective memory.

    This creates a new knowledge entry that other agents can discover and adopt.
    """
    valid_types = {
        "REPRODUCIBLE_EXPERIMENT", "REFUTED_STRATEGY", "STATISTICAL_TRAP",
        "VALIDATED_METHOD", "BEST_PRACTICE", "WARNING"
    }
    if knowledge_type not in valid_types:
        raise ValueError(f"knowledge_type must be one of {valid_types}")

    valid_levels = {"UNVERIFIED", "REPRODUCED", "VALIDATED", "CONFIRMED"}
    if proof_level not in valid_levels:
        raise ValueError(f"proof_level must be one of {valid_levels}")

    if not code.strip() or not title.strip() or not content.strip():
        raise ValueError("code, title and content cannot be empty")

    knowledge_id = uuid4()

    with connection.transaction():
        # Check if code already exists
        existing = connection.execute(
            "SELECT knowledge_id, version FROM edge_lab.collective_knowledge WHERE code = %s",
            (code,),
        ).fetchone()

        if existing:
            # Create a new version
            existing_id, existing_version = existing
            new_version = existing_version + 1
            connection.execute(
                """INSERT INTO edge_lab.collective_knowledge
                   (knowledge_id, code, title, knowledge_type, content, evidence,
                    proof_level, originating_agent_id, originating_experiment_id,
                    version, parent_knowledge_id, validation_count, rejection_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    knowledge_id, code, title, knowledge_type, content, Jsonb(evidence),
                    proof_level, originating_agent_id, originating_experiment_id,
                    new_version, existing_id, 0, 0,
                ),
            )
        else:
            # Create first version
            connection.execute(
                """INSERT INTO edge_lab.collective_knowledge
                   (knowledge_id, code, title, knowledge_type, content, evidence,
                    proof_level, originating_agent_id, originating_experiment_id,
                    version, parent_knowledge_id, validation_count, rejection_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    knowledge_id, code, title, knowledge_type, content, Jsonb(evidence),
                    proof_level, originating_agent_id, originating_experiment_id,
                    1, parent_knowledge_id, 0, 0,
                ),
            )

    row = connection.execute(
        """SELECT knowledge_id, code, title, knowledge_type, content, evidence,
                  proof_level, originating_agent_id, originating_experiment_id,
                  version, parent_knowledge_id, validation_count, rejection_count,
                  last_validated_at, created_at, updated_at
           FROM edge_lab.collective_knowledge WHERE knowledge_id = %s""",
        (knowledge_id,),
    ).fetchone()

    return CollectiveKnowledge(
        knowledge_id=row[0],
        code=row[1],
        title=row[2],
        knowledge_type=row[3],
        content=row[4],
        evidence=dict(row[5]),
        proof_level=row[6],
        originating_agent_id=row[7],
        originating_experiment_id=row[8],
        version=row[9],
        parent_knowledge_id=row[10],
        validation_count=row[11],
        rejection_count=row[12],
        last_validated_at=row[13],
        created_at=row[14],
        updated_at=row[15],
    )


def adopt_knowledge(
    connection: Any,
    *,
    agent_id: UUID | str,
    knowledge_id: UUID | str,
    adoption_reason: str,
) -> KnowledgeAdoption:
    """Adopt a piece of collective knowledge.

    An agent can adopt knowledge from the collective, but must validate it
    independently. The adoption is recorded to track the origin.
    """
    if not adoption_reason.strip():
        raise ValueError("adoption_reason cannot be empty")

    # Check if already adopted
    existing = connection.execute(
        """SELECT adoption_id FROM edge_lab.knowledge_adoption
           WHERE agent_id = %s AND knowledge_id = %s""",
        (agent_id, knowledge_id),
    ).fetchone()

    if existing:
        raise CollectiveMemoryError("Knowledge already adopted by this agent")

    adoption_id = uuid4()

    connection.execute(
        """INSERT INTO edge_lab.knowledge_adoption
           (adoption_id, agent_id, knowledge_id, adoption_reason, validation_status)
           VALUES (%s, %s, %s, %s, %s)""",
        (adoption_id, agent_id, knowledge_id, adoption_reason, "PENDING"),
    )

    return KnowledgeAdoption(
        adoption_id=adoption_id,
        agent_id=UUID(str(agent_id)),
        knowledge_id=UUID(str(knowledge_id)),
        adoption_reason=adoption_reason,
        validation_status="PENDING",
        validation_results={},
        adopted_at=datetime.now(),
        validated_at=None,
    )


def validate_knowledge_adoption(
    connection: Any,
    *,
    adoption_id: UUID | str,
    validation_status: str,
    validation_results: dict[str, Any],
) -> None:
    """Record the validation result of an adopted knowledge."""
    valid_statuses = {"PENDING", "VALIDATED", "REJECTED", "INCONCLUSIVE"}
    if validation_status not in valid_statuses:
        raise ValueError(f"validation_status must be one of {valid_statuses}")

    # Get the adoption record
    adoption = connection.execute(
        """SELECT agent_id, knowledge_id FROM edge_lab.knowledge_adoption
           WHERE adoption_id = %s""",
        (adoption_id,),
    ).fetchone()

    if adoption is None:
        raise CollectiveMemoryError("Adoption not found")

    agent_id, knowledge_id = adoption

    with connection.transaction():
        # Update adoption record
        connection.execute(
            """UPDATE edge_lab.knowledge_adoption
               SET validation_status = %s, validation_results = %s, validated_at = CURRENT_TIMESTAMP
               WHERE adoption_id = %s""",
            (validation_status, Jsonb(validation_results), adoption_id),
        )

        # Update collective knowledge validation counts
        if validation_status == "VALIDATED":
            connection.execute(
                """UPDATE edge_lab.collective_knowledge
                   SET validation_count = validation_count + 1,
                       last_validated_at = CURRENT_TIMESTAMP
                   WHERE knowledge_id = %s""",
                (knowledge_id,),
            )
        elif validation_status == "REJECTED":
            connection.execute(
                """UPDATE edge_lab.collective_knowledge
                   SET rejection_count = rejection_count + 1
                   WHERE knowledge_id = %s""",
                (knowledge_id,),
            )


def discover_knowledge(
    connection: Any,
    *,
    knowledge_type: str | None = None,
    proof_level: str | None = None,
    originating_agent_id: UUID | str | None = None,
    min_validations: int = 0,
    limit: int = 20,
) -> list[CollectiveKnowledge]:
    """Discover knowledge from the collective memory.

    Agents can search the collective memory to find relevant knowledge
    published by other agents.
    """
    conditions = []
    params = []
    param_count = 0

    if knowledge_type:
        param_count += 1
        conditions.append(f"knowledge_type = ${param_count}")
        params.append(knowledge_type)

    if proof_level:
        param_count += 1
        conditions.append(f"proof_level = ${param_count}")
        params.append(proof_level)

    if originating_agent_id:
        param_count += 1
        conditions.append(f"originating_agent_id = ${param_count}")
        params.append(originating_agent_id)

    if min_validations > 0:
        param_count += 1
        conditions.append(f"validation_count >= ${param_count}")
        params.append(min_validations)

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    sql = f"""
        SELECT knowledge_id, code, title, knowledge_type, content, evidence,
               proof_level, originating_agent_id, originating_experiment_id,
               version, parent_knowledge_id, validation_count, rejection_count,
               last_validated_at, created_at, updated_at
        FROM edge_lab.collective_knowledge
        WHERE {where_clause}
        ORDER BY validation_count DESC, updated_at DESC
        LIMIT ${param_count + 1}
    """
    params.append(limit)

    rows = connection.execute(sql, params).fetchall()

    return [
        CollectiveKnowledge(
            knowledge_id=row[0],
            code=row[1],
            title=row[2],
            knowledge_type=row[3],
            content=row[4],
            evidence=dict(row[5]),
            proof_level=row[6],
            originating_agent_id=row[7],
            originating_experiment_id=row[8],
            version=row[9],
            parent_knowledge_id=row[10],
            validation_count=row[11],
            rejection_count=row[12],
            last_validated_at=row[13],
            created_at=row[14],
            updated_at=row[15],
        )
        for row in rows
    ]


def get_agent_adoptions(
    connection: Any,
    agent_id: UUID | str,
    validation_status: str | None = None,
) -> list[KnowledgeAdoption]:
    """Get all knowledge adoptions for an agent."""
    if validation_status:
        rows = connection.execute(
            """SELECT ka.adoption_id, ka.agent_id, ka.knowledge_id, ka.adoption_reason,
                      ka.validation_status, ka.validation_results, ka.adopted_at, ka.validated_at
               FROM edge_lab.knowledge_adoption ka
               WHERE ka.agent_id = %s AND ka.validation_status = %s
               ORDER BY ka.adopted_at DESC""",
            (agent_id, validation_status),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT ka.adoption_id, ka.agent_id, ka.knowledge_id, ka.adoption_reason,
                      ka.validation_status, ka.validation_results, ka.adopted_at, ka.validated_at
               FROM edge_lab.knowledge_adoption ka
               WHERE ka.agent_id = %s
               ORDER BY ka.adopted_at DESC""",
            (agent_id,),
        ).fetchall()

    return [
        KnowledgeAdoption(
            adoption_id=row[0],
            agent_id=row[1],
            knowledge_id=row[2],
            adoption_reason=row[3],
            validation_status=row[4],
            validation_results=dict(row[5]),
            adopted_at=row[6],
            validated_at=row[7],
        )
        for row in rows
    ]


def get_collective_summary(connection: Any) -> list[dict[str, Any]]:
    """Get a summary of the collective memory by type and proof level."""
    rows = connection.execute(
        """SELECT knowledge_type, proof_level, count, contributing_agents,
                  avg_validations, last_updated
           FROM edge_lab.collective_summary
           ORDER BY knowledge_type, proof_level"""
    ).fetchall()

    cols = ["knowledge_type", "proof_level", "count", "contributing_agents",
            "avg_validations", "last_updated"]

    return [dict(zip(cols, row)) for row in rows]


def upgrade_knowledge_proof_level(
    connection: Any,
    *,
    knowledge_id: UUID | str,
    new_proof_level: str,
) -> None:
    """Upgrade the proof level of a piece of knowledge.

    This should only be called after rigorous validation.
    """
    valid_levels = {"UNVERIFIED", "REPRODUCED", "VALIDATED", "CONFIRMED"}
    if new_proof_level not in valid_levels:
        raise ValueError(f"new_proof_level must be one of {valid_levels}")

    connection.execute(
        """UPDATE edge_lab.collective_knowledge
           SET proof_level = %s, updated_at = CURRENT_TIMESTAMP
           WHERE knowledge_id = %s""",
        (new_proof_level, knowledge_id),
    )
