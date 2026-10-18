"""Inter-model fusion engine.

Combines the predictions of the platform's models into candidate combinations
whose goal is to reunite several winning numbers in a single selection (≥3),
which no single model can do on its own (each predicts only a handful).

All functions are PURE and past-only: given ``history`` up to an instant, they
produce selections for the *next* draw. No look-ahead by construction — the
caller walks forward and never feeds future draws.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Callable, Sequence

from lottery_intelligence_platform import calling_image as _ci
from lottery_intelligence_platform import lab_models as _lm
from lottery_intelligence_platform import meta_ensemble as _me

# The 18 predictive models, canonical interface predict(hist, rng, k) -> list[int].
# random / null_model_benchmark serve as the reference (uniform pick).
FUSION_MODELS: dict[str, Callable[..., list[int]]] = {
    "hot_frequency_v1": _lm.predict_hot_frequency_v1,
    "cold_delay_v1": _lm.predict_cold_delay_v1,
    "frequency_delay_v1": _lm.predict_frequency_delay_v1,
    "pair_frequency_v1": _lm.predict_pair_frequency_v1,
    "balanced_v1": _lm.predict_balanced_v1,
    "bayesian_v1": _lm.predict_bayesian_v1,
    "monte_carlo_v1": _lm.predict_monte_carlo_v1,
    "top_k_frequency": _lm.predict_top_k,
    "rolling_frequency": _lm.predict_rolling,
    "bayesian_shrinkage": _lm.predict_bayesian_shrinkage,
    "ensemble_v1": _lm.predict_ensemble_v1,
    "calling_numbers": _ci.predict_calling_numbers,
    "image_numbers": _ci.predict_image_numbers,
    "calling_image": _ci.predict_calling_image,
    "calling_image_position": _ci.predict_calling_image_position,
    "meta_consensus_count": _me.predict_meta_consensus_count,
    "meta_consensus_family": _me.predict_meta_consensus_family,
    "random": _lm.predict_random,
}

FUSION_METHODS = ("majority", "borda", "union")


def model_picks(history: Sequence[Sequence[int]], k: int = 5,
                seed: int = 0) -> dict[str, list[int]]:
    """Each model's top-k for the draw following ``history`` (deterministic)."""
    out: dict[str, list[int]] = {}
    for code, fn in FUSION_MODELS.items():
        try:
            p = fn(history, random.Random(seed), k)
            out[code] = sorted(set(int(x) for x in p))[:k]
        except Exception:
            continue
    return out


def _frequency_rank(history: Sequence[Sequence[int]]) -> dict[int, int]:
    freq: Counter = Counter()
    for draw in history:
        freq.update(draw)
    return {n: freq.get(n, 0) for n in range(1, 91)}


def fuse_majority_vote(picks: dict[str, list[int]], k: int = 5) -> list[int]:
    """Numbers ranked by how many models select them (simple consensus)."""
    counts: Counter = Counter()
    for p in picks.values():
        counts.update(p)
    return [n for n, _ in counts.most_common(k)]


def fuse_borda(picks: dict[str, list[int]], k: int = 5) -> list[int]:
    """Borda-count aggregation across models' ranked top-k."""
    scores: Counter = Counter()
    for p in picks.values():
        for rank, n in enumerate(p):
            scores[n] += len(p) - rank
    return [n for n, _ in scores.most_common(k)]


def fuse_union(picks: dict[str, list[int]], history, k: int = 5) -> list[int]:
    """Union of proposed numbers, ranked by vote count then historical frequency."""
    counts: Counter = Counter()
    for p in picks.values():
        counts.update(p)
    freq = _frequency_rank(history)
    ranked = sorted(counts, key=lambda n: (-counts[n], -freq.get(n, 0), n))
    return ranked[:k]


def generate_combinations(
    picks: dict[str, list[int]],
    history: Sequence[Sequence[int]],
    k: int = 5,
    methods: Sequence[str] = FUSION_METHODS,
) -> dict[str, list[int]]:
    """Candidate k-number combinations, one per fusion method."""
    out: dict[str, list[int]] = {}
    for m in methods:
        if m == "majority":
            out[m] = fuse_majority_vote(picks, k)
        elif m == "borda":
            out[m] = fuse_borda(picks, k)
        elif m == "union":
            out[m] = fuse_union(picks, history, k)
    return out


def hit_count(predicted: Sequence[int], winning: Sequence[int]) -> int:
    return len(set(predicted) & set(winning))


def evaluate_walkforward(
    history: Sequence[Sequence[int]],
    k: int = 5,
    methods: Sequence[str] = FUSION_METHODS,
    start: int = 20,
) -> dict:
    """Walk-forward fusion evaluation.

    For each draw i (with at least ``start`` draws of past), fuse every model
    using ONLY history[:i], build each method's combination, and count how many
    winning numbers it contains. Also records the best single model and a
    random reference. Returns hit distributions and P(>=3 hits) per method.
    """
    per_method: dict[str, list[int]] = {m: [] for m in methods}
    per_model: dict[str, list[int]] = {code: [] for code in FUSION_MODELS}
    random_ref: list[int] = []

    for i in range(start, len(history)):
        past = history[:i]
        winning = set(history[i])
        picks = model_picks(past, k)
        combos = generate_combinations(picks, past, k, methods)
        for m, combo in combos.items():
            per_method[m].append(hit_count(combo, winning))
        for code, p in picks.items():
            per_model[code].append(hit_count(p, winning))
        rng = random.Random(i)
        random_ref.append(len(set(rng.sample(range(1, 91), k)) & winning))

    def summarize(hits: Sequence[int]) -> dict:
        n = len(hits)
        dist = Counter(hits)
        return {
            "n": n,
            "mean_hits": round(sum(hits) / n, 4) if n else 0.0,
            "p_ge3": round(sum(1 for h in hits if h >= 3) / n, 4) if n else 0.0,
            "distribution": {f"h{i}": dist.get(i, 0) for i in range(k + 1)},
        }

    # best single model = ONE fixed model (highest mean hits), never a per-draw
    # cherry-pick of whichever model happened to hit — that would leak the future.
    model_means = {code: (sum(h) / len(h)) if h else 0.0 for code, h in per_model.items()}
    best_code = max(model_means, key=model_means.get)

    return {
        "draws_evaluated": len(history) - start,
        "methods": {m: summarize(per_method[m]) for m in methods},
        "best_single_model": summarize(per_model[best_code]),
        "best_single_code": best_code,
        "random_reference": summarize(random_ref),
        "per_model": {code: summarize(h) for code, h in per_model.items()},
    }


# ---------------------------------------------------------------------------
# Combinatorial search + complementarity (mission §5)
# ---------------------------------------------------------------------------

def generate_n_combination(
    picks: dict[str, list[int]], history, n: int
) -> list[int]:
    """A fused n-number combination (n = 2..5) by majority vote, frequency-tied."""
    counts: Counter = Counter()
    for p in picks.values():
        counts.update(p)
    freq = _frequency_rank(history)
    ranked = sorted(counts, key=lambda x: (-counts[x], -freq.get(x, 0), x))
    return ranked[:n]


def pairwise_jaccard(picks: dict[str, list[int]]) -> float:
    """Mean pairwise Jaccard of models' top-k — 0.0 = fully complementary,
    1.0 = all identical. Never a probability of winning."""
    keys = list(picks)
    if len(keys) < 2:
        return 1.0
    total = cnt = 0.0
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            sa, sb = set(picks[keys[a]]), set(picks[keys[b]])
            total += len(sa & sb) / len(sa | sb)
            cnt += 1
    return total / cnt


def complementary_pairs(
    picks: dict[str, list[int]], threshold: float = 0.2
) -> list[tuple[str, str, float]]:
    """Model pairs whose top-k barely overlap (complementary — candidates for
    fusion: one brings a number the other misses)."""
    keys = list(picks)
    out: list[tuple[str, str, float]] = []
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            sa, sb = set(picks[keys[a]]), set(picks[keys[b]])
            j = len(sa & sb) / len(sa | sb) if (sa | sb) else 1.0
            if j <= threshold:
                out.append((keys[a], keys[b], round(j, 3)))
    return out


# ---------------------------------------------------------------------------
# Multiple-testing correction
# ---------------------------------------------------------------------------

def benjamini_hochberg(pvals: Sequence[tuple[str, float]]) -> dict[str, float]:
    """Benjamini-Hochberg q-values, monotonic from the largest p.

    q_i = min_{j >= i} (p_j * m / rank_j) after sorting p ascending.
    """
    sorted_p = sorted(pvals, key=lambda x: x[1])
    m = len(sorted_p)
    bh = [p * m / (i + 1) for i, (_, p) in enumerate(sorted_p)]
    q_vals = [0.0] * m
    running_min = 1.0
    for i in range(m - 1, -1, -1):
        running_min = min(running_min, bh[i])
        q_vals[i] = running_min
    return {label: round(q_vals[i], 4) for i, (label, _) in enumerate(sorted_p)}


# ---------------------------------------------------------------------------
# Official-formula settlement (mission §3, betting_formulas.py)
# ---------------------------------------------------------------------------

def evaluate_formula_walkforward(
    history: Sequence[Sequence[int]],
    *,
    formula_code: str,
    method: str = "majority",
    k: int = 5,
    start: int = 20,
    stake: str = "100",
) -> dict:
    """Walk-forward fusion settled by an official betting formula.

    Each draw: fuse the models into a k-number combination using ONLY the
    past, then settle it against the official payout of ``formula_code``
    (e.g. 3N, 4N, 5N, CHANCE_5_PLUS, PERM_2). Returns net result and ROI.
    """
    from decimal import Decimal
    from lottery_intelligence_platform.betting_formulas import calculate_potential_gain

    stake_dec = Decimal(str(stake))
    hits: list[int] = []
    nets: list[float] = []
    for i in range(start, len(history)):
        past = history[:i]
        winning = list(history[i])
        picks = model_picks(past, k)
        combo = generate_combinations(picks, past, k, (method,))[method]
        hits.append(hit_count(combo, winning))
        g = calculate_potential_gain(formula_code, combo, winning, stake_dec)
        nets.append(float(g["net_profit"]))
    total_stake = float(stake_dec) * len(nets)
    total_net = sum(nets)
    return {
        "formula": formula_code,
        "method": method,
        "n": len(nets),
        "mean_hits": round(sum(hits) / len(hits), 4) if hits else 0.0,
        "p_ge3": round(sum(1 for h in hits if h >= 3) / len(hits), 4) if hits else 0.0,
        "total_stake": round(total_stake, 2),
        "total_net": round(total_net, 2),
        "roi": round(total_net / total_stake, 4) if total_stake else 0.0,
    }
