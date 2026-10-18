"""Betting Formulas Configuration for Loto Bonheur.

This module defines the official betting formulas, odds, and payout rules
for Loto Bonheur (LONACI). Used by autonomous agents to calculate
potential returns and make informed betting decisions.

Official source: https://lotobonheur.ci/distribution-des-gains
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4


class FormulaType(Enum):
    """Types of betting formulas."""
    STANDARD = "STANDARD"  # PN, 1N, 2N, 3N, 4N, 5N
    TURBO = "TURBO"  # Turbo 2, 3, 4, 5
    CHANCE = "CHANCE"  # Chance 3+, 4+, 5+
    PERM = "PERM"  # Permutation/Combination formulas


@dataclass(frozen=True, slots=True)
class FormulaConfig:
    """Configuration for a betting formula."""
    code: str
    name: str
    formula_type: FormulaType
    description: str
    numbers_required: int
    unit_stake: Decimal  # Mise unitaire en FCFA
    odds: dict[str, Decimal]  # Cotes par palier (ex: {"2N": 240})
    max_combinations: int | None = None  # Pour PERM
    position_sensitive: bool = False  # Pour Turbo (ordre important)
    payout_multiplier: Decimal = Decimal("1")  # Multiplicateur de gain


# Official odds from lotobonheur.ci
STANDARD_FORMULAS = {
    "PN": FormulaConfig(
        code="PN",
        name="Prédiction Numérique",
        formula_type=FormulaType.STANDARD,
        description="Parier sur 1 numéro exact",
        numbers_required=1,
        unit_stake=Decimal("100"),
        odds={"PN": Decimal("40")},
    ),
    "1N": FormulaConfig(
        code="1N",
        name="1 Numéro",
        formula_type=FormulaType.STANDARD,
        description="Parier sur 1 numéro gagnant",
        numbers_required=1,
        unit_stake=Decimal("100"),
        odds={"1N": Decimal("10")},
    ),
    "2N": FormulaConfig(
        code="2N",
        name="2 Numéros",
        formula_type=FormulaType.STANDARD,
        description="Parier sur 2 numéros gagnants",
        numbers_required=2,
        unit_stake=Decimal("100"),
        odds={"2N": Decimal("240")},
    ),
    "3N": FormulaConfig(
        code="3N",
        name="3 Numéros",
        formula_type=FormulaType.STANDARD,
        description="Parier sur 3 numéros gagnants",
        numbers_required=3,
        unit_stake=Decimal("100"),
        odds={"3N": Decimal("2000")},
    ),
    "4N": FormulaConfig(
        code="4N",
        name="4 Numéros",
        formula_type=FormulaType.STANDARD,
        description="Parier sur 4 numéros gagnants",
        numbers_required=4,
        unit_stake=Decimal("100"),
        odds={"4N": Decimal("5000")},
    ),
    "5N": FormulaConfig(
        code="5N",
        name="5 Numéros",
        formula_type=FormulaType.STANDARD,
        description="Parier sur 5 numéros gagnants",
        numbers_required=5,
        unit_stake=Decimal("100"),
        odds={"5N": Decimal("40000")},
    ),
}

TURBO_FORMULAS = {
    "TURBO_2": FormulaConfig(
        code="TURBO_2",
        name="Turbo 2",
        formula_type=FormulaType.TURBO,
        description="2 numéros doivent être les 2 premières boules dans l'ordre",
        numbers_required=2,
        unit_stake=Decimal("100"),
        odds={"TURBO_2": Decimal("2400")},
        position_sensitive=True,
    ),
    "TURBO_3": FormulaConfig(
        code="TURBO_3",
        name="Turbo 3",
        formula_type=FormulaType.TURBO,
        description="3 numéros doivent être les 3 premières boules dans l'ordre",
        numbers_required=3,
        unit_stake=Decimal("100"),
        odds={"TURBO_3": Decimal("800")},
        position_sensitive=True,
    ),
    "TURBO_4": FormulaConfig(
        code="TURBO_4",
        name="Turbo 4",
        formula_type=FormulaType.TURBO,
        description="4 numéros doivent être les 4 premières boules dans l'ordre",
        numbers_required=4,
        unit_stake=Decimal("100"),
        odds={"TURBO_4": Decimal("400")},
        position_sensitive=True,
    ),
    "TURBO_5": FormulaConfig(
        code="TURBO_5",
        name="Turbo 5",
        formula_type=FormulaType.TURBO,
        description="5 numéros doivent être les 5 premières boules dans l'ordre",
        numbers_required=5,
        unit_stake=Decimal("100"),
        odds={"TURBO_5": Decimal("240")},
        position_sensitive=True,
    ),
}

CHANCE_FORMULAS = {
    "CHANCE_3_PLUS": FormulaConfig(
        code="CHANCE_3_PLUS",
        name="Chance 3+",
        formula_type=FormulaType.CHANCE,
        description="Choisir 3 numéros, gains selon paliers 2N ou 3N",
        numbers_required=3,
        unit_stake=Decimal("100"),
        odds={"2N": Decimal("60"), "3N": Decimal("1750")},
    ),
    "CHANCE_4_PLUS": FormulaConfig(
        code="CHANCE_4_PLUS",
        name="Chance 4+",
        formula_type=FormulaType.CHANCE,
        description="Choisir 4 numéros, gains selon paliers 2N, 3N ou 4N",
        numbers_required=4,
        unit_stake=Decimal("100"),
        odds={"2N": Decimal("30"), "3N": Decimal("300"), "4N": Decimal("10000")},
    ),
    "CHANCE_5_PLUS": FormulaConfig(
        code="CHANCE_5_PLUS",
        name="Chance 5+",
        formula_type=FormulaType.CHANCE,
        description="Choisir 5 numéros, gains selon paliers 2N, 3N, 4N ou 5N",
        numbers_required=5,
        unit_stake=Decimal("100"),
        odds={"2N": Decimal("20"), "3N": Decimal("100"), "4N": Decimal("2000"), "5N": Decimal("50000")},
    ),
}

# PERM formulas (computed dynamically based on numbers selected)
PERM_CONFIGS = {
    "PERM_2": FormulaConfig(
        code="PERM_2",
        name="Permutation 2",
        formula_type=FormulaType.PERM,
        description="Générer toutes les paires possibles à partir de numéros choisis",
        numbers_required=2,  # Minimum, peut aller jusqu'à 90
        unit_stake=Decimal("100"),
        odds={"2N": Decimal("240")},
        max_combinations=4005,  # C(90, 2) = 4005
    ),
    "PERM_3": FormulaConfig(
        code="PERM_3",
        name="Permutation 3",
        formula_type=FormulaType.PERM,
        description="Générer tous les triplets possibles à partir de numéros choisis",
        numbers_required=3,  # Minimum, peut aller jusqu'à 90
        unit_stake=Decimal("100"),
        odds={"3N": Decimal("2000")},
        max_combinations=117480,  # C(90, 3) = 117480
    ),
}


def get_formula_config(formula_code: str) -> FormulaConfig | None:
    """Get formula configuration by code."""
    all_formulas = {
        **STANDARD_FORMULAS,
        **TURBO_FORMULAS,
        **CHANCE_FORMULAS,
        **PERM_CONFIGS,
    }
    return all_formulas.get(formula_code)


def calculate_combinations(n: int, k: int) -> int:
    """Calculate number of combinations C(n, k) = n! / (k! * (n-k)!)."""
    from math import comb
    return comb(n, k)


def calculate_perm_cost(
    formula_code: str,
    numbers_selected: int,
    total_stake: Decimal,
) -> tuple[int, Decimal]:
    """Calculate number of combinations and cost for PERM formulas.

    Returns:
        (number_of_combinations, cost_per_combination)
    """
    formula = get_formula_config(formula_code)
    if formula is None or formula.formula_type != FormulaType.PERM:
        raise ValueError(f"Formula {formula_code} is not a PERM formula")

    if formula_code == "PERM_2":
        k = 2
    elif formula_code == "PERM_3":
        k = 3
    else:
        raise ValueError(f"Unknown PERM formula: {formula_code}")

    combinations = calculate_combinations(numbers_selected, k)
    cost_per_combination = total_stake / Decimal(combinations)

    return combinations, cost_per_combination


def calculate_potential_gain(
    formula_code: str,
    numbers_selected: list[int],
    winning_numbers: list[int],
    total_stake: Decimal,
    winning_positions: list[int] | None = None,
) -> dict[str, Any]:
    """Calculate potential gain for a betting formula.

    Args:
        formula_code: Formula code (e.g., "CHANCE_3_PLUS", "PERM_2")
        numbers_selected: Numbers selected by the player
        winning_numbers: Winning numbers from the draw
        total_stake: Total stake in FCFA
        winning_positions: Positions of winning numbers (for Turbo formulas)

    Returns:
        Dictionary with:
        - status: "WIN" or "LOSE"
        - tier: Winning tier (e.g., "2N", "3N")
        - winning_combinations: Number of winning combinations
        - gain_per_combination: Gain per winning combination
        - total_gain: Total gain
        - net_profit: Total gain minus total stake
        - roi: Return on investment as percentage
    """
    formula = get_formula_config(formula_code)
    if formula is None:
        raise ValueError(f"Unknown formula: {formula_code}")

    # Count matches
    matches = len(set(numbers_selected) & set(winning_numbers))

    if formula.formula_type == FormulaType.STANDARD:
        # Standard formulas: exact match required
        if matches != formula.numbers_required:
            return {
                "status": "LOSE",
                "tier": None,
                "winning_combinations": 0,
                "gain_per_combination": Decimal("0"),
                "total_gain": Decimal("0"),
                "net_profit": -total_stake,
                "roi": Decimal("-100"),
            }

        tier = f"{formula.numbers_required}N"
        if tier not in formula.odds:
            raise ValueError(f"Tier {tier} not found in formula odds")

        gain_per_combination = total_stake * formula.odds[tier]
        total_gain = gain_per_combination
        net_profit = total_gain - total_stake
        roi = (net_profit / total_stake) * 100 if total_stake > 0 else Decimal("0")

        return {
            "status": "WIN",
            "tier": tier,
            "winning_combinations": 1,
            "gain_per_combination": gain_per_combination,
            "total_gain": total_gain,
            "net_profit": net_profit,
            "roi": roi,
        }

    elif formula.formula_type == FormulaType.TURBO:
        # Turbo formulas: position-sensitive
        if not formula.position_sensitive:
            raise ValueError(f"Turbo formula {formula_code} should be position-sensitive")

        if matches != formula.numbers_required:
            return {
                "status": "LOSE",
                "tier": None,
                "winning_combinations": 0,
                "gain_per_combination": Decimal("0"),
                "total_gain": Decimal("0"),
                "net_profit": -total_stake,
                "roi": Decimal("-100"),
            }

        # Check if positions match (first N positions)
        if winning_positions is None:
            # Assume positions match if not provided
            positions_match = True
        else:
            # Check if selected numbers are in the first N positions
            first_n_positions = set(winning_positions[:formula.numbers_required])
            positions_match = set(numbers_selected) == first_n_positions

        if not positions_match:
            return {
                "status": "LOSE",
                "tier": None,
                "winning_combinations": 0,
                "gain_per_combination": Decimal("0"),
                "total_gain": Decimal("0"),
                "net_profit": -total_stake,
                "roi": Decimal("-100"),
            }

        tier = formula_code
        gain_per_combination = total_stake * formula.odds[tier]
        total_gain = gain_per_combination
        net_profit = total_gain - total_stake
        roi = (net_profit / total_stake) * 100 if total_stake > 0 else Decimal("0")

        return {
            "status": "WIN",
            "tier": tier,
            "winning_combinations": 1,
            "gain_per_combination": gain_per_combination,
            "total_gain": total_gain,
            "net_profit": net_profit,
            "roi": roi,
        }

    elif formula.formula_type == FormulaType.CHANCE:
        # Chance formulas: tiered payouts
        if matches < 2:
            return {
                "status": "LOSE",
                "tier": None,
                "winning_combinations": 0,
                "gain_per_combination": Decimal("0"),
                "total_gain": Decimal("0"),
                "net_profit": -total_stake,
                "roi": Decimal("-100"),
            }

        # Find highest tier achieved
        tier = f"{matches}N"
        if tier not in formula.odds:
            # Use highest available tier
            available_tiers = sorted([int(t[:-1]) for t in formula.odds.keys()])
            highest_match = max([t for t in available_tiers if t <= matches])
            tier = f"{highest_match}N"

        gain_per_combination = total_stake * formula.odds[tier]
        total_gain = gain_per_combination
        net_profit = total_gain - total_stake
        roi = (net_profit / total_stake) * 100 if total_stake > 0 else Decimal("0")

        return {
            "status": "WIN",
            "tier": tier,
            "winning_combinations": 1,
            "gain_per_combination": gain_per_combination,
            "total_gain": total_gain,
            "net_profit": net_profit,
            "roi": roi,
        }

    elif formula.formula_type == FormulaType.PERM:
        # PERM formulas: multiple winning combinations
        if matches < 2:
            return {
                "status": "LOSE",
                "tier": None,
                "winning_combinations": 0,
                "gain_per_combination": Decimal("0"),
                "total_gain": Decimal("0"),
                "net_profit": -total_stake,
                "roi": Decimal("-100"),
            }

        k = formula.numbers_required
        if matches < k:
            return {
                "status": "LOSE",
                "tier": None,
                "winning_combinations": 0,
                "gain_per_combination": Decimal("0"),
                "total_gain": Decimal("0"),
                "net_profit": -total_stake,
                "roi": Decimal("-100"),
            }

        # Calculate winning combinations
        winning_combinations = calculate_combinations(matches, k)
        total_combinations = calculate_combinations(len(numbers_selected), k)
        cost_per_combination = total_stake / Decimal(total_combinations)

        tier = f"{k}N"
        if tier not in formula.odds:
            raise ValueError(f"Tier {tier} not found in formula odds")

        gain_per_combination = cost_per_combination * formula.odds[tier]
        total_gain = gain_per_combination * winning_combinations
        net_profit = total_gain - total_stake
        roi = (net_profit / total_stake) * 100 if total_stake > 0 else Decimal("0")

        return {
            "status": "WIN",
            "tier": tier,
            "winning_combinations": winning_combinations,
            "gain_per_combination": gain_per_combination,
            "total_gain": total_gain,
            "net_profit": net_profit,
            "roi": roi,
        }

    else:
        raise ValueError(f"Unknown formula type: {formula.formula_type}")


def get_all_formulas() -> dict[str, FormulaConfig]:
    """Get all available betting formulas."""
    return {
        **STANDARD_FORMULAS,
        **TURBO_FORMULAS,
        **CHANCE_FORMULAS,
        **PERM_CONFIGS,
    }


def get_formula_payout_matrix(formula_code: str, total_stake: Decimal = Decimal("100")) -> list[dict[str, Any]]:
    """Generate payout matrix for a formula showing all possible outcomes.

    Useful for agents to understand risk/reward profiles.
    """
    formula = get_formula_config(formula_code)
    if formula is None:
        raise ValueError(f"Unknown formula: {formula_code}")

    matrix = []

    if formula.formula_type == FormulaType.STANDARD:
        # Only one possible winning outcome
        matrix.append({
            "matches": formula.numbers_required,
            "tier": f"{formula.numbers_required}N",
            "winning_combinations": 1,
            "total_gain": total_stake * formula.odds[f"{formula.numbers_required}N"],
            "net_profit": total_stake * formula.odds[f"{formula.numbers_required}N"] - total_stake,
            "roi": ((formula.odds[f"{formula.numbers_required}N"] - 1) * 100),
        })

    elif formula.formula_type == FormulaType.CHANCE:
        # Tiered payouts
        for tier_code, odds in sorted(formula.odds.items(), key=lambda x: int(x[0][:-1])):
            matches = int(tier_code[:-1])
            if matches <= formula.numbers_required:
                matrix.append({
                    "matches": matches,
                    "tier": tier_code,
                    "winning_combinations": 1,
                    "total_gain": total_stake * odds,
                    "net_profit": total_stake * odds - total_stake,
                    "roi": ((odds - 1) * 100),
                })

    elif formula.formula_type == FormulaType.PERM:
        # Multiple combinations based on matches
        k = formula.numbers_required
        for matches in range(k, formula.numbers_required + 5):  # Show scenarios
            winning_combinations = calculate_combinations(matches, k)
            total_combinations = calculate_combinations(formula.numbers_required + 3, k)  # Example: 5 for PERM 2
            cost_per_combination = total_stake / Decimal(total_combinations)
            gain_per_combination = cost_per_combination * formula.odds[f"{k}N"]
            total_gain = gain_per_combination * winning_combinations

            matrix.append({
                "matches": matches,
                "tier": f"{k}N",
                "winning_combinations": winning_combinations,
                "total_gain": total_gain,
                "net_profit": total_gain - total_stake,
                "roi": ((total_gain / total_stake - 1) * 100) if total_stake > 0 else 0,
            })

    return matrix
