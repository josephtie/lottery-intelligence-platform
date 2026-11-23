# Anti-look-ahead guarantees

## Temporal proof per prediction

For every scored prediction the ledger can answer: generated **when**,
from **which** dataset version, by **which** model/strategy version,
**before** which draw — and the actual result.

Enforced checks:

1. **`created_at < result_observed_at`** — the canonical draw version's
   observation timestamp is authoritative. A prediction created after the
   result was observed can never be scored: `INVALID` + `LATE_PREDICTION`
   audit event.
2. **Immutability** — `research.guard_prediction_update()` freezes all
   content fields at insert; only whitelisted status transitions are
   allowed. Amendment attempts are rejected and audited
   (`IMMUTABLE_PREDICTION_VIOLATION` alert).
3. **Dataset-version leakage** — when a prediction declares
   `dataset_version_id`, settlement verifies that **no dataset member draw
   has `scheduled_date >=` the prediction target date**. Violation →
   `INVALID` + `LEAKAGE_DETECTED` critical alert; excluded from
   OOS/prospective metrics.
4. **Prospective-only insert** — `record_prediction` rejects target dates
   in the past, non-distinct numbers, out-of-range values, negative stake.

## Scope discipline

`research.strategy_settlements.scope` separates `IN_SAMPLE`, `VALIDATION`,
`WALK_FORWARD`, `OUT_OF_SAMPLE`, `PROSPECTIVE`, `REALIZED`. Metrics and
findings must never aggregate across scopes: a backtested ROI and a
realized ROI answer different questions with different evidence strength.

## What is still required for certification

- `PROSPECTIVE` scope metrics computed only from predictions that were
  `LOCKED` before their draw.
- A minimum count of prospective predictions per model before any
  validation claim (the historical catalog showed no validated edge —
  prospective evidence is the only admissible next proof).
