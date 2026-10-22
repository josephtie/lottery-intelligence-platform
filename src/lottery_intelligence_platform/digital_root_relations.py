"""Temporary relation discovery for digital root patterns.

Discovers and tracks temporary relationships between digital roots across:
- Same game successive draws
- Different games on same day
- Time slot relationships
- Root transitions and repetitions

All relations are time-limited (2-3 day observation window) and must be
continuously validated against new data. Relations expire if evidence weakens.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from lottery_intelligence_platform.digital_root import get_root_fast


class RelationType(Enum):
    """Types of relations to discover."""
    SAME_GAME_SUCCESSIVE = "SAME_GAME_SUCCESSIVE"  # Consecutive draws of same game
    CROSS_GAME_SAME_DAY = "CROSS_GAME_SAME_DAY"  # Different games, same calendar day
    TIME_SLOT = "TIME_SLOT"  # Same time slot across days
    ROOT_TRANSITION = "ROOT_TRANSITION"  # Pattern in root sequence
    POSITION_ASSOCIATION = "POSITION_ASSOCIATION"  # Root association with winning position


class RelationStatus(Enum):
    """Lifecycle status of a relation."""
    CANDIDATE = "CANDIDATE"  # Newly discovered, needs validation
    OBSERVING = "OBSERVING"  # Active observation window
    WEAKENING = "WEAKENING"  # Evidence declining
    EXPIRED = "EXPIRED"  # Observation window closed without confirmation
    CONFIRMED_TEMPORARY = "CONFIRMED_TEMPORARY"  # Validated but time-limited
    REJECTED = "REJECTED"  # Failed statistical validation


@dataclass(frozen=True, slots=True)
class RelationKey:
    """Unique identifier for a relation."""
    relation_type: RelationType
    source_game_id: UUID | None
    target_game_id: UUID | None
    source_root: int
    target_root: int
    position: int | None = None  # For position-sensitive relations
    time_slot: str | None = None  # For time slot relations

    def __str__(self) -> str:
        parts = [self.relation_type.value]
        if self.source_game_id:
            parts.append(f"src={self.source_game_id}")
        if self.target_game_id:
            parts.append(f"tgt={self.target_game_id}")
        parts.append(f"{self.source_root}→{self.target_root}")
        if self.position is not None:
            parts.append(f"pos={self.position}")
        if self.time_slot:
            parts.append(f"slot={self.time_slot}")
        return ":".join(parts)


@dataclass(slots=True)
class RelationEvidence:
    """Evidence supporting a relation."""
    total_observations: int = 0
    successful_predictions: int = 0
    last_observed_at: datetime | None = None
    discovery_date: date = field(default_factory=date.today)
    last_validation_date: date | None = None
    observation_window_days: int = 3  # Default 3-day window

    @property
    def success_rate(self) -> float:
        """Current success rate."""
        if self.total_observations == 0:
            return 0.0
        return self.successful_predictions / self.total_observations

    @property
    def age_days(self) -> int:
        """Days since discovery."""
        return (date.today() - self.discovery_date).days

    @property
    def is_expired(self) -> bool:
        """Check if observation window has expired."""
        return self.age_days > self.observation_window_days

    def add_observation(self, success: bool, observed_at: datetime | None = None) -> None:
        """Add a new observation."""
        self.total_observations += 1
        if success:
            self.successful_predictions += 1
        self.last_observed_at = observed_at or datetime.now()
        self.last_validation_date = date.today()


@dataclass(slots=True)
class DigitalRootRelation:
    """A temporary relation between digital roots."""
    relation_id: UUID = field(default_factory=uuid4)
    key: RelationKey = field(default_factory=lambda: RelationKey(
        relation_type=RelationType.SAME_GAME_SUCCESSIVE,
        source_game_id=None,
        target_game_id=None,
        source_root=0,
        target_root=0
    ))
    status: RelationStatus = RelationStatus.CANDIDATE
    evidence: RelationEvidence = field(default_factory=RelationEvidence)
    baseline_success_rate: float = 0.0  # Random baseline for comparison
    statistical_significance: float = 0.0  # P-value or similar metric
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_status(self) -> None:
        """Update status based on evidence and age."""
        if self.evidence.is_expired:
            if self.evidence.success_rate > self.baseline_success_rate * 1.5:
                self.status = RelationStatus.CONFIRMED_TEMPORARY
            else:
                self.status = RelationStatus.EXPIRED
            return

        if self.evidence.total_observations < 5:
            self.status = RelationStatus.CANDIDATE
            return

        current_rate = self.evidence.success_rate
        if current_rate < self.baseline_success_rate * 0.8:
            self.status = RelationStatus.WEAKENING
        elif current_rate > self.baseline_success_rate * 1.2:
            self.status = RelationStatus.OBSERVING
        else:
            self.status = RelationStatus.CANDIDATE

    def should_use_for_prediction(self) -> bool:
        """Check if relation should be used for predictions."""
        return self.status in (
            RelationStatus.OBSERVING,
            RelationStatus.CONFIRMED_TEMPORARY,
        )


class RelationDiscovery:
    """Discovers and tracks temporary digital root relations."""

    def __init__(self, *, observation_window_days: int = 3, min_observations: int = 5):
        self.observation_window_days = observation_window_days
        self.min_observations = min_observations
        self.relations: dict[RelationKey, DigitalRootRelation] = {}

    def discover_relations(
        self,
        historical_data: list[dict[str, Any]],
    ) -> list[DigitalRootRelation]:
        """Discover new relations from historical data.

        Args:
            historical_data: List of draw records with:
                - draw_id
                - draw_type_id
                - scheduled_date
                - winning_numbers (ordered list)
                - time_slot (optional)

        Returns:
            List of newly discovered relations
        """
        new_relations = []

        # Group by game type and date
        by_game: dict[UUID, list[dict]] = {}
        by_date: dict[date, list[dict]] = {}

        for draw in historical_data:
            game_id = draw["draw_type_id"]
            draw_date = draw["scheduled_date"]

            by_game.setdefault(game_id, []).append(draw)
            by_date.setdefault(draw_date, []).append(draw)

        # Discover same-game successive relations
        for game_id, draws in by_game.items():
            draws_sorted = sorted(draws, key=lambda d: d["scheduled_date"])
            for i in range(len(draws_sorted) - 1):
                current = draws_sorted[i]
                next_draw = draws_sorted[i + 1]

                current_roots = [get_root_fast(n) for n in current["winning_numbers"]]
                next_roots = [get_root_fast(n) for n in next_draw["winning_numbers"]]

                # Check for root transitions
                for pos, (cr, nr) in enumerate(zip(current_roots, next_roots)):
                    if pos >= len(next_roots):
                        break

                    key = RelationKey(
                        relation_type=RelationType.SAME_GAME_SUCCESSIVE,
                        source_game_id=game_id,
                        target_game_id=game_id,
                        source_root=cr,
                        target_root=nr,
                        position=pos,
                    )

                    if key not in self.relations:
                        # Calculate baseline for this root transition
                        baseline = self._calculate_baseline(
                            historical_data,
                            source_root=cr,
                            target_root=nr,
                            relation_type=RelationType.SAME_GAME_SUCCESSIVE,
                        )

                        relation = DigitalRootRelation(
                            key=key,
                            status=RelationStatus.CANDIDATE,
                            evidence=RelationEvidence(
                                discovery_date=current["scheduled_date"],
                                observation_window_days=self.observation_window_days,
                            ),
                            baseline_success_rate=baseline,
                        )
                        self.relations[key] = relation
                        new_relations.append(relation)

        # Discover cross-game same-day relations
        for draw_date, draws in by_date.items():
            if len(draws) < 2:
                continue

            for i, draw1 in enumerate(draws):
                for draw2 in draws[i + 1:]:
                    roots1 = [get_root_fast(n) for n in draw1["winning_numbers"]]
                    roots2 = [get_root_fast(n) for n in draw2["winning_numbers"]]

                    for r1 in roots1:
                        for r2 in roots2:
                            key = RelationKey(
                                relation_type=RelationType.CROSS_GAME_SAME_DAY,
                                source_game_id=draw1["draw_type_id"],
                                target_game_id=draw2["draw_type_id"],
                                source_root=r1,
                                target_root=r2,
                            )

                            if key not in self.relations:
                                baseline = self._calculate_baseline(
                                    historical_data,
                                    source_root=r1,
                                    target_root=r2,
                                    relation_type=RelationType.CROSS_GAME_SAME_DAY,
                                )

                                relation = DigitalRootRelation(
                                    key=key,
                                    status=RelationStatus.CANDIDATE,
                                    evidence=RelationEvidence(
                                        discovery_date=draw_date,
                                        observation_window_days=self.observation_window_days,
                                    ),
                                    baseline_success_rate=baseline,
                                )
                                self.relations[key] = relation
                                new_relations.append(relation)

        return new_relations

    def _calculate_baseline(
        self,
        historical_data: list[dict[str, Any]],
        source_root: int,
        target_root: int,
        relation_type: RelationType,
        samples: int = 1000,
    ) -> float:
        """Calculate random baseline success rate for Monte Carlo comparison.

        Args:
            historical_data: Historical draw data
            source_root: Source digital root
            target_root: Target digital root
            relation_type: Type of relation
            samples: Number of Monte Carlo samples

        Returns:
            Baseline success rate (0-1)
        """
        if not historical_data:
            return 0.1  # Conservative default

        # Extract all roots from historical data
        all_roots = []
        for draw in historical_data:
            all_roots.extend([get_root_fast(n) for n in draw["winning_numbers"]])

        if not all_roots:
            return 0.1

        # Monte Carlo simulation: randomly pick source, count how often target appears
        successes = 0
        total = 0

        for _ in range(samples):
            # Randomly pick a source root from distribution
            source = random.choice(all_roots)

            # Check if this specific source-target pair would match by chance
            # For same-game successive: probability of seeing target_root in next draw
            # For cross-game: probability of seeing target_root in other game

            # Simplified: just check frequency of target_root
            target_count = all_roots.count(target_root)
            probability = target_count / len(all_roots)

            if source == source_root:
                total += 1
                if random.random() < probability:
                    successes += 1

        return successes / total if total > 0 else 0.1

    def update_with_new_draw(self, draw: dict[str, Any]) -> list[DigitalRootRelation]:
        """Update all relations with a new draw result.

        Args:
            draw: New draw record

        Returns:
            List of relations whose status changed
        """
        changed_relations = []
        draw_roots = [get_root_fast(n) for n in draw["winning_numbers"]]

        for relation in self.relations.values():
            if not relation.should_use_for_prediction():
                continue

            # Check if this draw tests this relation
            tested = False
            success = False

            if relation.key.relation_type == RelationType.SAME_GAME_SUCCESSIVE:
                if relation.key.target_game_id == draw["draw_type_id"]:
                    # Check if target root appears in this draw
                    if relation.key.target_root in draw_roots:
                        if relation.key.position is not None:
                            # Position-sensitive check
                            if relation.key.position < len(draw_roots):
                                tested = True
                                success = draw_roots[relation.key.position] == relation.key.target_root
                        else:
                            tested = True
                            success = True

            elif relation.key.relation_type == RelationType.CROSS_GAME_SAME_DAY:
                if relation.key.target_game_id == draw["draw_type_id"]:
                    if relation.key.target_root in draw_roots:
                        tested = True
                        success = True

            if tested:
                relation.evidence.add_observation(success, datetime.now())
                old_status = relation.status
                relation.update_status()
                if old_status != relation.status:
                    changed_relations.append(relation)

        # Clean up expired relations
        self._cleanup_expired()

        return changed_relations

    def _cleanup_expired(self) -> None:
        """Remove expired and rejected relations."""
        to_remove = [
            key for key, rel in self.relations.items()
            if rel.status in (RelationStatus.EXPIRED, RelationStatus.REJECTED)
        ]
        for key in to_remove:
            del self.relations[key]

    def get_active_relations(self, *, game_id: UUID | None = None) -> list[DigitalRootRelation]:
        """Get relations that should be used for predictions.

        Args:
            game_id: Optional filter by game

        Returns:
            List of active relations
        """
        active = [
            rel for rel in self.relations.values()
            if rel.should_use_for_prediction()
        ]

        if game_id is not None:
            active = [rel for rel in active if rel.key.target_game_id == game_id]

        return sorted(
            active,
            key=lambda r: (r.evidence.success_rate, -r.evidence.age_days),
            reverse=True,
        )

    def predict_roots(
        self,
        game_id: UUID,
        position: int | None = None,
        top_k: int = 5,
    ) -> list[tuple[int, float, DigitalRootRelation]]:
        """Predict digital roots for a target game.

        Args:
            game_id: Target game type
            position: Optional position filter
            top_k: Number of top predictions to return

        Returns:
            List of (root, confidence_score, supporting_relation) tuples
        """
        active_relations = self.get_active_relations(game_id=game_id)

        # Aggregate predictions by root
        root_scores: dict[int, list[tuple[float, DigitalRootRelation]]] = {}

        for relation in active_relations:
            if position is not None and relation.key.position != position:
                continue

            root = relation.key.target_root
            confidence = relation.evidence.success_rate - relation.baseline_success_rate

            if confidence > 0:
                root_scores.setdefault(root, []).append((confidence, relation))

        # Sort roots by aggregated confidence
        ranked_roots = []
        for root, scores in root_scores.items():
            avg_confidence = sum(s for s, _ in scores) / len(scores)
            best_relation = max(scores, key=lambda x: x[0])[1]
            ranked_roots.append((root, avg_confidence, best_relation))

        ranked_roots.sort(key=lambda x: x[1], reverse=True)

        return ranked_roots[:top_k]
