"""Tests des agents de paris virtuels (fusion_agents)."""

import random

from lottery_intelligence_platform import fusion_agents as fa
from lottery_intelligence_platform.fusion_agents import FUSION_AGENT_PROFILES


def _history(n=80, seed=1):
    rng = random.Random(seed)
    return [rng.sample(range(1, 91), 5) for _ in range(n)]


def test_all_profiles_produce_valid_decisions():
    history = _history()
    rng = random.Random(7)
    for profile in FUSION_AGENT_PROFILES:
        d = fa.decide(profile, history, rng, k=5)
        nums = d["selected_numbers"]
        assert len(nums) == 5, profile.code
        assert len(set(nums)) == 5, profile.code
        assert all(1 <= n <= 90 for n in nums), profile.code
        assert d["stake_amount"] > 0
        assert d["reasoning"]
        assert 0.0 <= d["confidence_score"] <= 1.0


def test_profiles_are_distinct_strategies():
    codes = {p.strategy for p in FUSION_AGENT_PROFILES}
    assert len(codes) == len(FUSION_AGENT_PROFILES)


def test_decisions_are_deterministic():
    history = _history()
    d1 = fa.decide(fa.get_profile("fusion_synergist"), history, random.Random(3))
    d2 = fa.decide(fa.get_profile("fusion_synergist"), history, random.Random(3))
    assert d1["selected_numbers"] == d2["selected_numbers"]


def test_random_baseline_is_uniform():
    history = _history()
    d = fa.decide(fa.get_profile("fusion_random"), history, random.Random(5))
    assert len(d["selected_numbers"]) == 5


def test_settle_bet_2n_boundaries():
    from decimal import Decimal
    # 2N (cote 240) : 2 matchs exacts -> gain 23900 ; 1 match -> perte
    win = fa.settle_bet("2N", [5, 10, 20, 30, 40], [5, 10, 90, 89, 88], Decimal("100"))
    assert win["status"] == "WIN" and win["net_profit"] == Decimal("23900")
    lose = fa.settle_bet("2N", [5, 11, 20, 30, 40], [5, 10, 90, 89, 88], Decimal("100"))
    assert lose["status"] == "LOSE" and lose["net_profit"] == Decimal("-100")


def test_bet_type_assigned():
    assert fa.get_profile("fusion_frequentist").bet_type == "2N"
    assert fa.get_profile("fusion_evolver").bet_type == "CHANCE_5_PLUS"
