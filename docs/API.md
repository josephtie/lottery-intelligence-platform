# Read API

Stdlib-only HTTP server (`lottery_intelligence_platform.api`) exposing the
platform's live views. Read-only: no write endpoints, localhost bind.

```bash
PYTHONPATH=src .venv/bin/python -m lottery_intelligence_platform.api --port 8090
# LOTTERY_DB_DSN overrides the default local DSN.
```

## Endpoints

| Route | Source | Content |
|---|---|---|
| `GET /api/health` | ops + research | open alerts, pending/scored predictions, job runs & failures 24h, last run |
| `GET /api/prospective/metrics` | `research.prospective_metrics` | per cohort×model×draw_type: coverage denominators, settlement rate, positional hits, turbo economics, `historical_draws`, `low_power` |
| `GET /api/prospective/coverage` | `research.prediction_coverage` | status × reason counts — explicit absences |
| `GET /api/power` | `research.draw_type_power` | settled draws per type + 30-draw threshold flag |
| `GET /api/predictions?status=&limit=` | `research.predictions` | latest predictions (status filter: PENDING/LOCKED/SCORED/INVALID; limit ≤500) |
| `GET /api/findings` | `research.findings` + hypotheses | research ledger, newest first |
| `GET /api/outcomes` | `research.prediction_outcomes` | 200 most recent settled outcomes |

Unknown route → 404 with the route list. Any query error → 500 with a
truncated message; the server keeps serving.

All numbers come straight from the views: denominators (eligible_pairs,
generated, settled) are explicit, and `low_power` marks draw types below the
cohort's 30-draw threshold — a cell with 2 historical draws never carries the
same weight as one with 1 600.
