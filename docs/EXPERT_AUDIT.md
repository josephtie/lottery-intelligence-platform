# Expert audit — Lottery Intelligence Platform

Auditor posture: hostile re-read of the system as if taking it over in three
years. Findings classified CRITICAL / HIGH / MEDIUM / LOW. No CRITICAL/HIGH
was auto-fixed; this document is the report.

Date: 2026-10-04 · commit `cbf4a7e`+ · schema `0019` · dataset
`lotobonheur_archive_v1` v1 (15 583 members).

## CRITICAL

None found. The evidence pipeline (raw immutability, append-only ledgers,
prediction lock guards, checksumed migrations, content-addressed artifacts)
does not present a silently corruptible path. The closest criticals became
HIGH because they are mitigated or bounded.

## HIGH

### H1 — Single external source (LONACI)

- **Evidence**: `ingestion.sources` holds one source; collection quality view
  confirms one collector feeding everything.
- **Impact**: a source-side error, silent format change, or manipulation is
  undetectable by reconciliation — phase05's multi-source comparison is
  vacuous with N=1. A wrong-but-valid result would be frozen and settled.
- **Mitigation in place**: payload hashing + version conflicts surface
  *corrections*, not fabrications. Publication-time sanity (draw types,
  ranges, weekday patterns) is enforced by validation + draw_quality views.
- **Proposed correction**: add a second independent source (operator mirror,
  archived page, or manual-entry channel flagged `source_id` distinct), or at
  minimum a daily cross-check of result counts vs the schedule.
- **Test needed**: inject a conflicting second-source payload and assert a
  `CONFLICT` anomaly is raised, never silently chosen.

### H2 — Live data mutability between backup and restore

- **Evidence**: restore test PASS but the system keeps writing; RPO is 24 h.
  Predictions generated between backup and crash are lost — and a lost
  prospective prediction is lost *evidence*, not just data.
- **Impact**: worst case, up to 24 h of prospective predictions + settlements
  vanish on storage loss. The ledger of "what was predicted" is the
  platform's core asset.
- **Proposed correction**: enable WAL archiving or a second daily backup
  window; alternatively replicate `research.predictions` + `ops.job_events`
  inserts to an append-only log shipping target (cheap — low volume).
- **Test needed**: crash simulation after backup, verify replay of the
  delta window.

### H3 — Prospective evidence volume is structurally thin

- **Evidence**: `docs/POWER_ANALYSIS.md` — ~32 k Turbo-2 settlements needed
  to detect a 2× hit-rate deviation; weekly draw types need ~53 years for
  w=0.05 uniformity detection.
- **Impact**: the platform can run correctly for years and still be unable
  to answer its headline question at weekly-type granularity. Risk of a
  future operator over-claiming from early noise.
- **Proposed correction**: certification criteria must include minimum
  prospective sample sizes per claim type; never promote a finding on
  underpowered cells (the `low_power` flag exists — make certification read
  it).
- **Test needed**: certification checklist gate asserting settled ≥ N before
  a PROSPECTIVE_SUPPORTED status is assignable.

## MEDIUM

### M1 — Pickers read live tables, not the pinned snapshot

`_train_counts` queries `core.draws` at execution time; the recorded
`dataset_version_id` is provenance metadata, not the compute input. Correct
for freshness, but the two can diverge if corrections land between snapshot
and generation — a draw `CORRECTED` after prediction silently changes what a
"same" dataset_version would have produced. Acceptable if documented as
deliberate; **document and pin a `trained_as_of` timestamp** on predictions.

### M2 — Predictions for projected (non-EXPECTED) targets can inflate denominators

Weekday projection generates predictions for dates a draw may never run
(cancelled/rescheduled). Mitigated 2026-10-04 by the stale-sweep in
`audit_data_quality` (INVALID after 2-day grace, audited). Residual: a
permanently-cancelled weekly type keeps generating+invalidating weekly —
harmless but noisy. **Proposed**: retire members via cohort version bump
when a type shows consecutive cancellations.

### M3 — `test_orchestration` integration suite depends on live DB

Mitigated by synthetic fixtures, but the suite still runs against the real
database, not a scratch one — a buggy test could write to production tables.
**Proposed**: dedicated `lottery_platform_test` database in CI.

### M4 — Cron on macOS needs Full Disk Access

Silent no-op risk if the host denies `cron` FDA. **Proposed**: launchd
plists or a containerized scheduler for the VPS target anyway (phase07).

### M5 — `.pgpass` hygiene

Contains a malformed host entry (`hôte`) and a wildcard line; works because
of the localhost line. Tighten to one exact entry; document rotation.

## LOW

- **L1** API has no rate limiting/TLS — loopback bind + optional Bearer is
  proportionate today; harden before any non-localhost exposure.
- **L2** `_train_counts` is O(draws×types) per generation run; fine at
  15 k draws, will want a per-(type,date) counts table or incremental cache
  past ~100 k.
- **L3** `research.prospective_performance` view and metrics view partially
  overlap — acceptable duplication, both derived.
- **L4** Bilingual naming (French UI, English schema) — cosmetic.
- **L5** `model_artifacts` is unused until a parametric model exists —
  deliberate, not debt.

## What the audit confirmed strong

- Append-only triggers on audit/events/coverage/artifacts/cohorts; mutation
  of locked predictions physically rejected.
- Idempotence: unique keys + ON CONFLICT at every ingest/generate/settle
  boundary; verified by reruns (created=0).
- Corrections historisées: versions + SUPERSEDED + audit events, never
  rewritten.
- Anti-leakage: two independent barriers (build-time date filter + lock-time
  observation check + dataset member-date leakage alert) — all three
  exercised in tests.
- Explicit absence: coverage ledger marks MISSING/FAILED/INELIGIBLE per
  pair; reconciliation self-heals orphans.
- Honest verdicts: 0 model VALIDATED; no economic claim without rule version
  + denominators; findings ledger records rejections permanently.
