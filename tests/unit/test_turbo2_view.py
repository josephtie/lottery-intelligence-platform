"""Tests for turbo2_view — the read-only Turbo 2 per-game history layer.

The settlement engine seals hit/payout/net into
``metrics.turbo.turbo_2``; this module only reshapes sealed rows.
The tests therefore feed canned DB rows through a fake connection and
verify aggregation, segmentation and formatting rules (cases 4-7 of the
view spec plus the financial math).
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from uuid import uuid4

from lottery_intelligence_platform import turbo2_view


def _row(d: date, seq: int, model: str, predicted, winning,
         hits2: int, hit: bool, net: float | None = None):
    """One sealed outcome tuple as returned by the SQL query."""
    t2 = {"hit": hit, "stake": 100.0,
          "payout": 240_000.0 if hit else 0.0,
          "net": net if net is not None else (239_900.0 if hit else -100.0),
          "roi": 0.0, "positions": 2, "multiplier": 2400.0}
    return (uuid4(), d, seq, model, predicted, winning, hits2,
            {"first_2": hits2}, t2, datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 1, tzinfo=timezone.utc))


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.description = []
    def fetchall(self):
        return self._rows
    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    """Serves the game-name lookup, then the outcome rows; records the
    draw_type_id the outcome query was issued with (game separation)."""
    def __init__(self, rows):
        self.rows = rows
        self.seen_draw_type = None
        self._call = 0
    def execute(self, sql, params=()):
        self._call += 1
        if self._call == 1:
            return FakeCursor([("Afterwork",)])
        self.seen_draw_type = params[0]
        return FakeCursor(self.rows)


W40_MON = date(2026, 10, 5)   # lundi
W40_TUE = date(2026, 10, 6)   # mardi
W41_MON = date(2026, 10, 12)  # lundi semaine suivante


class TestAggregate(unittest.TestCase):
    def test_hit_math(self):
        rows = [{"turbo2_hit": True, "stake": 100.0, "gross": 240_000.0,
                 "net": 239_900.0}]
        a = turbo2_view._aggregate(rows)
        self.assertEqual(a["bets"], 1)
        self.assertEqual(a["hits"], 1)
        self.assertEqual(a["roi"], 2399.0)

    def test_loss_math(self):
        rows = [{"turbo2_hit": False, "stake": 100.0, "gross": 0.0,
                 "net": -100.0}] * 8
        a = turbo2_view._aggregate(rows)
        self.assertEqual(a["net"], -800.0)
        self.assertEqual(a["roi"], -1.0)

    def test_empty_is_na(self):
        a = turbo2_view._aggregate([])
        self.assertIsNone(a["roi"])
        self.assertIsNone(a["hit_rate"])
        self.assertEqual(a["total_stake"], 0)


class TestStreaks(unittest.TestCase):
    def test_streaks(self):
        flags = [False, False, True, True, True, False]
        rows = [{"turbo2_hit": f, "date": "2026-10-0%d" % (i + 1)}
                for i, f in enumerate(flags)]
        s = turbo2_view._streaks(rows)
        self.assertEqual(s["best_hit_streak"], 3)
        self.assertEqual(s["worst_loss_streak"], 2)
        self.assertEqual(s["last_hit_date"], "2026-10-05")


class TestTurbo2History(unittest.TestCase):
    def _make(self, rows):
        return turbo2_view.turbo2_history(
            FakeConnection(rows), uuid4())

    def test_row_shape_uses_sealed_values(self):
        out = self._make([_row(W40_MON, 1, "m1", [12, 36], [12, 36, 5, 7, 9],
                               hits2=2, hit=True)])
        r = out["rows"][0]
        self.assertEqual(r["predicted"], [12, 36])
        self.assertEqual(r["winning_first2"], [12, 36])
        self.assertEqual(r["hits_first2"], 2)
        self.assertTrue(r["turbo2_hit"])
        self.assertEqual(r["net"], 239_900.0)   # sealed, not recomputed
        self.assertEqual(r["iso_week"], "2026-W41")  # Oct 5 2026 = W41
        self.assertEqual(r["weekday"], 0)

    def test_game_separation_param(self):
        conn = FakeConnection([])
        tid = uuid4()
        turbo2_view.turbo2_history(conn, tid)
        self.assertEqual(conn.seen_draw_type, tid)  # WHERE draw_type = %s

    def test_two_draws_same_day_stay_distinct(self):
        out = self._make([
            _row(W40_TUE, 1, "m1", [1, 2], [9, 9, 9, 9, 9], 0, False),
            _row(W40_TUE, 2, "m1", [3, 4], [9, 9, 9, 9, 9], 0, False),
        ])
        self.assertEqual(len(out["rows"]), 2)
        self.assertEqual({r["sequence"] for r in out["rows"]}, {1, 2})

    def test_weeks_do_not_bleed(self):
        out = self._make([
            _row(W40_MON, 1, "m1", [1, 2], [9] * 5, 0, False),
            _row(W41_MON, 1, "m1", [1, 2], [1, 2, 3, 4, 5], 2, True),
        ])
        weekly = {w["iso_week"]: w for w in out["weekly"]}
        self.assertEqual(len(weekly), 2)
        self.assertEqual(weekly["2026-W41"]["hits"], 0)
        self.assertEqual(weekly["2026-W42"]["hits"], 1)
        # same-weekday view must keep both mondays as separate rows
        mondays = [r for r in out["rows"] if r["weekday"] == 0]
        self.assertEqual(len(mondays), 2)

    def test_model_sample_badge(self):
        weak = self._make([
            _row(W40_MON, 1, "m1", [1, 2], [9] * 5, 0, False)])
        strong = self._make([
            _row(W40_MON, 1, "m1", [1, 2], [9] * 5, 0, False)
            for _ in range(10)])
        self.assertEqual(weak["models"][0]["sample_level"], "weak")
        self.assertEqual(strong["models"][0]["sample_level"], "adequate")

    def test_chronological_order_for_cumulative(self):
        out = self._make([
            _row(W41_MON, 1, "m1", [1, 2], [9] * 5, 0, False),
            _row(W40_MON, 1, "m1", [1, 2], [9] * 5, 0, False),
        ])
        dates = [r["date"] for r in out["rows"]]
        self.assertEqual(dates, ["2026-10-05", "2026-10-12"])

    def test_unknown_game(self):
        class NoGame(FakeConnection):
            def execute(self, sql, params=()):
                return FakeCursor([])
        out = turbo2_view.turbo2_history(NoGame([]), uuid4())
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
