"""Game Temporal Intelligence — observation layer (no prediction).

For each game (draw_type) × model, replays the model strictly walk-forward
over the draw history — identical mechanism to lab_matrix.evaluate_game —
and aggregates the per-draw hit series along the temporal axis:

  * ISO week          → weekly hit means and ≥1/≥2/≥3 rates
  * weekday           → same-day-of-week comparison across weeks
  * profile           → n, mean, median, streaks, consistency, trend
  * change point      → drift.detect_change_point on weekly hit counts
  * null reference    → exact hypergeometric expectations + paired
                        comparison vs the null model on the same draws

Nothing here predicts, selects numbers, or writes anything. The sealed
predictions, settlements, cohorts and official rules are untouched. An
`as_of` cutoff guarantees that no result posterior to the analysis date
enters the profile.

Sample discipline (documented thresholds):
  n < 10   → "insufficient"  — no conclusion, stats hidden
  10..39   → "preliminary"   — stats shown, flagged as fragile
  n >= 40  → "adequate"      — matches MIN_WF used elsewhere
"""

from __future__ import annotations

import hashlib
import math
import random
from datetime import date
from typing import Any, Callable, Sequence
from uuid import UUID

from lottery_intelligence_platform import drift, lab_matrix

SEED = 20261005
WARMUP = lab_matrix.MIN_DRAWS          # draws a model must see before replay
MIN_ADEQUATE = lab_matrix.MIN_WF       # 40 — consistent with the matrix
MIN_PRELIMINARY = 10
CHANGE_POINT_MIN_WEEKS = 6             # need several periods on both sides
CP_PERMUTATIONS = 199
TREND_WEEKS = 4                        # last N weeks vs the rest
CV_STABLE = 0.35                       # documented stability thresholds
CV_VOLATILE = 0.60
NUMBERS_DRAWN = lab_matrix.NUMBERS_DRAWN  # 5
UNIVERSE = 90
MODELS: dict[str, Any] = lab_matrix.MATRIX_MODELS
NULL_MODEL = "null_model_benchmark"


def _stable_seed(*parts: str) -> int:
    """Deterministic model seed — hash() varies per process (PYTHONHASHSEED),
    sha256 does not. Reproducibility of aggregations is a requirement."""
    digest = hashlib.sha256(":".join(parts).encode()).digest()
    return int.from_bytes(digest[:4], "big")


def dated_history(
    connection: Any, draw_type_id: UUID, as_of: date
) -> list[tuple[date, list[int]]]:
    """Chronological (date, winning numbers) — latest VALID version per draw,
    strictly bounded to scheduled_date <= as_of (anti-leakage)."""
    rows = connection.execute(
        """SELECT d.scheduled_date, dn.number
           FROM core.draws d
           JOIN LATERAL (
               SELECT draw_version_id FROM core.draw_versions
               WHERE draw_id = d.draw_id AND validation_status = 'VALID'
               ORDER BY version_number DESC LIMIT 1
           ) v ON true
           JOIN core.draw_numbers dn
             ON dn.draw_version_id = v.draw_version_id
            AND dn.number_role = 'WINNING'
           WHERE d.draw_type_id = %s AND d.scheduled_date <= %s
           ORDER BY d.scheduled_date, dn.position""",
        (draw_type_id, as_of),
    ).fetchall()
    out: list[tuple[date, list[int]]] = []
    current_date = None
    current: list[int] = []
    for draw_date, number in rows:
        if draw_date != current_date:
            if current:
                out.append((current_date, current))
            current, current_date = [number], draw_date
        else:
            current.append(number)
    if current:
        out.append((current_date, current))
    return out


def wf_series(
    hist: Sequence[list[int]],
    dates: Sequence[date],
    fn: Callable[[list[list[int]], random.Random, int], list[int]],
    *,
    pick_count: int,
    seed: int,
    warmup: int = WARMUP,
    start: int | None = None,
) -> list[dict[str, Any]]:
    """Walk-forward hit series: model i only ever sees hist[:i].
    Same construction as lab_matrix.evaluate_game's walk_forward pass.
    `start` allows a windowed replay (last N draws) — the model still sees
    the full anterior history, only the scored window shrinks."""
    rng = random.Random(seed)
    lo = max(warmup, start if start is not None else warmup)
    out: list[dict[str, Any]] = []
    for i in range(lo, len(hist)):
        pick = set(fn(list(hist[:i]), rng, pick_count))
        out.append({"date": dates[i], "hits": len(pick & set(hist[i]))})
    return out


# ---------------------------------------------------------------------------
# Aggregations (pure — unit-tested without a database)
# ---------------------------------------------------------------------------

def iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def sample_level(n: int) -> str:
    if n < MIN_PRELIMINARY:
        return "insufficient"
    if n < MIN_ADEQUATE:
        return "preliminary"
    return "adequate"


def _aggregate(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """n, mean hits and ≥1/≥2/≥3 rates over a list of {hits} rows."""
    n = len(rows)
    if n == 0:
        return {"n": 0}
    ge = [sum(1 for r in rows if r["hits"] >= t) / n for t in (1, 2, 3)]
    return {
        "n": n,
        "mean_hits": round(sum(r["hits"] for r in rows) / n, 4),
        "ge1_pct": round(ge[0] * 100, 1),
        "ge2_pct": round(ge[1] * 100, 1),
        "ge3_pct": round(ge[2] * 100, 1),
        "sample_level": sample_level(n),
    }


def weekly_aggregate(series: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    weeks: dict[str, list[dict[str, Any]]] = {}
    for row in series:
        weeks.setdefault(iso_week(row["date"]), []).append(row)
    return [{"iso_week": w, **_aggregate(rows)}
            for w, rows in sorted(weeks.items())]


def weekday_aggregate(series: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Same weekday across weeks — e.g. all Mondays side by side."""
    days: dict[int, list[dict[str, Any]]] = {}
    for row in series:
        days.setdefault(row["date"].weekday(), []).append(row)
    return [{"weekday": wd, **_aggregate(days[wd])} for wd in sorted(days)]


def _streaks(hits: Sequence[int]) -> tuple[int, int]:
    """Longest run of draws with ≥1 hit / longest run with 0 hit."""
    best = worst = run_ge = run_zero = 0
    for h in hits:
        run_ge, run_zero = (run_ge + 1, 0) if h >= 1 else (0, run_zero + 1)
        best, worst = max(best, run_ge), max(worst, run_zero)
    return best, worst


def consistency(hits: Sequence[int], dates: Sequence[date]) -> dict[str, Any]:
    """Stability of the WEEKLY mean hit level — not a probability of winning.

    weekly means m_i → CV = sd(m_i)/mean(m_i); consistency_index = max(0, 1-CV)
    in [0,1]: 1 = identical weekly level every week, 0 = chaotic. Class:
    CV < 0.35 stable, < 0.60 mixed, else volatile. Reported alongside the
    level so 'high & stable' is distinguishable from 'high & volatile'.
    """
    weeks: dict[str, list[int]] = {}
    for h, d in zip(hits, dates):
        weeks.setdefault(iso_week(d), []).append(h)
    means = [sum(v) / len(v) for v in weeks.values()]
    if len(means) < 2 or sum(means) == 0:
        return {"weeks": len(means), "consistency_index": None,
                "cv_weekly": None, "stability": "not_computable"}
    mean = sum(means) / len(means)
    sd = math.sqrt(sum((m - mean) ** 2 for m in means) / (len(means) - 1))
    cv = sd / mean if mean else float("inf")
    index = max(0.0, 1.0 - cv)
    stability = "stable" if cv < CV_STABLE else (
        "mixed" if cv < CV_VOLATILE else "volatile")
    return {"weeks": len(means), "consistency_index": round(index, 4),
            "cv_weekly": round(cv, 4), "stability": stability}


def trend(weekly: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Mean hits of the last TREND_WEEKS weeks vs all earlier weeks."""
    usable = [w for w in weekly if w.get("n", 0) > 0]
    if len(usable) < TREND_WEEKS + 1:
        return {"label": "not_computable"}
    recent = usable[-TREND_WEEKS:]
    prior = usable[:-TREND_WEEKS]
    mean_r = sum(w["mean_hits"] for w in recent) / len(recent)
    mean_p = sum(w["mean_hits"] for w in prior) / len(prior)
    if mean_p == 0:
        return {"label": "not_computable"}
    delta = (mean_r - mean_p) / mean_p * 100
    label = "improving" if delta > 10 else ("declining" if delta < -10 else "flat")
    return {"recent_weeks": [w["iso_week"] for w in recent],
            "mean_recent": round(mean_r, 4), "mean_prior": round(mean_p, 4),
            "delta_pct": round(delta, 1), "label": label}


def hypergeom_ge(pick: int, threshold: int,
                 drawn: int = NUMBERS_DRAWN, universe: int = UNIVERSE) -> float:
    """Exact P(hits >= threshold): predicted `pick` numbers vs `drawn`
    winning numbers in `universe`. Hypergeometric — the honest null."""
    def choose(n: int, r: int) -> int:
        return math.comb(n, r) if 0 <= r <= n else 0
    total = choose(universe, drawn)
    return sum(choose(pick, h) * choose(universe - pick, drawn - h)
               for h in range(threshold, min(pick, drawn) + 1)) / total


def null_reference(pick_count: int) -> dict[str, Any]:
    """What a random pick expects under the hypergeometric null."""
    return {
        "expected_mean_hits": round(pick_count * NUMBERS_DRAWN / UNIVERSE, 4),
        "expected_ge1_pct": round(hypergeom_ge(pick_count, 1) * 100, 1),
        "expected_ge2_pct": round(hypergeom_ge(pick_count, 2) * 100, 1),
        "expected_ge3_pct": round(hypergeom_ge(pick_count, 3) * 100, 1),
    }


def vs_null(series: Sequence[dict[str, Any]], pick_count: int) -> dict[str, Any]:
    """Observed rates vs exact hypergeometric null + binomial p on ≥1 hits.
    Distinguishes raw performance from better-than-chance — never called
    'probability of success'."""
    n = len(series)
    if n == 0:
        return {}
    p1 = hypergeom_ge(pick_count, 1)
    k = sum(1 for r in series if r["hits"] >= 1)
    # two-sided exact binomial p on the ≥1 indicator — log-space terms:
    # comb(n, i) overflows float for n in the thousands.
    lgamma = math.lgamma
    def logpmf(i: int) -> float:
        return (lgamma(n + 1) - lgamma(i + 1) - lgamma(n - i + 1)
                + i * math.log(p1) + (n - i) * math.log1p(-p1))
    def tail(lo: int, hi: int) -> float:
        return min(1.0, sum(math.exp(logpmf(i)) for i in range(lo, hi + 1)))
    p_binom = min(1.0, 2 * min(tail(0, k), tail(k, n)))
    mean = sum(r["hits"] for r in series) / n
    expected = pick_count * NUMBERS_DRAWN / UNIVERSE
    return {
        "observed_ge1_pct": round(k / n * 100, 1),
        "expected_ge1_pct": round(p1 * 100, 1),
        "binomial_p_ge1": round(p_binom, 4),
        "mean_hits": round(mean, 4),
        "lift_mean_pct": round((mean - expected) / expected * 100, 1),
    }


def paired_vs_null(
    series: Sequence[dict[str, Any]],
    null_series: Sequence[dict[str, Any]],
    *,
    seed: int, permutations: int = 199,
) -> dict[str, Any] | None:
    """Same draws: mean hit difference model − null, sign-flip permutation p.
    This is 'better than the null on identical draws', not advantage proof."""
    if len(series) != len(null_series) or not series:
        return None
    diffs = [a["hits"] - b["hits"] for a, b in zip(series, null_series)]
    mean_diff = sum(diffs) / len(diffs)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(permutations):
        perm = sum(d * rng.choice((1, -1)) for d in diffs) / len(diffs)
        if abs(perm) >= abs(mean_diff):
            extreme += 1
    return {"mean_hit_diff": round(mean_diff, 4),
            "permutation_p": round((extreme + 1) / (permutations + 1), 4),
            "n": len(diffs)}


def change_point_observation(
    series: Sequence[dict[str, Any]], pick_count: int, *, seed: int
) -> dict[str, Any] | None:
    """Weekly hit-count vectors (0..pick) → drift.detect_change_point.
    Descriptive observation only — never a selection rule."""
    weeks: dict[str, list[int]] = {}
    for row in series:
        weeks.setdefault(iso_week(row["date"]), []).append(row["hits"])
    keys = sorted(weeks)
    if len(keys) < CHANGE_POINT_MIN_WEEKS:
        return None
    counts = [[weeks[k].count(h) for h in range(pick_count + 1)] for k in keys]
    # drop all-zero columns (e.g. hit=5 never occurs) for the chi2 machinery
    keep = [c for c in range(pick_count + 1) if sum(r[c] for r in counts) > 0]
    counts = [[r[c] for c in keep] for r in counts]
    if len(keep) < 2:
        return None
    cp = drift.detect_change_point(
        counts, permutations=CP_PERMUTATIONS, seed=seed)
    if cp is None or cp.permutation_p > 0.05:
        return None
    return {"iso_week": keys[cp.split_index],
            "permutation_p": cp.permutation_p,
            "statistic": round(cp.statistic, 2),
            "note": "observation descriptive — pas une règle de sélection"}


def model_profile(
    series: Sequence[dict[str, Any]],
    pick_count: int,
    *,
    seed: int,
) -> dict[str, Any]:
    """Full JEU×MODÈLE profile from one walk-forward hit series."""
    n = len(series)
    level = sample_level(n)
    hits = [r["hits"] for r in series]
    dates = [r["date"] for r in series]
    profile: dict[str, Any] = {"n": n, "sample_level": level}
    if level == "insufficient":
        profile["label"] = "Échantillon insuffisant"
        return profile
    best, worst = _streaks(hits)
    sorted_hits = sorted(hits)
    median = (sorted_hits[n // 2] if n % 2
              else (sorted_hits[n // 2 - 1] + sorted_hits[n // 2]) / 2)
    profile.update({
        "label": "Observation préliminaire" if level == "preliminary"
                 else "Échantillon suffisant",
        "median_hits": median,
        "best_ge1_streak": best,
        "worst_zero_streak": worst,
        **_aggregate(series),
        "consistency": consistency(hits, dates),
        "trend": trend(weekly_aggregate(series)),
        "vs_null": vs_null(series, pick_count),
        "change_point": change_point_observation(series, pick_count, seed=seed),
    })
    return profile


def weekly_model_matrix(
    series_by_model: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Rows: iso_week × mean hits per model — the 'progression' table."""
    weeks = sorted({iso_week(r["date"]) for s in series_by_model.values()
                    for r in s})
    out = []
    for w in weeks:
        row: dict[str, Any] = {"iso_week": w, "models": {}}
        for name, s in series_by_model.items():
            hits = [r["hits"] for r in s if iso_week(r["date"]) == w]
            if hits:
                row["models"][name] = round(sum(hits) / len(hits), 2)
                row["n_draws"] = row.get("n_draws", 0) or len(hits)
        out.append(row)
    return out


def game_profile(
    connection: Any,
    draw_type_id: UUID,
    display_name: str,
    *,
    as_of: date,
    pick_count: int = 5,
    seed: int = SEED,
    models: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Temporal profile of every model on ONE game — strict segmentation."""
    models = models or MODELS
    hist_pairs = dated_history(connection, draw_type_id, as_of)
    dates = [d for d, _ in hist_pairs]
    hist = [nums for _, nums in hist_pairs]
    out: dict[str, Any] = {
        "game": display_name, "as_of": as_of.isoformat(),
        "n_draws": len(hist), "n_replayed": max(0, len(hist) - WARMUP),
        "pick_count": pick_count, "warmup": WARMUP,
        "null_reference": null_reference(pick_count),
        "thresholds": {"preliminary": MIN_PRELIMINARY,
                       "adequate": MIN_ADEQUATE,
                       "cv_stable": CV_STABLE, "cv_volatile": CV_VOLATILE},
        "models": {},
    }
    if len(hist) <= WARMUP:
        out["error"] = "Échantillon insuffisant — historique trop court"
        return out
    series_by_model: dict[str, list[dict[str, Any]]] = {}
    for name, fn in models.items():
        series = wf_series(hist, dates, fn, pick_count=pick_count,
                           seed=_stable_seed(str(seed), name))
        series_by_model[name] = series
        profile = model_profile(series, pick_count,
                                seed=_stable_seed(str(seed), name, "cp"))
        entry = {"profile": profile,
                 "weekly": weekly_aggregate(series),
                 "weekday": weekday_aggregate(series)}
        out["models"][name] = entry
    # paired comparison model vs null on identical draws
    if NULL_MODEL in series_by_model:
        for name, series in series_by_model.items():
            if name == NULL_MODEL:
                continue
            out["models"][name]["paired_vs_null"] = paired_vs_null(
                series, series_by_model[NULL_MODEL],
                seed=_stable_seed(str(seed), name, "paired"))
    # per-draw detail for the UI "draw history" table — replayed window:
    # date, weekday, ISO week, winning numbers and each model's hit count.
    out["draws"] = [
        {"date": dates[i].isoformat(), "iso_week": iso_week(dates[i]),
         "weekday": dates[i].weekday(), "winning": hist[i],
         "hits": {name: series_by_model[name][i - WARMUP]["hits"]
                  for name in models}}
        for i in range(WARMUP, len(hist))
    ]
    out["weekly_models"] = weekly_model_matrix(series_by_model)
    out["model_names"] = list(models)
    return out


def prospective_matrix(connection: Any, as_of: date) -> dict[str, Any]:
    """Cross-game JEU × MODÈLE matrix from SEALED prospective outcomes only
    (research.prediction_outcomes). Real stats; sparse cells are labelled
    'Échantillon insuffisant' rather than hidden."""
    rows = connection.execute(
        """SELECT dt.display_name AS game, mv.code AS model,
                  o.hit_count
           FROM research.prediction_outcomes o
           JOIN research.predictions p ON p.prediction_id = o.prediction_id
           JOIN research.model_versions mv
             ON mv.model_version_id = p.model_version_id
           JOIN catalog.draw_types dt ON dt.draw_type_id = p.draw_type_id
           JOIN core.draws d ON d.draw_id = o.draw_id
           WHERE d.scheduled_date <= %s""",
        (as_of,),
    ).fetchall()
    games: dict[str, dict[str, list[int]]] = {}
    for game, model, hits in rows:
        games.setdefault(game, {}).setdefault(model, []).append(hits)
    matrix: dict[str, Any] = {}
    for game, model_hits in games.items():
        matrix[game] = {}
        for model, hits in model_hits.items():
            n = len(hits)
            series = [{"hits": h} for h in hits]
            matrix[game][model] = {
                "sample_level": sample_level(n),
                **({} if n < MIN_PRELIMINARY
                   else _aggregate(series)),
                "n": n,
            }
    return {"as_of": as_of.isoformat(), "source": "prospective_outcomes",
            "matrix": matrix}


CARD_WINDOW = 156  # ~26 weeks of draws replayed per card


def game_card(
    connection: Any, draw_type_id: UUID, display_name: str, *,
    as_of: date, window: int = CARD_WINDOW, pick_count: int = 5,
    seed: int = SEED, models: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One game card: windowed walk-forward summary (last `window` draws).
    Real stats, bounded cost — the full profile loads on game click."""
    models = models or MODELS
    hist_pairs = dated_history(connection, draw_type_id, as_of)
    dates = [d for d, _ in hist_pairs]
    hist = [nums for _, nums in hist_pairs]
    card: dict[str, Any] = {
        "game": display_name,
        "settled_draws": len(hist),
        "first_draw": dates[0].isoformat() if dates else None,
        "last_draw": dates[-1].isoformat() if dates else None,
        "window_draws": max(0, min(window, len(hist) - WARMUP)),
    }
    if len(hist) <= WARMUP + MIN_PRELIMINARY:
        card["sample_level"] = "insufficient"
        card["label"] = "Échantillon insuffisant"
        return card
    start = max(WARMUP, len(hist) - window)
    best = None
    pooled: list[int] = []
    for name, fn in models.items():
        series = wf_series(hist, dates, fn, pick_count=pick_count,
                           seed=_stable_seed(str(seed), name), start=start)
        pooled.extend(r["hits"] for r in series)
        agg = _aggregate(series)
        cons = consistency([r["hits"] for r in series],
                           [r["date"] for r in series])
        if name in (NULL_MODEL, "random"):
            continue
        if best is None or (agg.get("mean_hits") or -9) > best["mean_hits"]:
            best = {"model": name, "mean_hits": agg["mean_hits"],
                    "ge1_pct": agg["ge1_pct"], "ge2_pct": agg["ge2_pct"],
                    "ge3_pct": agg["ge3_pct"],
                    "stability": cons.get("stability"),
                    "consistency_index": cons.get("consistency_index")}
    card.update({
        "sample_level": sample_level(len(pooled)),
        "n_models": len(models),
        "pooled_mean_hits": round(sum(pooled) / len(pooled), 4) if pooled else None,
        "dominant_model": best,
    })
    return card


def game_cards(
    connection: Any, as_of: date, *, window: int = CARD_WINDOW
) -> list[dict[str, Any]]:
    """All game cards — windowed WF replay per game, ordered by volume."""
    rows = connection.execute(
        """SELECT DISTINCT ON (dt.display_name) dt.draw_type_id, dt.display_name
           FROM catalog.draw_types dt
           JOIN core.draws d ON d.draw_type_id = dt.draw_type_id
             AND d.status = 'SETTLED' AND d.scheduled_date <= %s
           ORDER BY dt.display_name, dt.draw_type_id""",
        (as_of,),
    ).fetchall()
    cards = [game_card(connection, tid, name, as_of=as_of, window=window)
             for tid, name in rows]
    cards.sort(key=lambda c: c["settled_draws"], reverse=True)
    return cards
