# Turbo 2 history view — per game

Observation layer only. Everything displayed is **already sealed** by the
settlement engine — the view never recomputes a hit, a payout, or a
prediction.

## Rule shown (from `settlement.py`, sealed at settlement time)

- **Turbo 2 HIT**: both predicted numbers appear among the first 2
  positions of the ordered winning result (set membership, positions are
  not individually ordered).
- Stake 100 FCFA, multiplier ×2400 → gross 240 000, net **+239 900** on a
  hit, **−100** on a loss.
- Source: `research.prediction_outcomes.metrics->turbo->turbo_2`,
  `positional_hits.first_2`, `winning_numbers` (ordered).

## Endpoint

`GET /api/lab/turbo2-history?draw_type=<code|display_name>`

Returns, for ONE game only (strict `WHERE draw_type_id` segmentation):

- `rows` — chronological sealed bets: date, ISO week, weekday, draw
  sequence, model, predicted pair, ordered winning numbers (first 2
  positions flagged in the UI), `hits_first2`, hit, stake, gross, net,
  `locked_at`/`settled_at` provenance.
- `weekly` / `daily` / `models` — aggregates computed from the same rows
  (bets, hits, hit rate, stake, gross, net, ROI).
- `models[].sample_level` — `weak` (< 10 bets) renders the
  *ÉCHANTILLON FAIBLE* badge; a short-period winner is never presented as
  a better predictor.
- `kpis`, `weeks` — totals and the week selector domain.

## UI

`Profils des jeux → <GAME> → 🎯 Turbo 2` — KPI cards, cumulative net
sparkline (descriptive only), full draw table, per-day and per-week
summaries, per-model table, same-weekday-across-weeks comparison.
ROI is `N/A` when total stake is 0 — never `0 %`.

## Boundaries

- No aggregation ever mixes draw types.
- `locked_at`/`settled_at` are displayed as provenance; predictions are
  the sealed ones — the view cannot recompute them with future data.
- "constance observée" wording — never "probabilité de gagner".
- Engine untouched: no change to predictions, models, null, scoring,
  settlement, payout rules, or the prospective protocol.
