"""Digital Root picker integration with existing prediction system.

Provides a picker function compatible with the lottery_intelligence_platform
prediction generation interface.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from lottery_intelligence_platform.digital_root_analyzer import DigitalRootTurboAnalyzer
from lottery_intelligence_platform.prediction_generation import (
    DEFAULT_PICK_COUNT,
    _history,
    _stable_seed,
)


# Global analyzer instance (would be initialized with connection in production)
_analyzer: DigitalRootTurboAnalyzer | None = None


def _get_analyzer() -> DigitalRootTurboAnalyzer:
    """Get or create the global analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = DigitalRootTurboAnalyzer(
            observation_window_days=3,
            min_observations=5,
            default_turbo_variant="turbo_2",
        )
    return _analyzer


def pick_digital_root_turbo(
    connection: Any,
    draw_type_id: Any,
    target: date,
    params: Mapping[str, Any],
    seed: int | None,
) -> list[int]:
    """Picker function for digital root-based Turbo predictions.

    Compatible with the prediction generation picker signature:
    (connection, draw_type_id, target, params, seed) -> list[int]

    Args:
        connection: Database connection
        draw_type_id: Target game type
        target: Target draw date
        params: Picker parameters (optional: turbo_variant, top_roots, candidates_per_root)
        seed: Random seed (not used for deterministic digital root)

    Returns:
        List of predicted numbers for Turbo bet
    """
    analyzer = _get_analyzer()

    # Extract parameters with defaults
    turbo_variant = params.get("turbo_variant", "turbo_2")
    top_roots = params.get("top_roots", 5)
    candidates_per_root = params.get("candidates_per_root", 10)

    # Discover and train on historical data
    analyzer.discover_and_train(
        connection,
        [draw_type_id],
        target,
    )

    # Generate prediction
    prediction = analyzer.predict(
        connection,
        draw_type_id,
        target,
        turbo_variant=turbo_variant,
        top_roots=top_roots,
        candidates_per_root=candidates_per_root,
    )

    return prediction.predicted_numbers


def pick_digital_root_turbo_v2(
    connection: Any,
    draw_type_id: Any,
    target: date,
    params: Mapping[str, Any],
    seed: int | None,
) -> list[int]:
    """Improved digital root picker with relation-aware selection.

    This version considers the strength and age of discovered relations
    when making predictions, favoring well-established patterns.
    """
    analyzer = _get_analyzer()

    # Use longer observation window for v2
    if analyzer.relation_discovery.observation_window_days < 5:
        analyzer.relation_discovery.observation_window_days = 5

    turbo_variant = params.get("turbo_variant", "turbo_2")
    top_roots = params.get("top_roots", 3)  # Fewer but higher confidence roots
    candidates_per_root = params.get("candidates_per_root", 15)

    analyzer.discover_and_train(connection, [draw_type_id], target)

    prediction = analyzer.predict(
        connection,
        draw_type_id,
        target,
        turbo_variant=turbo_variant,
        top_roots=top_roots,
        candidates_per_root=candidates_per_root,
    )

    return prediction.predicted_numbers
