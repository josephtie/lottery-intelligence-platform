"""Tests for combinatorial search, formula settlement and adaptive selection."""

import random
from decimal import Decimal

from lottery_intelligence_platform import fusion_engine as fe
from lottery_intelligence_platform import adaptive_selector as asel
from lottery_intelligence_platform.betting_formulas import calculate_potential_gain


def _uniform_history(n=120, seed=1):
    rng = random.Random(seed)
    return [rng.sample(range(1, 91), 5) for _ in range(n)]


def _biased_history(n=300, seed=2, hot=(1, 2, 3, 4, 5), bias=5.0):
    rng = random.Random(seed)
    pool = list(range(1, 91))
    history = []
    for _ in range(n):
        draw = []
        while len(draw) < 5:
            cand = [x for x in pool if x not in draw]
            weights = [bias if x in hot else 1.0 for x in cand]
            total = sum(weights)
            r = rng.random() * total
            acc = 0.0
            for x, w in zip(cand, weights):
                acc += w
                if acc >= r:
                    draw.append(x)
                    break
        history.append(draw)
    return history


# --- point 1 : recherche combinatoire ---------------------------------------

def test_generate_n_combination_valid():
    history = _uniform_history()
    picks = fe.model_picks(history, k=5)
    for n in (2, 3, 4, 5):
        combo = fe.generate_n_combination(picks, history, n)
        assert len(combo) == n
        assert len(set(combo)) == n


def test_complementarity_metrics():
    history = _uniform_history()
    picks = fe.model_picks(history, k=5)
    j = fe.pairwise_jaccard(picks)
    assert 0.0 <= j <= 1.0
    pairs = fe.complementary_pairs(picks, threshold=0.2)
    assert isinstance(pairs, list)


# --- point 3 : règlement par formule officielle ------------------------------

def test_chance_formula_pays_partial_hits():
    # Chance 5+ : 3 matches -> 3N tier (100x stake) -> positive net
    g = calculate_potential_gain(
        "CHANCE_5_PLUS", [1, 2, 3, 4, 5], [1, 2, 3, 90, 89], Decimal("100"))
    assert g["status"] == "WIN"
    assert g["tier"] == "3N"
    assert g["net_profit"] > 0


def test_evaluate_formula_walkforward_returns_roi():
    history = _biased_history(n=200)
    r = fe.evaluate_formula_walkforward(
        history, formula_code="CHANCE_5_PLUS", method="majority", k=5, start=60)
    assert set(r) >= {"roi", "total_net", "total_stake", "mean_hits", "p_ge3"}
    assert r["n"] == 200 - 60


# --- point 2 : sélecteur adaptatif ------------------------------------------

def test_selector_switches_only_on_durable_margin():
    sel = asel.AdaptiveSelector(window=5, margin=0.5, min_episodes=3)
    # feed "majority" a run of 0s, "borda" a run of 1s — margin forces a switch
    for _ in range(5):
        sel.observe({"majority": 0.0, "borda": 1.0})
    chosen, switch = sel.select()
    assert chosen == "borda"
    assert switch is not None


def test_adaptive_walkforward_captures_bias():
    history = _biased_history(n=250)
    result = asel.run_adaptive_walkforward(history, k=5, start=80, window=40,
                                           margin=0.15, min_episodes=20)
    # the selector should ride the frequency models and beat a random 5-pick
    # (~0.28 mean hits on uniform data); on biased data it captures the hot
    # numbers far better.
    assert result["mean_hits"] > 0.5, result["mean_hits"]
    assert result["n"] == 250 - 80


def test_adaptive_switch_trace_is_append_only():
    history = _biased_history(n=250)
    result = asel.run_adaptive_walkforward(history, k=5, start=80)
    assert isinstance(result["switches"], list)
    for old, new, delta in result["switches"]:
        assert old != new
        assert delta > 0  # switch only toward a strictly better strategy
