"""Model × game evaluation matrix — ported from lab_matrix v2.2.

For each draw type, every model is evaluated on exactly the same draws at
four separate levels:

  1. in_sample     : full history, exploration only (never proof)
  2. walk_forward  : each prediction only sees the past (real backtest)
  3. out_of_sample : strict temporal holdout — the newest fraction is hidden
  4. prospective   : real sealed predictions (research.prediction_outcomes)

Each cell reports n, mean_hits, lift vs chance, p-value, CI95, hit
distribution; walk-forward p-values get a Benjamini-Hochberg correction per
game. A cell is never declared winning on raw performance alone; "no model
demonstrated" is a valid default verdict.
"""

from __future__ import annotations

import math
import random
from datetime import date
from typing import Any
from uuid import UUID

from lottery_intelligence_platform import calling_image, lab_models
from lottery_intelligence_platform.prediction_generation import _history

SEED = 20260930
OOS_FRACTION = 0.2
MIN_DRAWS = 20
MIN_WF = 40
PRODUCTION = "hot_frequency_v1"
NUMBERS_DRAWN = 5  # winning numbers per draw

# Models evaluated in the matrix: the 9 lab models + the 4 platform pickers,
# all mapped onto the same (hist, rng, k) interface.
MATRIX_MODELS: dict[str, Any] = {
    **lab_models.HIST_MODELS,
    "null_model_benchmark": lab_models.predict_random,
    "top_k_frequency": lab_models.predict_top_k,
    "rolling_frequency": lab_models.predict_rolling,
    "bayesian_shrinkage": lab_models.predict_bayesian_shrinkage,
    **calling_image.CALLING_IMAGE_MODELS,
}


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def stats_for(hits: list[int], *, pick_count: int = 5) -> dict[str, Any] | None:
    """n, mean, lift vs chance, CI95, two-sided p vs binomial variance,
    hit distribution."""
    n = len(hits)
    if n == 0:
        return None
    expected = pick_count * NUMBERS_DRAWN / 90
    mean = sum(hits) / n
    p = NUMBERS_DRAWN / 90
    var_theo = pick_count * p * (1 - p)
    from collections import Counter
    dist = Counter(hits)
    out: dict[str, Any] = {
        "n": n, "mean_hits": round(mean, 4),
        "lift_pct": round((mean - expected) / expected * 100, 2),
        "distribution": {str(k): round(dist.get(k, 0) / n * 100, 1)
                         for k in range(pick_count + 1)},
    }
    if n >= 2:
        sd = math.sqrt(sum((h - mean) ** 2 for h in hits) / (n - 1))
        half = 1.96 * sd / math.sqrt(n)
        out["ci95"] = [round(mean - half, 4), round(mean + half, 4)]
        se = math.sqrt(var_theo / n)
        z = (mean - expected) / se
        out["p_value"] = round(2 * (1 - _normal_cdf(abs(z))), 4)
    return out


def fdr_bh(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg q-values aligned on the input p-values."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    q = [0.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        val = min(prev, pvalues[i] * m / rank)
        q[i] = round(val, 4)
        prev = val
    return q


def _prospective_hits(
    connection: Any, draw_type_id: UUID, model_code: str
) -> list[int]:
    """Real sealed-prediction hits for this model on this draw type."""
    rows = connection.execute(
        """SELECT o.hit_count
           FROM research.prediction_outcomes o
           JOIN research.predictions p ON p.prediction_id = o.prediction_id
           JOIN research.model_versions mv
             ON mv.model_version_id = p.model_version_id
           WHERE p.draw_type_id = %s AND mv.code = %s
           ORDER BY o.settled_at""",
        (draw_type_id, model_code),
    ).fetchall()
    return [r[0] for r in rows]


def evaluate_game(
    connection: Any,
    draw_type_id: UUID,
    display_name: str,
    *,
    pick_count: int = 5,
    seed: int = SEED,
    oos_fraction: float = OOS_FRACTION,
) -> dict[str, Any] | None:
    """Evaluate every model on the same draws of one game, 4 levels."""
    hist = _history(connection, draw_type_id, date(2100, 1, 1))
    n_total = len(hist)
    if n_total < MIN_DRAWS + MIN_WF:
        return None

    n_oos = max(1, int(n_total * oos_fraction))
    hist_only = hist[:n_total - n_oos]
    oos_draws = hist[n_total - n_oos:]

    results: dict[str, Any] = {
        "game": display_name, "n_history": n_total, "n_oos": n_oos,
        "pick_count": pick_count, "models": {},
    }
    pvals_wf: list[float] = []
    model_names: list[str] = []

    for name, fn in MATRIX_MODELS.items():
        entry: dict[str, Any] = {}

        rng_is = random.Random(seed + (hash(name + "_is") % 100000))
        is_hits = [
            len(set(fn(hist_only[:i + 1], rng_is, pick_count))
                & set(hist_only[i]))
            for i in range(len(hist_only) - MIN_DRAWS)
        ]
        entry["in_sample"] = stats_for(is_hits, pick_count=pick_count)

        rng_wf = random.Random(seed + (hash(name) % 100000))
        wf_hits = [
            len(set(fn(hist_only[:i], rng_wf, pick_count)) & set(hist_only[i]))
            for i in range(MIN_DRAWS, len(hist_only))
        ]
        entry["walk_forward"] = stats_for(wf_hits, pick_count=pick_count)
        if entry["walk_forward"]:
            pvals_wf.append(entry["walk_forward"].get("p_value") or 1.0)
            model_names.append(name)

        rng_oos = random.Random(seed + (hash(name + "_oos") % 100000))
        oos_hits = [
            len(set(fn(hist[:n_total - n_oos + i], rng_oos, pick_count))
                & set(actual))
            for i, actual in enumerate(oos_draws)
        ]
        entry["out_of_sample"] = stats_for(oos_hits, pick_count=pick_count)

        entry["prospective"] = stats_for(
            _prospective_hits(connection, draw_type_id, name),
            pick_count=2,  # sealed cohort picks are pick_count=2
        )
        results["models"][name] = entry

    if pvals_wf:
        for name, q in zip(model_names, fdr_bh(pvals_wf)):
            results["models"][name]["walk_forward"]["q_fdr"] = q
    return results


def robustness_score(entry: dict[str, Any]) -> tuple[int, list[str]]:
    """Synthetic solidity score 0-100: volume + significance + OOS
    coherence + CI stability."""
    wf = entry.get("walk_forward") or {}
    oos = entry.get("out_of_sample") or {}
    score, reasons = 0, []
    n = wf.get("n", 0)
    vol = min(25, n / 10)
    score += vol
    reasons.append(f"volume {n}→{vol:.0f}/25")
    q = wf.get("q_fdr")
    if q is not None:
        sig = 25 if q < 0.05 else (15 if q < 0.10 else 0)
        score += sig
        reasons.append(f"FDR q={q}→{sig}/25")
    lo, lw = oos.get("lift_pct"), wf.get("lift_pct")
    if lo is not None and lw is not None:
        coh = 25 if (lo > 0 and lw > 0) else (10 if lo > 0 or lw > 0 else 0)
        score += coh
        reasons.append(f"cohérence WF/OOS→{coh}/25")
    ci = wf.get("ci95")
    if ci:
        stab = 25 if ci[0] > 0 else (10 if ci[1] > 0 else 0)
        score += stab
        reasons.append(f"IC95 [{ci[0]},{ci[1]}]→{stab}/25")
    return round(score), reasons


def stage_of(entry: dict[str, Any]) -> str:
    """Promotion stage per the quantitative policy."""
    wf = entry.get("walk_forward") or {}
    oos = entry.get("out_of_sample") or {}
    q = wf.get("q_fdr")
    n = wf.get("n", 0)
    if n >= 100 and (wf.get("lift_pct") or 0) > 0 and (wf.get("p_value") or 1) < 0.05:
        if q is not None and q < 0.10 and (oos.get("lift_pct") or 0) > 0:
            return "CANDIDAT-FORT (survit FDR + OOS cohérent)"
        return "CANDIDAT (non corrigé multiple)"
    if (wf.get("lift_pct") or 0) > 0:
        return "TEST"
    return "EXPLORATION"


def candidate_for(results: dict[str, Any]) -> dict[str, Any]:
    """Best model per game — or the 'no model demonstrated' verdict."""
    best = None
    for name, entry in results["models"].items():
        if name in ("random", "null_model_benchmark"):
            continue
        wf = entry.get("walk_forward") or {}
        rob, reasons = robustness_score(entry)
        row = {
            "model": name, "stage": stage_of(entry), "robustness": rob,
            "reasons": reasons,
            "n_wf": wf.get("n"), "lift_wf": wf.get("lift_pct"),
            "q_fdr": wf.get("q_fdr"),
            "lift_oos": (entry.get("out_of_sample") or {}).get("lift_pct"),
            "p_wf": wf.get("p_value"),
        }
        if best is None or (wf.get("q_fdr") or 1) < (best["q_fdr"] or 1):
            best = row
    demonstrated = (
        best is not None
        and best["q_fdr"] is not None and best["q_fdr"] < 0.10
        and best["lift_oos"] is not None and best["lift_oos"] > 0
    )
    return {
        "game": results["game"],
        "candidate": best["model"] if demonstrated else None,
        "verdict": (
            f"CANDIDAT: {best['model']} (robustesse {best['robustness']}/100)"
            if demonstrated else
            "AUCUN MODÈLE SUFFISAMMENT DÉMONTRÉ (résultat valide)"),
        "best_raw": best,
    }
