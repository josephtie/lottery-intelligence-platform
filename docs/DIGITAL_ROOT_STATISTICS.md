# Digital Root Statistics - Lottery Edge Lab

## Overview

Digital Root Statistics is a descriptive analysis module for Lottery Edge Lab that analyzes digital root (racine numérique) patterns in historical lottery results across multiple time windows: 10, 30, 45, 60, and 90 calendar days.

**Key Principle**: This module provides descriptive statistics without predictive claims. It helps understand what has happened, not what will happen.

## Digital Root Convention

### Definition

Digital root is the recursive sum of digits until a single digit is obtained.

**Convention**: Digital root 9 is represented as 0.

### Examples

```
74 → 7 + 4 = 11 → 1 + 1 = 2
84 → 8 + 4 = 12 → 1 + 2 = 3
12 → 1 + 2 = 3
29 → 2 + 9 = 11 → 1 + 1 = 2
10 → 1 + 0 = 1
45 → 4 + 5 = 9 → 0
86 → 8 + 6 = 14 → 1 + 4 = 5
```

### Number Families

Each root (0-8) corresponds to 10 numbers in the 1-90 range:

```
Root 0: 09, 18, 27, 36, 45, 54, 63, 72, 81, 90
Root 1: 01, 10, 19, 28, 37, 46, 55, 64, 73, 82
Root 2: 02, 11, 20, 29, 38, 47, 56, 65, 74, 83
Root 3: 03, 12, 21, 30, 39, 48, 57, 66, 75, 84
Root 4: 04, 13, 22, 31, 40, 49, 58, 67, 76, 85
Root 5: 05, 14, 23, 32, 41, 50, 59, 68, 77, 86
Root 6: 06, 15, 24, 33, 42, 51, 60, 69, 78, 87
Root 7: 07, 16, 25, 34, 43, 52, 61, 70, 79, 88
Root 8: 08, 17, 26, 35, 44, 53, 62, 71, 80, 89
```

**Important**: This produces **9 classes** (0-8), not 10. Root 9 is merged into root 0.

## Time Windows

The module analyzes five nested time windows:

- **10 days**: Recent short-term patterns
- **30 days**: One month patterns
- **45 days**: Mid-term patterns
- **60 days**: Two months patterns
- **90 days**: Quarterly patterns

### Window Boundaries

- **Reference date**: Exclusive (the prediction date or "today")
- **End date**: Reference date - 1 day
- **Start date**: End date - (window_days - 1) days

Example for 30-day window with reference date 2024-01-31:
- End date: 2024-01-30
- Start date: 2024-01-02
- Analyzes: 2024-01-02 to 2024-01-30 (inclusive)

### Important Notes

- Uses **actual calendar days**, not draw counts
- Respects official draw dates and timezones
- Nested windows are **not independent samples**
- Sample sizes decrease with smaller windows

## Analysis Components

### 1. Global Distribution

For each root (0-8), within a window:
- **Occurrences**: Count of times this root appears
- **Percentage**: % of all numbers observed
- **Draws containing**: Number of draws with this root
- **Deviation from reference**: Difference from expected (10/90 ≈ 11.11%)

**Expected frequency**: Each root has 10 numbers out of 90, so expected is 11.11%.

### 2. Position-Specific Distribution

For each position in the ordered result:
- Root counts per position
- Root percentages per position
- Most frequent root per position
- Sample size

**Never mixes positions or games** without providing separate statistics.

### 3. Draw-Level Signatures

For each draw in the window:
- Original winning numbers
- Root sequence (roots in order)
- Number of distinct roots
- Root repetitions (which roots repeat)
- Date and game

### 4. Temporal Evolution

Compares changes between windows:
- Roots increasing or decreasing
- Percentage point differences
- Sample size changes
- Trend stability

**Nested windows**: Changes from 90→60→45→30→10 days show how patterns evolve.

### 5. Number Family Frequency

For each root's number family:
- Total historical occurrences
- Frequency by position
- Frequency by game
- Frequency by time window

**Important**: Families with more numbers naturally have more occurrences. Use comparable denominators for comparisons.

### 6. Transition Matrices

Analyzes root transitions between:
- Successive draws of the same game
- Different games on the same day
- Time slots (if data available)

For each source root:
- Count of transitions to each target root
- Conditional probability P(target|source)
- Total observations

**Warning**: Declares no predictive relationship without validation on future draws. Shows "insufficient data" for small samples.

## Data Quality

The module checks for:
- Duplicate draws (same draw counted twice)
- Missing dates
- Invalid dates

**Data quality score**: 0-1 scale
- -0.3 for duplicate draws
- -0.3 for missing dates
- Perfect = 1.0

## Statistical Validation

### Walk-Forward Validation

The module includes a walk-forward validator to test whether statistics have predictive power:

1. **Training Phase**: Calculate statistics from data before date T
2. **Prediction Phase**: Generate sealed prediction for date T
3. **Settlement Phase**: Wait for actual result, compare
4. **Update Phase**: Update metrics
5. **Repeat**: Move to next date

### Metrics

- **Root hit rate**: % of predicted roots that appear
- **Number hit rate**: % of predicted numbers that appear
- **Comparison to random baseline**
- **Statistical significance** (requires 30+ predictions)

### Baseline

Random baseline performance:
- Expected root hit rate: ~55.6% (5 random roots out of 9)
- Expected number hit rate: ~5.6% (5 random numbers out of 90)

**No window is declared better solely because it was chosen after observing results.**

## API Endpoints

### Get Available Games
```
GET /api/digital-root-stats/games
```

Returns list of games with total draw counts.

### Get Statistics Summary
```
GET /api/digital-root-stats/summary?draw_type={game}&window_days={10|30|45|60|90}&reference_date={YYYY-MM-DD}
```

Parameters:
- `draw_type`: Game name or code (required)
- `window_days`: Time window (default: 30)
- `reference_date`: Reference date (default: today)

Returns complete statistics including:
- Global distribution
- Position distributions
- Draw signatures (last 20)
- Family frequencies
- Temporal changes
- Transition matrices
- Data quality score
- Warning if sample size < 10

## Usage Example

```python
from lottery_intelligence_platform.digital_root_statistics import DigitalRootStatistics
import psycopg

# Initialize analyzer
analyzer = DigitalRootStatistics()

# Calculate statistics for a game
with psycopg.connect(dsn) as conn:
    game_stats = analyzer.calculate_game_statistics(
        conn,
        game_id=game_uuid,
        reference_date=date(2024, 1, 31),
    )

# Access 30-day window
window_30 = game_stats.windows[30]

print(f"Draws in 30-day window: {window_30.draw_count}")
print(f"Total numbers analyzed: {window_30.total_numbers_analyzed}")
print(f"Data quality score: {window_30.data_quality_score}")

# View global distribution
for dist in window_30.global_distribution:
    print(f"Root {dist.root}: {dist.occurrences} ({dist.percentage:.2f}%) "
          f"deviation: {dist.deviation_from_reference:+.2f}pp")

# View temporal changes
for change in game_stats.temporal_changes:
    if change.window_to == 30:
        print(f"Root {change.root}: {change.trend} "
              f"{change.percentage_change:+.2f}pp "
              f"({change.window_from}→{change.window_to} days)")
```

## Validation Example

```python
from lottery_intelligence_platform.digital_root_validation_stats import WalkForwardStatisticalValidator
from lottery_intelligence_platform.digital_root_statistics import DigitalRootStatistics

# Initialize
analyzer = DigitalRootStatistics()
validator = WalkForwardStatisticalValidator(analyzer, default_window=30)

# Run walk-forward validation
with psycopg.connect(dsn) as conn:
    metrics = validator.validate_game(
        conn,
        game_id=game_uuid,
        start_date=date(2023, 10, 1),
        end_date=date(2023, 12, 31),
        window_days=30,
    )

print(f"Root hit rate: {metrics.root_hit_rate:.2%}")
print(f"Number hit rate: {metrics.number_hit_rate:.2%}")

# Compare to baseline
comparison = validator.compare_to_baseline(metrics)
print(f"Improvement over random: {comparison['root_hit_rate_improvement_percent']:.1f}%")
print(f"Statistically significant: {comparison['statistically_significant']}")
```

## Interface Requirements

The Digital Root Statistics page should include:

- **Filter by game** (dropdown)
- **Reference date** (date picker)
- **Window selector** (10/30/45/60/90 days)
- **Root frequency table** (9 rows with occurrences, %, deviation)
- **Position view** (tabbed or stacked)
- **Window comparison chart** (bar or line chart)
- **Recent draw signatures** (last 10-20 draws)
- **Transition matrices** (9x9 heatmap)
- **Data quality indicator** (score 0-1)
- **Warning banner** when sample size < 10
- **Clear disclaimer**: "Descriptive statistics, not predictive"

## Limitations and Warnings

1. **Not Predictive**: High frequency ≠ guaranteed future occurrence
2. **Nested Windows**: Not independent samples, avoid treating as such
3. **Small Samples**: Short windows have few observations, high uncertainty
4. **Family Size Bias**: Larger families naturally have more occurrences
5. **No Causality**: Correlation does not imply causation
6. **Multiple Comparisons**: Risk of false positives without correction
7. **Time-Varying**: Patterns change over time, nothing is permanent

## Best Practices

1. **Always show sample sizes** alongside percentages
2. **Compare all windows** before drawing conclusions
3. **Use walk-forward validation** before predictive use
4. **Document data quality issues** when present
5. **Separate descriptive and predictive** phases
6. **Never claim predictive power** without validation
7. **Use appropriate baselines** for comparisons

## References

- Digital root: https://en.wikipedia.org/wiki/Digital_root
- Walk-forward validation: See walkforward_engine migration
- Statistical significance: Use Bonferroni correction for multiple comparisons
