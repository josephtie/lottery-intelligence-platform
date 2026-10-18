"""Agents de paris virtuels branchés sur le moteur de fusion + sélecteur.

Chaque profil est une STRATÉGIE DISTINCTE qui, à partir du seul historique
antérieur (walk-forward strict), produit une décision : numéros sélectionnés,
mise virtuelle, raisonnement et score de confiance (= degré d'accord des
modèles, jamais une probabilité de gain).

Ces décisions sont conçues pour être scellées via
``agent_engine.make_decision(...)`` — aucune mise réelle, aucune garantie de
gain. La référence ``random`` sert de benchmark au même budget.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Sequence

from lottery_intelligence_platform import adaptive_selector as asel
from lottery_intelligence_platform import fusion_engine as fe

K = 5
DEFAULT_STAKE = Decimal("100")


@dataclass(frozen=True, slots=True)
class FusionAgentProfile:
    code: str
    display_name: str
    mission: str
    specialties: list[str]
    preferred_methods: list[str]
    strategy: str  # clé de décision (voir _deciders)


FUSION_AGENT_PROFILES: tuple[FusionAgentProfile, ...] = (
    FusionAgentProfile(
        code="fusion_synergist",
        display_name="Le Synergiste",
        mission="Réunir les numéros de plusieurs modèles via vote majoritaire.",
        specialties=["fusion", "vote majoritaire"],
        preferred_methods=["majority"],
        strategy="majority",
    ),
    FusionAgentProfile(
        code="fusion_unionist",
        display_name="L'Unioniste",
        mission="Couvrir l'union des propositions des modèles les plus votées.",
        specialties=["fusion", "union"],
        preferred_methods=["union"],
        strategy="union",
    ),
    FusionAgentProfile(
        code="fusion_bordist",
        display_name="Le Bordiste",
        mission="Pondérer les numéros par rang de chaque modèle (Borda).",
        specialties=["fusion", "pondération"],
        preferred_methods=["borda"],
        strategy="borda",
    ),
    FusionAgentProfile(
        code="fusion_adaptive",
        display_name="L'Adaptatif",
        mission="Suivre la stratégie la plus performante récemment, en changeant prudemment.",
        specialties=["sélection adaptative"],
        preferred_methods=["adaptive"],
        strategy="adaptive",
    ),
    FusionAgentProfile(
        code="fusion_frequentist",
        display_name="Le Fréquentiste",
        mission="Jouer les numéros les plus fréquents sur une fenêtre récente.",
        specialties=["fréquence"],
        preferred_methods=["frequency"],
        strategy="frequency",
    ),
    FusionAgentProfile(
        code="fusion_complementarist",
        display_name="Le Complémentariste",
        mission="Fusionner les deux modèles les plus complémentaires (faible recouvrement).",
        specialties=["fusion", "complémentarité"],
        preferred_methods=["complementary"],
        strategy="complementary",
    ),
    FusionAgentProfile(
        code="fusion_random",
        display_name="La Référence Aléatoire",
        mission="Benchmark : tirer des numéros uniformes (aucune stratégie).",
        specialties=["benchmark"],
        preferred_methods=["random"],
        strategy="random",
    ),
)


def _agreement_confidence(picks: dict[str, list[int]]) -> float:
    """Degree of agreement among the top-5 of the models (0..1). Never a win probability."""
    if not picks:
        return 0.0
    j = fe.pairwise_jaccard(picks)
    return round(min(1.0, max(0.0, j)), 4)


def _decide_majority(picks, history, rng):
    combo = fe.generate_n_combination(picks, history, K)
    return combo


def _decide_union(picks, history, rng):
    return fe.generate_combinations(picks, history, K, ("union",))["union"]


def _decide_borda(picks, history, rng):
    return fe.generate_combinations(picks, history, K, ("borda",))["borda"]


def _decide_frequency(picks, history, rng):
    from collections import Counter
    recent = history[-60:]
    c = Counter(n for d in recent for n in d)
    return [n for n, _ in sorted(c.items(), key=lambda kv: (-kv[1], -kv[0]))][:K]


def _decide_complementary(picks, history, rng):
    comps = fe.complementary_pairs(picks, threshold=0.2)
    if comps:
        a, b, _ = min(comps, key=lambda t: t[2])
        combo = list(dict.fromkeys(list(picks[a]) + list(picks[b])))[:K]
        if len(combo) < K:
            combo.extend(fe.generate_n_combination(picks, history, K))
            combo = list(dict.fromkeys(combo))[:K]
        return combo
    return fe.generate_n_combination(picks, history, K)


def _decide_random(picks, history, rng):
    return rng.sample(range(1, 91), K)


_DECIDERS: dict[str, Callable] = {
    "majority": _decide_majority,
    "union": _decide_union,
    "borda": _decide_borda,
    "frequency": _decide_frequency,
    "complementary": _decide_complementary,
    "random": _decide_random,
}


def decide(
    profile: FusionAgentProfile,
    history: Sequence[Sequence[int]],
    rng: random.Random | None = None,
    *,
    k: int = K,
    stake: Decimal = DEFAULT_STAKE,
) -> dict:
    """Produce a sealed-ready decision for a profile from past history only.

    Returns a dict shaped for ``agent_engine.make_decision``:
      selected_numbers, stake_amount, reasoning, confidence_score.
    """
    rng = rng or random.Random(0)
    picks = fe.model_picks(history, k)

    if profile.strategy == "adaptive":
        # adaptive selector chooses among methods + single models, then emits its pick
        sel = asel.AdaptiveSelector(window=40, margin=0.15, min_episodes=20)
        # replay the walk-forward so the selector is stateful on this history
        for i in range(max(0, len(history) - 60), len(history)):
            past = history[:i]
            if not past:
                continue
            w = set(history[i])
            pp = fe.model_picks(past, k)
            combos = fe.generate_combinations(pp, past, k, fe.FUSION_METHODS)
            all_hits = {m: fe.hit_count(c, w) for m, c in combos.items()}
            all_hits.update({code: fe.hit_count(p, w) for code, p in pp.items()})
            chosen, _ = sel.select()
            sel.observe(all_hits)
        # final choice on the full history
        combos = fe.generate_combinations(picks, history, k, fe.FUSION_METHODS)
        options = dict(combos)
        options.update(picks)
        chosen, _ = sel.select()
        combo = options.get(chosen, fe.generate_n_combination(picks, history, k))
        reasoning = (f"Sélecteur adaptatif actif sur '{chosen}' "
                     f"({len(sel.switches)} bascule(s) enregistrée(s)).")
    else:
        combo = _DECIDERS[profile.strategy](picks, history, rng)
        reasoning = (
            f"Stratégie '{profile.strategy}' sur {len(picks)} modèles ; "
            f"complémentarité moyenne (Jaccard) = {fe.pairwise_jaccard(picks):.3f}."
        )

    confidence = _agreement_confidence(picks)

    return {
        "code": profile.code,
        "display_name": profile.display_name,
        "strategy": profile.strategy,
        "selected_numbers": list(combo),
        "stake_amount": stake,
        "reasoning": reasoning,
        "confidence_score": confidence,
    }


def get_profile(code: str) -> FusionAgentProfile | None:
    for p in FUSION_AGENT_PROFILES:
        if p.code == code:
            return p
    return None
