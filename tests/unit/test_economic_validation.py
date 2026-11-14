"""Tests économiques : cotes officielles, cas limites de paiement, plausibilité RTP."""

from decimal import Decimal

from lottery_intelligence_platform.betting_formulas import (
    STANDARD_FORMULAS,
    calculate_potential_gain,
)
from lottery_intelligence_platform.fusion_engine import benjamini_hochberg


def test_official_odds_1n_2n_pn():
    assert STANDARD_FORMULAS["1N"].odds["1N"] == Decimal("10")
    assert STANDARD_FORMULAS["2N"].odds["2N"] == Decimal("240")
    assert STANDARD_FORMULAS["PN"].odds["PN"] == Decimal("40")


def test_1n_payout_exact_match():
    # 1 number picked, 1 among the 5 winners -> net = 100*10 - 100 = 900
    g = calculate_potential_gain("1N", [5], [5, 10, 20, 30, 40], Decimal("100"))
    assert g["status"] == "WIN" and g["net_profit"] == Decimal("900")


def test_1n_payout_miss():
    g = calculate_potential_gain("1N", [6], [5, 10, 20, 30, 40], Decimal("100"))
    assert g["status"] == "LOSE" and g["net_profit"] == Decimal("-100")


def test_2n_payout_exact_and_partial():
    # exact 2 matches -> net 100*240 - 100 = 23900
    g = calculate_potential_gain("2N", [5, 10], [5, 10, 20, 30, 40], Decimal("100"))
    assert g["status"] == "WIN" and g["net_profit"] == Decimal("23900")
    # only 1 match -> exact match required, LOSE
    g = calculate_potential_gain("2N", [5, 11], [5, 10, 20, 30, 40], Decimal("100"))
    assert g["status"] == "LOSE" and g["net_profit"] == Decimal("-100")


def test_rtp_below_one_all_standard():
    # plausibility control: odds * P(exact k) must be < 1 for every standard bet
    from math import comb
    for code, f in STANDARD_FORMULAS.items():
        if code == "PN":
            p = 1 / 90  # exact first position
            rtp = float(f.odds["PN"]) * p
        else:
            k = f.numbers_required
            p = comb(5, k) / comb(90, k)
            rtp = float(f.odds[f"{k}N"]) * p
        assert rtp < 1.0, f"{code} RTP {rtp:.3f} >= 1 (cote fausse)"


def test_bh_holds_on_economic_pvalues():
    # a couple of "significant" p-values among noise stay non-significant after FDR
    q = benjamini_hochberg([("a", 0.02), ("b", 0.05), ("c", 0.4), ("d", 0.6), ("e", 0.8)])
    # smallest q = 0.02*5/1 = 0.10 -> boundary; none clearly below 0.10 except tie
    assert q["a"] <= 0.10
