# Frontend audit

## Existing frontend and location

`frontend/` — a Vue 3 + Vite + TypeScript single-page application
(Element Plus, ECharts, Pinia, vue-router, axios, hash router). It was
written for the *previous* project (a SQLite-backed statistics tool):
all ~18 views call endpoints that do not exist on this platform's API
(`/api/lab/*`, `/api/bettypes/*`, `/api/statistics`, `/api/structure`,
`/api/tables/*`, `/api/database` labelled "Base SQLite", …).

Also present: `src/lottery_intelligence_platform/console.html`, a
self-contained single-page dashboard served at `/` by `api.py` — useful
smoke view, not an application.

## API contract inspected

`src/lottery_intelligence_platform/api.py` — stdlib `http.server`,
read-only, returns `{"data": [...]}` (`{"data": {...}}` for singletons),
401 JSON when `LOTTERY_API_TOKEN` is set and Bearer auth is missing.
Endpoints after this phase's extension:

- `/api/health`, `/api/overview` — service health, totals, freshness
- `/api/draws`, `/api/quality`, `/api/quality/anomalies`,
  `/api/quality/collection` — draw history, per-type quality rollup,
  anomaly lines, collection rates
- `/api/predictions?status=&limit=`, `/api/outcomes`, `/api/cohorts`
- `/api/prospective/metrics`, `/api/prospective/coverage`, `/api/power`
- `/api/models`, `/api/findings`, `/api/datasets`
- `/api/jobs`, `/api/alerts`, `/api/reconciliation`,
  `/api/reconciliation/summary`

## Recoverable vs rebuild

| Piece | Verdict |
|---|---|
| `src/App.vue` shell (sidebar groups, dark/gold theme) | reuse, re-pointed nav |
| `src/router.ts` | rewrite route table to real screens |
| `src/api.ts` (axios `/api` + Bearer token) | reuse as-is |
| `src/style.css` design system | reuse as-is |
| All `src/views/*` (old backend calls) | rewrite — zero compatible endpoints |
| `TagsView`/pinia tab system, tags store | keep, optional |
| `console.html` | keep as zero-dependency fallback at `/console` |

## Missing / incomplete screens

All required screens were missing or pointed at dead endpoints:
overview, draws, predictions, research lab, prospective performance,
findings, data quality, operations, reconciliation.

## Strategy

Keep the Vue shell + design system; rewrite every view against the real
API; extend `api.py` with the read-only endpoints the screens need
(overview, jobs, alerts, quality, reconciliation, cohorts) — additive
only, consistent with the existing stdlib architecture. Serve
`frontend/dist` from `api.py` when built so the API remains the single
entry point; `console.html` stays as fallback.

## Integration risks

- **Schema drift** — view columns differed from guesses (fixed by
  querying `information_schema` before writing SQL).
- **Auth** — API requires Bearer only when `LOTTERY_API_TOKEN` is set;
  the UI must surface a token entry when it gets a 401.
- **No demo data** — every number on screen comes from a real endpoint;
  empty states are explicit, never fabricated.
