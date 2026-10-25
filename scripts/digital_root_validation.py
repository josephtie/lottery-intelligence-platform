"""Validation walk-forward des racines numériques — signal exploitable ou description du passé ?

Pour chaque jeu et fenêtre (10/30/45/60/90), on prédit la racine suivante par le
**mode** de la fenêtre strictement antérieure (aucune donnée future), on mesure le
taux de coïncidence, on le compare au hasard uniforme (1/9) par un **test binomial
unilatéral exact**, et on corrige les comparaisons multiples par **FDR
(Benjamini-Hochberg)** sur l'ensemble des tests (jeux × fenêtres × positions).

Sortie : statistiques descriptives réelles + performance prédictive + verdict.
"""

from __future__ import annotations

import math
import os
from collections import Counter
from datetime import date
from typing import Any

import psycopg

from lottery_intelligence_platform import digital_root_statistics as drs
from lottery_intelligence_platform.digital_root import digital_root
from lottery_intelligence_platform.fusion_engine import benjamini_hochberg

BASELINE = 1 / 9
WINDOWS = (10, 30, 45, 60, 90)
MIN_DRAWS = 100  # un jeu avec moins de tirages n'est pas analysé


def binomial_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) sous Binomial(n, p), unilatéral droit exact (log-gamma)."""
    if k > n:
        return 0.0
    if k <= 0:
        return 1.0
    logp = math.log(p)
    logq = math.log1p(-p)
    total = 0.0
    for i in range(k, n + 1):
        lp = (math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
              + i * logp + (n - i) * logq)
        total += math.exp(lp)
        if total > 1.0:
            total = 1.0
            break
    return total


def walkforward_by_position(draws: list[drs.Draw], window: int):
    """Mode de la racine par position sur la fenêtre passée, évalué sur le tirage suivant."""
    hits_by_pos: Counter = Counter()
    trials_by_pos: Counter = Counter()
    for idx in range(1, len(draws)):
        past = draws[max(0, idx - window):idx]
        if len(past) < 5:
            continue
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
    return hits_by_pos, trials_by_pos


def connect() -> psycopg.Connection:
    host = os.environ.get("LOTTERY_DATABASE_HOST", "localhost")
    port = int(os.environ.get("LOTTERY_DATABASE_PORT", "5432"))
    db = os.environ.get("LOTTERY_DATABASE_NAME", "lottery_platform")
    user = os.environ.get("LOTTERY_DATABASE_USER", "directus")
    pw = os.environ.get("LOTTERY_DATABASE_PASSWORD") or os.environ.get("PGPASSWORD")
    dsn = f"host={host} port={port} dbname={db} user={user}"
    if pw:
        dsn += f" password={pw}"
    return psycopg.connect(dsn)


def main() -> int:
    reference = date.today()
    conn = connect()
    games = conn.execute(
        """SELECT dt.draw_type_id, dt.display_name,
                  (SELECT count(*) FROM core.draws d WHERE d.draw_type_id = dt.draw_type_id
                   AND d.status = 'SETTLED') AS settled
           FROM catalog.draw_types dt
           WHERE (SELECT count(*) FROM core.draws d WHERE d.draw_type_id = dt.draw_type_id
                  AND d.status = 'SETTLED') >= %s
           ORDER BY settled DESC""",
        (MIN_DRAWS,),
    ).fetchall()

    # accumulateurs pour le FDR global
    all_tests: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []

    for draw_type_id, name, settled in games:
        draws = drs.load_draws(conn, draw_type_id, reference)
        if len(draws) < MIN_DRAWS:
            continue
        # Statistiques descriptives réelles sur les 5 fenêtres
        desc = {}
        for w in WINDOWS:
            sub = drs.filter_window(draws, reference, w)
            dist, total = drs.global_distribution(sub)
            top = max(drs.ROOTS, key=lambda r: dist[r]["count"]) if total else None
            desc[str(w)] = {
                "draws": len(sub),
                "numbers": total,
                "top_root": top,
                "top_pct": round(dist[top]["percentage"], 2) if total and top is not None else None,
                "top_deviation": round(dist[top]["deviation_pct"], 2) if total and top is not None else None,
            }
        # Walk-forward + test binomial
        wf = {}
        for w in WINDOWS:
            hits_by_pos, trials_by_pos = walkforward_by_position(draws, w)
            hits_total = sum(hits_by_pos.values())
            trials_total = sum(trials_by_pos.values())
            p_global = binomial_sf(hits_total, trials_total, BASELINE) if trials_total else None
            by_pos = {}
            for p in range(1, 6):
                h, t = hits_by_pos[p], trials_by_pos[p]
                pv = binomial_sf(h, t, BASELINE) if t else None
                by_pos[str(p)] = {"hits": h, "trials": t, "p": pv}
                all_tests.append({"game": name, "window": w, "position": p,
                                  "hits": h, "trials": t, "p": pv,
                                  "label": f"{name}|{w}|pos{p}"})
            wf[str(w)] = {
                "hits": hits_total, "trials": trials_total,
                "hit_rate": round(hits_total / trials_total, 4) if trials_total else None,
                "p_global": p_global,
                "by_position": by_pos,
            }
            all_tests.append({"game": name, "window": w, "position": None,
                              "hits": hits_total, "trials": trials_total, "p": p_global,
                              "label": f"{name}|{w}|global"})
        report.append({"game": name, "settled": settled, "draws": len(draws),
                       "descriptive": desc, "walkforward": wf})

    # FDR (Benjamini-Hochberg) sur tous les tests
    labeled = [(t["label"], t["p"]) for t in all_tests if t["p"] is not None]
    qmap = benjamini_hochberg(labeled) if labeled else {}
    sig = 0
    for t in all_tests:
        if t["p"] is not None:
            t["q"] = qmap[t["label"]]
            if t["q"] < 0.10:
                sig += 1

    # Verdict
    print("=" * 78)
    print("RACINES NUMÉRIQUES — validation walk-forward (mode par position, fenêtre passée)")
    print(f"Référence aléatoire : 1/9 = {BASELINE:.4f} · tests unilatéraux · FDR Benjamini-Hochberg")
    print(f"Jeux analysés : {len(report)} · tests au total : {len(all_tests)} · significatifs (q<0.10) : {sig}")
    print("=" * 78)

    for g in report:
        print(f"\n### {g['game']} — {g['draws']} tirages (settled {g['settled']})")
        print("  Statistiques descriptives (racine dominante par fenêtre) :")
        for w in WINDOWS:
            d = g["descriptive"][str(w)]
            print(f"    {w:>2}j : tirages={d['draws']:>4}  top_racine={d['top_root']}  "
                  f"part={d['top_pct']}%  écart={d['top_deviation']:+}pt")
        print("  Prédiction walk-forward (mode → tirage suivant) :")
        for w in WINDOWS:
            r = g["walkforward"][str(w)]
            hr = (r["hit_rate"] * 100) if r["hit_rate"] is not None else None
            print(f"    {w:>2}j : {r['hits']:>4}/{r['trials']:<5} "
                  f"taux={hr:.1f}% (hasard 11.1%)  p={r['p_global']:.3f}")
        # meilleure position par fenêtre
        best = None
        for w in WINDOWS:
            for p, d in g["walkforward"][str(w)]["by_position"].items():
                if d["p"] is not None and (best is None or d["p"] < best[0]):
                    best = (d["p"], w, p, d["hits"], d["trials"])
        if best:
            pv, w, p, h, t = best
            print(f"    meilleure position isolée : fenêtre {w}j, position {p} — "
                  f"{h}/{t} p={pv:.3f} (avant FDR)")

    print("\n" + "=" * 78)
    if sig == 0:
        print("VERDICT : aucun test ne survit au FDR — les racines numériques sont")
        print("une description du passé, PAS un signal prédictif exploitable.")
    else:
        print(f"VERDICT : {sig} test(s) significatif(s) après FDR — à examiner.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
