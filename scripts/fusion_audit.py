"""Multi-game audit of fusion value vs an equivalent random reference.

Answers, with evidence: can the platform models' predictions be *assembled*
into combinations that beat an equivalent random picker out-of-sample?

Method (all reproducible, no look-ahead):
  * walk-forward per game: at draw i only draws < i are seen;
  * strategies = 3 fusion methods + every single model + coverage (theoretical
    union of ALL model picks) + adaptive selector;
  * null = N_RANDOM equivalent random 5-picks over the SAME draws;
  * p-value = permutation share of the null >= the strategy's mean hits;
  * FDR (Benjamini-Hochberg) over the whole strategy x game family;
  * half/half replication for stability, never used to pick a winner.

Baselines (audit §1): one 5-pick against a 5-number draw out of 90 is
hypergeometric.  E[hits] = 5*5/90 = 0.2778.  P(h>=3) = P(3)+P(4)+P(5)
= [C(5,3)C(85,2)+C(5,4)C(85,1)+C(5,5)]/C(90,5) = 0.000822 = 0.0822%
(~1 in 1217 draws).  On N draws the null expects ~N*0.000822 ">=3 hits".
"""

from __future__ import annotations

import argparse
import json
import os
import random as _random
import sys
from collections import defaultdict
from statistics import mean

import httpx

from lottery_intelligence_platform import adaptive_selector as asel
from lottery_intelligence_platform import fusion_engine as fe

BASE = os.environ.get("PLATFORM_URL", "http://83.171.249.150:8095").rstrip("/")
TOKEN = os.environ.get("PLATFORM_TOKEN", "").strip()

# ordered by settled volume (from /api/lab/draw-types)
GAMES = [
    "digital_21h", "digital_23h", "digital_reveil_8h", "digital_22h",
    "benediction", "cash", "espoir", "fortune_thursday", "afterwork",
]

K = 5
N_RANDOM = 200          # equivalent random references for the null
WINDOW = 500            # max most-recent draws evaluated per game
MIN_START = 40          # minimum warm-up for the models
SELECTOR = dict(window=40, margin=0.15, min_episodes=20)

E_HITS = 5.0 * 5.0 / 90.0          # 0.2778
P_GE3 = 0.000822                   # 0.0822 %


def hit_count(pred, winning):
    return len(set(pred) & set(winning))


def load_draw_types() -> dict[str, str]:
    h = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    r = httpx.get(f"{BASE}/api/lab/draw-types", headers=h, timeout=30)
    r.raise_for_status()
    return {d["code"]: d["display_name"] for d in r.json().get("data", [])}


_DRAW_TYPES: dict[str, str] | None = None


def _get_draw_types() -> dict[str, str]:
    global _DRAW_TYPES
    if _DRAW_TYPES is None:
        _DRAW_TYPES = load_draw_types()
    return _DRAW_TYPES


def load_history(draw_type: str) -> list[list[int]]:
    h = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    display = _get_draw_types().get(draw_type, draw_type)
    r = httpx.get(f"{BASE}/api/draws",
                  params={"type": display, "status": "SETTLED", "limit": 2000},
                  headers=h, timeout=60)
    r.raise_for_status()
    rows = r.json().get("data", [])
    hist = [sorted(int(x) for x in row["winning_numbers"]) for row in rows
            if row.get("winning_numbers") and row.get("validation_status") == "VALID"]
    hist.reverse()  # chronological
    return hist


def evaluate_game(draw_type: str, window: int = WINDOW) -> dict:
    hist = load_history(draw_type)
    if len(hist) < MIN_START + 20:
        return {"game": draw_type, "skipped": True, "n_draws": len(hist)}
    start = max(MIN_START, len(hist) - window)
    idx = range(start, len(hist))

    per: dict[str, list[int]] = defaultdict(list)
    rand_refs: list[list[int]] = [[] for _ in range(N_RANDOM)]
    selector = asel.AdaptiveSelector(**SELECTOR)
    sel_hits: list[int] = []

    for i in idx:
        past = hist[:i]
        winning = set(hist[i])
        picks = fe.model_picks(past, K)
        combos = fe.generate_combinations(picks, past, K, fe.FUSION_METHODS)

        draw_hits: dict[str, int] = {}
        for m, combo in combos.items():
            h = hit_count(combo, winning)
            per[f"fusion:{m}"].append(h)
            draw_hits[f"fusion:{m}"] = h
        cover: set = set()
        for code, p in picks.items():
            h = hit_count(p, winning)
            per[f"model:{code}"].append(h)
            draw_hits[f"model:{code}"] = h
            cover |= set(p)
        # coverage = theoretical union of ALL model picks (~40 numbers) — a
        # metric, NOT a playable 5-number strategy. Never offered to the
        # selector (it would trivially "win" by picking the union).
        per["coverage"].append(len(cover & winning))

        chosen, _ = selector.select()
        sel_hits.append(draw_hits.get(chosen, 0))
        selector.observe(draw_hits)

        for r in range(N_RANDOM):
            rng = _random.Random(i * 100000 + r)
            rand_refs[r].append(hit_count(rng.sample(range(1, 91), K), winning))

    n = len(idx)
    rand_means = [mean(rand_refs[r]) for r in range(N_RANDOM)]

    def half_mean(hits):
        if not hits:
            return None
        m = len(hits) // 2
        return round(mean(hits[:m]), 4), round(mean(hits[m:]), 4)

    def pvalue(obs_mean: float) -> float:
        # one-sided permutation p: share of null means >= observed
        ge = sum(1 for rm in rand_means if rm >= obs_mean)
        return round((1 + ge) / (N_RANDOM + 1), 4)

    strategies = {}
    for label, hits in per.items():
        obs = mean(hits)
        strategies[label] = {
            "n": n,
            "mean_hits": round(obs, 4),
            "lift_vs_random": round(obs - E_HITS, 4),
            "p": pvalue(obs),
            "p_ge3_obs": round(sum(1 for h in hits if h >= 3) / n, 4),
            "half": half_mean(hits),
        }
    strategies["selector"] = {
        "n": n,
        "mean_hits": round(mean(sel_hits), 4),
        "lift_vs_random": round(mean(sel_hits) - E_HITS, 4),
        "p": pvalue(mean(sel_hits)),
        "p_ge3_obs": round(sum(1 for h in sel_hits if h >= 3) / n, 4),
        "half": half_mean(sel_hits),
        "switches": selector.switches,
    }

    return {
        "game": draw_type,
        "n_draws_total": len(hist),
        "n_evaluated": n,
        "first_date": None,
        "last_date": None,
        "strategies": strategies,
        "random_mean": round(mean(rand_means), 4),
        "random_sd": round(_pstdev(rand_means), 4),
        "expected_hits_null": E_HITS,
        "expected_ge3_per_1000": round(P_GE3 * 1000, 3),
    }


def _pstdev(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5


def classify(p, q, lift, n):
    if lift > 0 and q < 0.10:
        return "AVANTAGE À CONFIRMER"
    if n < 100:
        return "indéterminé (n<100)" if lift > 0 else "≤ référence"
    if lift <= 0:
        return "≤ référence"
    return "compatible hasard"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", nargs="*", default=None)
    ap.add_argument("--window", type=int, default=WINDOW)
    ap.add_argument("--out", default="reports/fusion_audit.json")
    args = ap.parse_args()

    games = args.games or GAMES
    results = []
    all_pvals: list[tuple[str, float]] = []
    for g in games:
        print(f"[audit] {g} …", file=sys.stderr)
        res = evaluate_game(g, window=args.window)
        if res.get("skipped"):
            results.append(res)
            continue
        results.append(res)
        for label, s in res["strategies"].items():
            all_pvals.append((f"{g}::{label}", s["p"]))
    qvals = fe.benjamini_hochberg(all_pvals)

    # annotate + classify
    for res in results:
        if res.get("skipped"):
            continue
        for label, s in res["strategies"].items():
            key = f"{res['game']}::{label}"
            s["q"] = qvals.get(key, 1.0)
            s["verdict"] = classify(s["p"], s["q"], s["lift_vs_random"], s["n"])
            if label == "coverage":
                s["verdict"] = "métrique théorique (union des picks, injouable)"

    report = {
        "baselines": {
            "E_hits_null": E_HITS,
            "P_ge3": P_GE3,
            "P_ge3_per_1000_draws": round(P_GE3 * 1000, 3),
            "note": "5 picks vs 5-number draw out of 90, hypergeometric",
        },
        "n_random": N_RANDOM,
        "games": results,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[ok] rapport écrit : {args.out}", file=sys.stderr)

    _print_report(report)
    return 0


def _print_report(report):
    print("\n" + "=" * 78)
    print("AUDIT MULTI-JEUX — valeur des fusions vs référence aléatoire équivalente")
    print("=" * 78)
    b = report["baselines"]
    print(f"Null: E[hits]= {b['E_hits_null']:.4f}  |  P(≥3 hits)= {b['P_ge3']*100:.4f}% "
          f"(≈ {b['P_ge3_per_1000_draws']}/1000 tirages)  |  {report['n_random']} références aléatoires")
    print()

    for res in report["games"]:
        if res.get("skipped"):
            print(f"### {res['game']} — SKIPPED ({res['n_draws']} tirages)")
            continue
        print(f"### {res['game']} — {res['n_evaluated']} tirages évalués "
              f"(total {res['n_draws_total']}) | random mean {res['random_mean']:.4f} ± {res['random_sd']:.4f}")
        rows = sorted(res["strategies"].items(),
                      key=lambda kv: kv[1]["mean_hits"], reverse=True)
        for label, s in rows:
            half = s.get("half")
            h = f"{half[0]}/{half[1]}" if half else "-"
            flag = " <=" if s["lift_vs_random"] <= 0 else ""
            print(f"  {label:24s} hits={s['mean_hits']:.4f}  lift={s['lift_vs_random']:+.4f}{flag} "
                  f" p={s['p']:.3f} q={s['q']:.3f}  P(≥3)={s['p_ge3_obs']:.4%}  "
                  f"moitiés={h}  [{s['verdict']}]")
        print()


if __name__ == "__main__":
    sys.exit(main())
