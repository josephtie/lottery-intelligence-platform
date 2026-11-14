# Digital Root Turbo Analyzer

## Overview

The Digital Root Turbo Analyzer is a predictive model for lottery Turbo markets based on digital root (racine numérique) patterns. It discovers temporary relationships between digital roots across draws and games, then uses these patterns to generate Turbo bet candidates.

## Core Principles

1. **Observe First, Detect Later**: The model discovers patterns from data rather than assuming fixed rules
2. **Temporary Relations**: All relations are time-limited (2-3 day observation window) and must be continuously validated
3. **Statistical Validation**: Every detected relation is compared to a random baseline
4. **Walk-Forward Validation**: Strict separation of exploration, out-of-sample, and prospective phases
5. **No Assumptions**: Never presumes a game predicts another, a day has a fixed rule, or a relation persists

## Architecture

### Components

1. **digital_root.py** - Digital root transformation utilities
   - Calculate digital roots (1-90 → 0-8, where 0 represents 9)
   - Generate number families by root
   - Precomputed lookup tables for performance

2. **digital_root_relations.py** - Relation discovery and tracking
   - Discover temporary patterns (same-game successive, cross-game same-day, time slots)
   - Track relation lifecycle (candidate → observing → confirmed/expired)
   - Monte Carlo baseline calculation
   - Statistical significance testing

3. **digital_root_analyzer.py** - Main prediction engine
   - Load historical data
   - Discover and train on patterns
   - Generate root predictions
   - Generate Turbo candidates from roots
   - Update with actual results

4. **digital_root_validation.py** - Walk-forward validation
   - Strict temporal separation
   - Sealed predictions before results known
   - Performance metrics calculation
   - Baseline comparison

5. **digital_root_picker.py** - Integration with prediction system
   - Picker functions compatible with existing architecture
   - `digital_root_turbo` and `digital_root_turbo_v2` variants

## Digital Root Transformation

### Definition

Digital root is the recursive sum of digits until a single digit is obtained.

**Convention**: Digital root 9 is represented as 0.

### Examples

```
74 → 7 + 4 = 11 → 1 + 1 = 2
45 → 4 + 5 = 9 → 0
86 → 8 + 6 = 14 → 1 + 4 = 5
9 → 0
18 → 1 + 8 = 9 → 0
```

### Number Families

Each root (0-8) corresponds to 10 numbers in the 1-90 range:

```
Root 0: 9, 18, 27, 36, 45, 54, 63, 72, 81, 90
Root 1: 1, 10, 19, 28, 37, 46, 55, 64, 73, 82
Root 2: 2, 11, 20, 29, 38, 47, 56, 65, 74, 83
Root 3: 3, 12, 21, 30, 39, 48, 57, 66, 75, 84
Root 4: 4, 13, 22, 31, 40, 49, 58, 67, 76, 85
Root 5: 5, 14, 23, 32, 41, 50, 59, 68, 77, 86
Root 6: 6, 15, 24, 33, 42, 51, 60, 69, 78, 87
Root 7: 7, 16, 25, 34, 43, 52, 61, 70, 79, 88
Root 8: 8, 17, 26, 35, 44, 53, 62, 71, 80, 89
```

## Relation Discovery

### Relation Types

1. **SAME_GAME_SUCCESSIVE**: Consecutive draws of the same game
2. **CROSS_GAME_SAME_DAY**: Different games on the same calendar day
3. **TIME_SLOT**: Same time slot across different days
4. **ROOT_TRANSITION**: Patterns in root sequences
5. **POSITION_ASSOCIATION**: Root association with winning positions

### Relation Lifecycle

```
CANDIDATE → OBSERVING → CONFIRMED_TEMPORARY
     ↓           ↓
   WEAKENING → EXPIRED
     ↓
   REJECTED
```

- **CANDIDATE**: Newly discovered, needs validation
- **OBSERVING**: Active observation window (2-3 days)
- **WEAKENING**: Evidence declining
- **EXPIRED**: Observation window closed without confirmation
- **CONFIRMED_TEMPORARY**: Validated but time-limited
- **REJECTED**: Failed statistical validation

### Evidence Tracking

For each relation, track:
- Total observations
- Successful predictions
- Discovery date
- Last validation date
- Current success rate
- Baseline success rate (random)
- Statistical significance

## Prediction Pipeline

### 1. Load Historical Data

Load settled draws before the target date, preserving:
- Game type
- Scheduled date
- Winning numbers (ordered)
- Time slot (if available)

### 2. Discover Relations

From historical data, discover:
- Same-game successive root transitions
- Cross-game same-day root associations
- Time slot patterns
- Position-specific root patterns

### 3. Predict Roots

For each target position:
- Get active relations for the game
- Rank by confidence (success rate - baseline)
- Return top N root predictions

Each prediction includes:
- Root value
- Confidence score
- Supporting relation
- Uncertainty level (HIGH/MEDIUM/LOW)
- Observation window days
- Comparison to random baseline

### 4. Generate Turbo Candidates

For each predicted root:
- Get the 10-number family for that root
- Rank by historical frequency
- Calculate adjusted score (70% root confidence + 30% number frequency)

### 5. Select Final Numbers

Sort candidates by adjusted score and select top K numbers for the Turbo variant:
- Turbo 2: 2 numbers
- Turbo 3: 3 numbers
- Turbo 4: 4 numbers
- Turbo 5: 5 numbers

## Walk-Forward Validation

### Process

1. **Training Phase**: Use data before date T to discover relations
2. **Prediction Phase**: Generate sealed prediction for date T
3. **Settlement Phase**: Wait for actual result, compare prediction
4. **Update Phase**: Update relations with actual result
5. **Repeat**: Move to next date

### Metrics

- Hit rate (numbers in winning set)
- Turbo hit rate (all predicted numbers in first K positions)
- Total stake vs payout
- ROI (return on investment)
- Comparison to random baseline

### Baseline Calculation

Monte Carlo simulation of random predictions to establish:
- Expected hit rate
- Expected Turbo hit rate
- Expected ROI

A relation is statistically significant only if it consistently outperforms this baseline.

## Integration

### Using the Picker

```python
from lottery_intelligence_platform.prediction_generation import PICKERS

# Digital root Turbo picker
predicted_numbers = PICKERS["digital_root_turbo"](
    connection=conn,
    draw_type_id=game_id,
    target=target_date,
    params={
        "turbo_variant": "turbo_2",
        "top_roots": 5,
        "candidates_per_root": 10,
    },
    seed=None,
)
```

### Direct Analyzer Usage

```python
from lottery_intelligence_platform.digital_root_analyzer import DigitalRootTurboAnalyzer

analyzer = DigitalRootTurboAnalyzer(
    observation_window_days=3,
    min_observations=5,
    default_turbo_variant="turbo_2",
)

# Discover and train
analyzer.discover_and_train(connection, [game_id], training_cutoff)

# Predict
prediction = analyzer.predict(
    connection,
    game_id,
    target_date,
    turbo_variant="turbo_2",
)

# Get final numbers
numbers = prediction.predicted_numbers
```

## API Endpoints

### Active Relations
```
GET /api/digital-root/relations
```
Returns currently active relations (OBSERVING or CONFIRMED_TEMPORARY).

### Relations History
```
GET /api/digital-root/relations/history
```
Returns all relations with their discovery and validation history.

### Predictions
```
GET /api/digital-root/predictions
```
Returns digital root predictions with settlement status.

### Validation Results
```
GET /api/digital-root/validation
```
Returns walk-forward validation results and baseline comparisons.

### Summary
```
GET /api/digital-root/summary
```
Returns aggregate statistics:
- Active/candidate/expired relation counts
- Total/settled prediction counts
- Average Turbo hit rate
- Average ROI

## Database Schema

### Tables

1. **research.digital_root_relations**
   - Stores discovered relations with evidence and status
   - Indexed by game, status, relation type

2. **research.digital_root_predictions**
   - Stores predictions for audit and analysis
   - Links to draws and contains settlement results

3. **research.digital_root_validation**
   - Stores walk-forward validation results
   - Contains aggregated metrics and baseline comparisons

### Migration

Apply migration 0025_digital_root_relations.sql to create the schema.

## Testing

Run tests:
```bash
pytest tests/test_digital_root.py -v
```

Test coverage:
- Digital root calculation
- Relation evidence tracking
- Relation lifecycle
- Discovery from historical data
- Prediction generation
- Validation metrics

## Performance Considerations

- Precomputed lookup tables for root → number mapping
- In-memory relation tracking (for runtime)
- Batch loading of historical data
- Efficient database indexes for relation queries

## Limitations and Warnings

1. **No Guaranteed Patterns**: The model only reports what it observes. Not all games have predictable root patterns.
2. **Time-Limited Relations**: Relations expire after 2-3 days. A pattern that worked yesterday may not work today.
3. **Small Sample Sizes**: Temporary relations may have few observations, leading to high uncertainty.
4. **Statistical Significance**: Many discovered patterns may be random. Always compare to baseline.
5. **Not a Magic Bullet**: This is one tool among many. Use with other models and risk management.

## Future Enhancements

- Support for longer observation windows (with adaptive decay)
- Cross-game relation graph analysis
- Ensemble with other prediction models
- Real-time relation strength monitoring
- Automated relation pruning based on statistical decay
- Integration with agent decision system

## References

- Digital root: https://en.wikipedia.org/wiki/Digital_root
- Turbo market rules: See betting_formulas.py
- Walk-forward validation: See walkforward_engine migration
