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
npm run dev       # dev server :8792, proxies /api → :8080
npm run build     # production build → dist/
```

```bash
lottery-api --port 8080        # serves dist at /, console.html at /console
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
| `LOTTERY_API_PORT` | VPS compose | host port mapped to container 8080 |

## Screens ↔ API

| Screen | Endpoints |
|---|---|
| Dashboard | `/api/overview`, `/api/draws`, `/api/alerts` |
| Tirages | `/api/draws` |
| Prédictions | `/api/predictions`, `/api/outcomes` |
| Performance prospective | `/api/prospective/metrics`, `/api/prospective/coverage` |
| Laboratoire | `/api/cohorts`, `/api/models`, `/api/datasets` |
| Findings | `/api/findings` |
| Qualité | `/api/quality`, `/api/quality/anomalies`, `/api/quality/collection` |
| Opérations | `/api/jobs`, `/api/reconciliation`, `/api/reconciliation/summary` |

All data is live — there is no demo/fixture path.

## VPS deployment

The `api` service in `infrastructure/vps/compose.yaml` serves the built SPA —
copy `frontend/dist` into the image build context (the Dockerfile already
copies `src/`; add `COPY frontend/dist ./frontend/dist` if you bake it in),
or run a `npm run build` stage. Token is mandatory beyond loopback.

## Verification checklist

- `npm run build` completes (warning about chunk size is cosmetic).
- `curl -s localhost:8080/` returns the SPA HTML.
- `curl -s localhost:8080/api/health` returns JSON.
- Without token (auth enabled): API returns 401, UI shows the token prompt.
- `/console` always serves the dependency-free fallback page.
