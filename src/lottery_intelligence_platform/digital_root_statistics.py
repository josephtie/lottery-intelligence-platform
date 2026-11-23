"""Digital Root Statistics — descriptive statistics of digital roots.

Convention (see ``digital_root.py``): the digital root of a number is the
recursive digit sum reduced to a single digit, with digital root **9
represented as 0**. This yields **9 classes: 0..8**. Every class covers exactly
10 numbers out of 90 (1..90), so the null reference frequency is uniform
``10/90 ≈ 11.11 %`` per class — including per position, since every position
also draws from the same 1..90 universe.

**Descriptive only.** A high past frequency is never presented as a guarantee
of future output. Frequencies are compared to the uniform reference above;
windows are nested in time and therefore NOT independent samples.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Sequence

from lottery_intelligence_platform.digital_root import digital_root, numbers_by_root

TIMEZONE = "Africa/Abidjan"
WINDOWS: tuple[int, ...] = (10, 30, 45, 60, 90)
ROOTS: tuple[int, ...] = tuple(range(9))  # 0..8
NUMBERS_PER_ROOT = 10
REFERENCE_FREQ = NUMBERS_PER_ROOT / 90  # ≈ 0.1111


@dataclass(frozen=True, slots=True)
class Draw:
    """One settled draw with its winning numbers ordered by position (1..5)."""

    draw_id: str
    draw_date: date
    numbers: tuple[int, ...]


def roots_of(numbers: Sequence[int]) -> tuple[int, ...]:
    """Digital roots of a number sequence, preserving order/position."""
    return tuple(digital_root(n) for n in numbers)


def load_draws(conn: Any, draw_type_id: Any, reference_date: date) -> list[Draw]:
    """Load settled winning draws (ordered by position) up to ``reference_date``.

    Uses the same source as ``api._statistics``: VALID draw versions + WINNING
    numbers. Only draws at or before the reference date are returned.
    """
    rows = conn.execute(
        """SELECT d.draw_id, d.scheduled_date, n.number
           FROM core.draws d
           JOIN core.draw_versions v
             ON v.draw_id = d.draw_id AND v.validation_status = 'VALID'
           JOIN core.draw_numbers n
             ON n.draw_version_id = v.draw_version_id
            AND n.number_role = 'WINNING'
           WHERE d.draw_type_id = %s AND d.scheduled_date <= %s
           ORDER BY d.scheduled_date, d.scheduled_sequence, n.position""",
        (draw_type_id, reference_date),
    ).fetchall()
    draws: dict[tuple[str, date], list[int]] = {}
    for draw_id, draw_date, number in rows:
        draws.setdefault((str(draw_id), draw_date), []).append(number)
    return [
        Draw(draw_id=did, draw_date=dd, numbers=tuple(nums))
        for (did, dd), nums in draws.items()
    ]


def filter_window(draws: Sequence[Draw], reference: date, days: int) -> list[Draw]:
    """Draws whose date is in the inclusive window ``[reference - days, reference]``."""
    start = reference - timedelta(days=days)
    return [d for d in draws if start <= d.draw_date <= reference]


def _counts_in_window(draws: Sequence[Draw]) -> tuple[Counter, Counter, int]:
    """(root -> number count, root -> draw count, total numbers)."""
    root_count: Counter = Counter()
    draw_count: Counter = Counter()
    total = 0
    for d in draws:
        roots = roots_of(d.numbers)
        root_count.update(roots)
        draw_count.update(set(roots))
        total += len(roots)
    return root_count, draw_count, total


def global_distribution(draws: Sequence[Draw]) -> tuple[list[dict], int]:
    """Per-root global distribution (occurrences, %, draws, deviation from uniform)."""
    root_count, draw_count, total = _counts_in_window(draws)
    out: list[dict] = []
    for r in ROOTS:
        c = root_count[r]
        pct = (c / total * 100) if total else 0.0
        out.append({
            "root": r,
            "family": numbers_by_root(r),
            "count": c,
            "percentage": round(pct, 3),
            "draws": draw_count[r],
            "deviation_pct": round(pct - REFERENCE_FREQ * 100, 3),
        })
    return out, total


def position_distribution(draws: Sequence[Draw]) -> dict:
    """Per-position root counts and percentages.

    Returns ``{position: {root, count, percentage, top_root}}`` keyed by the
    1-indexed position (1..5).
    """
    positions = sorted({len(d.numbers) for d in draws}) if draws else []
    max_pos = positions[-1] if positions else 0
    per_pos: dict[int, Counter] = {p: Counter() for p in range(1, max_pos + 1)}
    for d in draws:
        for pos, n in enumerate(d.numbers, start=1):
            per_pos[pos][digital_root(n)] += 1
    result: dict = {}
    for pos in range(1, max_pos + 1):
        cnt = per_pos[pos]
        total = sum(cnt.values())
        rows = []
        for r in ROOTS:
            c = cnt[r]
            rows.append({
                "root": r,
                "count": c,
                "percentage": round((c / total * 100) if total else 0.0, 3),
            })
        top = max(ROOTS, key=lambda r: (cnt[r], -r)) if total else None
        result[str(pos)] = {
            "position": pos,
            "total": total,
            "rows": rows,
            "top_root": top,
            "top_count": cnt[top] if top is not None else 0,
        }
    return result


def draw_signatures(draws: Sequence[Draw], limit: int = 20) -> list[dict]:
    """Per-draw root signature for the most recent draws (chronological last)."""
    out: list[dict] = []
    for d in draws[-limit:]:
        roots = roots_of(d.numbers)
        distinct = len(set(roots))
        repeats = [r for r, c in Counter(roots).items() if c > 1]
        out.append({
            "draw_id": d.draw_id,
            "date": d.draw_date.isoformat(),
            "numbers": list(d.numbers),
            "roots": list(roots),
            "signature": "-".join(str(r) for r in roots),
            "distinct_count": distinct,
            "repeats": repeats,
        })
    return out


def family_stats(draws: Sequence[Draw]) -> list[dict]:
    """Per-root family: candidate numbers + occurrence frequency by position."""
    per_pos: dict[int, Counter] = {}
    total_by_root: Counter = Counter()
    for d in draws:
        for pos, n in enumerate(d.numbers, start=1):
            r = digital_root(n)
            per_pos.setdefault(pos, Counter())[r] += 1
            total_by_root[r] += 1
    out: list[dict] = []
    for r in ROOTS:
        fam = numbers_by_root(r)
        by_pos = {str(p): per_pos[p][r] for p in sorted(per_pos)}
        out.append({
            "root": r,
            "family": fam,
            "family_size": len(fam),
            "occurrences": total_by_root[r],
            "by_position": by_pos,
            "position_total": {str(p): sum(c.values()) for p, c in per_pos.items()},
        })
    return out


def transitions(draws: Sequence[Draw]) -> dict:
    """Root transition matrix between successive draws of the same game.

    For each consecutive pair of draws, every number of draw N is paired with
    every number of draw N+1 (25 pairs) and the root→root transition is counted.
    Returns the raw 9×9 matrix and conditional frequencies P(row|col) normalized
    per origin root, plus the number of observed transition pairs.
    """
    matrix = [[0] * 9 for _ in range(9)]
    total_pairs = 0
    for prev, nxt in zip(draws, draws[1:]):
        for pn in prev.numbers:
            pr = digital_root(pn)
            for nn in nxt.numbers:
                nr = digital_root(nn)
                matrix[pr][nr] += 1
                total_pairs += 1
    conditional = []
    for i in range(9):
        row_sum = sum(matrix[i])
        conditional.append([
            round(matrix[i][j] / row_sum, 4) if row_sum else 0.0
            for j in range(9)
        ])
    return {
        "matrix": matrix,
        "conditional": conditional,
        "total_pairs": total_pairs,
        "roots": list(ROOTS),
    }


def temporal_evolution(
    draws: Sequence[Draw], reference: date, windows: Sequence[int] = WINDOWS
) -> dict:
    """Nested-window comparison: per window, top root, share, and pp-change.

    Windows are nested (10 ⊂ 30 ⊂ 45 ⊂ 60 ⊂ 90) — results are NOT independent
    samples and must not be treated as such.
    """
    windows = tuple(windows)
    per_window = {}
    prev_top: dict[int, int] = {}
    prev_share: dict[int, float] = {}
    for w in windows:
        sub = filter_window(draws, reference, w)
        dist, total = global_distribution(sub)
        top = max(ROOTS, key=lambda r: dist[r]["count"]) if total else None
        share = (dist[top]["count"] / total * 100) if total and top is not None else 0.0
        changes = []
        for r in ROOTS:
            if r in prev_share:
                changes.append({
                    "root": r,
                    "from_pct": round(prev_share[r], 3),
                    "to_pct": dist[r]["percentage"],
                    "delta_pct": round(dist[r]["percentage"] - prev_share[r], 3),
                })
        per_window[str(w)] = {
            "days": w,
            "draws": len(sub),
            "numbers": total,
            "top_root": top,
            "top_share": round(share, 3),
            "distribution": dist,
            "changes": changes,
            "sufficient": total >= 30,  # arbitrary but explicit floor for readability
        }
        prev_top = {w: top}
        prev_share = {r: dist[r]["percentage"] for r in ROOTS}
    return {
        "windows": list(per_window.keys()),
        "nested": True,
        "note": "fenêtres imbriquées — ne pas traiter comme des échantillons indépendants",
        "per_window": per_window,
    }


def quality_report(draws: Sequence[Draw], reference: date) -> dict:
    """Data quality: duplicates, invalid dates, gaps, volume per window."""
    if not draws:
        return {"draw_count": 0, "duplicates": 0, "invalid_future": 0,
                "date_min": None, "date_max": None, "gaps": [], "windows": {}}
    seen: set[tuple[date, tuple[int, ...]]] = set()
    duplicates = 0
    for d in draws:
        key = (d.draw_date, d.numbers)
        if key in seen:
            duplicates += 1
        seen.add(key)
    invalid_future = sum(1 for d in draws if d.draw_date > reference)
    dates = sorted({d.draw_date for d in draws})
    gaps = []
    for a, b in zip(dates, dates[1:]):
        gap = (b - a).days - 1
        if gap > 0:
            gaps.append({"from": a.isoformat(), "to": b.isoformat(), "missing_days": gap})
    windows = {}
    for w in WINDOWS:
        sub = filter_window(draws, reference, w)
        windows[str(w)] = {"draws": len(sub), "numbers": sum(len(d.numbers) for d in sub)}
    return {
        "draw_count": len(draws),
        "duplicates": duplicates,
        "invalid_future": invalid_future,
        "date_min": dates[0].isoformat() if dates else None,
        "date_max": dates[-1].isoformat() if dates else None,
        "distinct_dates": len(dates),
        "gaps": gaps[:20],
        "gap_count": len(gaps),
        "windows": windows,
    }


def walkforward_validation(draws: Sequence[Draw]) -> dict:
    """Chronological walk-forward: predict each position's next root by the
    mode of the past window (per window size), evaluated on the following draw.

    Reference: uniform random root (1/9 ≈ 11.11 %). Strictly uses only past
    draws for each prediction. Returns per-position and per-window hit rates.
    """
    results: list[dict] = []
    for w in WINDOWS:
        hits_by_pos: Counter = Counter()
        trials_by_pos: Counter = Counter()
        for idx in range(1, len(draws)):
            past = draws[max(0, idx - w):idx]
            if len(past) < 5:
                continue
            # mode of each position over the past window
            pos_mode: dict[int, int] = {}
            for p in range(1, 6):
                cnt = Counter(digital_root(d.numbers[p - 1]) for d in past if len(d.numbers) >= p)
                if cnt:
                    pos_mode[p] = cnt.most_common(1)[0][0]
            cur = draws[idx]
            for p, pred in pos_mode.items():
                if len(cur.numbers) >= p:
                    trials_by_pos[p] += 1
                    if digital_root(cur.numbers[p - 1]) == pred:
                        hits_by_pos[p] += 1
        per_pos = {}
        total_hits = sum(hits_by_pos.values())
        total_trials = sum(trials_by_pos.values())
        for p in range(1, 6):
            t = trials_by_pos[p]
            per_pos[str(p)] = {
                "hits": hits_by_pos[p],
                "trials": t,
                "hit_rate": round(hits_by_pos[p] / t, 4) if t else None,
                "random_baseline": round(1 / 9, 4),
            }
        results.append({
            "window": w,
            "hits": total_hits,
            "trials": total_trials,
            "hit_rate": round(total_hits / total_trials, 4) if total_trials else None,
            "random_baseline": round(1 / 9, 4),
            "by_position": per_pos,
        })
    return {"results": results, "note": "mode de la racine par position, strictement antérieur"}


def compute_digital_root_statistics(
    conn: Any, draw_type_id: Any, draw_type_name: str, reference: date
) -> dict[str, Any]:
    """Orchestrate the full digital-root statistics payload for one game."""
    draws = load_draws(conn, draw_type_id, reference)
    quality = quality_report(draws, reference)
    evolution = temporal_evolution(draws, reference, WINDOWS)
    walkforward = walkforward_validation(draws)
    global_rows, global_total = global_distribution(draws)
    position = position_distribution(draws)
    families = family_stats(draws)
    trans = transitions(draws)
    signatures = draw_signatures(draws, limit=20)
    total_numbers = global_total
    return {
        "draw_type": draw_type_name,
        "reference_date": reference.isoformat(),
        "timezone": TIMEZONE,
        "convention": "racine numérique 9→0, classes 0..8 (10 numéros chacune)",
        "reference_freq_pct": round(REFERENCE_FREQ * 100, 3),
        "total_draws": len(draws),
        "total_numbers": total_numbers,
        "windows": list(map(str, WINDOWS)),
        "quality": quality,
        "global": global_rows,
        "position": position,
        "families": families,
        "transitions": trans,
        "evolution": evolution,
        "signatures": signatures,
        "walkforward": walkforward,
        "warning": (
            "échantillon insuffisant" if total_numbers < 30
            else "fréquences passées ≠ probabilités futures"
        ),
    }
