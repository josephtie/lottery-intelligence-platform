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
scope `REALIZED`. Never mixed with backtest/walk-forward/OOS scopes.

Two read layers, both derived — never mutated:

- `research.prospective_performance` (0015): one row per settled prediction
  (model, draw, hits, positional_hits, turbo metrics).
- `research.prospective_metrics` (0016): per cohort_version × model ×
  draw_type — explicit denominators: `eligible_pairs`, `generated`,
  `missing`, `failed`, `ineligible`, `absent_total`, `pending`, `locked`,
  `invalid`, `settled`, `settlement_rate = settled/generated`, `mean_hits`,
  `hits_first_1..5`, and `turbo` JSONB per variant (bets, hits, stake,
  payout, net, roi). The weekly report reads this view.

A hit is never evidence of profitability; ROI is the economic metric.

## Coverage reconciliation

`_reconcile_coverage` runs at the start of every generation (idempotent):

- predictions matching an ACTIVE cohort member but lacking a coverage row
  are linked back as `GENERATED` / `reason='reconciled…'`;
- settled draws inside the cohort window whose pair never produced a
  prediction are marked `MISSING` / `reason='draw settled before
  generation evaluated this pair'`.

Silent absence is impossible: every admissible draw×model pair has a row.

## Change-point review (2026-10-04)

The 22 scan-flagged distribution splits (strongest: Fortune Thursday
2023-08, Midweek 2022-09/11, Digital 23h 2023-01) were reviewed for cause:

- **No renaming**: every draw type runs continuously since 2020-11.
- **No structural change**: universe stays 1-90, weekly/daily volumes stable.
- **No global event**: cross-type chi2 at 2023-08 averages 89 = the null df;
  only 2-3 types deviate, marginally.
- **Power artefacts**: Digital 21h/23h flag trivial deviations because
  n > 16k numbers gives the test extreme sensitivity.
- **No coverage artefact**: Midweek has one missing Wednesday, not a gap.

Verdict (findings ledger, `INCONCLUSIVE`): small-magnitude drift, no
exploitable regime — consistent with regime conditioning improving 0/277
cells. Decision: **no draw-type split, no cohort segmentation**. The cohort
keeps draw types as atomic units.

## Generation horizon (2026-10-04 update)

`_targets` now unions official `EXPECTED` draws with per-type weekday
projections over a 7-day horizon: a daily type gets seven future targets, a
weekly type one. Predictions are recorded days ahead of publication instead
of hours — the 12 `MISSING` pairs of 2026-10-04 (draws settled before the
cohort existed) remain the only legitimate misses.

`historical_draws` and `low_power` (< 30 settled draws, per the cohort
charter) are exposed on every metrics cell via `research.draw_type_power`;
Digital 7h (2 draws) and Nuit Etoilee (22) are the only flagged types.

Settlement resolves the payout rule temporally: highest `effective_from`
covering the draw date on its game_version, `VERIFIED_OFFICIAL` preferred,
game-level fallback for versions carrying no rule.

## Verified live

2026-10-04 *Digital Reveil 8h*: 4 predictions generated → result collected →
locked → scored (outcomes + turbo rows recorded). First realized prospective
evidence in the ledger. Reconciliation healed 4 orphan predictions and
marked 12 legitimately missed pairs (04/10 draws settled before the first
cohort run).
