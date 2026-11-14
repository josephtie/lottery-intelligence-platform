# Prediction settlement

## Lifecycle

```
PENDING ──(draw frozen, created_at < result_observed_at)──▶ LOCKED ──▶ SCORED
   │                                                            ▲
   ├──(created_at ≥ result_observed_at)──▶ INVALID               │ comparison
   └──(dataset_version leakage)──────────▶ INVALID + LEAKAGE_DETECTED alert
```

`SCORED` and `INVALID` are terminal. All content fields are immutable from
insert (trigger `research.guard_prediction_update`).

## Outcome record — `research.prediction_outcomes`

One row per prediction (`UNIQUE(prediction_id)` ⇒ no double settlement):

- `predicted_numbers`, `winning_numbers`, `hit_count`
- `positional_hits`: `{"first_1": n, …, "first_5": n}` — hits within the
  first k ordered positions
- `metrics.turbo`: per-variant settlement under the **verified official
  positional rule** (`official-turbo-position-2026-10`):

| Variant | Condition | Multiplier |
|---|---|---|
| turbo_2 | picks ⊆ first 2 positions | 2400 |
| turbo_3 | picks ⊆ first 3 positions | 800 |
| turbo_4 | picks ⊆ first 4 positions | 400 |
| turbo_5 | picks ⊆ first 5 positions | 240 |

Each variant reports `hit, stake, payout, net, roi`. Multipliers are read
from the payout rule version linked to the strategy (fallback: the
official rule) — never hardcoded in the settlement path.

## Strategy settlements — `research.strategy_settlements`

For every `strategy_version_id` carried by a settled prediction, one row
per Turbo variant with `scope='REALIZED'`:
`total_stake, total_payout, net_profit, roi`.
The UNIQUE key `(strategy_version_id, draw_id, variant, scope)` makes
re-settlement a no-op. Scopes `IN_SAMPLE / VALIDATION / WALK_FORWARD /
OUT_OF_SAMPLE / PROSPECTIVE / REALIZED` are distinct — backtests and live
results never mix.

## Concurrency

`settle_draw` takes `FOR UPDATE` on the draw row; concurrent workers
serialize there. The outcome insert uses `ON CONFLICT DO NOTHING`, so two
workers racing produce exactly one settlement.
