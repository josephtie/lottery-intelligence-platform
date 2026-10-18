"""Adaptive strategy selector (mission: « agents sélecteurs adaptatifs »).

A follow-the-winner agent over the fusion methods AND the individual models.
It picks the strategy with the best *recent* walk-forward performance, but
switches only on a durable margin over a minimum number of episodes — never
on a single draw — so it does not flip-flop and does not over-fit noise.
The chosen combination is what an agent would feed to
``agent_engine.make_decision(selected_numbers=...)``.

No look-ahead: at draw i the selector uses only performance observed on
draws < i (the current draw's outcome is recorded *after* the choice).
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Sequence

from lottery_intelligence_platform import fusion_engine as fe


class AdaptiveSelector:
    """Prudent follow-the-winner over a set of named strategies."""

    def __init__(self, window: int = 40, margin: float = 0.15,
                 min_episodes: int = 20):
        self.window = window
        self.margin = margin
        self.min_episodes = min_episodes
        self.active: str = "majority"
        self.performance: dict[str, list[float]] = defaultdict(list)
        self.switches: list[tuple[str, str, float]] = []

    def observe(self, hits: dict[str, float]) -> None:
        for strategy, h in hits.items():
            self.performance[strategy].append(float(h))

    def select(self) -> tuple[str, tuple[str, str, float] | None]:
        """Choose the best recent strategy; switch only on a durable margin."""
        recent = {
            s: mean(self.performance[s][-self.window:])
            for s in self.performance
            if len(self.performance[s]) >= self.min_episodes
        }
        if not recent:
            return self.active, None
        best = max(recent, key=recent.get)
        if best != self.active and recent[best] >= recent.get(self.active, 0.0) * (1.0 + self.margin):
            switch = (self.active, best, round(recent[best] - recent.get(self.active, 0.0), 4))
            self.active = best
            self.switches.append(switch)
            return best, switch
        return self.active, None


# All selectable strategies: the three fusion methods + every single model.
def _strategy_picks(picks: dict[str, list[int]], history, k: int) -> dict[str, list[int]]:
    out = dict(fe.generate_combinations(picks, history, k, fe.FUSION_METHODS))
    out.update(picks)  # single models (their own top-k)
    return out


def run_adaptive_walkforward(
    history: Sequence[Sequence[int]],
    *,
    k: int = 5,
    start: int = 40,
    window: int = 40,
    margin: float = 0.15,
    min_episodes: int = 20,
) -> dict:
    """Walk-forward adaptive selection.

    At each draw the selector chooses a strategy from past performance only,
    then records that strategy's hit on the current draw. Returns the chosen
    strategy's hit distribution and the switch trace.
    """
    selector = AdaptiveSelector(window=window, margin=margin, min_episodes=min_episodes)
    chosen_hits: list[int] = []
    for i in range(start, len(history)):
        past = history[:i]
        winning = set(history[i])
        picks = fe.model_picks(past, k)
        strategies = _strategy_picks(picks, past, k)
        # choose from PAST only
        chosen, _ = selector.select()
        chosen_hits.append(fe.hit_count(strategies.get(chosen, []), winning))
        # observe this draw's outcome for the next iteration (now it is "past")
        selector.observe({s: fe.hit_count(c, winning) for s, c in strategies.items()})

    n = len(chosen_hits)
    return {
        "n": n,
        "mean_hits": round(sum(chosen_hits) / n, 4) if n else 0.0,
        "p_ge3": round(sum(1 for h in chosen_hits if h >= 3) / n, 4) if n else 0.0,
        "switches": selector.switches,
        "final_strategy": selector.active,
    }
