# Model Research Catalog

Generated from `research.model_versions`, experiment findings and the structured per-family documentation in `model_catalog.py`.

Evaluation protocol: identical walk-forward windows (`expanding_2y_semiannual`, 8 windows) on snapshot `lotobonheur_archive_v1` (15,583 draws, EXPLORATORY_ONLY, rules UNVERIFIED). No statistical result below is a demonstrated predictive advantage or an economic profitability claim.

## bayesian_shrinkage (v1, PREDICTIVE)
**Priority**: P0

- **Hypothesis**: Shrinkage toward uniformity denoises frequency estimates.
- **Formula**: Dirichlet posterior (count + alpha)/(total + 90*alpha) for selection; Beta posterior toward 5/90 for inclusion probability.
- **Inputs**: Expanding training window per draw type.
- **Parameters**: alpha=5.
- **Limitations**: Symmetric prior preserves ordering, so rankings equal top_k; only probability scale differs.
- **Rejection criteria**: Must beat top_k on Brier score OOS.

**Recorded findings**:
- `REJECTED` — 1/277 cells beat the null benchmark on Brier score (bootstrap 95% CI); 134/277 cells are worse.

## bootstrap_uncertainty (evaluation framework, not a registered model)
**Priority**: P0

- **Hypothesis**: Paired resampling quantifies estimation uncertainty without parametric assumptions.
- **Formula**: Percentile bootstrap of paired per-draw differences.
- **Inputs**: Per-draw metric series (brier, hits).
- **Parameters**: resamples, seed, alpha=0.05.
- **Limitations**: iid resampling is optimistic when draws are dependent (see dependence_aware_resampling).
- **Rejection criteria**: CIs excluding zero on both sides drive favorable/adverse classification.

**Recorded findings**: none yet.

## candidate_ranking (v1, PREDICTIVE)
**Priority**: P1

- **Hypothesis**: The ensemble's top-K ranking covers more winners than random.
- **Formula**: Hits per draw for ensemble top-10 vs seeded uniform pick, paired bootstrap.
- **Inputs**: First-test-draw ensemble ranking (train-only information).
- **Parameters**: top_k=10.
- **Limitations**: Single fixed ranking per cell; does not re-rank online.
- **Rejection criteria**: Rejected when hit advantage CI excludes zero in fewer than 10% of cells.

**Recorded findings**:
- `INCONCLUSIVE` — Ensemble top-10 covered more winners than random in 15/277 cells (fewer in 12).

## conditional_dependence (v1, STATISTICAL_TEST)
**Priority**: P1

- **Hypothesis**: Number pairs co-occur beyond independence.
- **Formula**: Binomial right-tail on pair counts vs 20/8010 baseline; Benjamini-Hochberg within cell.
- **Inputs**: Winning sets per type and window.
- **Parameters**: top_pairs=10 for OOS replication check.
- **Limitations**: ~2.5 expected co-occurrences per 1000 draws - very low power; tests uniformity not conditional independence given marginals.
- **Rejection criteria**: Significant pairs must retain OOS lift > 1.

**Recorded findings**:
- `INCONCLUSIVE` — 9/277 cells show BH-significant pairs; top-10 train pairs retain lift>1 OOS in 121/277 cells.

## dependence_aware_resampling (v1, STATISTICAL_TEST)
**Priority**: P1

- **Hypothesis**: Bootstrap conclusions are robust to dependence between draws.
- **Formula**: Moving-block bootstrap (size 20) vs iid paired bootstrap on the same difference series.
- **Inputs**: Per-draw paired difference series.
- **Parameters**: block_size=20, resamples, seed.
- **Limitations**: Block size choice is heuristic; only tests the top_k comparison currently.
- **Rejection criteria**: Robustness hypothesis rejected when >10% of cells change classification.

**Recorded findings**:
- `REJECTED` — Block bootstrap (size 20) changed the classification in 96/277 cells compared to iid resampling.

## distribution_drift (v1, STATISTICAL_TEST)
**Priority**: P0

- **Hypothesis**: Number distributions are not stationary across time.
- **Formula**: Max over monthly splits of the homogeneity chi-square; permutation p-value over block order (prefix-sum optimized).
- **Inputs**: Monthly count vectors per draw type.
- **Parameters**: permutations, alpha=0.05.
- **Limitations**: Monthly blocks; exchangeable-periods assumption; detects breaks, not their cause.
- **Rejection criteria**: Change-point claims must replicate across consecutive windows.

**Recorded findings**: none yet.

## ensemble_ablation (v1, ENSEMBLE)
**Priority**: P1

- **Hypothesis**: A mixture of probability predictors beats its best component.
- **Formula**: Uniform mixture of expanding/bayesian/rolling/regime predictions; leave-one-out ablation contributions.
- **Inputs**: Component prediction vectors per draw.
- **Parameters**: 4 components, uniform weights.
- **Limitations**: Components share the same information source (frequency history) so diversity is limited by construction.
- **Rejection criteria**: Rejected when the mixture never beats its best single component or the null.

**Recorded findings**:
- `REJECTED` — Ensemble beat best component in 1/277 cells (worse in 35); vs null: 0 better, 138 worse.

## null_model_benchmark (v1, BENCHMARK)
**Priority**: P0

- **Hypothesis**: Drawn numbers are exchangeable; a uniform random selection is the reference any candidate must beat.
- **Formula**: Match count follows Hypergeometric(90, 5, K) for a top-K selection; z-test on mean matches, seeded permutation p-values.
- **Inputs**: Winning numbers per draw type and evaluation window.
- **Parameters**: top_k, random seed, permutation count.
- **Limitations**: Normal z-test is an approximation, weak for sparse draw types; permutations assume block exchangeability.
- **Rejection criteria**: A candidate must beat this benchmark by paired intervals; cells where the null itself looks significant mark the noise floor.

**Recorded findings**: none yet.

## payout_sensitivity (v1, STRATEGY)
**Priority**: P2

- **Hypothesis**: Profitability conclusions must be robust to payout interpretation.
- **Formula**: Breakeven multiplier n/hits; scenario grid {provisional, 0.5x, 1x, 2x breakeven}.
- **Inputs**: Bet ledger per cell.
- **Parameters**: scenario multipliers.
- **Limitations**: Only multiplicative payout interpretations are covered.
- **Rejection criteria**: Rejected when the net-result sign flips under fair-odds assumptions in the majority of cells.

**Recorded findings**:
- `REJECTED` — Net-result sign depends on the unverified multiplier in 277/277 cells; no profitability claim stands under fair-odds assumptions.

## portfolio_risk (v1, STRATEGY)
**Priority**: P2

- **Hypothesis**: Risk is quantified under explicit bankroll assumptions.
- **Formula**: Equity curve max drawdown, losing streak, variance; ruin probability via resampled paths.
- **Inputs**: Bet ledger, starting bankroll in stake units.
- **Parameters**: bankroll=100 stakes, ruin_paths.
- **Limitations**: Ruin paths resample iid outcomes; no stake sizing or correlation across draw types.
- **Rejection criteria**: Descriptive; no acceptance criterion.

**Recorded findings**:
- `INCONCLUSIVE` — Descriptive risk and simulation metrics recorded per window and draw type; not a profitability claim while payout rules remain UNVERIFIED.

## probability_calibration (evaluation framework, not a registered model)
**Priority**: P0

- **Hypothesis**: Predicted inclusion probabilities match observed frequencies.
- **Formula**: Brier score, clipped log-loss, decile reliability curve, ECE.
- **Inputs**: Per-number predictions vs realized 0/1 outcomes.
- **Parameters**: 10 quantile bins, epsilon=1e-7 clipping.
- **Limitations**: Marginal-inclusion approximation ignores without-replacement intra-draw dependence.
- **Rejection criteria**: Model rejected when it cannot beat the null on Brier under paired bootstrap.

**Recorded findings**: none yet.

## regime_aware (v1, PREDICTIVE)
**Priority**: P1

- **Hypothesis**: Post-change-point history alone predicts better than full history.
- **Formula**: Detect monthly change-point on train, refit on retained draws, compare Brier vs expanding baseline.
- **Inputs**: Ordered draws; monthly change-point test.
- **Parameters**: cp permutations, alpha=0.05.
- **Limitations**: Smaller regime samples inflate variance; cutoff is monthly.
- **Rejection criteria**: Rejected when regime conditioning fails to improve Brier on cells with detected breaks.

**Recorded findings**:
- `INCONCLUSIVE` — Change-points detected in 22/277 cells; regime conditioning improved Brier in 0/277 cells and degraded it in 11.

## rolling_frequency (v1, PREDICTIVE)
**Priority**: P0

- **Hypothesis**: Recent draws carry more predictive information than deep history.
- **Formula**: Same as top_k but counts restricted to the last W draws (online update, never including the predicted draw).
- **Inputs**: Ordered draws per type; rolling window of W=200 draws.
- **Parameters**: window_draws=200, prior_draws=1.
- **Limitations**: Window size is arbitrary; loses data relative to expanding.
- **Rejection criteria**: Must beat expanding baseline and null OOS.

**Recorded findings**:
- `REJECTED` — 0/277 cells beat the null benchmark on Brier score (bootstrap 95% CI); 159/277 cells are worse.

## strategy_benchmark (v1, BENCHMARK)
**Priority**: P2

- **Hypothesis**: A strategy must beat its random economic equivalent.
- **Formula**: Paired bootstrap on per-draw net vs seeded random picks with identical stake and payout.
- **Inputs**: Strategy and random bet ledgers.
- **Parameters**: resamples, seed.
- **Limitations**: Random baseline shares the same payout rule, so unverified multipliers cancel in the comparison.
- **Rejection criteria**: Rejected when it cannot beat the random equivalent in more than 10% of cells.

**Recorded findings**:
- `INCONCLUSIVE` — Frequency strategy beat the random equivalent in 0/277 cells and lost in 0.

## top_k_frequency (v1, BASELINE)
**Priority**: P0

- **Hypothesis**: Historical winners repeat more often than uniform chance.
- **Formula**: Select the K numbers with the largest training counts; inclusion probability (count + prior mass)/(n + prior draws).
- **Inputs**: Expanding training window per draw type.
- **Parameters**: top_k, prior_draws=1.
- **Limitations**: Ranks identical to symmetric-prior shrinkage; probabilities slightly miscalibrated vs the null.
- **Rejection criteria**: Brier/coverage advantage vs null must be positive and significant under dependence-aware resampling.

**Recorded findings**:
- `REJECTED` — 1/277 cells beat the null benchmark on Brier score (bootstrap 95% CI); 132/277 cells are worse.

## turbo_strategy_simulator (v1, STRATEGY)
**Priority**: P2

- **Hypothesis**: Per-draw bet ledger under versioned payout rules.
- **Formula**: net = stake*multiplier - stake if pick subset of winners else -stake.
- **Inputs**: Test draws, top-k pick, payout multiplier.
- **Parameters**: numbers_picked=2, stake=100, provisional multipliers.
- **Limitations**: Payout rule UNVERIFIED - economic outputs are descriptive, not profit claims.
- **Rejection criteria**: Any positive result is void until the official payout rule is verified.

**Recorded findings**:
- `INCONCLUSIVE` — Descriptive risk and simulation metrics recorded per window and draw type; not a profitability claim while payout rules remain UNVERIFIED.

All conclusions remain provisional while rule effectivity and payout rules are UNVERIFIED.
