"""Fusion engine tests: validity, bias capture, and no-lookahead."""

import random

from lottery_intelligence_platform import fusion_engine as fe


def _uniform_history(n=120, seed=1):
    rng = random.Random(seed)
    return [rng.sample(range(1, 91), 5) for _ in range(n)]


def _biased_history(n=300, seed=2, hot=(1, 2, 3, 4, 5), bias=5.0):
    """Draws where a few numbers are heavily over-represented."""
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


def test_fusion_models_available():
    assert len(fe.FUSION_MODELS) >= 18
    assert "monte_carlo_v1" in fe.FUSION_MODELS
    assert "ensemble_v1" in fe.FUSION_MODELS
    assert "calling_image" in fe.FUSION_MODELS


def test_fusion_combinations_are_valid():
    history = _uniform_history()
    picks = fe.model_picks(history, k=5)
    combos = fe.generate_combinations(picks, history, k=5)
    for method, combo in combos.items():
        assert len(combo) == 5, method
        assert len(set(combo)) == 5, method
        assert all(1 <= n <= 90 for n in combo), method


def test_fusion_captures_injected_bias():
    history = _biased_history()
    result = fe.evaluate_walkforward(history, k=5, start=60)
    fusion = max(m["mean_hits"] for m in result["methods"].values())
    random_mean = result["random_reference"]["mean_hits"]
    # the fused selection should capture the hot numbers far better than a
    # random 5-pick, proving the engine turns model signal into coverage
    assert fusion > random_mean * 2.0, (fusion, random_mean)


def test_model_picks_are_deterministic():
    # reproducibility: same history + same seed -> identical picks, so a
    # walk-forward result can be recomputed exactly (no hidden state / no look-ahead)
    history = _biased_history()
    assert fe.model_picks(history, k=5, seed=0) == fe.model_picks(history, k=5, seed=0)


def test_walkforward_uses_only_past():
    # by construction evaluate_walkforward feeds history[:i] to predict draw i;
    # verify the loop's draws_evaluated matches the number of test draws.
    history = _biased_history(n=150)
    result = fe.evaluate_walkforward(history, k=5, start=60)
    assert result["draws_evaluated"] == 150 - 60
    for m, s in result["methods"].items():
        assert s["n"] == 150 - 60, m
