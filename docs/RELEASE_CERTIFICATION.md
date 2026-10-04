# Release certification — Lottery Intelligence Platform

Status: **CERTIFIED — technically and methodologically ready to continue
research.** This certification does NOT claim profitability; no model is
VALIDATED and no economic edge has been demonstrated.

| Field | Value |
|---|---|
| Date | 2026-10-04 |
| Git commit | `cbf4a7e` (+ pending phase05–09 docs commit) |
| Branch | `feature/data-foundation` |
| Schema version | `0019_data_quality` (19 migrations, checksums enforced) |
| Dataset version | `lotobonheur_archive_v1` v1 — 15 583 members, cutoff 2026-10-04 |
| Prospective cohort | `prospective_turbo_v1` v1, sealed 2026-10-04 |
| Tests | 150 unit + 46 integration, all green (run 2026-10-04) |

## Criteria (phase 09 checklist)

### DATA — complete
- [x] RAW immutable (content-addressed sha256, MinIO)
- [x] PostgreSQL source of truth
- [x] full provenance (source, payload hash, collection run, event)
- [x] dataset versioning + snapshots
- [x] corrections historisées (versions, SUPERSEDED, audit)
- [x] backups (daily pg_dump + raw mirror, cron-scheduled)
- [x] **restore tested** — 2026-10-04, PASS (15 667 draws / 147 870 numbers
      / 15 583 members in scratch DB)

### RESEARCH — complete
- [x] feature versioning (`research.feature_versions`)
- [x] model registry (18 versions) + artifact registry (0017, unused by
      current stateless models)
- [x] experiment registry (experiments/runs/metrics, 277 cells)
- [x] reproducibility (params+seed+dataset+cohort on every prediction)
- [x] anti-leakage tests (build-time cutoff, lock-time observation,
      `LEAKAGE_DETECTED` — deterministic test)
- [x] walk-forward, OOS, prospective — all three scopes separated
      (`prospective_metrics` never mixes with experiment metrics)

### STRATEGY — complete
- [x] Turbo versioned (`official-turbo-position-2026-10`, VERIFIED_OFFICIAL)
- [x] payout rules versioned + temporally resolved (effective_from/to)
- [x] backtesting, bankroll simulation, drawdown, losing streak
      (`turbo_strategy_simulator`, `portfolio_risk`)
- [x] profitability measured under verified rule: ≈ −57% ROI realized
- [x] NO_EDGE: no economic claim without denominators and rule version

### KNOWLEDGE — complete
- [x] hypothesis + findings registries, rejected hypotheses preserved
- [x] similar-experiment detection — `knowledge.py` Hermes interface
      (search/find_similar/history functions)
- [x] research history queryable (model, strategy, failure)

### PRODUCTION — partial by design
- [x] healthchecks (`orchestrator_cli health`, `/api/health`)
- [x] monitoring (`ops.alerts`, job events ledger, `audit_data_quality`)
- [x] backup + restore tested
- [~] Docker deployment: DB+MinIO containerized; API/console/workers run
      host-side (cron). VPS compose of remaining services = future work
- [~] security: secrets out of git, optional API Bearer token, loopback
      default; TLS not needed on loopback, required before remote exposure
- [~] structured logs: job events are the structured ledger; free-text
      script logs go to `logs/`

## Known limitations

1. Single data source (LONACI) — no reconciliation possible (audit H1).
2. RPO 24 h — prospective predictions between backup and loss are lost
   evidence (audit H2).
3. Statistical power: Turbo-2 verdict needs ~32 k settlements (~2 years);
   weekly types need ~53 years for w=0.05 uniformity detection — certifying
   "no exploitable signal" is bounded by these denominators (audit H3).
4. `Digital 7h`/`Nuit Etoilee` flagged `low_power` — excluded from
   evidentiary claims.
5. Digital RNG types show small non-uniformity (w≈0.12) — tracked as a
   data-integrity signal, not exploitable (~40× baseline needed).
6. macOS cron requires Full Disk Access; VPS deployment uses launchd/
   containers (phase07 remaining).

## Research validation status

18 model versions evaluated, 277 walk-forward cells: **0 VALIDATED**,
7 REJECTED, 12 INCONCLUSIVE. Prospective loop live since 2026-10-04:
14 scored / 324 pending at certification time. The platform is certified
*as an instrument* — claims await prospective accumulation per
`docs/POWER_ANALYSIS.md` denominators.

## Recovery test

`scripts/restore_postgresql.sh` — PASS 2026-10-04 (see OPERATIONS.md).
