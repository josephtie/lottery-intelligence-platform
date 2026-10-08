"""Structure Map — audit of the statistical structure of the draw process.

Answers the question: are draws compatible with an independent, stable
random process, or do detectable temporal / frequency / positional /
cross-game dependencies exist?  Every phenomenon is tested against an
explicitly declared null, with Benjamini-Hochberg FDR control and —
where applicable — out-of-sample replication on the trailing holdout.

NULL MODELS
-----------

NULL A (theoretical)
    Uniform independent draws.  Point expectations come from binomial /
    hypergeometric laws (``dependence.binomial_right_tail``).
NULL B (permutation)
    Draw-order permutation (``null_model.permutation_p_value``):
    preserves the empirical multiset of draws, destroys all temporal
    dependence.  Used for serial / transition / positional structure.
NULL C (structural / empirical)
    ``structural_null`` resamples each draw as a k-without-replacement
    sample from the empirical per-number weights of the same history.
    Preserves draw size and marginal number frequencies; destroys
    temporal dependence, position dependence and within-draw
    correlation.  Used for delay / run distributions so phenomena are
    compared against a process with the same marginals — not against an
    unrealistically symmetric one.

Statuses follow the declared ladder NO_SIGNAL < INTERESTING < UNSTABLE <
ROBUST < VALIDATED.  VALIDATED additionally requires prospective
evidence and is never emitted automatically (``prospective_ok`` must be
supplied explicitly by the caller).
"""

from __future__ import annotations

import bisect
import math
import random
from collections import defaultdict
from typing import Any, Mapping, Sequence

from .calling_image import (
    CALLING_EDGES,
    DOMAIN,
    IMAGE_EDGES,
    MIN_SUPPORT,
    _stable_seed,
    evaluate_edges,
    evaluate_family,
)
from .dependence import binomial_right_tail
from .drift import detect_change_point
from .null_model import normal_sf, permutation_p_value
from .regime import monthly_period_counts
from .stats import chi_square_sf

# ---------------------------------------------------------------------------
# Declared windows / horizons / statuses
# ---------------------------------------------------------------------------

FREQUENCY_WINDOWS = (7, 14, 30, 60, 100, 250, 500, 1000)
AUTOCORR_LAGS = (1, 2, 3)
TRANSITION_LAGS = (1,)
DEFAULT_HOLDOUT = 0.2
FDR_Q = 0.05

NO_SIGNAL = "NO_SIGNAL"
INTERESTING = "INTERESTING"
UNSTABLE = "UNSTABLE"
ROBUST = "ROBUST"
VALIDATED = "VALIDATED"
_STATUS_ORDER = (NO_SIGNAL, INTERESTING, UNSTABLE, ROBUST, VALIDATED)

NULL_DOC = {
    "NULL_A": "Uniform independent draws; binomial/hypergeometric point "
              "expectations.",
    "NULL_B": "Draw-order permutation; preserves the empirical multiset of "
              "draws, destroys temporal dependence.",
    "NULL_C": "Structural resampling; each draw resampled without "
              "replacement from empirical number frequencies — preserves "
              "draw size and marginal frequencies, destroys temporal and "
              "positional structure.",
}


def _right_tail(n: int, p: float, k: int) -> float:
    """binomial_right_tail with clamped p and underflow tolerance."""
    p = min(1.0 - 1e-9, max(1e-9, p))
    try:
        return binomial_right_tail(n, p, k)
    except (ValueError, OverflowError):
        return 0.0


def _fdr(rows: list[dict[str, Any]], alpha: float = FDR_Q) -> None:
    """Attach BH q-values + significance flags to rows having p_value."""
    from lottery_intelligence_platform.lab_matrix import fdr_bh

    for row, q in zip(rows, fdr_bh([r["p_value"] for r in rows])):
        row["q_fdr"] = q
        row["significant"] = q < alpha


def _min_q(rows: Sequence[Mapping[str, Any]]) -> float | None:
    qs = [r["q_fdr"] for r in rows if r.get("q_fdr") is not None]
    return min(qs) if qs else None


def _status(
    min_q: float | None,
    *,
    oos_ok: bool | None = None,
    prospective_ok: bool = False,
) -> str:
    """Conservative status ladder.  VALIDATED requires prospective evidence."""
    if min_q is None or min_q >= FDR_Q:
        return NO_SIGNAL
    if prospective_ok:
        return VALIDATED
    if oos_ok is True:
        return ROBUST
    if oos_ok is False:
        return UNSTABLE
    return INTERESTING


def _sig_rows(res: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Significant edge rows of an evaluate_edges-style result."""
    return [r for r in res.get("edges", []) if r.get("q_fdr", 1.0) < FDR_Q]


# ---------------------------------------------------------------------------
# NULL C — structural resampling
# ---------------------------------------------------------------------------


def structural_null(
    hist: Sequence[Sequence[int]],
    rng: random.Random,
    n_histories: int = 1,
) -> list[list[list[int]]]:
    """Resample histories preserving draw size and marginal frequencies.

    Each synthetic draw is a weighted sample without replacement from
    per-number weights estimated on ``hist`` (count + 1 smoothing).
    """
    n = max(1, len(hist))
    probs = {num: (1.0 + sum(1 for d in hist if num in d)) / (n + 1)
             for num in DOMAIN}
    population = list(DOMAIN)
    out: list[list[list[int]]] = []
    for _ in range(n_histories):
        out.append([_inclusion_sample(rng, population, probs, len(draw))
                    for draw in hist])
    return out


def _inclusion_sample(
    rng: random.Random,
    population: Sequence[int],
    probs: Mapping[int, float],
    k: int,
) -> list[int]:
    """Independent-inclusion sample corrected to exactly k by marginal
    probability order — preserves heavy marginals (p≈1 stays ≈1) while
    remaining structure-free across draws."""
    chosen = {n for n in population if rng.random() < probs[n]}
    by_prob = sorted(population, key=lambda n: -probs[n])
    if len(chosen) > k:
        chosen = set(sorted(chosen, key=lambda n: -probs[n])[:k])
    else:
        for n in by_prob:
            if len(chosen) >= k:
                break
            chosen.add(n)
    return sorted(chosen)


# ---------------------------------------------------------------------------
# Family: frequency windows
# ---------------------------------------------------------------------------


def frequency_windows(
    hist: Sequence[Sequence[int]],
    windows: Sequence[int] = FREQUENCY_WINDOWS,
    *,
    alpha: float = FDR_Q,
) -> dict[str, Any]:
    """Rolling-window frequency deviations vs NULL A (binomial approx).

    For each number and window w (measured from the tail), compares the
    observed count in the last w draws against a binomial whose per-draw
    probability is estimated on the *preceding* history only — strictly
    past, no look-ahead.  FDR is applied jointly over numbers x windows.
    """
    n = len(hist)
    p_bar = (sum(len(d) for d in hist) / (n * 90.0)) if n else 5 / 90.0
    rows: list[dict[str, Any]] = []
    for w in windows:
        w_eff = min(w, n)
        base_n = n - w_eff
        # A window is only tested when its strict-past baseline is at
        # least as long as the window itself (and >= 60 draws): a noisy
        # baseline would manufacture deviations out of thin air.
        if w_eff < 5 or base_n < max(60, w_eff):
            continue
        base_hist = hist[: n - w_eff]
        if base_n:
            base_counts = {num: 0 for num in DOMAIN}
            for d in base_hist:
                for num in d:
                    base_counts[num] += 1
        recent = hist[n - w_eff:]
        for num in DOMAIN:
            p0 = (base_counts[num] / base_n) if base_n else p_bar
            p0 = max(1e-9, min(1.0, p0))
            obs = sum(1 for d in recent if num in d)
            exp = w_eff * p0
            sd = math.sqrt(exp * max(0.0, 1.0 - p0)) or 1e-9
            z = (obs - exp) / sd
            # Exact two-sided binomial (normal approx is anti-conservative
            # on short windows).
            if obs > exp:
                tail = _right_tail(w_eff, p0, obs)
            elif obs < exp:
                tail = _right_tail(w_eff, 1.0 - p0, w_eff - obs)
            else:
                tail = 1.0
            p_val = min(1.0, 2.0 * tail)
            rows.append({
                "number": num, "window": w,
                "observed": obs, "expected": round(exp, 2),
                "z": round(z, 3), "p_value": p_val,
            })
    _fdr(rows, alpha)
    rows.sort(key=lambda r: (r["q_fdr"], -abs(r["z"])))
    return {
        "family": "frequency",
        "null": "NULL_A",
        "n_tests": len(rows),
        "significant": sum(r["significant"] for r in rows),
        "min_q": _min_q(rows),
        "top": rows[:15],
        "flag_keys": [(r["number"], r["window"]) for r in rows
                      if r["significant"]],
    }


# ---------------------------------------------------------------------------
# Family: autocorrelation (self transitions) — reuses the edge engine
# ---------------------------------------------------------------------------

_SELF_EDGES = tuple((a, a) for a in DOMAIN)


def autocorrelation(
    hist: Sequence[Sequence[int]],
    lags: Sequence[int] = AUTOCORR_LAGS,
    *,
    seed: int = 0,
    permutations: int = 200,
    min_support: int = MIN_SUPPORT,
) -> dict[str, Any]:
    """A(t) -> A(t+k) per lag.  NULL A binomial + NULL B permutation."""
    per_lag: dict[int, dict[str, Any]] = {}
    flat: list[dict[str, Any]] = []
    for lag in lags:
        res = evaluate_edges(
            hist, _SELF_EDGES, horizon=lag, min_support=min_support,
            permutations=permutations,
            seed=_stable_seed("autocorr", seed, lag))
        rows = [dict(r, lag=lag) for r in res["edges"]]
        per_lag[lag] = {"n_tests": res["edges_tested"],
                        "significant": res["significant_fdr"],
                        "min_q": _min_q(res["edges"])}
        flat += rows
    top = sorted(flat, key=lambda r: (r["q_fdr"], -(r["lift"] or 0)))[:15]
    return {
        "family": "autocorrelation",
        "null": "NULL_A+NULL_B",
        "lags": list(lags),
        "n_tests": len(flat),
        "significant": sum(1 for r in flat if r["q_fdr"] < FDR_Q),
        "min_q": _min_q(flat),
        "per_lag": {str(k): v for k, v in per_lag.items()},
        "top": top,
        "flag_keys": [(r["a"], r["b"], r["lag"]) for r in flat
                      if r["q_fdr"] < FDR_Q],
    }


# ---------------------------------------------------------------------------
# Family: full directed transition matrix 90x90
# ---------------------------------------------------------------------------

_ALL_PAIRS = tuple((a, b) for a in DOMAIN for b in DOMAIN if a != b)


def transition_matrix(
    hist: Sequence[Sequence[int]],
    lags: Sequence[int] = TRANSITION_LAGS,
    *,
    seed: int = 0,
    permutations: int = 100,
    min_support: int = MIN_SUPPORT,
) -> dict[str, Any]:
    """Unconstrained discovery over all directed pairs A->B.

    Significant edges are then intersected with the Calling and Image
    edge sets, so the grid becomes a hypothesis compared against free
    discovery — not the discovery space itself.
    """
    per_lag: dict[int, dict[str, Any]] = {}
    sig_edges: set[tuple[int, int]] = set()
    all_rows: list[dict[str, Any]] = []
    for lag in lags:
        res = evaluate_edges(
            hist, _ALL_PAIRS, horizon=lag, min_support=min_support,
            permutations=permutations,
            seed=_stable_seed("transition", seed, lag))
        rows = res["edges"]
        per_lag[lag] = {"n_tests": res["edges_tested"],
                        "significant": res["significant_fdr"],
                        "min_q": _min_q(rows)}
        if lag == lags[0]:
            all_rows = rows
            sig_edges = {(r["a"], r["b"]) for r in _sig_rows(res)}
    calling_overlap = len(sig_edges & set(CALLING_EDGES))
    image_overlap = len(sig_edges & set(IMAGE_EDGES))
    return {
        "family": "transition",
        "null": "NULL_A+NULL_B",
        "lags": list(lags),
        "n_tests": sum(v["n_tests"] for v in per_lag.values()),
        "significant": len(sig_edges),
        "min_q": _min_q(all_rows),
        "top": all_rows[:20],
        "calling_overlap": calling_overlap,
        "image_overlap": image_overlap,
        "calling_share": round(calling_overlap / len(sig_edges), 3)
        if sig_edges else None,
        "per_lag": {str(k): v for k, v in per_lag.items()},
        "flag_keys": sorted(sig_edges),
    }


# ---------------------------------------------------------------------------
# Family: positional structure
# ---------------------------------------------------------------------------


def positional_structure(
    hist: Sequence[Sequence[int]],
    *,
    alpha: float = FDR_Q,
    permutations: int = 200,
    seed: int = 0,
) -> dict[str, Any]:
    """Two discovery layers, positions never pooled with each other:

    1. per-position uniformity: chi-square of the 90-number distribution
       at each position (FDR over positions) — NULL A;
    2. pooled positional persistence: draws where the number at position
       i reappears at position j of the next draw, per (i,j) cell —
       binomial vs k/90 (NULL A) + draw-order permutation (NULL B).
    """
    n = len(hist)
    k = len(hist[0]) if n else 5

    pos_rows: list[dict[str, Any]] = []
    for p in range(k):
        counts = [0] * 91
        for d in hist:
            counts[d[p]] += 1
        stat = sum((counts[num] - n / 90.0) ** 2 / (n / 90.0)
                   for num in DOMAIN)
        pos_rows.append({
            "position": p + 1, "chi2": round(stat, 2), "df": 89,
            "p_value": chi_square_sf(stat, 89),
        })
    _fdr(pos_rows, alpha)

    obs = [[0] * k for _ in range(k)]
    for t in range(n - 1):
        nxt_pos = {num: j for j, num in enumerate(hist[t + 1])}
        for i, a in enumerate(hist[t]):
            j = nxt_pos.get(a)
            if j is not None:
                obs[i][j] += 1
    exp_cell = (n - 1) * k / 90.0
    p_cell = k / 90.0
    perm_p = _positional_persist_perm(hist, obs, permutations, seed)
    cell_rows: list[dict[str, Any]] = []
    for i in range(k):
        for j in range(k):
            o = obs[i][j]
            cell_rows.append({
                "from_pos": i + 1, "to_pos": j + 1,
                "observed": o, "expected": round(exp_cell, 2),
                "lift": round(o / exp_cell, 3) if exp_cell else None,
                "p_value": _right_tail(n - 1, p_cell, o)
                if o > exp_cell else 1.0,
                "p_perm": perm_p[i][j],
            })
    _fdr(cell_rows, alpha)

    rows_all = pos_rows + cell_rows
    return {
        "family": "position",
        "null": "NULL_A+NULL_B",
        "n_tests": len(rows_all),
        "significant": sum(r["significant"] for r in rows_all),
        "min_q": _min_q(rows_all),
        "position_uniformity": pos_rows,
        "persistence": sorted(cell_rows,
                              key=lambda r: (r["q_fdr"], -(r["lift"] or 0))),
        "flag_keys": [("pos", r.get("position"), r.get("from_pos"),
                       r.get("to_pos")) for r in rows_all
                      if r["significant"]],
    }


def _positional_persist_perm(
    hist: Sequence[Sequence[int]],
    obs: list[list[int]],
    permutations: int,
    seed: int,
) -> list[list[float]]:
    """NULL B: permute draw order, recompute the (i,j) persistence cells."""
    k = len(obs)
    rng = random.Random(_stable_seed("posperm", seed))
    order = list(range(len(hist)))
    ge = [[1] * k for _ in range(k)]
    for _ in range(permutations):
        perm_order = order[:]
        rng.shuffle(perm_order)
        sim = [[0] * k for _ in range(k)]
        for t in range(len(perm_order) - 1):
            nxt_pos = {num: j for j, num in
                       enumerate(hist[perm_order[t + 1]])}
            for i, a in enumerate(hist[perm_order[t]]):
                j = nxt_pos.get(a)
                if j is not None:
                    sim[i][j] += 1
        for i in range(k):
            for j in range(k):
                if sim[i][j] >= obs[i][j]:
                    ge[i][j] += 1
    return [[g / (permutations + 1) for g in row] for row in ge]


# ---------------------------------------------------------------------------
# Family: runs / delay
# ---------------------------------------------------------------------------

_DELAY_BUCKETS = ((0, 0), (1, 1), (2, 2), (3, 5), (6, 10), (11, 20),
                  (21, 10 ** 9))


def runs_delay(
    hist: Sequence[Sequence[int]],
    *,
    alpha: float = FDR_Q,
    null_c_simulations: int = 100,
    seed: int = 0,
) -> dict[str, Any]:
    """Delay-conditioned return probability + long-run analysis.

    Delay: P(A in draw t | last seen d draws ago) per number x delay
    bucket, binomial vs marginal p — NULL A, FDR over all cells.
    Runs: runs >= 3 consecutive appearances per number, vs NULL C
    simulated distribution (same marginals) — FDR over numbers.
    """
    n = len(hist)
    p_bar = (sum(len(d) for d in hist) / (n * 90.0)) if n else 5 / 90.0
    sets = [set(d) for d in hist]

    last = {num: -1 for num in DOMAIN}
    cells: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
    for t in range(n):
        for num in DOMAIN:
            prev = last[num]
            if num in sets[t]:
                last[num] = t
            if prev < 0:
                continue
            d = t - prev - 1
            for bi, (lo, hi) in enumerate(_DELAY_BUCKETS):
                if lo <= d <= hi:
                    cells[(num, bi)][1] += 1
                    if num in sets[t]:
                        cells[(num, bi)][0] += 1
                    break
    delay_rows: list[dict[str, Any]] = []
    for (num, bi), (hits, trials) in cells.items():
        if trials < 10:
            continue
        lo, hi = _DELAY_BUCKETS[bi]
        delay_rows.append({
            "number": num,
            "delay_bucket": f"{lo}-{hi if hi < 10 ** 9 else 'inf'}",
            "trials": trials, "hits": hits,
            "rate": round(hits / trials, 4),
            "marginal": round(p_bar, 4),
            "lift": round(hits / (trials * p_bar), 3),
            "p_value": _right_tail(trials, p_bar, hits)
            if hits > trials * p_bar else 1.0,
        })
    _fdr(delay_rows, alpha)

    obs_runs = {num: _run_count(sets, num) for num in DOMAIN}
    rng = random.Random(_stable_seed("rundelay", seed))
    null_runs: list[int] = []
    for syn in structural_null(hist, rng, null_c_simulations):
        syn_sets = [set(d) for d in syn]
        for num in DOMAIN:
            null_runs.append(_run_count(syn_sets, num))
    null_runs.sort()
    m = len(null_runs)
    null_mean = sum(null_runs) / m if m else 0.0
    run_rows: list[dict[str, Any]] = []
    for num in DOMAIN:
        o = obs_runs[num]
        p_emp = (m - bisect.bisect_left(null_runs, o) + 1) / (m + 1)
        run_rows.append({
            "number": num, "runs_ge3": o,
            "null_mean": round(null_mean, 2),
            "p_value": min(1.0, p_emp),
        })
    _fdr(run_rows, alpha)

    rows_all = delay_rows + run_rows
    return {
        "family": "runs_delay",
        "null": "NULL_A+NULL_C",
        "n_tests": len(rows_all),
        "significant": sum(r["significant"] for r in rows_all),
        "min_q": _min_q(rows_all),
        "delay_top": sorted(delay_rows,
                            key=lambda r: (r["q_fdr"], -r["lift"]))[:15],
        "runs_top": sorted(run_rows, key=lambda r: r["q_fdr"])[:15],
        "flag_keys": [(r["number"], r.get("delay_bucket", "run"))
                      for r in rows_all if r["significant"]],
    }


def _run_count(sets: Sequence[set[int]], num: int) -> int:
    runs = streak = 0
    for s in sets:
        if num in s:
            streak += 1
        else:
            if streak >= 3:
                runs += 1
            streak = 0
    if streak >= 3:
        runs += 1
    return runs


# ---------------------------------------------------------------------------
# Families: change point (drift.py) and seasonality
# ---------------------------------------------------------------------------


def change_point_family(
    dated: Sequence[tuple[Any, Sequence[int]]],
    *,
    permutations: int = 500,
    seed: int = 0,
) -> dict[str, Any]:
    """Monthly homogeneity split, delegated to drift.detect_change_point
    (permutation null — NULL B)."""
    draws = [(d, None, set(nums)) for d, nums in dated]
    periods = [counts for _, counts in monthly_period_counts(draws)
               if sum(counts) > 0]
    res = (detect_change_point(periods, permutations=permutations,
                               seed=seed) if len(periods) >= 3 else None)
    if res is None:
        return {"family": "change_point", "null": "NULL_B",
                "n_tests": 0, "significant": 0, "min_q": None,
                "detail": "insufficient history"}
    return {
        "family": "change_point",
        "null": "NULL_B",
        "n_tests": 1,
        "significant": 1 if res.permutation_p < FDR_Q else 0,
        "min_q": res.permutation_p,
        "detail": {"split_index": res.split_index,
                   "statistic": round(res.statistic, 2),
                   "df": res.degrees_of_freedom,
                   "permutation_p": res.permutation_p},
    }


def seasonality(
    dated: Sequence[tuple[Any, Sequence[int]]],
    *,
    alpha: float = FDR_Q,
) -> dict[str, Any]:
    """Weekday x number homogeneity (chi-square on a 7x90 table) plus an
    aggregate per-weekday totals test.  NULL A: context-independent."""
    rows = [[0] * 90 for _ in range(7)]
    per_wd = [0] * 7
    for d, nums in dated:
        wd = d.weekday()
        for num in nums:
            rows[wd][num - 1] += 1
            per_wd[wd] += 1
    total = sum(per_wd)
    if total == 0:
        return {"family": "seasonality", "null": "NULL_A",
                "n_tests": 0, "significant": 0, "min_q": None}
    col_tot = [sum(rows[w][c] for w in range(7)) for c in range(90)]
    stat = 0.0
    for w in range(7):
        for c in range(90):
            e = per_wd[w] * col_tot[c] / total
            if e > 0:
                stat += (rows[w][c] - e) ** 2 / e
    df = 6 * 89
    p_table = chi_square_sf(stat, df)
    exp_wd = total / 7.0
    stat_wd = sum((c - exp_wd) ** 2 / exp_wd for c in per_wd)
    p_wd = chi_square_sf(stat_wd, 6)
    tests = [{"p_value": p_table}, {"p_value": p_wd}]
    _fdr(tests, alpha)
    return {
        "family": "seasonality",
        "null": "NULL_A",
        "n_tests": 2,
        "significant": sum(t["significant"] for t in tests),
        "min_q": _min_q(tests),
        "weekday_table": {"chi2": round(stat, 2), "df": df,
                          "p_value": p_table, "q_fdr": tests[0]["q_fdr"]},
        "weekday_totals": {"chi2": round(stat_wd, 2), "df": 6,
                           "p_value": p_wd, "q_fdr": tests[1]["q_fdr"],
                           "counts": per_wd},
    }


# ---------------------------------------------------------------------------
# Family: cross-game (ordered intra-day transitions X -> Y)
# ---------------------------------------------------------------------------


def cross_game(
    day_games: Mapping[Any, Sequence[tuple[int, str, Sequence[int]]]],
    *,
    permutations: int = 300,
    seed: int = 0,
    alpha: float = FDR_Q,
    min_days: int = 10,
) -> dict[str, Any]:
    """``day_games``: date -> ordered list of (scheduled_sequence,
    draw_type, numbers).  For each ordered adjacent game pair X -> Y on
    >= min_days days: mean |X ∩ Y| vs hypergeometric expectation with a
    NULL B permutation over Y-assignments, and directed calling-edge
    density X -> Y (normal approximation on aggregate counts)."""
    pair_days: dict[tuple[str, str], list[tuple[frozenset[int],
                                               frozenset[int]]]] = \
        defaultdict(list)
    for games in day_games.values():
        ordered = sorted(games)
        for (_, g1, n1), (_, g2, n2) in zip(ordered, ordered[1:]):
            pair_days[(g1, g2)].append((frozenset(n1), frozenset(n2)))

    def _calling_hits(x_sets: list[frozenset[int]],
                      ys: list[frozenset[int]]) -> float:
        hits = 0
        for x, y in zip(x_sets, ys):
            for a in x:
                if any(b in y for b in CALLING_EDGES.get(a, ())):
                    hits += 1
        return float(hits)

    rows: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    for (gx, gy), days in sorted(pair_days.items()):
        if len(days) < min_days:
            continue
        obs = sum(len(x & y) for x, y in days) / len(days)
        k1 = sum(len(x) for x, _ in days) / len(days)
        k2 = sum(len(y) for _, y in days) / len(days)
        exp = k1 * k2 / 90.0
        x_sets = [x for x, _ in days]
        y_sets = [y for _, y in days]
        # Both tests permute the Y-assignment across days: X stays fixed,
        # every Y draw keeps its content — temporal pairing is destroyed.
        p_overlap, _ = permutation_p_value(
            y_sets,
            lambda ys: sum(len(x_sets[i] & ys[i])
                           for i in range(len(days))) / len(days),
            permutations=permutations,
            seed=_stable_seed("xg-ov", seed, gx, gy))
        p_call, _ = permutation_p_value(
            y_sets,
            lambda ys: _calling_hits(x_sets, ys),
            permutations=permutations,
            seed=_stable_seed("xg-call", seed, gx, gy))
        hits = trials = 0
        exp_hits = 0.0
        for x, y in days:
            for a in x:
                deg = len(CALLING_EDGES.get(a, ()))
                if not deg:
                    continue
                trials += 1
                exp_hits += 1.0 - (math.comb(90 - len(y), deg)
                                   / math.comb(90, deg))
                if any(b in y for b in CALLING_EDGES[a]):
                    hits += 1
        row = {
            "from": gx, "to": gy, "days": len(days),
            "overlap_mean": round(obs, 3),
            "overlap_expected": round(exp, 3),
            "overlap_lift": round(obs / exp, 3) if exp else None,
            "overlap_p_perm": p_overlap,
            "calling_hits": hits, "calling_trials": trials,
            "calling_expected": round(exp_hits, 1),
            "calling_p_perm": p_call,
        }
        rows.append(row)
        tests.append({"p_value": p_overlap, "_row": row, "_t": "overlap"})
        tests.append({"p_value": p_call, "_row": row, "_t": "calling"})
    # FDR over ALL declared tests (2 per pair) — never min() of p-values.
    _fdr(tests, alpha)
    for t in tests:
        t["_row"][f"{t['_t']}_q_fdr"] = t["q_fdr"]
    for r in rows:
        r["q_fdr"] = min(r["overlap_q_fdr"], r["calling_q_fdr"])
        r["significant"] = r["q_fdr"] < alpha
    rows.sort(key=lambda r: (r["q_fdr"], -(r["overlap_lift"] or 0)))
    return {
        "family": "cross_game",
        "null": "NULL_B",
        "n_tests": len(tests),
        "significant": sum(r["significant"] for r in rows),
        "min_q": _min_q(rows),
        "pairs": rows,
        "flag_keys": [(r["from"], r["to"]) for r in rows
                      if r["significant"]],
    }


# ---------------------------------------------------------------------------
# Calling/Image — one declared family among the others
# ---------------------------------------------------------------------------


def calling_image_family(
    hist: Sequence[Sequence[int]],
    *,
    permutations: int = 200,
    seed: int = 0,
) -> dict[str, Any]:
    """Wraps calling_image.evaluate_family (H1–H4 with per-horizon FDR and
    OOS replication) and projects it into the structure-map summary."""
    res = evaluate_family(
        hist, horizons=(0, 1, 3), permutations=permutations, seed=seed)
    n_tests = significant = 0
    min_q: float | None = None
    sub: dict[str, Any] = {}
    for code, hyp in res["hypotheses"].items():
        h_min: float | None = None
        h_tests = h_sig = 0
        for per in hyp["per_horizon"].values():
            h_tests += per["edges_tested"]
            h_sig += per["significant_fdr"]
            q = _min_q(per["edges"])
            if q is not None and (h_min is None or q < h_min):
                h_min = q
        sub[code] = {"label": hyp["label"], "n_tests": h_tests,
                     "significant": h_sig, "min_q": h_min}
        n_tests += h_tests
        significant += h_sig
        if h_min is not None and (min_q is None or h_min < min_q):
            min_q = h_min
    return {
        "family": "calling_image",
        "null": "NULL_A+NULL_B",
        "n_tests": n_tests,
        "significant": significant,
        "min_q": min_q,
        "sub": sub,
        "full": res,
    }


# ---------------------------------------------------------------------------
# OOS replication + assembly
# ---------------------------------------------------------------------------


def _oos_ok(
    flag_keys: Sequence[Any],
    holdout_hist: Sequence[Sequence[int]],
    family_fn: Any,
    kwargs: Mapping[str, Any],
) -> bool | None:
    """Re-run the family on the trailing holdout; True if at least half of
    the train-side flags reproduce as FDR-significant there.  None when
    inapplicable (no flags / short holdout / family not rerunable)."""
    if not flag_keys or len(holdout_hist) < 30:
        return None
    res = family_fn(holdout_hist, **dict(kwargs))
    hold_keys = set(res.get("flag_keys", []))
    if not hold_keys:
        return False
    overlap = sum(1 for k in flag_keys if k in hold_keys)
    return overlap >= max(1, len(flag_keys) // 2)


def build_structure_map(
    hist: Sequence[Sequence[int]],
    *,
    dated: Sequence[tuple[Any, Sequence[int]]] | None = None,
    permutations: int = 200,
    seed: int = 0,
    holdout: float = DEFAULT_HOLDOUT,
    light: bool = False,
) -> dict[str, Any]:
    """Full structure audit for one game.

    ``light=True`` skips the full 90x90 transition matrix (used by tests
    and quick diagnostics).
    """
    n = len(hist)
    split = max(30, int(n * (1 - holdout)))
    hold = hist[split:]

    families: dict[str, Any] = {}
    families["frequency"] = frequency_windows(hist)
    families["autocorrelation"] = autocorrelation(
        hist, permutations=permutations, seed=seed)
    if not light:
        families["transition"] = transition_matrix(
            hist, permutations=max(50, permutations // 2), seed=seed)
    families["position"] = positional_structure(
        hist, permutations=max(50, permutations // 2), seed=seed)
    families["runs_delay"] = runs_delay(
        hist, null_c_simulations=max(30, permutations // 2), seed=seed)
    if dated:
        families["change_point"] = change_point_family(
            dated, permutations=permutations, seed=seed)
        families["seasonality"] = seasonality(dated)
    families["calling_image"] = calling_image_family(
        hist, permutations=permutations, seed=seed)

    # OOS replication on the trailing holdout where flags exist.
    if "transition" in families:
        families["transition"]["oos_ok"] = _oos_ok(
            families["transition"]["flag_keys"], hold,
            transition_matrix,
            {"permutations": 50, "seed": seed})
    families["autocorrelation"]["oos_ok"] = _oos_ok(
        families["autocorrelation"]["flag_keys"], hold,
        autocorrelation, {"permutations": 100, "seed": seed})
    families["frequency"]["oos_ok"] = _oos_ok(
        families["frequency"]["flag_keys"], hold,
        frequency_windows, {})
    families["runs_delay"]["oos_ok"] = _oos_ok(
        families["runs_delay"]["flag_keys"], hold,
        runs_delay, {"null_c_simulations": 30, "seed": seed + 1})
    families["position"]["oos_ok"] = _oos_ok(
        families["position"]["flag_keys"], hold,
        positional_structure, {"permutations": 50, "seed": seed})

    summary = []
    for name, res in families.items():
        summary.append({
            "family": name,
            "status": _status(res.get("min_q"), oos_ok=res.get("oos_ok")),
            "n_tests": res.get("n_tests", 0),
            "significant": res.get("significant", 0),
            "min_q": res.get("min_q"),
            "null": res.get("null"),
            "oos_ok": res.get("oos_ok"),
        })
    verdict = max(
        (s["status"] for s in summary),
        key=lambda s: _STATUS_ORDER.index(s),
        default=NO_SIGNAL)
    return {
        "n_draws": n,
        "train_size": split,
        "holdout_size": n - split,
        "null_models": NULL_DOC,
        "verdict": verdict,
        "statuses": summary,
        "families": families,
        "disclaimer": (
            "Une anomalie statistique n'est pas un avantage prédictif : "
            "INTERESTING marque un survivant FDR in-sample seulement ; "
            "ROBUST exige la réplication OOS ; VALIDATED exige de plus le "
            "prospectif scellé et n'est jamais attribué automatiquement."),
    }
