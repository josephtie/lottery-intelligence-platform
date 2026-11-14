#!/usr/bin/env python3
"""Holdout final : valider top_k_frequency / bayesian_shrinkage sur les 200
derniers tirages de digital_21h (jamais utilisés pour sélectionner le modèle).

Split chronologique strict :
  * développement = tirages [0, N-200] (déjà explorés -> candidat = fréquence)
  * holdout final = tirages [N-200, N] (jamais vus, walk-forward pur)
"""
import os
import random as _random
import httpx

from lottery_intelligence_platform import fusion_engine as fe

BASE = "http://83.171.249.150:8095"
TOKEN = os.environ.get("PLATFORM_TOKEN", "").strip()

def load(draw_type):
    h = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
    rows = httpx.get(f"{BASE}/api/draws", params={"type": draw_type, "status": "SETTLED", "limit": 2000},
                     headers=h, timeout=60).json().get("data", [])
    hist = [sorted(int(x) for x in r["winning_numbers"]) for r in rows if r.get("winning_numbers")]
    hist.reverse()
    return hist

def hits(pred, win):
    return len(set(pred) & set(win))

HOLDOUT = 200
N_RANDOM = 200

for game, candidates in [("Digital 21h", ["top_k_frequency", "bayesian_shrinkage"]),
                         ("Digital 23h", ["top_k_frequency", "bayesian_shrinkage"])]:
    hist = load(game)
    n = len(hist)
    dev, hold = hist[:n - HOLDOUT], hist[n - HOLDOUT:]
    print(f"\n===== {game}: {n} tirages | dev={len(dev)} | HOLDOUT final={len(hold)} =====")
    for code in candidates:
        fn = fe.FUSION_MODELS[code]
        hs = []
        for i in range(n - HOLDOUT, n):
            rng = _random.Random(i)
            pred = fn(hist[:i], rng, 5)
            hs.append(hits(pred, hold[i - (n - HOLDOUT)]))
        mean = sum(hs) / len(hs)
        # reference random on the SAME holdout draws
        rand = []
        for r in range(N_RANDOM):
            rh = []
            for j, win in enumerate(hold):
                rng = _random.Random((n - HOLDOUT + j) * 100000 + r)
                rh.append(hits(rng.sample(range(1, 91), 5), win))
            rand.append(sum(rh) / len(rh))
        p = (1 + sum(1 for m in rand if m >= mean)) / (N_RANDOM + 1)
        print(f"  {code:20s} holdout_hits={mean:.4f}  lift={mean-0.2778:+.4f}  "
              f"p(perm, unilatéral)={p:.3f}  random_mean={sum(rand)/len(rand):.4f}")
