"""Agent Memory Management System.

This module implements the 8-compartment memory system for autonomous agents:
1. Identity Memory - Mission, specialties, objectives, version history
2. Hypotheses Memory - Ideas, justifications, predictions, refutation criteria
3. Experiments Memory - Data used, parameters, results, validation status
4. Successes Memory - What worked, periods, uncertainty, confirmation status
5. Failures Memory - Refuted hypotheses, losses, conditions, abandonment reasons
6. Changes Memory - Why parameters changed, before/after comparisons
7. Calibration Memory - Probability estimates vs observed outcomes, reliability
8. Risk Memory - Drawdown, volatility, exposure, stop thresholds

All memory is append-only and references the experiences that produced it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb


class MemoryError(RuntimeError):
    """Base exception for memory-related errors."""
    pass


# ============================================================================
# MEMORY COMPARTMENT 1: IDENTITY
# ============================================================================

@dataclass(frozen=True, slots=True)
class IdentityMemory:
    """Agent's identity and mission configuration."""
    memory_id: UUID
    agent_id: UUID
    agent_version_id: UUID | None
    mission: str
    specialties: list[str]
    objectives: list[str]
    preferred_methods: list[str]
    constraints: dict[str, Any]
    version_summary: str
    recorded_at: datetime


def record_identity_memory(
    connection: Any,
    *,
    agent_id: UUID | str,
    agent_version_id: UUID | str | None = None,
    mission: str,
    specialties: list[str],
    objectives: list[str],
    preferred_methods: list[str],
    constraints: dict[str, Any] | None = None,
    version_summary: str,
) -> IdentityMemory:
    """Record a snapshot of the agent's identity."""
    if not mission.strip() or not version_summary.strip():
        raise ValueError("mission and version_summary cannot be empty")

    memory_id = uuid4()
    constraints = constraints or {}

    connection.execute(
        """INSERT INTO edge_lab.memory_identity
           (memory_id, agent_id, agent_version_id, mission, specialties,
            objectives, preferred_methods, constraints, version_summary)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            memory_id, agent_id, agent_version_id, mission,
            Jsonb(specialties), Jsonb(objectives), Jsonb(preferred_methods),
            Jsonb(constraints), version_summary,
        ),
    )

    return IdentityMemory(
        memory_id=memory_id,
        agent_id=UUID(str(agent_id)),
        agent_version_id=UUID(str(agent_version_id)) if agent_version_id else None,
        mission=mission,
        specialties=specialties,
        objectives=objectives,
        preferred_methods=preferred_methods,
        constraints=constraints,
        version_summary=version_summary,
        recorded_at=datetime.now(),
    )


# ============================================================================
# MEMORY COMPARTMENT 2: HYPOTHESES
# ============================================================================

@dataclass(frozen=True, slots=True)
class HypothesisMemory:
    """Agent's hypothesis with justification and refutation criteria."""
    hypothesis_id: UUID
    agent_id: UUID
    code: str
    title: str
    statement: str
    justification: str
    predicted_outcome: dict[str, Any]
    counter_hypothesis: str | None
    refutation_criteria: list[str]
    status: str
    confidence_level: float | None
    origin: str
    origin_agent_id: UUID | None
    origin_knowledge_id: UUID | None
    created_at: datetime
    updated_at: datetime


def record_hypothesis(
    connection: Any,
    *,
    agent_id: UUID | str,
    code: str,
    title: str,
    statement: str,
    justification: str,
    predicted_outcome: dict[str, Any] | None = None,
    counter_hypothesis: str | None = None,
    refutation_criteria: list[str] | None = None,
    confidence_level: float | None = None,
    origin: str = "SELF",
    origin_agent_id: UUID | str | None = None,
    origin_knowledge_id: UUID | str | None = None,
) -> HypothesisMemory:
    """Record a hypothesis in the agent's memory."""
    if not code.strip() or not title.strip() or not statement.strip() or not justification.strip():
        raise ValueError("code, title, statement and justification cannot be empty")
    if origin not in {"SELF", "COLLECTIVE", "EXTERNAL"}:
        raise ValueError("origin must be SELF, COLLECTIVE or EXTERNAL")

    hypothesis_id = uuid4()
    predicted_outcome = predicted_outcome or {}
    refutation_criteria = refutation_criteria or []

    connection.execute(
        """INSERT INTO edge_lab.memory_hypotheses
           (hypothesis_id, agent_id, code, title, statement, justification,
            predicted_outcome, counter_hypothesis, refutation_criteria,
            confidence_level, origin, origin_agent_id, origin_knowledge_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            hypothesis_id, agent_id, code, title, statement, justification,
            Jsonb(predicted_outcome), counter_hypothesis, Jsonb(refutation_criteria),
            confidence_level, origin, origin_agent_id, origin_knowledge_id,
        ),
    )

    return HypothesisMemory(
        hypothesis_id=hypothesis_id,
        agent_id=UUID(str(agent_id)),
        code=code,
        title=title,
        statement=statement,
        justification=justification,
        predicted_outcome=predicted_outcome,
        counter_hypothesis=counter_hypothesis,
        refutation_criteria=refutation_criteria,
        status="OPEN",
        confidence_level=confidence_level,
        origin=origin,
        origin_agent_id=UUID(str(origin_agent_id)) if origin_agent_id else None,
        origin_knowledge_id=UUID(str(origin_knowledge_id)) if origin_knowledge_id else None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def update_hypothesis_status(
    connection: Any,
    *,
    hypothesis_id: UUID | str,
    status: str,
) -> None:
    """Update the status of a hypothesis."""
    valid_statuses = {"OPEN", "TESTING", "SUPPORTED", "REJECTED", "INCONCLUSIVE", "ABANDONED"}
    if status not in valid_statuses:
        raise ValueError(f"status must be one of {valid_statuses}")

    connection.execute(
        """UPDATE edge_lab.memory_hypotheses
           SET status = %s, updated_at = CURRENT_TIMESTAMP
           WHERE hypothesis_id = %s""",
        (status, hypothesis_id),
    )


# ============================================================================
# MEMORY COMPARTMENT 3: EXPERIMENTS
# ============================================================================

@dataclass(frozen=True, slots=True)
class ExperimentMemory:
    """Agent's experiment with data, parameters, and results."""
    experiment_id: UUID
    agent_id: UUID
    hypothesis_id: UUID | None
    dataset_version_id: UUID | None
    model_version_id: UUID | None
    strategy_version_id: UUID | None
    test_period_start: date
    test_period_end: date
    parameters: dict[str, Any]
    results: dict[str, Any]
    comparative_reference: dict[str, Any] | None
    validation_status: str
    scope: str
    reproducible: bool
    created_at: datetime
    completed_at: datetime | None


def record_experiment(
    connection: Any,
    *,
    agent_id: UUID | str,
    hypothesis_id: UUID | str | None = None,
    dataset_version_id: UUID | str | None = None,
    model_version_id: UUID | str | None = None,
    strategy_version_id: UUID | str | None = None,
    test_period_start: date,
    test_period_end: date,
    parameters: dict[str, Any],
    results: dict[str, Any],
    comparative_reference: dict[str, Any] | None = None,
    scope: str = "HISTORICAL",
    reproducible: bool = False,
) -> ExperimentMemory:
    """Record an experiment in the agent's memory."""
    valid_scopes = {"HISTORICAL", "OUT_OF_SAMPLE", "PROSPECTIVE", "WALK_FORWARD"}
    if scope not in valid_scopes:
        raise ValueError(f"scope must be one of {valid_scopes}")
    if test_period_start > test_period_end:
        raise ValueError("test_period_start must be before test_period_end")

    experiment_id = uuid4()
    comparative_reference = comparative_reference or {}

    connection.execute(
        """INSERT INTO edge_lab.memory_experiments
           (experiment_id, agent_id, hypothesis_id, dataset_version_id,
            model_version_id, strategy_version_id, test_period_start,
            test_period_end, parameters, results, comparative_reference,
            validation_status, scope, reproducible, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            experiment_id, agent_id, hypothesis_id, dataset_version_id,
            model_version_id, strategy_version_id, test_period_start,
            test_period_end, Jsonb(parameters), Jsonb(results),
            Jsonb(comparative_reference), "PENDING", scope, reproducible, datetime.now(),
        ),
    )

    return ExperimentMemory(
        experiment_id=experiment_id,
        agent_id=UUID(str(agent_id)),
        hypothesis_id=UUID(str(hypothesis_id)) if hypothesis_id else None,
        dataset_version_id=UUID(str(dataset_version_id)) if dataset_version_id else None,
        model_version_id=UUID(str(model_version_id)) if model_version_id else None,
        strategy_version_id=UUID(str(strategy_version_id)) if strategy_version_id else None,
        test_period_start=test_period_start,
        test_period_end=test_period_end,
        parameters=parameters,
        results=results,
        comparative_reference=comparative_reference,
        validation_status="PENDING",
        scope=scope,
        reproducible=reproducible,
        created_at=datetime.now(),
        completed_at=None,
    )


def complete_experiment(
    connection: Any,
    *,
    experiment_id: UUID | str,
    validation_status: str,
) -> None:
    """Mark an experiment as completed with validation status."""
    valid_statuses = {"PENDING", "VALIDATED", "REJECTED", "INCONCLUSIVE"}
    if validation_status not in valid_statuses:
        raise ValueError(f"validation_status must be one of {valid_statuses}")

    connection.execute(
        """UPDATE edge_lab.memory_experiments
           SET validation_status = %s, completed_at = CURRENT_TIMESTAMP
           WHERE experiment_id = %s""",
        (validation_status, experiment_id),
    )


# ============================================================================
# MEMORY COMPARTMENT 4: SUCCESSES
# ============================================================================

@dataclass(frozen=True, slots=True)
class SuccessMemory:
    """Agent's successful strategies and what worked."""
    success_id: UUID
    agent_id: UUID
    experiment_id: UUID | None
    hypothesis_id: UUID | None
    strategy_description: str
    period_start: date
    period_end: date
    metrics: dict[str, Any]
    uncertainty_estimate: float | None
    out_of_sample_confirmed: bool
    prospective_confirmed: bool
    replication_count: int
    notes: str | None
    recorded_at: datetime


def record_success(
    connection: Any,
    *,
    agent_id: UUID | str,
    experiment_id: UUID | str | None = None,
    hypothesis_id: UUID | str | None = None,
    strategy_description: str,
    period_start: date,
    period_end: date,
    metrics: dict[str, Any],
    uncertainty_estimate: float | None = None,
    out_of_sample_confirmed: bool = False,
    prospective_confirmed: bool = False,
    replication_count: int = 0,
    notes: str | None = None,
) -> SuccessMemory:
    """Record a successful strategy in the agent's memory."""
    if not strategy_description.strip():
        raise ValueError("strategy_description cannot be empty")
    if period_start > period_end:
        raise ValueError("period_start must be before period_end")

    success_id = uuid4()

    connection.execute(
        """INSERT INTO edge_lab.memory_successes
           (success_id, agent_id, experiment_id, hypothesis_id,
            strategy_description, period_start, period_end, metrics,
            uncertainty_estimate, out_of_sample_confirmed,
            prospective_confirmed, replication_count, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            success_id, agent_id, experiment_id, hypothesis_id,
            strategy_description, period_start, period_end, Jsonb(metrics),
            uncertainty_estimate, out_of_sample_confirmed,
            prospective_confirmed, replication_count, notes,
        ),
    )

    return SuccessMemory(
        success_id=success_id,
        agent_id=UUID(str(agent_id)),
        experiment_id=UUID(str(experiment_id)) if experiment_id else None,
        hypothesis_id=UUID(str(hypothesis_id)) if hypothesis_id else None,
        strategy_description=strategy_description,
        period_start=period_start,
        period_end=period_end,
        metrics=metrics,
        uncertainty_estimate=uncertainty_estimate,
        out_of_sample_confirmed=out_of_sample_confirmed,
        prospective_confirmed=prospective_confirmed,
        replication_count=replication_count,
        notes=notes,
        recorded_at=datetime.now(),
    )


# ============================================================================
# MEMORY COMPARTMENT 5: FAILURES
# ============================================================================

@dataclass(frozen=True, slots=True)
class FailureMemory:
    """Agent's failures and what was learned."""
    failure_id: UUID
    agent_id: UUID
    experiment_id: UUID | None
    hypothesis_id: UUID | None
    failure_type: str
    description: str
    conditions: dict[str, Any]
    loss_amount: Decimal | None
    conditions_of_failure: str
    abandonment_reason: str
    lessons_learned: str | None
    recorded_at: datetime


def record_failure(
    connection: Any,
    *,
    agent_id: UUID | str,
    experiment_id: UUID | str | None = None,
    hypothesis_id: UUID | str | None = None,
    failure_type: str,
    description: str,
    conditions: dict[str, Any] | None = None,
    loss_amount: Decimal | None = None,
    conditions_of_failure: str,
    abandonment_reason: str,
    lessons_learned: str | None = None,
) -> FailureMemory:
    """Record a failure in the agent's memory."""
    valid_types = {"HYPOTHESIS_REFUTED", "STRATEGY_DEFICIT", "CALIBRATION_ERROR",
                  "CAPITAL_LOSS", "DATA_ISSUE", "OTHER"}
    if failure_type not in valid_types:
        raise ValueError(f"failure_type must be one of {valid_types}")
    if not description.strip() or not conditions_of_failure.strip() or not abandonment_reason.strip():
        raise ValueError("description, conditions_of_failure and abandonment_reason cannot be empty")

    failure_id = uuid4()
    conditions = conditions or {}

    connection.execute(
        """INSERT INTO edge_lab.memory_failures
           (failure_id, agent_id, experiment_id, hypothesis_id, failure_type,
            description, conditions, loss_amount, conditions_of_failure,
            abandonment_reason, lessons_learned)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            failure_id, agent_id, experiment_id, hypothesis_id, failure_type,
            description, Jsonb(conditions), loss_amount, conditions_of_failure,
            abandonment_reason, lessons_learned,
        ),
    )

    return FailureMemory(
        failure_id=failure_id,
        agent_id=UUID(str(agent_id)),
        experiment_id=UUID(str(experiment_id)) if experiment_id else None,
        hypothesis_id=UUID(str(hypothesis_id)) if hypothesis_id else None,
        failure_type=failure_type,
        description=description,
        conditions=conditions,
        loss_amount=loss_amount,
        conditions_of_failure=conditions_of_failure,
        abandonment_reason=abandonment_reason,
        lessons_learned=lessons_learned,
        recorded_at=datetime.now(),
    )


# ============================================================================
# MEMORY COMPARTMENT 6: CHANGES
# ============================================================================

@dataclass(frozen=True, slots=True)
class ChangeMemory:
    """Agent's changes and the rationale behind them."""
    change_id: UUID
    agent_id: UUID
    agent_version_id: UUID | None
    change_type: str
    reason: str
    before_state: dict[str, Any]
    after_state: dict[str, Any]
    comparison_metrics: dict[str, Any]
    decision_rationale: str
    expected_impact: str | None
    recorded_at: datetime


def record_change(
    connection: Any,
    *,
    agent_id: UUID | str,
    agent_version_id: UUID | str | None = None,
    change_type: str,
    reason: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    comparison_metrics: dict[str, Any],
    decision_rationale: str,
    expected_impact: str | None = None,
) -> ChangeMemory:
    """Record a change in the agent's configuration or strategy."""
    valid_types = {"PARAMETER_ADJUSTMENT", "MODEL_REPLACEMENT", "STRATEGY_REPLACEMENT",
                  "GENERATION_PROMOTION", "NEW_AGENT_PROPOSAL", "CAPITAL_REALLOCATION", "OTHER"}
    if change_type not in valid_types:
        raise ValueError(f"change_type must be one of {valid_types}")
    if not reason.strip() or not decision_rationale.strip():
        raise ValueError("reason and decision_rationale cannot be empty")

    change_id = uuid4()

    connection.execute(
        """INSERT INTO edge_lab.memory_changes
           (change_id, agent_id, agent_version_id, change_type, reason,
            before_state, after_state, comparison_metrics, decision_rationale,
            expected_impact)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            change_id, agent_id, agent_version_id, change_type, reason,
            Jsonb(before_state), Jsonb(after_state), Jsonb(comparison_metrics),
            decision_rationale, expected_impact,
        ),
    )

    return ChangeMemory(
        change_id=change_id,
        agent_id=UUID(str(agent_id)),
        agent_version_id=UUID(str(agent_version_id)) if agent_version_id else None,
        change_type=change_type,
        reason=reason,
        before_state=before_state,
        after_state=after_state,
        comparison_metrics=comparison_metrics,
        decision_rationale=decision_rationale,
        expected_impact=expected_impact,
        recorded_at=datetime.now(),
    )


# ============================================================================
# MEMORY COMPARTMENT 7: CALIBRATION
# ============================================================================

@dataclass(frozen=True, slots=True)
class CalibrationMemory:
    """Agent's calibration records and reliability assessment."""
    calibration_id: UUID
    agent_id: UUID
    model_version_id: UUID | None
    strategy_version_id: UUID | None
    period_start: date
    period_end: date
    estimated_probabilities: dict[str, Any]
    observed_outcomes: dict[str, Any]
    calibration_error: float | None
    signal_reliability: float | None
    uncertainty_degree: str
    brier_score: float | None
    reliability_curve: dict[str, Any] | None
    notes: str | None
    recorded_at: datetime


def record_calibration(
    connection: Any,
    *,
    agent_id: UUID | str,
    model_version_id: UUID | str | None = None,
    strategy_version_id: UUID | str | None = None,
    period_start: date,
    period_end: date,
    estimated_probabilities: dict[str, Any],
    observed_outcomes: dict[str, Any],
    calibration_error: float | None = None,
    signal_reliability: float | None = None,
    uncertainty_degree: str = "UNKNOWN",
    brier_score: float | None = None,
    reliability_curve: dict[str, Any] | None = None,
    notes: str | None = None,
) -> CalibrationMemory:
    """Record calibration data in the agent's memory."""
    valid_degrees = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
    if uncertainty_degree not in valid_degrees:
        raise ValueError(f"uncertainty_degree must be one of {valid_degrees}")
    if period_start > period_end:
        raise ValueError("period_start must be before period_end")

    calibration_id = uuid4()

    connection.execute(
        """INSERT INTO edge_lab.memory_calibration
           (calibration_id, agent_id, model_version_id, strategy_version_id,
            period_start, period_end, estimated_probabilities, observed_outcomes,
            calibration_error, signal_reliability, uncertainty_degree,
            brier_score, reliability_curve, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            calibration_id, agent_id, model_version_id, strategy_version_id,
            period_start, period_end, Jsonb(estimated_probabilities),
            Jsonb(observed_outcomes), calibration_error, signal_reliability,
            uncertainty_degree, brier_score, Jsonb(reliability_curve), notes,
        ),
    )

    return CalibrationMemory(
        calibration_id=calibration_id,
        agent_id=UUID(str(agent_id)),
        model_version_id=UUID(str(model_version_id)) if model_version_id else None,
        strategy_version_id=UUID(str(strategy_version_id)) if strategy_version_id else None,
        period_start=period_start,
        period_end=period_end,
        estimated_probabilities=estimated_probabilities,
        observed_outcomes=observed_outcomes,
        calibration_error=calibration_error,
        signal_reliability=signal_reliability,
        uncertainty_degree=uncertainty_degree,
        brier_score=brier_score,
        reliability_curve=reliability_curve,
        notes=notes,
        recorded_at=datetime.now(),
    )


# ============================================================================
# MEMORY COMPARTMENT 8: RISK
# ============================================================================

@dataclass(frozen=True, slots=True)
class RiskMemory:
    """Agent's risk metrics and exposure tracking."""
    risk_record_id: UUID
    agent_id: UUID
    period_start: date
    period_end: date
    drawdown_max: Decimal | None
    drawdown_current: Decimal | None
    volatility: float | None
    exposure_by_market: dict[str, Any]
    average_stake_size: Decimal | None
    max_stake_size: Decimal | None
    stop_threshold_triggered: bool
    stop_threshold_value: Decimal | None
    losing_streak_max: int | None
    losing_streak_current: int | None
    risk_limit_encountered: str | None
    capital_at_risk: float | None
    recorded_at: datetime


def record_risk(
    connection: Any,
    *,
    agent_id: UUID | str,
    period_start: date,
    period_end: date,
    drawdown_max: Decimal | None = None,
    drawdown_current: Decimal | None = None,
    volatility: float | None = None,
    exposure_by_market: dict[str, Any] | None = None,
    average_stake_size: Decimal | None = None,
    max_stake_size: Decimal | None = None,
    stop_threshold_triggered: bool = False,
    stop_threshold_value: Decimal | None = None,
    losing_streak_max: int | None = None,
    losing_streak_current: int | None = None,
    risk_limit_encountered: str | None = None,
    capital_at_risk: float | None = None,
) -> RiskMemory:
    """Record risk metrics in the agent's memory."""
    if period_start > period_end:
        raise ValueError("period_start must be before period_end")

    risk_record_id = uuid4()
    exposure_by_market = exposure_by_market or {}

    connection.execute(
        """INSERT INTO edge_lab.memory_risk
           (risk_record_id, agent_id, period_start, period_end, drawdown_max,
            drawdown_current, volatility, exposure_by_market, average_stake_size,
            max_stake_size, stop_threshold_triggered, stop_threshold_value,
            losing_streak_max, losing_streak_current, risk_limit_encountered,
            capital_at_risk)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            risk_record_id, agent_id, period_start, period_end, drawdown_max,
            drawdown_current, volatility, Jsonb(exposure_by_market),
            average_stake_size, max_stake_size, stop_threshold_triggered,
            stop_threshold_value, losing_streak_max, losing_streak_current,
            risk_limit_encountered, capital_at_risk,
        ),
    )

    return RiskMemory(
        risk_record_id=risk_record_id,
        agent_id=UUID(str(agent_id)),
        period_start=period_start,
        period_end=period_end,
        drawdown_max=drawdown_max,
        drawdown_current=drawdown_current,
        volatility=volatility,
        exposure_by_market=exposure_by_market,
        average_stake_size=average_stake_size,
        max_stake_size=max_stake_size,
        stop_threshold_triggered=stop_threshold_triggered,
        stop_threshold_value=stop_threshold_value,
        losing_streak_max=losing_streak_max,
        losing_streak_current=losing_streak_current,
        risk_limit_encountered=risk_limit_encountered,
        capital_at_risk=capital_at_risk,
        recorded_at=datetime.now(),
    )


# ============================================================================
# MEMORY QUERY FUNCTIONS
# ============================================================================

def get_agent_memory_summary(connection: Any, agent_id: UUID | str) -> dict[str, int]:
    """Get a summary of all memory compartments for an agent."""
    row = connection.execute(
        """SELECT * FROM edge_lab.agent_memory_summary WHERE agent_id = %s""",
        (agent_id,),
    ).fetchone()

    if row is None:
        return {}

    cols = [
        "agent_id", "agent_code", "identity_records", "hypothesis_records",
        "experiment_records", "success_records", "failure_records",
        "change_records", "calibration_records", "risk_records",
    ]

    return dict(zip(cols, row))


def query_recent_hypotheses(
    connection: Any,
    agent_id: UUID | str,
    status: str | None = None,
    limit: int = 10,
) -> list[HypothesisMemory]:
    """Query recent hypotheses from agent's memory."""
    if status:
        rows = connection.execute(
            """SELECT hypothesis_id, agent_id, code, title, statement, justification,
                      predicted_outcome, counter_hypothesis, refutation_criteria,
                      status, confidence_level, origin, origin_agent_id,
                      origin_knowledge_id, created_at, updated_at
               FROM edge_lab.memory_hypotheses
               WHERE agent_id = %s AND status = %s
               ORDER BY created_at DESC LIMIT %s""",
            (agent_id, status, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT hypothesis_id, agent_id, code, title, statement, justification,
                      predicted_outcome, counter_hypothesis, refutation_criteria,
                      status, confidence_level, origin, origin_agent_id,
                      origin_knowledge_id, created_at, updated_at
               FROM edge_lab.memory_hypotheses
               WHERE agent_id = %s
               ORDER BY created_at DESC LIMIT %s""",
            (agent_id, limit),
        ).fetchall()

    return [
        HypothesisMemory(
            hypothesis_id=row[0],
            agent_id=row[1],
            code=row[2],
            title=row[3],
            statement=row[4],
            justification=row[5],
            predicted_outcome=dict(row[6]),
            counter_hypothesis=row[7],
            refutation_criteria=list(row[8]),
            status=row[9],
            confidence_level=row[10],
            origin=row[11],
            origin_agent_id=row[12],
            origin_knowledge_id=row[13],
            created_at=row[14],
            updated_at=row[15],
        )
        for row in rows
    ]


def query_recent_experiments(
    connection: Any,
    agent_id: UUID | str,
    scope: str | None = None,
    limit: int = 10,
) -> list[ExperimentMemory]:
    """Query recent experiments from agent's memory."""
    if scope:
        rows = connection.execute(
            """SELECT experiment_id, agent_id, hypothesis_id, dataset_version_id,
                      model_version_id, strategy_version_id, test_period_start,
                      test_period_end, parameters, results, comparative_reference,
                      validation_status, scope, reproducible, created_at, completed_at
               FROM edge_lab.memory_experiments
               WHERE agent_id = %s AND scope = %s
               ORDER BY created_at DESC LIMIT %s""",
            (agent_id, scope, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT experiment_id, agent_id, hypothesis_id, dataset_version_id,
                      model_version_id, strategy_version_id, test_period_start,
                      test_period_end, parameters, results, comparative_reference,
                      validation_status, scope, reproducible, created_at, completed_at
               FROM edge_lab.memory_experiments
               WHERE agent_id = %s
               ORDER BY created_at DESC LIMIT %s""",
            (agent_id, limit),
        ).fetchall()

    return [
        ExperimentMemory(
            experiment_id=row[0],
            agent_id=row[1],
            hypothesis_id=row[2],
            dataset_version_id=row[3],
            model_version_id=row[4],
            strategy_version_id=row[5],
            test_period_start=row[6],
            test_period_end=row[7],
            parameters=dict(row[8]),
            results=dict(row[9]),
            comparative_reference=dict(row[10]) if row[10] else None,
            validation_status=row[11],
            scope=row[12],
            reproducible=row[13],
            created_at=row[14],
            completed_at=row[15],
        )
        for row in rows
    ]
