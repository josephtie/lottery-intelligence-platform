# Power analysis — what the data can and cannot prove

Computed by `scripts/power_analysis.py` (pure-stdlib statistics: regularized
incomplete gamma, Poisson-mixture noncentral chi-square). Re-run it any time;
numbers below are from 2026-10-04, 15 594 settled draws.

## Uniformity per draw type (WINNING numbers only)

Chi-square GOF, 89 df, alpha = 0.05. `w_obs` = observed Cohen's w;
`w_mde` = minimum detectable effect at 80% power given the sample size.

| Draw type | Draws | p-value | w_obs | w_mde | Verdict |
|---|---|---|---|---|---|
| **Digital 21h** | 1 661 | <0.0001 | 0.142 | 0.068 | **non-uniform** |
| **Digital 23h** | 1 609 | 0.016 | 0.122 | 0.069 | **non-uniform** |
| **Digital Reveil 7h** | 1 609 | 0.001 | 0.130 | 0.069 | **non-uniform** |
| Digital Reveil 8h | 476 | 0.115 | 0.210 | 0.127 | underpowered |
| Special Weekend 1h/3h | 444 | 0.24–0.47 | ~0.21 | 0.132 | compatible |
| 25 weekly types | ~309 | 0.17–0.99 | ~0.2 | 0.158 | compatible |
| Day Off | 82 | 0.86 | — | 0.307 | underpowered |
| Nuit Etoilee | 22 | 0.66 | — | 0.592 | underpowered |
| Digital 7h | 2 | — | — | 1.96 | unusable |

Multiple-comparison context: 39 tests at alpha 0.05 expect ~2 false
positives; the three Digital hits (two at p < 0.005) exceed that, so the
Digital-RNG deviation is probably real, but it is *small* (w ≈ 0.12).

## Why the weekly types cannot settle anything yet

Detecting a modest deviation w = 0.05 requires 3 085 draws per type:

- weekly types: ~309 draws now → **~53 more years** at 1 draw/week;
- daily Digital types: ~1 600 draws now → ~4 more years.

## Prospective Turbo-2 power

Baseline hit probability: both picks inside the first 2 drawn positions =
1/C(90,2) = 1/4005 ≈ 0.025%. Detecting a *doubling* of that rate at
alpha = 0.05 / power = 0.8 needs **~32 180 settled predictions per model**
(or fewer for larger effects: ~8 000 to detect a 3× rate).

Current cadence: ~40 predictions/day → first meaningful prospective verdict
for a single model in roughly 2 years at the doubled-effect boundary, sooner
if effects are larger. Report coverage accordingly.

## Exploitability of the Digital deviation

Even where non-uniformity is real (w ≈ 0.12), the per-number excess is at
most ~1.5–2% relative — far below what is needed to move Turbo-2 hit rates
into profitable territory (needs ≈ 40× baseline). It is a data-integrity
signal worth tracking prospectively, not an economic edge.

## Method notes

- Only `number_role = 'WINNING'` counts (draws also record MACHINE numbers).
- Latest valid draw_version per draw; superseded draws excluded.
- Required noncentrality lambda = 38.6 for df = 89, alpha .05, power .8
  (bisection over Poisson-mixture noncentral chi-square CDF).
