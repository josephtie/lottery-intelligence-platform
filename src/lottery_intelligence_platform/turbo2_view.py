"""Turbo 2 per-game history view — read-only observation layer.

Everything served here is already SEALED by the settlement engine:
``research.prediction_outcomes.metrics->turbo->turbo_2`` carries the
official verdict (hit, stake 100 FCFA, multiplier 2400, payout, net).
This module only reshapes sealed rows into week/day/model aggregates.
It never recomputes a hit, never replays a prediction, never mixes games.

Rule reminder (settlement.py): Turbo 2 HIT = both predicted numbers appear
among the first 2 positions of the ordered winning result (set membership,
not exact positional order). ``positional_hits.first_2`` counts how many of
the predicted numbers landed inside those 2 positions.
"""

from __future__ import annotations

from typing import Any

MIN_MODEL_SAMPLE = 10  # below this a model line gets the weak-sample badge


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """KPI block over a subset of sealed rows."""
    bets = len(rows)
    hits = sum(1 for r in rows if r["turbo2_hit"])
    stake = sum(r["stake"] for r in rows)
    gross = sum(r["gross"] for r in rows)
    net = sum(r["net"] for r in rows)
    return {
        "bets": bets,
        "hits": hits,
        "losses": bets - hits,
        "hit_rate": round(hits / bets, 4) if bets else None,
        "total_stake": stake,
        "gross": gross,
        "net": net,
        "roi": round(net / stake, 4) if stake else None,  # None -> "N/A"
    }


def _streaks(rows: list[dict[str, Any]]) -> dict[str, int | None]:
    """Best hit streak / worst loss streak over chronological rows."""
    best_hit = best_loss = cur_hit = cur_loss = 0
    last_hit = None
    for r in rows:
        if r["turbo2_hit"]:
            cur_hit += 1
            cur_loss = 0
            last_hit = r["date"]
        else:
            cur_loss += 1
            cur_hit = 0
        best_hit = max(best_hit, cur_hit)
        best_loss = max(best_loss, cur_loss)
    return {"best_hit_streak": best_hit, "worst_loss_streak": best_loss,
            "last_hit_date": last_hit}


def turbo2_history(connection: Any, draw_type_id: Any) -> dict[str, Any]:
    """All sealed Turbo 2 outcomes for ONE game, chronological, plus
    weekly / weekday / per-model aggregates computed from the same rows."""
    game = connection.execute(
        "SELECT display_name FROM catalog.draw_types WHERE draw_type_id = %s",
        (draw_type_id,),
    ).fetchone()
    if not game:
        return {"error": "unknown draw_type"}

    raw = connection.execute(
        """SELECT o.outcome_id, d.scheduled_date, d.scheduled_sequence,
                  mv.code AS model_code,
                  o.predicted_numbers, o.winning_numbers, o.hit_count,
                  o.positional_hits,
                  o.metrics -> 'turbo' -> 'turbo_2' AS t2,
                  o.settled_at, p.locked_at
           FROM research.prediction_outcomes o
           JOIN research.predictions p ON p.prediction_id = o.prediction_id
           JOIN research.model_versions mv
             ON mv.model_version_id = p.model_version_id
           JOIN core.draws d ON d.draw_id = o.draw_id
           WHERE d.draw_type_id = %s
             AND o.metrics -> 'turbo' -> 'turbo_2' IS NOT NULL
           ORDER BY d.scheduled_date, d.scheduled_sequence, mv.code""",
        (draw_type_id,),
    ).fetchall()

    raw = sorted(raw, key=lambda r: (r[1], r[2], r[3]))
    rows: list[dict[str, Any]] = []
    for (oid, dt_date, seq, model, predicted, winning, hit_count,
         pos_hits, t2, settled_at, locked_at) in raw:
        iso = dt_date.isocalendar()
        rows.append({
            "outcome_id": str(oid),
            "date": dt_date.isoformat(),
            "iso_week": f"{iso.year}-W{iso.week:02d}",
            "weekday": dt_date.isoweekday() - 1,  # 0 = lundi
            "sequence": seq,
            "model": model,
            "predicted": predicted,
            "winning": winning,
            "winning_first2": winning[:2] if winning else [],
            "hits_first2": (pos_hits or {}).get("first_2"),
            "hit_count": hit_count,
            "turbo2_hit": bool(t2["hit"]),
            "stake": float(t2["stake"]),
            "gross": float(t2["payout"]),
            "net": float(t2["net"]),
            "multiplier": float(t2["multiplier"]),
            "settled_at": settled_at.isoformat() if settled_at else None,
            "locked_at": locked_at.isoformat() if locked_at else None,
        })

    # --- aggregates -------------------------------------------------------
    def by(key: str) -> dict[Any, list[dict[str, Any]]]:
        out: dict[Any, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(r[key], []).append(r)
        return out

    weekly = [{"iso_week": w, **_aggregate(rs)} for w, rs in sorted(by("iso_week").items())]
    daily = [{"weekday": d, **_aggregate(rs)} for d, rs in sorted(by("weekday").items())]
    models = []
    for m, rs in sorted(by("model").items()):
        agg = _aggregate(rs)
        agg["model"] = m
        agg.update(_streaks(rs))
        agg["sample_level"] = "adequate" if agg["bets"] >= MIN_MODEL_SAMPLE \
            else "weak"  # -> badge ÉCHANTILLON FAIBLE
        models.append(agg)

    return {
        "game": game[0],
        "rule": {
            "variant": "turbo_2",
            "positions": 2,
            "multiplier": 2400.0,
            "stake": 100.0,
            "definition": "les 2 numéros prédits figurent parmi les 2 "
                          "premières positions du résultat officiel",
        },
        "kpis": _aggregate(rows),
        "n_draws": len({r["date"] for r in rows}),
        "weeks": sorted(by("iso_week")),
        "rows": rows,
        "weekly": weekly,
        "daily": daily,
        "models": models,
    }
