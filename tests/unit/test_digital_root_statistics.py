from datetime import date, timedelta

from lottery_intelligence_platform import digital_root_statistics as drs
from lottery_intelligence_platform.digital_root import digital_root, numbers_by_root


def _draws():
    """Deterministic set of draws spanning ~100 days for window tests."""
    out = []
    base = date(2026, 10, 25)
    # 5 numbers each, positions 1..5, over 100 distinct dates (gaps included)
    seq = [
        (74, 84, 12, 29, 10),
        (45, 86, 3, 21, 66),
        (9, 18, 27, 36, 90),
        (1, 10, 19, 28, 37),
        (2, 11, 20, 29, 38),
        (3, 12, 21, 30, 39),
        (4, 13, 22, 31, 40),
        (5, 14, 23, 32, 41),
        (6, 15, 24, 33, 42),
        (7, 16, 25, 34, 43),
    ]
    for i in range(60):
        nums = seq[i % len(seq)]
        out.append(drs.Draw(f"d{i}", base - timedelta(days=i), nums))
    return out


def test_convention_examples():
    assert [digital_root(n) for n in (74, 84, 12, 29, 10, 45, 86)] == [2, 3, 3, 2, 1, 0, 5]
    # 9 → 0
    assert digital_root(9) == 0
    assert digital_root(90) == 0


def test_nine_classes_only():
    for n in range(1, 91):
        assert digital_root(n) in range(9)


def test_each_root_covers_ten_numbers():
    for r in range(9):
        assert len(numbers_by_root(r)) == 10


def test_roots_of_preserves_position():
    assert drs.roots_of((74, 84, 12, 29, 10)) == (2, 3, 3, 2, 1)


def test_filter_window_inclusive_bounds():
    draws = _draws()
    ref = date(2026, 10, 25)
    sub = drs.filter_window(draws, ref, 10)
    # inclusive [ref-10, ref] → 11 calendar days max
    assert all(ref - timedelta(days=10) <= d.draw_date <= ref for d in sub)
    # nothing after reference
    assert all(d.draw_date <= ref for d in sub)


def test_global_distribution_nine_rows_and_reference():
    draws = _draws()
    dist, total = drs.global_distribution(draws)
    assert len(dist) == 9
    assert total == sum(d["count"] for d in dist) == 60 * 5
    # reference ≈ 11.111 %
    assert abs(drs.REFERENCE_FREQ * 100 - 11.111) < 0.01
    # percentages sum to ~100
    assert abs(sum(d["percentage"] for d in dist) - 100.0) < 1e-6


def test_position_distribution_top_root():
    draws = _draws()
    pos = drs.position_distribution(draws)
    assert set(pos.keys()) == {"1", "2", "3", "4", "5"}
    for p in pos.values():
        assert p["total"] == 60
        assert sum(r["count"] for r in p["rows"]) == 60
        assert p["top_root"] in range(9)


def test_draw_signatures_distinct_and_repeats():
    d = [drs.Draw("a", date(2026, 10, 25), (74, 84, 12, 29, 10))]
    sig = drs.draw_signatures(d, 1)[0]
    assert sig["signature"] == "2-3-3-2-1"
    assert sig["distinct_count"] == 3  # {1,2,3}
    assert set(sig["repeats"]) == {2, 3}  # roots 2 and 3 each appear twice


def test_family_stats_candidate_numbers():
    draws = _draws()
    fams = drs.family_stats(draws)
    assert len(fams) == 9
    # root 3 family from the spec
    assert numbers_by_root(3) == [3, 12, 21, 30, 39, 48, 57, 66, 75, 84]
    assert fams[3]["family"] == [3, 12, 21, 30, 39, 48, 57, 66, 75, 84]


def test_transitions_matrix_shape_and_conditional():
    draws = _draws()
    tr = drs.transitions(draws)
    assert len(tr["matrix"]) == 9 and all(len(r) == 9 for r in tr["matrix"])
    # conditional rows sum to ~1 when non-empty, ~0 when the origin root never occurs
    for row in tr["conditional"]:
        s = sum(row)
        assert abs(s - 1.0) < 1e-2 or abs(s) < 1e-9


def test_transitions_total_pairs():
    draws = _draws()
    tr = drs.transitions(draws)
    # (n_draws - 1) * 5 * 5 pairs
    assert tr["total_pairs"] == (len(draws) - 1) * 25


def test_temporal_evolution_windows_nested():
    draws = _draws()
    ev = drs.temporal_evolution(draws, date(2026, 10, 25), (10, 30, 45, 60, 90))
    assert ev["nested"] is True
    assert list(ev["per_window"].keys()) == ["10", "30", "45", "60", "90"]
    # nested windows: draw count never decreases as window grows
    counts = [ev["per_window"][w]["draws"] for w in ("10", "30", "45", "60", "90")]
    assert counts == sorted(counts)


def test_quality_report_detects_duplicates():
    base = date(2026, 10, 25)
    dup = [
        drs.Draw("a", base, (1, 2, 3, 4, 5)),
        drs.Draw("b", base, (1, 2, 3, 4, 5)),  # same date + numbers → duplicate
        drs.Draw("c", base - timedelta(days=1), (6, 7, 8, 9, 10)),
    ]
    q = drs.quality_report(dup, base)
    assert q["duplicates"] == 1
    assert q["draw_count"] == 3


def test_walkforward_baseline_and_shape():
    draws = _draws()
    wf = drs.walkforward_validation(draws)
    assert len(wf["results"]) == 5
    for r in wf["results"]:
        assert r["random_baseline"] == round(1 / 9, 4)
        if r["trials"]:
            assert 0.0 <= r["hit_rate"] <= 1.0
