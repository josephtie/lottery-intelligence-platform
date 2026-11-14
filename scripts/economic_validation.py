"""Validation économique du signal de fréquence (paris 1N et 2N).

Protocole FIGÉ avant tout calcul :
  * stratégie = jouer les k numéros les plus fréquents sur les 60 derniers
    tirages (fenêtre unique, prédéfinie) — 1N (k=1, cote 10) et 2N (k=2,
    cote 240) ;
  * référence = k numéros aléatoires, mêmes mises et mêmes cotes ;
  * walk-forward strict (tirage i ne voit que les tirages < i) ;
  * split chronologique : développement = [0, N-200], holdout final = [N-200, N].

Règles officielles (lonaci.ci/loto_bonheur) :
  Gain = Mise × Coefficient.  1N cote 10, 2N cote 240, PN cote 40.
  Mise unitaire 25 FCFA, prix minimum 100 FCFA (on modélise 100 FCFA/pari).
"""

from __future__ import annotations

import argparse
import json
import os
import random as _random
import sys
from collections import Counter

import httpx

BASE = os.environ.get("PLATFORM_URL", "http://83.171.249.150:8095").rstrip("/")
TOKEN = os.environ.get("PLATFORM_TOKEN", "").strip()

STAKE = 100            # FCFA par pari
WINDOW = 60            # fenêtre de fréquence (tirages)
HOLDOUT = 200          # tirages finaux jamais utilisés pour ajuster
N_RANDOM = 200         # références aléatoires pour la distribution nulle

OFFICIAL_ODDS = {"1N": 10, "2N": 240, "PN": 40}


def load_history(draw_type: str) -> list[list[int]]:
    h = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    rows = httpx.get(f"{BASE}/api/draws",
                     params={"type": draw_type, "status": "SETTLED", "limit": 2000},
                     headers=h, timeout=60).json().get("data", [])
    hist = [sorted(int(x) for x in r["winning_numbers"]) for r in rows
            if r.get("winning_numbers") and r.get("validation_status") == "VALID"]
    hist.reverse()
    return hist


def top_k_frequent(past: list[list[int]], k: int) -> list[int]:
    """k most frequent numbers over the last WINDOW draws (tie-break: higher)."""
    recent = past[-WINDOW:]
    c = Counter(n for draw in recent for n in draw)
    return [n for n, _ in sorted(c.items(), key=lambda kv: (-kv[1], -kv[0]))][:k]


def settle(picked: list[int], winning: list[int], k: int, odds: int) -> int:
    """Net result of one bet (STAKE at stake). Win = exact k matches."""
    return STAKE * (odds - 1) if len(set(picked) & set(winning)) == k else -STAKE


def run_strategy(history, k, odds, start, *, random_mode=False, seed=0):
    nets = []
    for i in range(start, len(history)):
        if random_mode:
            rng = _random.Random(seed * 100000 + i)
            picked = rng.sample(range(1, 91), k)
        else:
            picked = top_k_frequent(history[:i], k)
        nets.append(settle(picked, history[i], k, odds))
    return nets


def metrics(nets: list[int]) -> dict:
    n = len(nets)
    total_stake = STAKE * n
    wins = sum(1 for x in nets if x > 0)
    total_net = sum(nets)
    roi = total_net / total_stake if total_stake else 0.0
    ev = total_net / n if n else 0.0

    # drawdown (cumulative equity)
    equity = 0
    peak = 0
    max_dd = 0.0
    for x in nets:
        equity += x
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    # bootstrap 95% CI on mean net (EV) and ROI
    _rng = _random.Random(42)
    evs, rois = [], []
    for _ in range(1000):
        s = [_rng.choice(nets) for _ in range(n)]
        sev = sum(s) / n
        evs.append(sev)
        rois.append(sum(s) / (STAKE * n))
    evs.sort(); rois.sort()
    return {
        "n": n,
        "total_stake": total_stake,
        "wins": wins,
        "win_rate": round(wins / n, 5) if n else 0.0,
        "total_net": total_net,
        "roi": round(roi, 4),
        "ev_per_bet": round(ev, 2),
        "ev_ci95": [round(evs[25], 2), round(evs[974], 2)],
        "roi_ci95": [round(rois[25], 4), round(rois[974], 4)],
        "max_drawdown": round(max_dd, 0),
    }


def evaluate_game(game: str, odds: dict[str, int], start: int = WINDOW + 1) -> dict:
    hist = load_history(game)
    n = len(hist)
    dev_nets = {"1N_freq": [], "2N_freq": [], "1N_rand": [], "2N_rand": []}
    hold_nets = {"1N_freq": [], "2N_freq": [], "1N_rand": [], "2N_rand": []}
    # random reference nets (averaged over N_RANDOM seeds) for the null
    rand_1n_means, rand_2n_means = [], []

    # full walk-forward for the frequency strategy
    freq_1n = run_strategy(hist, 1, odds["1N"], start)
    freq_2n = run_strategy(hist, 2, odds["2N"], start)

    split = n - HOLDOUT - start
    dev_nets["1N_freq"] = freq_1n[:split]
    dev_nets["2N_freq"] = freq_2n[:split]
    hold_nets["1N_freq"] = freq_1n[split:]
    hold_nets["2N_freq"] = freq_2n[split:]

    # random reference on the same draw indices
    for r in range(N_RANDOM):
        r1 = run_strategy(hist, 1, odds["1N"], start, random_mode=True, seed=r)
        r2 = run_strategy(hist, 2, odds["2N"], start, random_mode=True, seed=r)
        rand_1n_means.append(sum(r1) / len(r1))
        rand_2n_means.append(sum(r2) / len(r2))
        if r == 0:
            dev_nets["1N_rand"] = r1[:split]
            dev_nets["2N_rand"] = r2[:split]
            hold_nets["1N_rand"] = r1[split:]
            hold_nets["2N_rand"] = r2[split:]

    def pvalue(obs_ev, null_means):
        ge = sum(1 for m in null_means if m >= obs_ev)
        return round((1 + ge) / (N_RANDOM + 1), 4)

    out = {"game": game, "n_total": n, "n_evaluated": len(freq_1n),
           "split_dev": split, "holdout": len(freq_1n) - split}
    for phase, nets in (("dev", dev_nets), ("holdout", hold_nets)):
        for label, nn in nets.items():
            if not nn:
                continue
            m = metrics(nn)
            m["ev_pvalue"] = (pvalue(m["ev_per_bet"], rand_1n_means) if "1N" in label
                              else pvalue(m["ev_per_bet"], rand_2n_means))
            out[f"{phase}:{label}"] = m
    out["null_1n_ev_mean"] = round(sum(rand_1n_means) / N_RANDOM, 2)
    out["null_2n_ev_mean"] = round(sum(rand_2n_means) / N_RANDOM, 2)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", nargs="*", default=["Digital 21h", "Digital 23h"])
    ap.add_argument("--out", default="reports/economic_validation.json")
    args = ap.parse_args()

    results = [evaluate_game(g, OFFICIAL_ODDS) for g in args.games]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"stake": STAKE, "window": WINDOW, "holdout": HOLDOUT,
                   "odds": OFFICIAL_ODDS, "games": results}, f, indent=2)
    print(f"[ok] {args.out}")

    for r in results:
        print(f"\n===== {r['game']} (n={r['n_evaluated']}, dev={r['split_dev']}, holdout={r['holdout']}) =====")
        print(f"  null EV/pari (random): 1N={r['null_1n_ev_mean']} F, 2N={r['null_2n_ev_mean']} F")
        for phase in ("dev", "holdout"):
            print(f"  -- {phase} --")
            for label in ("1N_freq", "1N_rand", "2N_freq", "2N_rand"):
                key = f"{phase}:{label}"
                if key not in r:
                    continue
                m = r[key]
                print(f"    {label:8s} n={m['n']:4d} wins={m['win_rate']*100:6.2f}% "
                      f"EV={m['ev_per_bet']:7.2f} F  ROI={m['roi']*100:7.1f}%  "
                      f"IC95_EV={m['ev_ci95']}  dd={m['max_drawdown']:.0f}  p={m['ev_pvalue']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
