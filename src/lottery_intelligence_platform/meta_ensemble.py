"""Meta-ensemble — deterministic consensus over the lab pickers.

`meta_consensus_count`  : each contributor votes for its top-k; numbers
                          ranked by vote count.
`meta_consensus_family` : votes are first pooled inside each declared
                          methodological family, then families contribute
                          equally — a 4-variant family cannot dominate a
                          1-model one.

Both are pure functions of ``hist`` — no learned weights, no metric
computed after the prediction instant, no look-ahead.  ``random``,
``null_model_benchmark`` and ``ensemble_v1`` are excluded from the
contributor set: the nulls are references, and ``ensemble_v1`` already
aggregates part of the same models (double counting).

Tie-break (declared): CONSENSUS_COUNT sorts by votes desc, then Borda
score desc (k - rank summed over voting models), then number asc.
CONSENSUS_FAMILY sorts by family-share mean desc, then raw votes desc,
then number asc.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Mapping, Sequence

from lottery_intelligence_platform import calling_image, lab_models

# (hist, rng, k) -> top-k — deterministic cores only.
CONTRIBUTORS: dict[str, Callable[..., list[int]]] = {
    "hot_frequency_v1": lab_models.predict_hot_frequency_v1,
    "cold_delay_v1": lab_models.predict_cold_delay_v1,
    "frequency_delay_v1": lab_models.predict_frequency_delay_v1,
    "pair_frequency_v1": lab_models.predict_pair_frequency_v1,
    "balanced_v1": lab_models.predict_balanced_v1,
    "bayesian_v1": lab_models.predict_bayesian_v1,
    "monte_carlo_v1": lab_models.predict_monte_carlo_v1,
    "top_k_frequency": lab_models.predict_top_k,
    "rolling_frequency": lab_models.predict_rolling,
    "bayesian_shrinkage": lab_models.predict_bayesian_shrinkage,
    **calling_image.CALLING_IMAGE_MODELS,
}

# Declared methodological families — a family votes with equal weight
# whatever its size (CONSENSUS_FAMILY) and is exposed in the UI.
MODEL_FAMILIES: dict[str, tuple[str, ...]] = {
    "frequency": ("hot_frequency_v1", "top_k_frequency",
                  "rolling_frequency"),
    "delay": ("cold_delay_v1", "frequency_delay_v1"),
    "bayesian": ("bayesian_v1", "bayesian_shrinkage"),
    "combinatorial": ("pair_frequency_v1", "balanced_v1"),
    "simulation": ("monte_carlo_v1",),
    "calling_image": tuple(calling_image.CALLING_IMAGE_MODELS),
}

MODEL_CODES: tuple[str, ...] = ("meta_consensus_count",
                                "meta_consensus_family")

_TIE_BREAK_DOC = (
    "CONSENSUS_COUNT: votes desc → Borda (Σ k−rang) desc → numéro asc. "
    "CONSENSUS_FAMILY: part moyenne par famille desc → votes bruts desc "
    "→ numéro asc.")


def _family_of(code: str) -> str | None:
    for fam, members in MODEL_FAMILIES.items():
        if code in members:
            return fam
    return None


def model_votes(
    hist: Sequence[Sequence[int]],
    k: int = 5,
) -> dict[str, list[int]]:
    """Each contributor's top-k on ``hist`` — deterministic: stochastic
    pickers get a fixed per-code rng, identical across calls."""
    votes: dict[str, list[int]] = {}
    for code, fn in CONTRIBUTORS.items():
        try:
            out = fn(hist, random.Random(
                calling_image._stable_seed("meta", code)), k)
        except Exception:
            continue
        votes[code] = sorted(set(out))[:k]
    return votes


def _borda(votes: Mapping[str, list[int]]) -> dict[int, int]:
    """Σ (k - rank_index) over the models that placed the number in top-k."""
    score: dict[int, int] = {}
    for picks in votes.values():
        k = len(picks)
        for rank, num in enumerate(picks):
            score[num] = score.get(num, 0) + (k - rank)
    return score


def consensus_count_detail(
    hist: Sequence[Sequence[int]], k: int = 5
) -> dict[str, Any]:
    """Raw vote count — one vote per model, no family balancing."""
    votes = model_votes(hist, k)
    n_models = len(votes)
    counts: dict[int, int] = {}
    fams: dict[int, set[str]] = {}
    for code, picks in votes.items():
        fam = _family_of(code) or code
        for num in picks:
            counts[num] = counts.get(num, 0) + 1
            fams.setdefault(num, set()).add(fam)
    borda = _borda(votes)
    ranking = sorted(
        lab_models.POOL,
        key=lambda x: (-counts.get(x, 0), -borda.get(x, 0), x))
    return {
        "strategy": "CONSENSUS_COUNT",
        "votes": votes,
        "n_models": n_models,
        "ranking": [
            {"rank": i + 1, "number": x,
             "votes": counts.get(x, 0),
             "vote_pct": round(counts.get(x, 0) / n_models, 4)
             if n_models else 0.0,
             "families": len(fams.get(x, ())),
             "borda": borda.get(x, 0)}
            for i, x in enumerate(ranking)],
        "top_k": sorted(ranking[:k]),
        "tie_break": "votes desc → Borda desc → numéro asc",
    }


def consensus_family_detail(
    hist: Sequence[Sequence[int]], k: int = 5
) -> dict[str, Any]:
    """Family-balanced consensus: a number's score is the mean, across
    declared families, of the share of that family's models voting for it."""
    votes = model_votes(hist, k)
    n_models = len(votes)
    # per-family vote counts
    fam_votes: dict[str, dict[int, int]] = {}
    fam_sizes: dict[str, int] = {}
    for code, picks in votes.items():
        fam = _family_of(code) or code
        fv = fam_votes.setdefault(fam, {})
        fam_sizes[fam] = fam_sizes.get(fam, 0) + 1
        for num in picks:
            fv[num] = fv.get(num, 0) + 1
    counts: dict[int, int] = {}
    fams: dict[int, set[str]] = {}
    score: dict[int, float] = {}
    for fam, fv in fam_votes.items():
        size = fam_sizes[fam]
        for num, c in fv.items():
            counts[num] = counts.get(num, 0) + c
            fams.setdefault(num, set()).add(fam)
            score[num] = score.get(num, 0.0) + c / size
    n_fam = len(fam_sizes)
    ranking = sorted(
        lab_models.POOL,
        key=lambda x: (-score.get(x, 0.0), -counts.get(x, 0), x))
    return {
        "strategy": "CONSENSUS_FAMILY",
        "votes": votes,
        "n_models": n_models,
        "n_families": n_fam,
        "ranking": [
            {"rank": i + 1, "number": x,
             "votes": counts.get(x, 0),
             "vote_pct": round(counts.get(x, 0) / n_models, 4)
             if n_models else 0.0,
             "families": len(fams.get(x, ())),
             "score": round(score.get(x, 0.0) / n_fam, 4)
             if n_fam else 0.0}
            for i, x in enumerate(ranking)],
        "family_scores": {
            fam: sorted(
                ((num, round(c / fam_sizes[fam], 4))
                 for num, c in fv.items()),
                key=lambda t: (-t[1], t[0]))[:10]
            for fam, fv in fam_votes.items()},
        "top_k": sorted(ranking[:k]),
        "tie_break": "part famille desc → votes bruts desc → numéro asc",
    }


# ---------------------------------------------------------------------------
# (hist, rng, k) pickers — registered like every other lab model
# ---------------------------------------------------------------------------


def predict_meta_consensus_count(hist, rng, k) -> list[int]:
    """Top-k of the raw vote count."""
    return consensus_count_detail(hist, k)["top_k"]


def predict_meta_consensus_family(hist, rng, k) -> list[int]:
    """Top-k of the family-balanced consensus."""
    return consensus_family_detail(hist, k)["top_k"]


META_ENSEMBLE_MODELS: dict[str, Any] = {
    "meta_consensus_count": predict_meta_consensus_count,
    "meta_consensus_family": predict_meta_consensus_family,
}


# ---------------------------------------------------------------------------
# API payload — votes matrix + both rankings + declared mechanics
# ---------------------------------------------------------------------------


def detail(hist: Sequence[Sequence[int]], k: int = 5) -> dict[str, Any]:
    """Full consensus payload for the UI: contributor top-k's, both
    rankings, family decomposition, declared tie-breaks. Everything is
    computed from `hist` only — strictly past information."""
    count = consensus_count_detail(hist, k)
    family = consensus_family_detail(hist, k)
    votes = count["votes"]
    return {
        "n_draws": len(hist),
        "k": k,
        "n_models": count["n_models"],
        "n_families": family["n_families"],
        "contributors": [
            {"code": code, "family": _family_of(code) or code,
             "picks": votes[code]}
            for code in sorted(votes)],
        "families": {fam: list(m) for fam, m in MODEL_FAMILIES.items()},
        "excluded": ["random", "null_model_benchmark", "ensemble_v1"],
        "strategies": {"CONSENSUS_COUNT": count,
                       "CONSENSUS_FAMILY": family},
        "tie_break_doc": _TIE_BREAK_DOC,
        "disclaimer": (
            "Le consensus agrège des modèles dont aucun n'a démontré un "
            "avantage : un vote majoritaire n'est pas une probabilité de "
            "gain. Évalué comme tout autre modèle — null, FDR, OOS, "
            "walk-forward, prospectif scellé."),
    }
