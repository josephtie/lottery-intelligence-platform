# Betting Formulas Integration Guide

This document explains how the official Loto Bonheur betting formulas have been integrated into the autonomous agent system.

## Overview

The betting formulas from Loto Bonheur (LONACI) have been integrated to allow agents to:
- Choose from multiple betting formulas (Standard, Turbo, Chance, PERM)
- Calculate potential gains based on official odds
- Track performance by formula type
- Optimize betting strategies based on formula characteristics

## Official Formulas

### Standard Formulas
- **PN** (Prédiction Numérique): 1 numéro, côte 40
- **1N**: 1 numéro, côte 10
- **2N**: 2 numéros, côte 240
- **3N**: 3 numéros, côte 2 000
- **4N**: 4 numéros, côte 5 000
- **5N**: 5 numéros, côte 40 000

### Turbo Formulas (Position-Sensitive)
- **Turbo 2**: 2 numéros en position 1-2, côte 2 400
- **Turbo 3**: 3 numéros en position 1-3, côte 800
- **Turbo 4**: 4 numéros en position 1-4, côte 400
- **Turbo 5**: 5 numéros en position 1-5, côte 240

### Chance Formulas (Tiered Payouts)
- **Chance 3+**: 3 numéros, paliers 2N (60) et 3N (1 750)
- **Chance 4+**: 4 numéros, paliers 2N (30), 3N (300), 4N (10 000)
- **Chance 5+**: 5 numéros, paliers 2N (20), 3N (100), 4N (2 000), 5N (50 000)

### PERM Formulas (Combination Generation)
- **PERM 2**: Génère toutes les paires à partir de N numéros (3-90), côte 240 par paire
- **PERM 3**: Génère tous les triplets à partir de N numéros (4-90), côte 2 000 par triplet

## Database Schema

### Tables

1. **catalog.betting_formulas**
   - Stores formula configurations
   - Includes formula type, numbers required, unit stake
   - Flags for position sensitivity (Turbo)

2. **catalog.betting_odds**
   - Stores odds for each formula tier
   - Multiple tiers per formula (e.g., Chance 3+ has 2N and 3N)

3. **catalog.perm_combination_costs**
   - Pre-calculated costs for standard PERM configurations
   - Numbers selected → combinations generated → cost per combination

4. **edge_lab.agent_betting_preferences**
   - Agent-specific formula preferences
   - Preferred numbers count, stake ratio, confidence threshold
   - Priority for formula selection

5. **edge_lab.agent_decisions** (extended)
   - Added formula_id, formula_type, numbers_selected_count
   - Added combinations_generated, cost_per_combination

6. **edge_lab.decision_outcomes** (extended)
   - Added tier_achieved, winning_combinations
   - Added gain_per_combination, formula_roi

### Views

1. **catalog.active_formulas_with_odds**
   - All active formulas with their odds in JSONB format
   - Useful for agent formula selection

2. **edge_lab.agent_formula_preferences**
   - Agent preferences with formula details
   - Shows which formulas each agent uses

3. **catalog.formula_performance_summary**
   - Performance metrics by formula
   - Total decisions, win rate, average ROI, profit/loss

## Python Module

### betting_formulas.py

#### Formula Configurations

```python
from lottery_intelligence_platform.betting_formulas import (
    STANDARD_FORMULAS,
    TURBO_FORMULAS,
    CHANCE_FORMULAS,
    PERM_CONFIGS,
    get_formula_config,
    get_all_formulas,
)
```

#### Calculating Potential Gains

```python
from lottery_intelligence_platform.betting_formulas import calculate_potential_gain
from decimal import Decimal

# Example: Chance 3+ with 3 numbers selected
result = calculate_potential_gain(
    formula_code="CHANCE_3_PLUS",
    numbers_selected=[10, 20, 30],
    winning_numbers=[10, 20, 45],  # 2 matches
    total_stake=Decimal("1000"),
)

# Returns:
# {
#     "status": "WIN",
#     "tier": "2N",
#     "winning_combinations": 1,
#     "gain_per_combination": 60000,
#     "total_gain": 60000,
#     "net_profit": 59000,
#     "roi": 5900.0
# }
```

#### PERM Cost Calculation

```python
from lottery_intelligence_platform.betting_formulas import calculate_perm_cost

# PERM 2 with 5 numbers
combinations, cost_per_combination = calculate_perm_cost(
    formula_code="PERM_2",
    numbers_selected=5,
    total_stake=Decimal("1000"),
)

# Returns: (10, Decimal("100"))
# 10 combinations, 100 FCFA per combination
```

#### Payout Matrix

```python
from lottery_intelligence_platform.betting_formulas import get_formula_payout_matrix

# Get all possible outcomes for a formula
matrix = get_formula_payout_matrix("CHANCE_3_PLUS", Decimal("1000"))

# Returns list of dictionaries showing each scenario:
# [
#     {"matches": 2, "tier": "2N", "winning_combinations": 1,
#      "total_gain": 60000, "net_profit": 59000, "roi": 5900},
#     {"matches": 3, "tier": "3N", "winning_combinations": 1,
#      "total_gain": 1750000, "net_profit": 1749000, "roi": 174900}
# ]
```

## Agent Integration

### Setting Agent Formula Preferences

```python
import psycopg
from lottery_intelligence_platform.betting_formulas import get_formula_config

connection = psycopg.connect(dsn)

# Get formula ID
formula = get_formula_config("CHANCE_3_PLUS")

# Set agent preference
connection.execute(
    """INSERT INTO edge_lab.agent_betting_preferences
       (preference_id, agent_id, formula_id, preferred_numbers_count,
        preferred_stake_ratio, min_confidence_threshold, is_enabled, priority)
       VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s)""",
    (agent_id, formula.formula_id, 3, 0.02, 0.6, True, 1),
)
```

### Making Decisions with Formulas

```python
from lottery_intelligence_platform.agent_engine import make_decision
from lottery_intelligence_platform.betting_formulas import get_formula_config

# Get formula configuration
formula = get_formula_config("CHANCE_3_PLUS")

# Make decision with formula
decision = make_decision(
    connection,
    agent_id=agent_id,
    draw_id=draw_id,
    draw_type_id=draw_type_id,
    decision_type="BET",
    selected_numbers=[10, 20, 30],
    stake_amount=Decimal("1000"),
    reasoning="Chance 3+ with frequency-based selection",
    confidence_score=0.65,
    formula_id=formula.formula_id,  # NEW PARAMETER
    expected_outcome={
        "expected_tier": "2N",
        "expected_gain": 60000,
    },
)
```

### Settlement with Formula Calculations

```python
from lottery_intelligence_platform.agent_engine import settle_decision
from lottery_intelligence_platform.betting_formulas import calculate_potential_gain

# Calculate actual gain with formula
result = calculate_potential_gain(
    formula_code="CHANCE_3_PLUS",
    numbers_selected=decision.selected_numbers,
    winning_numbers=winning_numbers,
    total_stake=decision.stake_amount,
)

# Settle with formula-specific data
outcome = settle_decision(
    connection,
    decision_id=decision.decision_id,
    draw_version_id=draw_version_id,
    winning_numbers=winning_numbers,
    hit_count=len(set(decision.selected_numbers) & set(winning_numbers)),
    payout=result["total_gain"],
    settlement_details={
        "tier_achieved": result["tier"],
        "winning_combinations": result["winning_combinations"],
        "formula_roi": result["roi"],
    },
)
```

## Formula Comparison for Agents

### PERM 2 vs Chance 3+ (Budget 1000 FCFA)

| Scenario | PERM 2 (5 numéros) | Chance 3+ (3 numéros) |
|----------|-------------------|----------------------|
| 0-1 numéro | 0 FCFA | 0 FCFA |
| 2 numéros | 24 000 FCFA (1 paire) | 60 000 FCFA (palier 2N) |
| 3 numéros | 72 000 FCFA (3 paires) | 1 750 000 FCFA (palier 3N) |
| 4 numéros | 144 000 FCFA (6 paires) | 1 750 000 FCFA (max) |
| 5 numéros | 240 000 FCFA (10 paires) | 1 750 000 FCFA (max) |

**Agent Strategy Considerations:**
- **PERM 2**: Higher probability of at least 2 matches (5 numbers vs 3), but lower maximum gain
- **Chance 3+**: Lower probability of 2 matches, but massive jackpot if 3 matches hit
- **Risk Tolerance**: Conservative agents prefer PERM 2, aggressive agents prefer Chance 3+

### PERM 2 Cost Analysis (100 FCFA per combination)

| Numéros | Combinaisons | Coût total | Coût/combinaison |
|---------|-------------|------------|------------------|
| 3 | 3 | 300 FCFA | 100 FCFA |
| 4 | 6 | 600 FCFA | 100 FCFA |
| 5 | 10 | 1 000 FCFA | 100 FCFA |
| 6 | 15 | 1 500 FCFA | 100 FCFA |
| 7 | 21 | 2 100 FCFA | 100 FCFA |
| 8 | 28 | 2 800 FCFA | 100 FCFA |
| 9 | 36 | 3 600 FCFA | 100 FCFA |
| 10 | 45 | 4 500 FCFA | 100 FCFA |

**Agent Budget Considerations:**
- 10 000 FCFA capital: Max 10 numbers with PERM 2
- 50 000 FCFA capital: Can use up to 10 numbers multiple times
- 100 000 FCFA capital: Full range of options

## Testing

### Unit Tests

```python
import pytest
from lottery_intelligence_platform.betting_formulas import (
    calculate_potential_gain,
    calculate_perm_cost,
    get_formula_payout_matrix,
)
from decimal import Decimal

def test_chance_3_plus_2_matches():
    result = calculate_potential_gain(
        formula_code="CHANCE_3_PLUS",
        numbers_selected=[10, 20, 30],
        winning_numbers=[10, 20, 45],
        total_stake=Decimal("1000"),
    )
    assert result["status"] == "WIN"
    assert result["tier"] == "2N"
    assert result["total_gain"] == Decimal("60000")

def test_perm_2_cost():
    combinations, cost = calculate_perm_cost(
        formula_code="PERM_2",
        numbers_selected=5,
        total_stake=Decimal("1000"),
    )
    assert combinations == 10
    assert cost == Decimal("100")
```

### Integration Tests

```python
def test_agent_decision_with_formula(connection):
    # Create agent
    agent = create_agent(connection, code="TEST_FORMULA", ...)

    # Set formula preference
    formula = get_formula_config("CHANCE_3_PLUS")
    connection.execute(
        "INSERT INTO edge_lab.agent_betting_preferences ...",
        (agent.agent_id, formula.formula_id, ...)
    )

    # Make decision with formula
    decision = make_decision(
        connection,
        agent_id=agent.agent_id,
        formula_id=formula.formula_id,
        ...
    )

    # Verify formula stored
    stored = connection.execute(
        "SELECT formula_id FROM edge_lab.agent_decisions WHERE decision_id = %s",
        (decision.decision_id,),
    ).fetchone()
    assert stored[0] == formula.formula_id
```

## Migration

Apply migration 0023 to add betting formulas to the database:

```bash
# Migration will be applied automatically on startup
# Or manually:
python -c "
import psycopg
from lottery_intelligence_platform.migrations import apply_migrations

conn = psycopg.connect('your_dsn')
migrations = apply_migrations(conn)
print(f'Applied {len(migrations)} migrations')
conn.close()
"
```

## API Endpoints

The following endpoints will be added to expose formula data:

- `/api/formulas` - All active formulas with odds
- `/api/formulas/{code}` - Specific formula details
- `/api/formulas/perm-costs` - PERM combination costs
- `/api/agents/{agent_id}/formula-preferences` - Agent's formula preferences
- `/api/formulas/performance` - Performance by formula

## Next Steps

1. **Apply migration 0023** to create betting formula tables
2. **Update agent decision logic** to use formula calculations
3. **Add formula selection heuristics** to agent decision-making
4. **Create formula-specific strategies** in agent memory
5. **Track formula performance** in agent success/failure memory
6. **Add API endpoints** for formula data
7. **Update frontend** to show formula information in agent dashboard

## Reference

Official source: https://lotobonheur.ci/distribution-des-gains
