"""CALLING_IMAGE family — "called numbers" (grid neighbourhood) and "image
numbers" (digit reversal) tested as directional conditional associations.

These are *hypotheses*, not mechanisms. The scientific statement is never
"57 calls 49 so 49 will come out" but "when 57 is observed, 49 shows a
measurable conditional association — does it exceed the null model and
survive OOS, walk-forward and prospective validation?".

Four experiments, kept strictly separate:

  H1  IMAGE                  A -> image(A)
  H2  CALLING                A -> grid neighbours of A
  H3  CALLING + IMAGE        A -> neighbours of A -> image(neighbour)
  H4  CALLING + IMAGE + POSITION  same edges, conditioned on draw position

Every edge is directed: A -> B is measured independently of B -> A even
when the geometry is symmetric. The grid below is configuration, not
ground truth — pass a different one to `calling_edges` to test another.
"""

from __future__ import annotations

import bisect
import hashlib
import random
from typing import Any, Iterable, Mapping, Sequence

from lottery_intelligence_platform.dependence import binomial_right_tail
from lottery_intelligence_platform.null_model import permutation_p_value

NUMBER_MIN, NUMBER_MAX = 1, 90
DOMAIN = range(NUMBER_MIN, NUMBER_MAX + 1)

DEFAULT_HORIZONS: tuple[int, ...] = (0, 1, 3)
DEFAULT_OOS_FRACTION = 0.2
MIN_SUPPORT = 5
# Permutation tests are only run on edges that look at least mildly
# interesting under the theoretical null — running them on every edge of
# every horizon would be pure noise-chasing compute.
PERMUTATION_CANDIDATE_P = 0.25

# ---------------------------------------------------------------------------
# H1 — image numbers: 2-digit zero-padded digit reversal.
# 57 -> 75, 90 -> 09, 80 -> 08. The zero-padded string form keeps 09 and 90
# distinct representations; the int form is the lottery number itself.
# ---------------------------------------------------------------------------


def image_repr(n: int) -> str:
    """Two-character mirror image preserving the leading zero: 90 -> '09'."""
    if not NUMBER_MIN <= n <= NUMBER_MAX:
        raise ValueError(f"number out of domain: {n}")
    return str(n).zfill(2)[::-1]


def image_number(n: int) -> int:
    """Digit-reversal image: 57 -> 75, 90 -> 9 ('09'), 9 -> 90.

    The reversal may exceed the 1..90 draw domain (49 -> 94, 19 -> 91):
    such images are kept in the edge sets (they are part of the hypothesis
    as stated) but can never appear in a draw — they measure as zeros.
    """
    return int(image_repr(n))


def is_self_image(n: int) -> bool:
    """Palindromes map to themselves (11 -> 11): a degenerate edge."""
    return image_number(n) == n


def image_edges() -> dict[int, list[int]]:
    """Directed edges A -> image(A), both directions of each pair,
    excluding self-images."""
    edges: dict[int, list[int]] = {}
    for a in DOMAIN:
        b = image_number(a)
        edges[a] = [] if b == a else [b]
    return edges


IMAGE_EDGES = image_edges()

# ---------------------------------------------------------------------------
# H2 — calling numbers: Moore neighbourhood on the configured grid.
# Neighbour order is clockwise starting West, which reproduces the mandated
# example exactly: 57 -> 49, 78, 79, 18, 16. Numbers appearing several times
# in the grid are anchored at their first (row-major) occurrence.
# ---------------------------------------------------------------------------

DEFAULT_CALLING_GRID: tuple[tuple[int, ...], ...] = (
    (88, 49, 57, 16, 58, 42, 65, 71, 76, 67),
    (83, 78, 79, 18, 13, 56, 37, 54, 73, 80),
    (30,  2, 62, 15, 72, 33, 29, 74, 84, 68),
    (59, 61, 17, 48, 50, 34, 90,  8, 53, 80),
    (44, 19, 31, 46,  1, 87, 77, 36,  7, 63),
    (69,  6, 65, 45, 85, 32, 81, 82, 26, 23),
    (25,  5, 11,  3, 47, 41, 60, 52, 85, 27),
    (57, 43, 20, 75, 39, 70, 38, 21, 66, 14),
    (89,  9, 12, 40, 21, 28,  1, 10, 64, 23),
)

# (drow, dcol) clockwise from West: W, SW, S, SE, E, NE, N, NW.
_NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = (
    (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1),
)


def _validate_grid(grid: Sequence[Sequence[int]]) -> None:
    if not grid:
        raise ValueError("grid cannot be empty")
    width = len(grid[0])
    if width == 0 or any(len(row) != width for row in grid):
        raise ValueError("grid must be rectangular and non-empty")
    for row in grid:
        for n in row:
            if not NUMBER_MIN <= n <= NUMBER_MAX:
                raise ValueError(f"grid value out of domain: {n}")


def first_positions(grid: Sequence[Sequence[int]]) -> dict[int, tuple[int, int]]:
    """First row-major occurrence of each grid value."""
    pos: dict[int, tuple[int, int]] = {}
    for r, row in enumerate(grid):
        for c, n in enumerate(row):
            pos.setdefault(n, (r, c))
    return pos


def calling_edges(
    grid: Sequence[Sequence[int]] = DEFAULT_CALLING_GRID,
) -> dict[int, list[int]]:
    """Directed edges A -> grid neighbours of A (Moore neighbourhood).

    Numbers absent from the grid have no outgoing edge; any grid value may
    still be an edge *target*. Self-neighbours (possible when a value is
    duplicated in the grid) and duplicate targets are removed.
    """
    _validate_grid(grid)
    positions = first_positions(grid)
    edges: dict[int, list[int]] = {}
    for a, (r, c) in positions.items():
        seen: set[int] = set()
        out: list[int] = []
        for dr, dc in _NEIGHBOR_OFFSETS:
            rr, cc = r + dr, c + dc
            if 0 <= rr < len(grid) and 0 <= cc < len(grid[rr]):
                b = grid[rr][cc]
                if b != a and b not in seen:
                    seen.add(b)
                    out.append(b)
        edges[a] = out
    return edges


CALLING_EDGES = calling_edges()


def calling_image_edges(
    grid: Sequence[Sequence[int]] = DEFAULT_CALLING_GRID,
) -> dict[int, list[int]]:
    """H3 edges: A -> neighbours of A and A -> image(neighbour), deduplicated."""
    out: dict[int, list[int]] = {}
    for a, neighbours in calling_edges(grid).items():
        seen: set[int] = set()
        seq: list[int] = []
        for b in neighbours:
            for c in (b, image_number(b)):
                if c != a and c not in seen:
                    seen.add(c)
                    seq.append(c)
        out[a] = seq
    return out


CALLING_IMAGE_EDGES = calling_image_edges()


def _edge_pairs(edges: Mapping[int, Iterable[int]]) -> list[tuple[int, int]]:
    return [(a, b) for a, targets in edges.items() for b in targets]


def _stable_seed(*parts: object) -> int:
    """sha256-based seed — reproducible across processes (unlike hash())."""
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big")


# ---------------------------------------------------------------------------
# Directional association measurement.
#
# For an edge A -> B and a horizon h:
#   trigger = draw index i containing A, with a full h-draw window after it
#   hit     = B appears in draws i+1 .. i+h      (h = 0: B in the same draw)
#   baseline = fraction of all h-windows containing B
# ---------------------------------------------------------------------------


def _presence(hist_sets: Sequence[frozenset[int]]) -> dict[int, set[int]]:
    presence = {n: set() for n in DOMAIN}
    for i, s in enumerate(hist_sets):
        for n in s:
            if n in presence:
                presence[n].add(i)
    return presence


def _window_baselines(
    hist_sets: Sequence[frozenset[int]],
    presence: Mapping[int, set[int]],
    horizon: int,
) -> dict[int, float]:
    """Empirical P(B in the target window) for every number.

    horizon = 0: fraction of draws containing B.
    horizon >= 1: fraction of length-`horizon` windows (starting right after
    any index i in [0, n - horizon)) that contain B — the same window space
    the triggers are measured on.
    """
    n = len(hist_sets)
    if horizon == 0:
        return {b: len(idx) / n for b, idx in presence.items()} if n else {}
    n_windows = n - horizon
    if n_windows <= 0:
        return {}
    out: dict[int, float] = {}
    for b in DOMAIN:
        idx = sorted(presence[b])
        covered = 0
        prev_end = -1
        for j in idx:
            lo = max(0, j - horizon, prev_end + 1)
            hi = min(n_windows - 1, j - 1)
            if hi >= lo:
                covered += hi - lo + 1
                prev_end = hi
        out[b] = covered / n_windows
    return out


def _edge_counts(
    presence: Mapping[int, set[int]],
    n: int,
    a: int,
    b: int,
    horizon: int,
    presence_sorted: Mapping[int, list[int]] | None = None,
) -> tuple[int, int]:
    """(n_trigger, hits) for edge A -> B at the given horizon."""
    if horizon == 0:
        triggers = presence[a]
        return len(triggers), len(triggers & presence.get(b, set()))
    if presence_sorted is None:
        presence_sorted = {num: sorted(idx) for num, idx in presence.items()}
    valid = n - horizon
    triggers = [i for i in presence_sorted[a] if i < valid]
    idx_b = presence_sorted.get(b, [])
    hits = 0
    for i in triggers:
        j = bisect.bisect_right(idx_b, i)
        if j < len(idx_b) and idx_b[j] <= i + horizon:
            hits += 1
    return len(triggers), hits


def _conditional_rate(sets: Sequence[frozenset[int]], a: int, b: int, horizon: int) -> float:
    """P(B in window | A) recomputed on a (possibly permuted) sequence —
    the statistic handed to the draw-order permutation null."""
    n = len(sets)
    trig = hits = 0
    for i, s in enumerate(sets):
        if a not in s or i >= n - horizon:
            continue
        trig += 1
        if any(b in sets[j] for j in range(i + 1, i + 1 + horizon)):
            hits += 1
    return hits / trig if trig else 0.0


def evaluate_edges(
    hist: Sequence[Sequence[int]],
    edge_pairs: Iterable[tuple[int, int]],
    *,
    horizon: int = 0,
    min_support: int = MIN_SUPPORT,
    permutations: int = 0,
    seed: int = 0,
) -> dict[str, Any]:
    """Per-edge directional metrics at one horizon.

    Returns tested edges (support >= min_support) with P(B|A), P(B), lift,
    absolute/relative deviation, binomial right-tail p-value, optional
    permutation p-value and a Benjamini-Hochberg q-value over the whole
    tested set. Edges below the support floor are reported separately so
    the correction only covers real tests.
    """
    n = len(hist)
    sets = [frozenset(d) for d in hist]
    presence = _presence(sets)
    presence_sorted = {num: sorted(idx) for num, idx in presence.items()}
    baselines = _window_baselines(sets, presence, horizon)
    rows: list[dict[str, Any]] = []
    skipped = 0
    for a, b in edge_pairs:
        n_trigger, hits = _edge_counts(
            presence, n, a, b, horizon, presence_sorted)
        if n_trigger < min_support:
            skipped += 1
            continue
        p_base = baselines.get(b, 0.0)
        p_cond = hits / n_trigger
        expected = n_trigger * p_base
        p_value = (
            binomial_right_tail(n_trigger, p_base, hits)
            if hits > expected and p_base > 0
            else 1.0
        )
        rows.append({
            "a": a, "b": b,
            "n_trigger": n_trigger, "hits": hits,
            "p_cond": round(p_cond, 5), "p_base": round(p_base, 5),
            "expected_hits": round(expected, 3),
            "lift": round(p_cond / p_base, 4) if p_base > 0 else None,
            "abs_diff": round(p_cond - p_base, 5),
            "rel_diff": round((p_cond - p_base) / p_base, 4) if p_base else None,
            "p_value": round(p_value, 6),
        })
    if permutations:
        for row in rows:
            if row["p_value"] > PERMUTATION_CANDIDATE_P:
                continue
            a, b = row["a"], row["b"]
            edge_seed = _stable_seed(seed, "edge", a, b, horizon)
            if horizon == 0:
                # Permute which draws contain B (marginals preserved),
                # measure P(B | A) on the reassigned flags.
                a_flags = [a in s for s in sets]
                b_flags = [b in s for s in sets]

                def stat(flags: list[bool]) -> float:
                    trig = hits = 0
                    for fa, fb in zip(a_flags, flags):
                        if fa:
                            trig += 1
                            hits += fb
                    return hits / trig if trig else 0.0

                p_perm, _ = permutation_p_value(
                    b_flags, stat, permutations=permutations, seed=edge_seed)
            else:
                # Permute the draw order: destroys temporal adjacency while
                # preserving every draw's content and the marginals.
                def stat(seq: list[frozenset[int]]) -> float:
                    return _conditional_rate(seq, a, b, horizon)

                p_perm, _ = permutation_p_value(
                    sets, stat, permutations=permutations, seed=edge_seed)
            row["p_perm"] = round(p_perm, 5)
    # Benjamini-Hochberg over the full tested edge set (lazy import:
    # lab_matrix imports this module for the matrix models).
    from lottery_intelligence_platform.lab_matrix import fdr_bh

    for row, q in zip(rows, fdr_bh([r["p_value"] for r in rows])):
        row["q_fdr"] = q
    rows.sort(key=lambda r: (r["p_value"], -(r["lift"] or 0), r["a"], r["b"]))
    return {
        "horizon": horizon,
        "n_draws": n,
        "edges_tested": len(rows),
        "edges_low_support": skipped,
        "significant_fdr": sum(1 for r in rows if r["q_fdr"] < 0.05),
        "edges": rows,
    }


# ---------------------------------------------------------------------------
# H4 — positional conditioning. Draws are position-ordered (position p is the
# index inside the draw's number list). Each directed edge is tested per
# (pos_A, pos_B): P(B at q | A at p) vs P(B at q). Positions are never pooled.
# ---------------------------------------------------------------------------


def evaluate_positional_edges(
    hist: Sequence[Sequence[int]],
    edge_pairs: Iterable[tuple[int, int]],
    *,
    min_support: int = MIN_SUPPORT,
) -> dict[str, Any]:
    """Same-draw positional association per (a, b, pos_a, pos_b)."""
    n = len(hist)
    pos_index: dict[tuple[int, int], set[int]] = {}
    for i, draw in enumerate(hist):
        for p, num in enumerate(draw):
            pos_index.setdefault((num, p), set()).add(i)
    base_pos: dict[tuple[int, int], float] = {
        key: len(idx) / n for key, idx in pos_index.items()
    }
    rows: list[dict[str, Any]] = []
    skipped = 0
    pairs = list(edge_pairs)
    max_pos = max((len(d) for d in hist), default=0)
    for a, b in pairs:
        for p in range(max_pos):
            triggers = pos_index.get((a, p))
            if not triggers or len(triggers) < min_support:
                skipped += 1
                continue
            for q in range(max_pos):
                idx_bq = pos_index.get((b, q))
                if idx_bq is None:
                    continue
                hits = len(triggers & idx_bq)
                p_base = base_pos[(b, q)]
                p_cond = hits / len(triggers)
                expected = len(triggers) * p_base
                p_value = (
                    binomial_right_tail(len(triggers), p_base, hits)
                    if hits > expected and p_base > 0
                    else 1.0
                )
                rows.append({
                    "a": a, "b": b, "pos_a": p + 1, "pos_b": q + 1,
                    "n_trigger": len(triggers), "hits": hits,
                    "p_cond": round(p_cond, 5), "p_base": round(p_base, 5),
                    "expected_hits": round(expected, 3),
                    "lift": round(p_cond / p_base, 4) if p_base > 0 else None,
                    "abs_diff": round(p_cond - p_base, 5),
                    "rel_diff": round((p_cond - p_base) / p_base, 4) if p_base else None,
                    "p_value": round(p_value, 6),
                })
    from lottery_intelligence_platform.lab_matrix import fdr_bh

    for row, q in zip(rows, fdr_bh([r["p_value"] for r in rows])):
        row["q_fdr"] = q
    rows.sort(key=lambda r: (r["p_value"], -(r["lift"] or 0), r["a"], r["b"]))
    return {
        "horizon": 0,
        "n_draws": n,
        "edges_tested": len(rows),
        "edges_low_support": skipped,
        "significant_fdr": sum(1 for r in rows if r["q_fdr"] < 0.05),
        "edges": rows,
    }


# ---------------------------------------------------------------------------
# OOS replication — same discipline as conditional_dependence: an edge that
# looked good on the training fraction must keep lift > 1 on the held-out
# tail. Nothing is promoted on in-sample strength alone.
# ---------------------------------------------------------------------------


def _oos_replication(
    hist: Sequence[Sequence[int]],
    edge_pairs: list[tuple[int, int]],
    *,
    horizon: int,
    oos_fraction: float,
    min_support: int,
    positional: bool = False,
) -> dict[str, Any]:
    n = len(hist)
    n_oos = max(1, int(n * oos_fraction))
    train, holdout = hist[:n - n_oos], hist[n - n_oos:]
    evaluate = evaluate_positional_edges if positional else evaluate_edges
    kwargs: dict[str, Any] = {"min_support": min_support}
    if not positional:
        kwargs["horizon"] = horizon
    train_res = evaluate(train, edge_pairs, **kwargs)
    candidates = [
        (r["a"], r["b"], r.get("pos_a"), r.get("pos_b"))
        for r in train_res["edges"]
        if r["p_value"] < 0.05 and (r["lift"] or 0) > 1
    ]
    holdout_res = evaluate(holdout, edge_pairs, **kwargs)
    holdout_by_key = {
        (r["a"], r["b"], r.get("pos_a"), r.get("pos_b")): r
        for r in holdout_res["edges"]
    }
    surviving = [
        {
            "a": a, "b": b,
            **({"pos_a": pa, "pos_b": pb} if pa is not None else {}),
            "train_lift": next(
                r["lift"] for r in train_res["edges"]
                if r["a"] == a and r["b"] == b
                and r.get("pos_a") == pa and r.get("pos_b") == pb
            ),
            "oos_lift": holdout_by_key[(a, b, pa, pb)]["lift"],
        }
        for a, b, pa, pb in candidates
        if (a, b, pa, pb) in holdout_by_key
        and (holdout_by_key[(a, b, pa, pb)]["lift"] or 0) > 1
    ]
    return {
        "n_train": len(train), "n_oos": len(holdout),
        "train_candidates": len(candidates),
        "oos_surviving": len(surviving),
        "surviving_edges": surviving[:20],
    }


HYPOTHESES: dict[str, dict[str, Any]] = {
    "H1_IMAGE": {
        "label": "Image numbers",
        "edges": IMAGE_EDGES,
        "positional": False,
    },
    "H2_CALLING": {
        "label": "Calling numbers (grid neighbourhood)",
        "edges": CALLING_EDGES,
        "positional": False,
    },
    "H3_CALLING_IMAGE": {
        "label": "Calling numbers + images of called numbers",
        "edges": CALLING_IMAGE_EDGES,
        "positional": False,
    },
    "H4_CALLING_IMAGE_POSITION": {
        "label": "Calling + image, conditioned on draw position",
        "edges": CALLING_IMAGE_EDGES,
        "positional": True,
    },
}


def evaluate_family(
    hist: Sequence[Sequence[int]],
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    permutations: int = 0,
    seed: int = 0,
    oos_fraction: float = DEFAULT_OOS_FRACTION,
    min_support: int = MIN_SUPPORT,
) -> dict[str, Any]:
    """Run H1–H4 on one chronological history.

    Every hypothesis is measured separately, at each horizon separately.
    A good in-sample number is never a verdict — it is a candidate that
    must still beat the null, the FDR correction and the OOS holdout.
    """
    out: dict[str, Any] = {
        "n_draws": len(hist),
        "horizons": list(horizons),
        "hypotheses": {},
    }
    for code, spec in HYPOTHESES.items():
        pairs = _edge_pairs(spec["edges"])
        if spec["positional"]:
            pos_res = evaluate_positional_edges(
                hist, pairs, min_support=min_support)
            out["hypotheses"][code] = {
                "label": spec["label"],
                "edge_count": len(pairs),
                "per_horizon": {"position": pos_res},
                "oos": _oos_replication(
                    hist, pairs, horizon=0, oos_fraction=oos_fraction,
                    min_support=min_support, positional=True),
            }
            continue
        per_horizon: dict[str, Any] = {}
        oos: dict[str, Any] = {}
        for h in horizons:
            res = evaluate_edges(
                hist, pairs, horizon=h, min_support=min_support,
                permutations=permutations,
                seed=_stable_seed(seed, code, h))
            res["edges"] = res["edges"][:25]
            per_horizon[str(h)] = res
            oos[str(h)] = _oos_replication(
                hist, pairs, horizon=h, oos_fraction=oos_fraction,
                min_support=min_support)
        out["hypotheses"][code] = {
            "label": spec["label"],
            "edge_count": len(pairs),
            "per_horizon": per_horizon,
            "oos": oos,
        }
    out["disclaimer"] = (
        "Une association conditionnelle mesurable n'est pas un avantage "
        "prédictif : elle doit battre le modèle nul, survivre à la "
        "correction FDR, à l'OOS, au walk-forward et au prospectif scellé."
    )
    return out


# ---------------------------------------------------------------------------
# Pickers — the (hist, rng, k) interface of lab_models, so the matrix,
# walk-forward, OOS and the sealed prospective cohort evaluate this family
# exactly like every other. Deterministic; `rng` is ignored.
# ---------------------------------------------------------------------------


def _frequency(hist: Sequence[Sequence[int]]) -> dict[int, int]:
    freq: dict[int, int] = {}
    for draw in hist:
        for n in draw:
            freq[n] = freq.get(n, 0) + 1
    return freq


def _fill(hist: Sequence[Sequence[int]], chosen: list[int], k: int) -> list[int]:
    """Pad to k with the most frequent numbers not already chosen — the
    deterministic fallback used when an edge set yields < k candidates."""
    freq = _frequency(hist)
    seen = set(chosen)
    out = list(chosen)
    for n in sorted(DOMAIN, key=lambda x: (-freq.get(x, 0), x)):
        if len(out) >= k:
            break
        if n not in seen:
            seen.add(n)
            out.append(n)
    return sorted(out[:k])


def predict_calling_numbers(hist, rng, k) -> list[int]:
    """H2 picker: the grid neighbours of the last draw's numbers."""
    if not hist:
        return _fill(hist, [], k)
    seen: set[int] = set()
    chosen: list[int] = []
    for a in hist[-1]:
        for b in CALLING_EDGES.get(a, []):
            if b not in seen:
                seen.add(b)
                chosen.append(b)
    return _fill(hist, chosen[:k], k)


def predict_image_numbers(hist, rng, k) -> list[int]:
    """H1 picker: the digit-reversal images of the last draw's numbers."""
    if not hist:
        return _fill(hist, [], k)
    seen: set[int] = set()
    chosen: list[int] = []
    for a in hist[-1]:
        b = image_number(a)
        if b != a and NUMBER_MIN <= b <= NUMBER_MAX and b not in seen:
            seen.add(b)
            chosen.append(b)
    return _fill(hist, chosen[:k], k)


def predict_calling_image(hist, rng, k) -> list[int]:
    """H3 picker: neighbours of the last draw, then their images."""
    if not hist:
        return _fill(hist, [], k)
    seen: set[int] = set()
    chosen: list[int] = []
    for a in hist[-1]:
        for b in CALLING_IMAGE_EDGES.get(a, []):
            if NUMBER_MIN <= b <= NUMBER_MAX and b not in seen:
                seen.add(b)
                chosen.append(b)
    return _fill(hist, chosen[:k], k)


def predict_calling_image_position(hist, rng, k) -> list[int]:
    """H4 picker: H3 candidates scored by their strongest historical
    positional co-occurrence count(a at p, b at q), past draws only."""
    if not hist:
        return _fill(hist, [], k)
    last = hist[-1]
    past = hist[:-1]
    freq = _frequency(past)
    scores: dict[int, int] = {}
    for p, a in enumerate(last):
        for b in CALLING_IMAGE_EDGES.get(a, []):
            if not NUMBER_MIN <= b <= NUMBER_MAX:
                continue
            best = 0
            for q in range(len(last)):
                count = sum(
                    1
                    for d in past
                    if p < len(d) and q < len(d) and d[p] == a and d[q] == b
                )
                best = max(best, count)
            scores[b] = scores.get(b, 0) + best
    ranked = sorted(scores, key=lambda b: (-scores[b], -freq.get(b, 0), b))
    return _fill(hist, ranked[:k], k)


CALLING_IMAGE_MODELS: dict[str, Any] = {
    "calling_numbers": predict_calling_numbers,
    "image_numbers": predict_image_numbers,
    "calling_image": predict_calling_image,
    "calling_image_position": predict_calling_image_position,
}
