"""Tests for Benjamini-Hochberg correction (fusion_engine.benjamini_hochberg)."""

from lottery_intelligence_platform import fusion_engine as fe


def test_bh_known_values():
    # p=[0.01,0.02,0.5] -> q=[0.03,0.03,0.5]; only the two smallest survive q<0.10
    q = fe.benjamini_hochberg([("a", 0.01), ("b", 0.5), ("c", 0.02)])
    assert q["a"] == 0.03
    assert q["c"] == 0.03
    assert q["b"] == 0.5


def test_bh_monotonic_in_p():
    pvals = [(f"s{i}", p) for i, p in enumerate([0.001, 0.01, 0.04, 0.3, 0.9])]
    q = fe.benjamini_hochberg(pvals)
    # larger p -> q never smaller (q is monotone non-decreasing in p)
    by_p = sorted(pvals, key=lambda x: x[1])
    qs = [q[label] for label, _ in by_p]
    assert qs == sorted(qs)


def test_bh_no_rejection_on_uniform_noise():
    # uniform p-values = pure noise -> nothing survives q<0.10
    pvals = [(f"n{i}", 0.5) for i in range(20)]
    q = fe.benjamini_hochberg(pvals)
    assert all(v > 0.10 for v in q.values())


def test_bh_single_low_p_gets_heavily_penalized():
    # one "significant" p among many nulls is NOT declared a winner
    pvals = [("sig", 0.03)] + [(f"null{i}", 0.5) for i in range(29)]
    q = fe.benjamini_hochberg(pvals)
    # BH monotonicity is dragged by the trailing nulls: q[sig] = 0.5, far above 0.10
    assert q["sig"] == 0.5
