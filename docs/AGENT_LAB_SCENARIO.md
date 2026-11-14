# Agent Lab End-to-End Scenario

This document demonstrates the complete autonomous agent cycle:
1. Agent initialization with memory and capital
2. Observation of platform data (read-only, with temporal cutoff)
3. Hypothesis formulation
4. Decision making and sealing
5. Draw settlement
6. Memory update and learning
7. Evolution and collective knowledge sharing

## Scenario: THE EXPLORER Agent

### Step 1: Agent Creation

```python
from lottery_intelligence_platform.agent_engine import create_agent
from lottery_intelligence_platform.agent_memory import record_identity_memory
from decimal import Decimal

# Create THE EXPLORER agent
agent = create_agent(
    connection,
    code="THE_EXPLORER",
    display_name="THE EXPLORER",
    mission="Explore diverse prediction strategies and identify patterns across markets",
    specialties=["frequency_analysis", "pattern_detection", "ensemble_methods"],
    objectives=["find_strategies_with_positive_roi", "identify_market_anomalies"],
    preferred_methods=["bayesian_shrinkage", "rolling_frequency", "meta_consensus"],
    operational_level="RESEARCH",  # Can launch experiments
    autonomy_config={
        "max_stake_ratio": 0.02,  # Max 2% of capital per bet
        "min_confidence": 0.5,  # Minimum confidence to bet
        "lookback_window": 200,  # Draws to analyze
    },
    initial_capital=Decimal("100000.00"),
)

print(f"Created agent: {agent.display_name} (Generation {agent.generation})")
# Output: Created agent: THE EXPLORER (Generation 1)
```

### Step 2: Initial Reflection and Hypothesis

```python
from lottery_intelligence_platform.agent_memory import record_hypothesis
from lottery_intelligence_platform.agent_engine import record_reflection

# Record initial reflection
record_reflection(
    connection,
    agent_id=agent.agent_id,
    reflection_type="PERIOD_REVIEW",
    content="Starting exploration phase. Will test frequency-based strategies across multiple markets.",
    context={"phase": "initialization"},
    next_steps=["Formulate frequency hypothesis", "Select test market"],
)

# Formulate first hypothesis
hypothesis = record_hypothesis(
    connection,
    agent_id=agent.agent_id,
    code="freq_signal_rolling",
    title="Rolling frequency provides better signals than expanding frequency",
    statement="Recent draws (last 200) contain more predictive information than full history",
    justification="Markets may have regime changes; older data may be irrelevant",
    predicted_outcome={
        "expected_roi_improvement": 0.02,
        "expected_hit_rate_improvement": 0.05,
    },
    counter_hypothesis="Expanding frequency captures long-term patterns that rolling misses",
    refutation_criteria=[
        "out_of_sample_roi <= expanding_baseline",
        "hit_rate not significantly different (p > 0.05)",
    ],
    confidence_level=0.6,
)

print(f"Hypothesis created: {hypothesis.title}")
```

### Step 3: Historical Experiment

```python
from lottery_intelligence_platform.agent_memory import record_experiment, complete_experiment
from datetime import date

# Get dataset for historical testing
dataset_version = connection.execute(
    "SELECT dataset_version_id FROM datasets.dataset_versions ORDER BY created_at DESC LIMIT 1"
).fetchone()[0]

# Run historical experiment
experiment = record_experiment(
    connection,
    agent_id=agent.agent_id,
    hypothesis_id=hypothesis.hypothesis_id,
    dataset_version_id=dataset_version,
    test_period_start=date(2023, 1, 1),
    test_period_end=date(2023, 12, 31),
    parameters={
        "method": "rolling_frequency",
        "window_size": 200,
        "top_k": 5,
    },
    results={
        "roi": 0.03,
        "hit_rate": 0.28,
        "total_bets": 365,
        "winning_bets": 102,
    },
    comparative_reference={
        "expanding_frequency_roi": 0.01,
        "expanding_frequency_hit_rate": 0.25,
    },
    scope="HISTORICAL",
    reproducible=True,
)

# Validate experiment
complete_experiment(
    connection,
    experiment_id=experiment.experiment_id,
    validation_status="VALIDATED",
)

print(f"Experiment validated: ROI {experiment.results['roi']:.1%}")
```

### Step 4: Record Success in Memory

```python
from lottery_intelligence_platform.agent_memory import record_success

# Record the successful strategy
success = record_success(
    connection,
    agent_id=agent.agent_id,
    experiment_id=experiment.experiment_id,
    hypothesis_id=hypothesis.hypothesis_id,
    strategy_description="Rolling frequency with 200-draw window, top-5 selection",
    period_start=date(2023, 1, 1),
    period_end=date(2023, 12, 31),
    metrics={
        "roi": 0.03,
        "hit_rate": 0.28,
        "max_drawdown": 0.15,
    },
    uncertainty_estimate=0.05,
    out_of_sample_confirmed=False,  # Needs OOS validation
    prospective_confirmed=False,
    replication_count=0,
    notes="Historical validation only. Requires out-of-sample and prospective testing.",
)

print("Success recorded in memory")
```

### Step 5: Observation and Decision (Real Draw)

```python
from lottery_intelligence_platform.agent_engine import make_decision
from datetime import datetime

# Get upcoming draw (example)
draw = connection.execute(
    """SELECT draw_id, draw_type_id, scheduled_date
       FROM core.draws
       WHERE status = 'EXPECTED'
       ORDER BY scheduled_date
       LIMIT 1"""
).fetchone()

if draw:
    draw_id, draw_type_id, scheduled_date = draw

    # Calculate cutoff (1 hour before draw)
    cutoff_at = datetime.combine(scheduled_date, datetime.min.time()) - timedelta(hours=1)

    # THE EXPLORER makes a decision based on its hypothesis
    decision = make_decision(
        connection,
        agent_id=agent.agent_id,
        draw_id=draw_id,
        draw_type_id=draw_type_id,
        decision_type="BET",
        selected_numbers=[7, 23, 45],  # Based on rolling frequency analysis
        stake_amount=Decimal("2000.00"),  # 2% of capital
        reasoning="Rolling frequency analysis (last 200 draws) shows 7, 23, 45 in top 5. Confidence 0.65 based on historical validation.",
        confidence_score=0.65,
        hypothesis_ids=[hypothesis.hypothesis_id],
        expected_outcome={
            "expected_hits": 1,
            "expected_probability": 0.28,
        },
        risk_assessment={
            "capital_at_risk": 0.02,
            "max_loss": Decimal("2000.00"),
            "risk_level": "MODERATE",
        },
        cutoff_at=cutoff_at,
    )

    print(f"Decision sealed: {decision.decision_type} on {[7, 23, 45]}")
    print(f"Decision sealed at: {decision.sealed_at}")
```

### Step 6: Draw Settlement

```python
from lottery_intelligence_platform.agent_engine import settle_decision

# After draw is settled
draw_version = connection.execute(
    """SELECT dv.draw_version_id, v.validation_status
       FROM core.draws d
       JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
       WHERE d.draw_id = %s
       ORDER BY dv.version_number DESC
       LIMIT 1""",
    (draw_id,),
).fetchone()

if draw_version and draw_version[1] == "VALID":
    draw_version_id, _ = draw_version

    # Get winning numbers
    winning = connection.execute(
        """SELECT jsonb_agg(n.number ORDER BY n.position)
           FROM core.draw_numbers n
           WHERE n.draw_version_id = %s AND n.number_role = 'WINNING'""",
        (draw_version_id,),
    ).fetchone()[0]

    # Calculate hits
    hits = len(set(decision.selected_numbers) & set(winning))

    # Calculate payout (example: 5x multiplier for 1 hit)
    payout = Decimal("10000.00") if hits >= 1 else Decimal("0")

    # Settle the decision
    outcome = settle_decision(
        connection,
        decision_id=decision.decision_id,
        draw_version_id=draw_version_id,
        winning_numbers=winning,
        hit_count=hits,
        positional_hits={},
        stake_returned=Decimal("0"),
        payout=payout,
        settlement_details={
            "multiplier": 5,
            "hits": hits,
        },
    )

    print(f"Outcome: {outcome.outcome_type}")
    print(f"Net result: {outcome.net_result} FCFA")
    # Example output: Outcome: WIN, Net result: 8000 FCFA
```

### Step 7: Post-Settlement Reflection and Learning

```python
from lottery_intelligence_platform.agent_memory import record_calibration, record_risk

# Record post-settlement reflection
record_reflection(
    connection,
    agent_id=agent.agent_id,
    reflection_type="POST_SETTLEMENT",
    content=f"Decision settled: {outcome.outcome_type}. Hit {hits}/{len(decision.selected_numbers)} numbers. Net result: {outcome.net_result} FCFA.",
    context={
        "decision_id": str(decision.decision_id),
        "outcome_type": outcome.outcome_type,
        "hit_count": hits,
        "net_result": str(outcome.net_result),
    },
    action_taken="Update calibration if hit rate deviates from expected",
    next_steps=["Compare to expected probability", "Update risk metrics"],
)

# Update calibration memory
record_calibration(
    connection,
    agent_id=agent.agent_id,
    period_start=date.today() - timedelta(days=30),
    period_end=date.today(),
    estimated_probabilities={
        "expected_hit_rate": 0.28,
        "expected_roi": 0.03,
    },
    observed_outcomes={
        "actual_hit_rate": 0.30,
        "actual_roi": 0.04,
    },
    calibration_error=0.02,
    signal_reliability=0.85,
    uncertainty_degree="MEDIUM",
    brier_score=0.15,
    notes="Rolling frequency showing consistent performance. Signal reliability moderate.",
)

# Update risk memory
capital = get_agent_capital(connection, agent.agent_id)
record_risk(
    connection,
    agent_id=agent.agent_id,
    period_start=date.today() - timedelta(days=30),
    period_end=date.today(),
    drawdown_max=capital.max_drawdown,
    drawdown_current=(capital.peak_capital - capital.current_capital) / capital.peak_capital * 100,
    volatility=0.12,
    exposure_by_market={
        "Loto 5/90": 0.6,
        "Loto 4/45": 0.4,
    },
    average_stake_size=Decimal("1500.00"),
    max_stake_size=Decimal("2000.00"),
    stop_threshold_triggered=False,
    losing_streak_max=3,
    losing_streak_current=0,
    capital_at_risk=0.02,
)

print("Memory updated with calibration and risk data")
```

### Step 8: Share to Collective Memory

```python
from lottery_intelligence_platform.collective_memory import publish_knowledge

# After sufficient validation, share to collective
knowledge = publish_knowledge(
    connection,
    code="rolling_freq_200_window",
    title="Rolling frequency with 200-draw window validated",
    knowledge_type="VALIDATED_METHOD",
    content="Rolling frequency analysis with 200-draw window and top-5 selection achieved 3% ROI historically. Out-of-sample validation pending.",
    evidence={
        "historical_roi": 0.03,
        "historical_hit_rate": 0.28,
        "test_period": "2023-01-01 to 2023-12-31",
        "markets_tested": 2,
    },
    originating_agent_id=agent.agent_id,
    originating_experiment_id=experiment.experiment_id,
    proof_level="REPRODUCED",  # Has been reproduced in testing
)

print(f"Knowledge published to collective: {knowledge.title}")
```

### Step 9: Agent Evolution (Promotion to New Generation)

```python
from lottery_intelligence_platform.agent_lifecycle import (
    create_agent_version,
    validate_agent_version,
    upgrade_operational_level,
)

# After 50 successful bets with positive ROI
if capital.total_bets >= 50 and capital.roi > 0:
    # Create new version with refined parameters
    version = create_agent_version(
        connection,
        agent_id=agent.agent_id,
        change_reason="Refined parameters based on 50-bet validation",
        configuration_changes={
            "window_size": 200,
            "top_k": 5,
            "max_stake_ratio": 0.03,  # Increased from 0.02
            "min_confidence": 0.55,  # Increased from 0.5
        },
        performance_before={
            "roi": float(capital.roi),
            "total_bets": capital.total_bets,
            "winning_bets": capital.winning_bets,
        },
        validation_criteria={
            "required_metrics": ["roi", "hit_rate", "max_drawdown"],
            "min_roi": 0.02,
            "max_drawdown": 0.20,
        },
    )

    # Validate after testing
    validate_agent_version(
        connection,
        agent_version_id=version.agent_version_id,
        performance_after={
            "roi": 0.04,
            "hit_rate": 0.30,
            "max_drawdown": 0.12,
        },
        validation_status="VALIDATED",
    )

    # Upgrade to EVOLUTION level (can create new agents)
    upgrade_operational_level(
        connection,
        agent_id=agent.agent_id,
        new_level="EVOLUTION",
        justification="Agent has validated strategies and can now propose new specialized agents",
    )

    print(f"Agent promoted to Generation {version.version_number}")
    print(f"Operational level: EVOLUTION")
```

### Step 10: Propose New Specialized Agent

```python
from lottery_intelligence_platform.agent_lifecycle import propose_new_agent

# THE EXPLORER proposes a specialized agent for a specific market
new_agent_id = propose_new_agent(
    connection,
    originating_agent_id=agent.agent_id,
    code="FREQ_SPECIALIST",
    display_name="Frequency Specialist",
    mission="Specialize in frequency-based strategies for Loto 5/90 market",
    specialties=["frequency_analysis", "market_specific"],
    objectives=["optimize frequency parameters for Loto 5/90"],
    preferred_methods=["rolling_frequency", "bayesian_shrinkage"],
    operational_level="RESEARCH",
    autonomy_config={
        "max_stake_ratio": 0.02,
        "focus_market": "Loto 5/90",
    },
    justification="Frequency analysis shows distinct patterns in Loto 5/90. A specialized agent can optimize parameters for this market.",
    initial_capital=Decimal("50000.00"),
)

print(f"New agent proposed: FREQ_SPECIALIST (ID: {new_agent_id})")
```

## Summary of the Complete Cycle

1. **Initialization**: Agent created with identity, mission, and virtual capital
2. **Reflection**: Initial reflection sets goals and next steps
3. **Hypothesis**: Agent formulates testable hypothesis with refutation criteria
4. **Experiment**: Historical experiment validates hypothesis with reproducible results
5. **Success Recording**: Successful strategy recorded in memory with metrics
6. **Observation**: Agent observes upcoming draw with strict temporal cutoff
7. **Decision**: Agent makes and seals decision before cutoff
8. **Settlement**: Draw result recorded, capital updated
9. **Learning**: Post-settlement reflection, calibration, and risk updates
10. **Collective**: Validated knowledge shared to collective memory
11. **Evolution**: Agent promoted to new generation with refined parameters
12. **Specialization**: Agent proposes new specialized agent for specific market

This cycle demonstrates the key principles:
- **Autonomy**: Agent makes its own decisions based on its memory and hypotheses
- **Memory**: All experiences are recorded in structured, append-only memory
- **Learning**: Agent updates its understanding based on outcomes
- **Evolution**: Successful strategies lead to generation promotions
- **Collaboration**: Validated knowledge is shared to collective memory
- **Anti-lookahead**: Strict temporal cutoffs prevent data leakage
- **Risk Management**: Virtual capital constraints prevent catastrophic losses
