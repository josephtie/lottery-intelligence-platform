"""Digital Root Turbo Analyzer - Main prediction engine.

Integrates digital root transformation, relation discovery, and Turbo candidate
generation into a coherent prediction system compatible with the existing
Lottery Intelligence Platform architecture.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from lottery_intelligence_platform.betting_formulas import TURBO_FORMULAS
from lottery_intelligence_platform.digital_root import (
    NumberWithRoot,
    get_numbers_by_root_fast,
    get_root_fast,
    transform_sequence,
)
from lottery_intelligence_platform.digital_root_relations import (
    DigitalRootRelation,
    RelationDiscovery,
    RelationType,
)


@dataclass(slots=True)
class RootPrediction:
    """A prediction for a digital root."""
    root: int
    confidence: float
    supporting_relation: DigitalRootRelation | None
    uncertainty_level: str  # "HIGH", "MEDIUM", "LOW"
    observation_window_days: int
    comparison_to_random: float  # How much better than random


@dataclass(slots=True)
class TurboCandidate:
    """A Turbo bet candidate derived from a root prediction."""
    number: int
    root: int
    rank_in_family: int  # Position within the root's number family
    historical_frequency: float  # How often this number appears historically
    adjusted_score: float  # Final score combining root prediction and number stats


@dataclass(slots=True)
class DigitalRootPrediction:
    """Complete prediction set for a draw."""
    draw_type_id: UUID
    scheduled_date: date
    predicted_roots: list[RootPrediction]
    turbo_candidates: list[TurboCandidate]
    turbo_variant: str  # "turbo_2", "turbo_3", etc.
    predicted_numbers: list[int]
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_final_selection(self, k: int) -> list[int]:
        """Get top k numbers for Turbo bet."""
        sorted_candidates = sorted(
            self.turbo_candidates,
            key=lambda c: c.adjusted_score,
            reverse=True,
        )
        return [c.number for c in sorted_candidates[:k]]


class DigitalRootTurboAnalyzer:
    """Main analyzer combining digital root patterns with Turbo market rules."""

    def __init__(
        self,
        *,
        observation_window_days: int = 3,
        min_observations: int = 5,
        default_turbo_variant: str = "turbo_2",
    ):
        self.relation_discovery = RelationDiscovery(
            observation_window_days=observation_window_days,
            min_observations=min_observations,
        )
        self.default_turbo_variant = default_turbo_variant
        self.historical_cache: dict[UUID, list[dict]] = {}

    def load_historical_data(
        self,
        connection: Any,
        draw_type_id: UUID,
        before_date: date,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Load historical draw data for a game type.

        Args:
            connection: Database connection
            draw_type_id: Game type to load
            before_date: Load draws before this date
            limit: Maximum number of draws to load

        Returns:
            List of draw records
        """
        cache_key = (draw_type_id, before_date, limit)
        if cache_key in self.historical_cache:
            return self.historical_cache[cache_key]

        rows = connection.execute(
            """SELECT d.draw_id, d.draw_type_id, d.scheduled_date,
                      dn.number, dn.position, dn.number_role
               FROM core.draws d
               JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
               JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
               WHERE d.draw_type_id = %s
                 AND d.scheduled_date < %s
                 AND d.status = 'SETTLED'
                 AND dv.validation_status = 'VALID'
                 AND dn.number_role = 'WINNING'
               ORDER BY d.scheduled_date DESC, dv.version_number DESC, dn.position
               LIMIT %s""",
            (draw_type_id, before_date, limit * 10),  # Get enough for aggregation
        ).fetchall()

        # Aggregate by draw
        draws_dict: dict[UUID, dict] = {}
        for row in rows:
            draw_id, draw_type_id, scheduled_date, number, position, _ = row
            if draw_id not in draws_dict:
                draws_dict[draw_id] = {
                    "draw_id": draw_id,
                    "draw_type_id": draw_type_id,
                    "scheduled_date": scheduled_date,
                    "winning_numbers": [],
                }
            draws_dict[draw_id]["winning_numbers"].append(number)

        draws = list(draws_dict.values())[:limit]
        self.historical_cache[cache_key] = draws
        return draws

    def discover_and_train(
        self,
        connection: Any,
        draw_type_ids: list[UUID],
        training_cutoff: date,
    ) -> list[DigitalRootRelation]:
        """Discover relations from historical data.

        Args:
            connection: Database connection
            draw_type_ids: List of game types to analyze
            training_cutoff: Use data before this date for training

        Returns:
            List of discovered relations
        """
        all_historical = []
        for game_id in draw_type_ids:
            historical = self.load_historical_data(
                connection,
                game_id,
                before_date=training_cutoff,
                limit=200,
            )
            all_historical.extend(historical)

        new_relations = self.relation_discovery.discover_relations(all_historical)
        return new_relations

    def predict(
        self,
        connection: Any,
        draw_type_id: UUID,
        target_date: date,
        *,
        turbo_variant: str | None = None,
        top_roots: int = 5,
        candidates_per_root: int = 10,
    ) -> DigitalRootPrediction:
        """Generate a prediction for a target draw.

        Args:
            connection: Database connection
            draw_type_id: Target game type
            target_date: Date of the target draw
            turbo_variant: Turbo variant to use (default: self.default_turbo_variant)
            top_roots: Number of top roots to predict
            candidates_per_root: Number of candidates per root

        Returns:
            Complete prediction with roots and Turbo candidates
        """
        variant = turbo_variant or self.default_turbo_variant

        # Load historical data up to target date
        historical = self.load_historical_data(
            connection,
            draw_type_id,
            before_date=target_date,
            limit=100,
        )

        # Get numbers required for this Turbo variant
        formula = TURBO_FORMULAS.get(f"TURBO_{variant.replace('turbo_', '').upper()}")
        if formula is None:
            raise ValueError(f"Unknown Turbo variant: {variant}")
        numbers_required = formula.numbers_required

        # Predict roots
        root_predictions = self._predict_roots(
            draw_type_id,
            numbers_required,
            top_k=top_roots,
        )

        # Generate Turbo candidates from predicted roots
        turbo_candidates = self._generate_turbo_candidates(
            connection,
            draw_type_id,
            target_date,
            root_predictions,
            candidates_per_root=candidates_per_root,
        )

        # Select final numbers
        predicted_numbers = DigitalRootPrediction(
            draw_type_id=draw_type_id,
            scheduled_date=target_date,
            predicted_roots=root_predictions,
            turbo_candidates=turbo_candidates,
            turbo_variant=variant,
            predicted_numbers=[],
        ).get_final_selection(numbers_required)

        return DigitalRootPrediction(
            draw_type_id=draw_type_id,
            scheduled_date=target_date,
            predicted_roots=root_predictions,
            turbo_candidates=turbo_candidates,
            turbo_variant=variant,
            predicted_numbers=predicted_numbers,
            metadata={
                "numbers_required": numbers_required,
                "timestamp": datetime.now().isoformat(),
            },
        )

    def _predict_roots(
        self,
        draw_type_id: UUID,
        numbers_required: int,
        top_k: int = 5,
    ) -> list[RootPrediction]:
        """Predict digital roots for target positions.

        Args:
            draw_type_id: Target game type
            numbers_required: Number of positions to predict
            top_k: Number of top predictions per position

        Returns:
            List of root predictions
        """
        predictions = []

        for position in range(numbers_required):
            ranked = self.relation_discovery.predict_roots(
                game_id=draw_type_id,
                position=position,
                top_k=top_k,
            )

            for root, confidence, relation in ranked:
                # Calculate uncertainty level
                obs_count = relation.evidence.total_observations if relation else 0
                if obs_count >= 20:
                    uncertainty = "LOW"
                elif obs_count >= 10:
                    uncertainty = "MEDIUM"
                else:
                    uncertainty = "HIGH"

                comparison = confidence - (relation.baseline_success_rate if relation else 0)

                predictions.append(
                    RootPrediction(
                        root=root,
                        confidence=confidence,
                        supporting_relation=relation,
                        uncertainty_level=uncertainty,
                        observation_window_days=relation.evidence.observation_window_days if relation else 3,
                        comparison_to_random=comparison,
                    )
                )

        # Sort by confidence and deduplicate by root
        seen_roots = set()
        unique_predictions = []
        for pred in sorted(predictions, key=lambda p: p.confidence, reverse=True):
            if pred.root not in seen_roots:
                seen_roots.add(pred.root)
                unique_predictions.append(pred)

        return unique_predictions[:top_k]

    def _generate_turbo_candidates(
        self,
        connection: Any,
        draw_type_id: UUID,
        target_date: date,
        root_predictions: list[RootPrediction],
        candidates_per_root: int = 10,
    ) -> list[TurboCandidate]:
        """Generate Turbo number candidates from root predictions.

        Args:
            connection: Database connection
            draw_type_id: Target game type
            target_date: Target draw date
            root_predictions: Predicted roots
            candidates_per_root: Candidates to generate per root

        Returns:
            List of Turbo candidates
        """
        candidates = []

        # Load historical frequencies
        historical = self.load_historical_data(
            connection,
            draw_type_id,
            before_date=target_date,
            limit=500,
        )

        # Calculate number frequencies
        number_counts: dict[int, int] = {}
        total_numbers = 0
        for draw in historical:
            for num in draw["winning_numbers"]:
                number_counts[num] = number_counts.get(num, 0) + 1
                total_numbers += 1

        # For each predicted root, generate its number family
        for pred in root_predictions:
            numbers = get_numbers_by_root_fast(pred.root)

            # Rank numbers by historical frequency
            ranked_numbers = sorted(
                numbers,
                key=lambda n: number_counts.get(n, 0),
                reverse=True,
            )[:candidates_per_root]

            for rank, num in enumerate(ranked_numbers):
                freq = number_counts.get(num, 0) / total_numbers if total_numbers > 0 else 0

                # Adjusted score combines root confidence with number frequency
                adjusted_score = pred.confidence * 0.7 + freq * 0.3

                candidates.append(
                    TurboCandidate(
                        number=num,
                        root=pred.root,
                        rank_in_family=rank,
                        historical_frequency=freq,
                        adjusted_score=adjusted_score,
                    )
                )

        return candidates

    def update_with_result(
        self,
        connection: Any,
        draw_id: UUID,
    ) -> list[DigitalRootRelation]:
        """Update relations with actual draw result.

        Args:
            connection: Database connection
            draw_id: Draw that was just settled

        Returns:
            List of relations whose status changed
        """
        # Load the draw result
        row = connection.execute(
            """SELECT d.draw_id, d.draw_type_id, d.scheduled_date,
                      dn.number, dn.position
               FROM core.draws d
               JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
               JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
               WHERE d.draw_id = %s
                 AND dv.validation_status = 'VALID'
                 AND dn.number_role = 'WINNING'
               ORDER BY dn.position""",
            (draw_id,),
        ).fetchall()

        if not row:
            return []

        draw_record = {
            "draw_id": row[0][0],
            "draw_type_id": row[0][1],
            "scheduled_date": row[0][2],
            "winning_numbers": [r[3] for r in row],
        }

        return self.relation_discovery.update_with_new_draw(draw_record)
