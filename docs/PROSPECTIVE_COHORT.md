# Prospective cohort — generation contract

## Cohort manifest (sealed, versioned)

`research.prospective_cohorts` + `prospective_cohort_versions` (append-only,
hash of definition) + `prospective_cohort_members`.

Current sealed version: **`prospective_turbo_v1` v1**, effective 2026-10-04:

- **Models** (all draw types, `draw_type_id NULL`): `null_model_benchmark`
  (seeded uniform reference), `top_k_frequency`, `rolling_frequency`
  (200 draws), `bayesian_shrinkage` (α=5).
- **Contract**: pick 2 numbers from [1, 90], stake 100 XOF.
- **Primary metrics**: `hit_rate`, `turbo_2_hit_rate`, `net_profit`, `roi`.
- **Exclusion criteria**: draw types with < 30 historical draws are eligible
  but reported under low-power.
- Changing membership or parameters requires a **new cohort_version** —
  v1 is never edited.

## Generation (`generate_predictions` job, 2×/hour)

1. Refresh the official schedule (best effort) → targets = real
   `EXPECTED`/`SCHEDULED` draws within 7 days without a valid result;
   fallback = recently active types for tomorrow.
2. For each (target, ACTIVE member): compute picks **strictly** from draws
   `scheduled_date < target` (expanding/rolling/Dirichlet/seeded-null).
3. `record_prediction` — idempotent via
   `UNIQUE(model_version_id, draw_type_id, scheduled_date, predicted_numbers)`.
4. Coverage row per combination: `GENERATED` / `MISSING` / `FAILED` /
   `INELIGIBLE` — absences are explicit, a `FAILED` member never kills the batch.

## Anti-leakage (two barriers)

- Construction: `_train_counts` reads only draws strictly before the target.
- Settlement lock: `created_at < result_observed_at`, else `INVALID` +
  audit; `dataset_version` member-date check → `LEAKAGE_DETECTED`.

## Settlement & metrics

Reuses `settle_draw`: `prediction_outcomes` (hit_count, positional_hits,
turbo variants under the official positional rule), `strategy_settlements`
scope `REALIZED`. Aggregates via `research.prospective_performance` view —
never mixed with backtest/walk-forward/OOS scopes.

## Verified live

2026-10-04 *Digital Reveil 8h*: 4 predictions generated → result collected →
locked → scored (outcomes + turbo rows recorded). First realized prospective
evidence in the ledger.
