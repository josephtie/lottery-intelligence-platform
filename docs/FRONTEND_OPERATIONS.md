# Frontend operations

## Stack

Vue 3 + Vite + TypeScript in `frontend/` — Element Plus, ECharts, Pinia,
vue-router (hash mode), axios. Single entry point is the Python read API:
it serves `frontend/dist` at `/` when built, and falls back to the
self-contained `console.html` at `/console` when it isn't.

## Commands

```bash
cd frontend
npm ci            # reproducible install (package-lock.json committed)
npm run dev       # dev server :8792, proxies /api → :8090
npm run build     # production build → dist/
```

```bash
lottery-api --port 8090        # serves dist at /, console.html at /console
```

## Authentication

If `LOTTERY_API_TOKEN` is set on the API, every `/api/*` call needs a Bearer
token. The UI detects a 401, shows a token prompt (`TokenGate.vue`), stores it
in `localStorage` (`lottery_token`). No secrets are bundled — the token is
entered by the operator at runtime only.

## Environment

| Variable | Where | Purpose |
|---|---|---|
| `LOTTERY_API_TOKEN` | API process | enables Bearer auth; recommended on any non-loopback bind |
| `LOTTERY_DB_DSN` / `LOTTERY_DATABASE_*` | API process | PostgreSQL connection |
| `LOTTERY_API_PORT` | VPS compose | host port mapped to container 8090 |

## Screens ↔ API

| Screen | Endpoints |
|---|---|
| Turbo Laboratory (`/`) | `/api/turbo/summary`, `/api/turbo/variants`, `/api/turbo/models`, `/api/turbo/next`, `/api/turbo/results` |
| Dashboard | `/api/overview`, `/api/draws`, `/api/alerts` |
| Tirages | `/api/draws` |
| Prédictions | `/api/predictions`, `/api/outcomes` |
| Performance prospective | `/api/prospective/metrics`, `/api/prospective/coverage` |
| Laboratoire | `/api/cohorts`, `/api/models`, `/api/datasets` |
| Findings | `/api/findings` |
| Qualité | `/api/quality`, `/api/quality/anomalies`, `/api/quality/collection` |
| Opérations | `/api/jobs`, `/api/reconciliation`, `/api/reconciliation/summary` |

All data is live — there is no demo/fixture path.

## Turbo Laboratory

The landing screen answers four questions from real data only:

- **Next draws** — sealed predictions per model × draw type, with ranks
  (position = array index, matching the positional Turbo rule).
- **Financial summary** — cumulative stakes, gross payout, net, realized ROI
  over `prediction_outcomes.metrics.turbo` (computed by the settlement
  engine under the versioned official rule — never recomputed client-side).
- **Per-variant table** — Turbo 2/3/4/5: registered multiplier, evaluated
  bets, wins, hit rate, stakes, gross, net, cumulative ROI (`n/c` when the
  denominator is zero — never a fake 0 %).
- **Model comparison** — the four pickers vs `null_model_benchmark` on the
  same evaluated draws; per-draw result table with CSV export.

Labeling rule enforced in the UI: these are *prospective evaluations*, not
wagered bets — the banner states no real stake was engaged or collected.

## VPS deployment

The `api` service in `infrastructure/vps/compose.yaml` serves the built SPA —
copy `frontend/dist` into the image build context (the Dockerfile already
copies `src/`; add `COPY frontend/dist ./frontend/dist` if you bake it in),
or run a `npm run build` stage. Token is mandatory beyond loopback.

## Verification checklist

- `npm run build` completes (warning about chunk size is cosmetic).
- `curl -s localhost:8090/` returns the SPA HTML.
- `curl -s localhost:8090/api/health` returns JSON.
- Without token (auth enabled): API returns 401, UI shows the token prompt.
- `/console` always serves the dependency-free fallback page.
