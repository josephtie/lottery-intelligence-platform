from __future__ import annotations

from typing import Any, Mapping

# Structured documentation per model family (rule D of the model catalog):
# hypothesis, formula, inputs, parameters, limitations and rejection criteria.
FAMILY_DOCS: dict[str, dict[str, str]] = {
    "null_model_benchmark": {
        "priority": "P0",
        "hypothesis": (
            "Drawn numbers are exchangeable; a uniform random selection is the "
            "reference any candidate must beat."
        ),
        "formula": (
            "Match count follows Hypergeometric(90, 5, K) for a top-K selection; "
            "z-test on mean matches, seeded permutation p-values."
        ),
        "inputs": "Winning numbers per draw type and evaluation window.",
        "parameters": "top_k, random seed, permutation count.",
        "limitations": (
            "Normal z-test is an approximation, weak for sparse draw types; "
            "permutations assume block exchangeability."
        ),
        "rejection_criteria": (
            "A candidate must beat this benchmark by paired intervals; cells where "
            "the null itself looks significant mark the noise floor."
        ),
    },
    "top_k_frequency": {
        "priority": "P0",
        "hypothesis": "Historical winners repeat more often than uniform chance.",
        "formula": "Select the K numbers with the largest training counts; "
                   "inclusion probability (count + prior mass)/(n + prior draws).",
        "inputs": "Expanding training window per draw type.",
        "parameters": "top_k, prior_draws=1.",
        "limitations": "Ranks identical to symmetric-prior shrinkage; "
                       "probabilities slightly miscalibrated vs the null.",
        "rejection_criteria": "Brier/coverage advantage vs null must be positive "
                              "and significant under dependence-aware resampling.",
    },
    "rolling_frequency": {
        "priority": "P0",
        "hypothesis": "Recent draws carry more predictive information than deep history.",
        "formula": "Same as top_k but counts restricted to the last W draws "
                   "(online update, never including the predicted draw).",
        "inputs": "Ordered draws per type; rolling window of W=200 draws.",
        "parameters": "window_draws=200, prior_draws=1.",
        "limitations": "Window size is arbitrary; loses data relative to expanding.",
        "rejection_criteria": "Must beat expanding baseline and null OOS.",
    },
    "bayesian_shrinkage": {
        "priority": "P0",
        "hypothesis": "Shrinkage toward uniformity denoises frequency estimates.",
        "formula": "Dirichlet posterior (count + alpha)/(total + 90*alpha) for "
                   "selection; Beta posterior toward 5/90 for inclusion probability.",
        "inputs": "Expanding training window per draw type.",
        "parameters": "alpha=5.",
        "limitations": (
            "Symmetric prior preserves ordering, so rankings equal top_k; only "
            "probability scale differs."
        ),
        "rejection_criteria": "Must beat top_k on Brier score OOS.",
    },
    "distribution_drift": {
        "priority": "P0",
        "hypothesis": "Number distributions are not stationary across time.",
        "formula": "Max over monthly splits of the homogeneity chi-square; "
                   "permutation p-value over block order (prefix-sum optimized).",
        "inputs": "Monthly count vectors per draw type.",
        "parameters": "permutations, alpha=0.05.",
        "limitations": "Monthly blocks; exchangeable-periods assumption; "
                       "detects breaks, not their cause.",
        "rejection_criteria": "Change-point claims must replicate across "
                              "consecutive windows.",
    },
    "bootstrap_uncertainty": {
        "priority": "P0",
        "hypothesis": "Paired resampling quantifies estimation uncertainty "
                      "without parametric assumptions.",
        "formula": "Percentile bootstrap of paired per-draw differences.",
        "inputs": "Per-draw metric series (brier, hits).",
        "parameters": "resamples, seed, alpha=0.05.",
        "limitations": "iid resampling is optimistic when draws are dependent "
                       "(see dependence_aware_resampling).",
        "rejection_criteria": "CIs excluding zero on both sides drive "
                              "favorable/adverse classification.",
    },
    "probability_calibration": {
        "priority": "P0",
        "hypothesis": "Predicted inclusion probabilities match observed frequencies.",
        "formula": "Brier score, clipped log-loss, decile reliability curve, ECE.",
        "inputs": "Per-number predictions vs realized 0/1 outcomes.",
        "parameters": "10 quantile bins, epsilon=1e-7 clipping.",
        "limitations": "Marginal-inclusion approximation ignores without-replacement "
                       "intra-draw dependence.",
        "rejection_criteria": "Model rejected when it cannot beat the null on Brier "
                              "under paired bootstrap.",
    },
    "conditional_dependence": {
        "priority": "P1",
        "hypothesis": "Number pairs co-occur beyond independence.",
        "formula": "Binomial right-tail on pair counts vs 20/8010 baseline; "
                   "Benjamini-Hochberg within cell.",
        "inputs": "Winning sets per type and window.",
        "parameters": "top_pairs=10 for OOS replication check.",
        "limitations": "~2.5 expected co-occurrences per 1000 draws - very low "
                       "power; tests uniformity not conditional independence given marginals.",
        "rejection_criteria": "Significant pairs must retain OOS lift > 1.",
    },
    "regime_aware": {
        "priority": "P1",
        "hypothesis": "Post-change-point history alone predicts better than full history.",
        "formula": "Detect monthly change-point on train, refit on retained draws, "
                   "compare Brier vs expanding baseline.",
        "inputs": "Ordered draws; monthly change-point test.",
        "parameters": "cp permutations, alpha=0.05.",
        "limitations": "Smaller regime samples inflate variance; cutoff is monthly.",
        "rejection_criteria": "Rejected when regime conditioning fails to improve "
                              "Brier on cells with detected breaks.",
    },
    "candidate_ranking": {
        "priority": "P1",
        "hypothesis": "The ensemble's top-K ranking covers more winners than random.",
        "formula": "Hits per draw for ensemble top-10 vs seeded uniform pick, "
                   "paired bootstrap.",
        "inputs": "First-test-draw ensemble ranking (train-only information).",
        "parameters": "top_k=10.",
        "limitations": "Single fixed ranking per cell; does not re-rank online.",
        "rejection_criteria": "Rejected when hit advantage CI excludes zero "
                              "in fewer than 10% of cells.",
    },
    "ensemble_ablation": {
        "priority": "P1",
        "hypothesis": "A mixture of probability predictors beats its best component.",
        "formula": "Uniform mixture of expanding/bayesian/rolling/regime "
                   "predictions; leave-one-out ablation contributions.",
        "inputs": "Component prediction vectors per draw.",
        "parameters": "4 components, uniform weights.",
        "limitations": "Components share the same information source "
                       "(frequency history) so diversity is limited by construction.",
        "rejection_criteria": "Rejected when the mixture never beats its best "
                              "single component or the null.",
    },
    "dependence_aware_resampling": {
        "priority": "P1",
        "hypothesis": "Bootstrap conclusions are robust to dependence between draws.",
        "formula": "Moving-block bootstrap (size 20) vs iid paired bootstrap on "
                   "the same difference series.",
        "inputs": "Per-draw paired difference series.",
        "parameters": "block_size=20, resamples, seed.",
        "limitations": "Block size choice is heuristic; only tests the top_k "
                       "comparison currently.",
        "rejection_criteria": "Robustness hypothesis rejected when >10% of cells "
                              "change classification.",
    },
    "turbo_strategy_simulator": {
        "priority": "P2",
        "hypothesis": "Per-draw bet ledger under versioned payout rules.",
        "formula": "net = stake*multiplier - stake if pick subset of winners "
                   "else -stake.",
        "inputs": "Test draws, top-k pick, payout multiplier.",
        "parameters": "numbers_picked=2, stake=100, provisional multipliers.",
        "limitations": "Payout rule UNVERIFIED - economic outputs are descriptive, "
                       "not profit claims.",
        "rejection_criteria": "Any positive result is void until the official "
                              "payout rule is verified.",
    },
    "payout_sensitivity": {
        "priority": "P2",
        "hypothesis": "Profitability conclusions must be robust to payout "
                      "interpretation.",
        "formula": "Breakeven multiplier n/hits; scenario grid "
                   "{provisional, 0.5x, 1x, 2x breakeven}.",
        "inputs": "Bet ledger per cell.",
        "parameters": "scenario multipliers.",
        "limitations": "Only multiplicative payout interpretations are covered.",
        "rejection_criteria": "Rejected when the net-result sign flips under "
                              "fair-odds assumptions in the majority of cells.",
    },
    "portfolio_risk": {
        "priority": "P2",
        "hypothesis": "Risk is quantified under explicit bankroll assumptions.",
        "formula": "Equity curve max drawdown, losing streak, variance; ruin "
                   "probability via resampled paths.",
        "inputs": "Bet ledger, starting bankroll in stake units.",
        "parameters": "bankroll=100 stakes, ruin_paths.",
        "limitations": "Ruin paths resample iid outcomes; no stake sizing or "
                       "correlation across draw types.",
        "rejection_criteria": "Descriptive; no acceptance criterion.",
    },
    "strategy_benchmark": {
        "priority": "P2",
        "hypothesis": "A strategy must beat its random economic equivalent.",
        "formula": "Paired bootstrap on per-draw net vs seeded random picks "
                   "with identical stake and payout.",
        "inputs": "Strategy and random bet ledgers.",
        "parameters": "resamples, seed.",
        "limitations": "Random baseline shares the same payout rule, so "
                       "unverified multipliers cancel in the comparison.",
        "rejection_criteria": "Rejected when it cannot beat the random equivalent "
                              "in more than 10% of cells.",
    },
    "image_numbers": {
        "priority": "P1",
        "hypothesis": (
            "A number's digit-reversal 'image' (57 -> 75, 90 -> 09) appears "
            "conditionally more often than its marginal rate — tested as an "
            "association hypothesis, never assumed predictive."
        ),
        "formula": (
            "Directed edges A -> image(A); P(B | A) vs empirical P(B) per "
            "horizon (same draw, next draw, N-draw window); binomial "
            "right-tail and seeded permutation p-values; BH FDR per horizon."
        ),
        "inputs": "Chronological winning sets per draw type.",
        "parameters": "horizons=(0,1,3), min_support=5, permutations.",
        "limitations": (
            "Out-of-domain reversals (19 -> 91) have no edge; ~75 directed "
            "tests only, so power is limited; grid-free hypothesis still "
            "assumes digit reversal is a meaningful operator."
        ),
        "rejection_criteria": (
            "Rejected when no edge keeps q_fdr < 0.05 and OOS lift > 1; an "
            "in-sample anomaly alone is not a validated advantage."
        ),
    },
    "calling_numbers": {
        "priority": "P1",
        "hypothesis": (
            "Numbers spatially adjacent on the configured grid 'call' each "
            "other: when A is drawn, its neighbours appear more often than "
            "baseline — a directional, configurable hypothesis."
        ),
        "formula": (
            "Directed edges A -> Moore-neighbourhood cells (clockwise from "
            "West); same P(B | A) vs P(B) machinery as image_numbers, per "
            "horizon, with theoretical and draw-order permutation nulls."
        ),
        "inputs": "Winning sets per draw type; the calling grid as config.",
        "parameters": "grid=DEFAULT_CALLING_GRID, horizons=(0,1,3), min_support=5.",
        "limitations": (
            "Grid has duplicated values (first occurrence anchors the "
            "neighbourhood); numbers absent from the grid have no outgoing "
            "edges; geometry is symmetric but the measured association may "
            "not be — both directions are tested separately."
        ),
        "rejection_criteria": "Same bar as image_numbers: FDR + OOS replication.",
    },
    "calling_image": {
        "priority": "P1",
        "hypothesis": (
            "Images of called numbers add signal beyond calling alone and "
            "image alone — the interaction is tested, not presumed."
        ),
        "formula": (
            "Edges A -> neighbour and A -> image(neighbour) of the grid; "
            "metrics identical to the component hypotheses."
        ),
        "inputs": "Winning sets; grid config; image map.",
        "parameters": "horizons=(0,1,3), min_support=5.",
        "limitations": (
            "Larger edge set inflates the multiple-testing burden vs H1/H2; "
            "must be compared against its components, not only against "
            "chance."
        ),
        "rejection_criteria": (
            "Rejected when it shows no FDR-surviving edges beyond what "
            "calling_numbers or image_numbers already surface."
        ),
    },
    "calling_image_position": {
        "priority": "P1",
        "hypothesis": (
            "The calling/image association depends on the position of the "
            "numbers inside the draw result."
        ),
        "formula": (
            "P(B at position q | A at position p) vs P(B at q) for each "
            "(edge, p, q) — positions never pooled without measurement."
        ),
        "inputs": "Position-ordered winning numbers per draw type.",
        "parameters": "max_pos = draw size, min_support=5.",
        "limitations": (
            "~25 (p, q) sub-tests per edge: severe multiple-testing load and "
            "low per-cell support; positional recording must be reliable."
        ),
        "rejection_criteria": (
            "Rejected when positional cells do not beat the non-positional "
            "edges after FDR, or fail OOS replication."
        ),
    },
}


def render_model_catalog(connection: Any) -> str:
    models = connection.execute(
        """SELECT code, family, version, definition_sha256, created_at
           FROM research.model_versions ORDER BY code, version"""
    ).fetchall()
    findings = connection.execute(
        """SELECT e.configuration->>'model_code' AS code, f.status, f.conclusion
           FROM research.findings f
           JOIN research.experiments e ON e.experiment_id = f.experiment_id
           ORDER BY f.created_at"""
    ).fetchall()
    latest_by_code: dict[str, list[tuple[str, str]]] = {}
    for code, status, conclusion in findings:
        latest_by_code.setdefault(code or "", []).append((status, conclusion))

    lines = [
        "# Model Research Catalog",
        "",
        "Generated from `research.model_versions`, experiment findings and the "
        "structured per-family documentation in `model_catalog.py`.",
        "",
        "Evaluation protocol: identical walk-forward windows (`expanding_2y_semiannual`, "
        "8 windows) on snapshot `lotobonheur_archive_v1` (15,583 draws, EXPLORATORY_ONLY, "
        "rules UNVERIFIED). No statistical result below is a demonstrated predictive "
        "advantage or an economic profitability claim.",
        "",
    ]
    registered = {code: (family, version) for code, family, version, _, _ in models}
    ordered_codes = sorted(set(FAMILY_DOCS) | set(registered))
    for code in ordered_codes:
        if code in registered:
            family, version = registered[code]
            lines.append(f"## {code} (v{version}, {family})")
        else:
            lines.append(f"## {code} (evaluation framework, not a registered model)")
        doc = FAMILY_DOCS.get(code, {})
        if doc:
            lines.append(f"**Priority**: {doc['priority']}")
            lines.append("")
            for key, label in (
                ("hypothesis", "Hypothesis"), ("formula", "Formula"),
                ("inputs", "Inputs"), ("parameters", "Parameters"),
                ("limitations", "Limitations"),
                ("rejection_criteria", "Rejection criteria"),
            ):
                lines.append(f"- **{label}**: {doc[key]}")
        else:
            lines.append("- *No structured documentation registered for this model.*")
        outcomes = latest_by_code.get(code, [])
        if outcomes:
            lines.append("")
            lines.append("**Recorded findings**:")
            for status, conclusion in outcomes:
                lines.append(f"- `{status}` — {conclusion}")
        else:
            lines.append("")
            lines.append("**Recorded findings**: none yet.")
        lines.append("")
    lines.append(
        "All conclusions remain provisional while rule effectivity and payout "
        "rules are UNVERIFIED."
    )
    return "\n".join(lines) + "\n"
