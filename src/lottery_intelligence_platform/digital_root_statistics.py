"""Digital Root Statistics for Lottery Edge Lab.

Analyzes digital root patterns in historical lottery results across multiple
time windows (10, 30, 45, 60, 90 days). Provides descriptive statistics
without assuming predictive power.

Key principles:
- Separate analysis by game and position
- Compare nested time windows (not independent samples)
- Distinguish descriptive observation from prediction
- Use actual calendar days, not arbitrary draw counts
- Show sample sizes alongside percentages
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from lottery_intelligence_platform.digital_root import (
    NumberWithRoot,
    get_numbers_by_root_fast,
    get_root_fast,
    transform_sequence,
)


TIME_WINDOWS = [10, 30, 45, 60, 90]
ROOT_RANGE = range(9)  # 0-8 (9 is represented as 0)


@dataclass(frozen=True, slots=True)
class RootDistribution:
    """Distribution of a single root."""
    root: int
    occurrences: int
    percentage: float
    draws_containing: int
    deviation_from_reference: float  # Percentage points from expected


@dataclass(frozen=True, slots=True)
class PositionDistribution:
    """Root distribution for a specific position."""
    position: int
    root_counts: dict[int, int]  # root → count
    root_percentages: dict[int, float]  # root → percentage
    most_frequent_root: int
    sample_size: int


@dataclass(frozen=True, slots=True)
class DrawSignature:
    """Digital root signature of a single draw."""
    draw_id: UUID
    draw_type_id: UUID
    scheduled_date: date
    original_numbers: list[int]
    root_sequence: list[int]
    distinct_roots: int
    root_repetitions: dict[int, int]  # root → count of repetitions


@dataclass(frozen=True, slots=True)
class TemporalChange:
    """Change in root frequency between time windows."""
    root: int
    window_from: int  # e.g., 30
    window_to: int  # e.g., 10
    percentage_change: float  # percentage points
    trend: str  # "up", "down", "stable"
    sample_size_from: int
    sample_size_to: int


@dataclass(frozen=True, slots=True)
class FamilyFrequency:
    """Frequency of a number family (all numbers with same root)."""
    root: int
    family_numbers: list[int]
    total_occurrences: int
    frequency_by_position: dict[int, float]
    frequency_by_game: dict[UUID, float]
    frequency_by_window: dict[int, float]


@dataclass(frozen=True, slots=True)
class TransitionMatrix:
    """Transition matrix between roots."""
    source_root: int
    target_counts: dict[int, int]  # target_root → count
    conditional_probabilities: dict[int, float]  # target_root → P(target|source)
    total_observations: int


@dataclass(slots=True)
class WindowStatistics:
    """Statistics for a single time window."""
    window_days: int
    reference_date: date
    start_date: date
    end_date: date
    draw_count: int
    total_numbers_analyzed: int

    # Global distribution
    global_distribution: list[RootDistribution] = field(default_factory=list)

    # Position-specific distributions
    position_distributions: dict[int, PositionDistribution] = field(default_factory=dict)

    # Draw signatures
    draw_signatures: list[DrawSignature] = field(default_factory=list)

    # Number family frequencies
    family_frequencies: dict[int, FamilyFrequency] = field(default_factory=dict)

    # Data quality flags
    has_duplicate_draws: bool = False
    has_missing_dates: bool = False
    data_quality_score: float = 1.0  # 0-1


@dataclass(slots=True)
class GameStatistics:
    """Complete statistics for a single game."""
    game_id: UUID
    game_name: str
    reference_date: date
    windows: dict[int, WindowStatistics] = field(default_factory=dict)

    # Temporal evolution
    temporal_changes: list[TemporalChange] = field(default_factory=list)

    # Transition matrices
    transition_matrices: dict[int, TransitionMatrix] = field(default_factory=dict)


class DigitalRootStatistics:
    """Analyzer for digital root statistics across time windows."""

    def __init__(self, *, time_windows: list[int] | None = None):
        self.time_windows = time_windows or TIME_WINDOWS
        self._cache: dict[tuple[UUID, date], GameStatistics] = {}

    def calculate_game_statistics(
        self,
        connection: Any,
        game_id: UUID,
        reference_date: date,
    ) -> GameStatistics:
        """Calculate complete statistics for a game.

        Args:
            connection: Database connection
            game_id: Game type to analyze
            reference_date: Reference date for windows (exclusive)

        Returns:
            Complete game statistics
        """
        cache_key = (game_id, reference_date)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Get game name
        game_name = connection.execute(
            "SELECT display_name FROM catalog.draw_types WHERE draw_type_id = %s",
            (game_id,),
        ).fetchone()[0]

        stats = GameStatistics(
            game_id=game_id,
            game_name=game_name,
            reference_date=reference_date,
        )

        # Calculate statistics for each time window
        for window_days in self.time_windows:
            window_stats = self._calculate_window_statistics(
                connection,
                game_id,
                reference_date,
                window_days,
            )
            stats.windows[window_days] = window_stats

        # Calculate temporal evolution between windows
        stats.temporal_changes = self._calculate_temporal_evolution(stats.windows)

        # Calculate transition matrices
        stats.transition_matrices = self._calculate_transition_matrices(
            connection,
            game_id,
            reference_date,
        )

        self._cache[cache_key] = stats
        return stats

    def _calculate_window_statistics(
        self,
        connection: Any,
        game_id: UUID,
        reference_date: date,
        window_days: int,
    ) -> WindowStatistics:
        """Calculate statistics for a single time window.

        Args:
            connection: Database connection
            game_id: Game type
            reference_date: Reference date (exclusive)
            window_days: Number of calendar days

        Returns:
            Window statistics
        """
        end_date = reference_date - timedelta(days=1)  # Exclusive
        start_date = end_date - timedelta(days=window_days - 1)  # Inclusive

        # Load draws in the window
        draws = connection.execute(
            """SELECT d.draw_id, d.draw_type_id, d.scheduled_date,
                      dn.number, dn.position
               FROM core.draws d
               JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
               JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
               WHERE d.draw_type_id = %s
                 AND d.scheduled_date >= %s
                 AND d.scheduled_date <= %s
                 AND d.status = 'SETTLED'
                 AND dv.validation_status = 'VALID'
                 AND dn.number_role = 'WINNING'
               ORDER BY d.scheduled_date, dv.version_number DESC, dn.position""",
            (game_id, start_date, end_date),
        ).fetchall()

        # Aggregate by draw
        draws_dict: dict[UUID, dict] = {}
        draw_ids: set[UUID] = set()

        for row in draws:
            draw_id, draw_type_id, scheduled_date, number, position = row
            draw_ids.add(draw_id)

            if draw_id not in draws_dict:
                draws_dict[draw_id] = {
                    "draw_id": draw_id,
                    "draw_type_id": draw_type_id,
                    "scheduled_date": scheduled_date,
                    "winning_numbers": [],
                }
            draws_dict[draw_id]["winning_numbers"].append(number)

        # Check for data quality issues
        has_duplicate_draws = len(draw_ids) != len(draws_dict)
        has_missing_dates = any(
            d["scheduled_date"] is None for d in draws_dict.values()
        )
        data_quality_score = 1.0
        if has_duplicate_draws:
            data_quality_score -= 0.3
        if has_missing_dates:
            data_quality_score -= 0.3

        window_stats = WindowStatistics(
            window_days=window_days,
            reference_date=reference_date,
            start_date=start_date,
            end_date=end_date,
            draw_count=len(draws_dict),
            total_numbers_analyzed=sum(len(d["winning_numbers"]) for d in draws_dict.values()),
            has_duplicate_draws=has_duplicate_draws,
            has_missing_dates=has_missing_dates,
            data_quality_score=data_quality_score,
        )

        if not draws_dict:
            return window_stats

        # Calculate global distribution
        window_stats.global_distribution = self._calculate_global_distribution(
            draws_dict.values(),
        )

        # Calculate position-specific distributions
        window_stats.position_distributions = self._calculate_position_distributions(
            draws_dict.values(),
        )

        # Calculate draw signatures
        window_stats.draw_signatures = self._calculate_draw_signatures(
            draws_dict.values(),
        )

        # Calculate family frequencies
        window_stats.family_frequencies = self._calculate_family_frequencies(
            draws_dict.values(),
            game_id,
        )

        return window_stats

    def _calculate_global_distribution(
        self,
        draws: list[dict],
    ) -> list[RootDistribution]:
        """Calculate global root distribution.

        Args:
            draws: List of draw records

        Returns:
            List of root distributions
        """
        total_numbers = sum(len(d["winning_numbers"]) for d in draws)
        root_counter = Counter()
        draws_with_root: dict[int, set[UUID]] = defaultdict(set)

        for draw in draws:
            roots_seen = set()
            for number in draw["winning_numbers"]:
                root = get_root_fast(number)
                root_counter[root] += 1
                roots_seen.add(root)

            for root in roots_seen:
                draws_with_root[root].add(draw["draw_id"])

        # Expected frequency: each root has 10 numbers out of 90
        expected_percentage = 10.0 / 90.0 * 100.0

        distributions = []
        for root in ROOT_RANGE:
            count = root_counter[root]
            percentage = (count / total_numbers * 100.0) if total_numbers > 0 else 0.0
            draws_containing = len(draws_with_root[root])
            deviation = percentage - expected_percentage

            distributions.append(
                RootDistribution(
                    root=root,
                    occurrences=count,
                    percentage=percentage,
                    draws_containing=draws_containing,
                    deviation_from_reference=deviation,
                )
            )

        return sorted(distributions, key=lambda d: d.root)

    def _calculate_position_distributions(
        self,
        draws: list[dict],
    ) -> dict[int, PositionDistribution]:
        """Calculate position-specific root distributions.

        Args:
            draws: List of draw records

        Returns:
            Dictionary mapping position → distribution
        """
        position_data: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))

        for draw in draws:
            for position, number in enumerate(draw["winning_numbers"]):
                root = get_root_fast(number)
                position_data[position][root] += 1

        distributions = {}
        for position, root_counts in position_data.items():
            total = sum(root_counts.values())
            root_percentages = {
                root: (count / total * 100.0) if total > 0 else 0.0
                for root, count in root_counts.items()
            }
            most_frequent = max(root_counts.items(), key=lambda x: x[1])[0] if root_counts else 0

            distributions[position] = PositionDistribution(
                position=position,
                root_counts=dict(root_counts),
                root_percentages=root_percentages,
                most_frequent_root=most_frequent,
                sample_size=total,
            )

        return distributions

    def _calculate_draw_signatures(
        self,
        draws: list[dict],
    ) -> list[DrawSignature]:
        """Calculate digital root signatures for each draw.

        Args:
            draws: List of draw records

        Returns:
            List of draw signatures
        """
        signatures = []

        for draw in draws:
            numbers = draw["winning_numbers"]
            root_sequence = [get_root_fast(n) for n in numbers]
            distinct_roots = len(set(root_sequence))
            repetitions = Counter(root_sequence)

            signatures.append(
                DrawSignature(
                    draw_id=draw["draw_id"],
                    draw_type_id=draw["draw_type_id"],
                    scheduled_date=draw["scheduled_date"],
                    original_numbers=numbers,
                    root_sequence=root_sequence,
                    distinct_roots=distinct_roots,
                    root_repetitions=dict(repetitions),
                )
            )

        return sorted(signatures, key=lambda s: s.scheduled_date, reverse=True)

    def _calculate_family_frequencies(
        self,
        draws: list[dict],
        game_id: UUID,
    ) -> dict[int, FamilyFrequency]:
        """Calculate frequency of number families by root.

        Args:
            draws: List of draw records
            game_id: Game type

        Returns:
            Dictionary mapping root → family frequency
        """
        family_frequencies = {}

        for root in ROOT_RANGE:
            family_numbers = get_numbers_by_root_fast(root)

            # Count occurrences
            total_occurrences = 0
            position_counts: dict[int, int] = defaultdict(int)

            for draw in draws:
                for position, number in enumerate(draw["winning_numbers"]):
                    if number in family_numbers:
                        total_occurrences += 1
                        position_counts[position] += 1

            # Calculate frequencies by position
            total = sum(position_counts.values())
            frequency_by_position = {
                pos: (count / total * 100.0) if total > 0 else 0.0
                for pos, count in position_counts.items()
            }

            family_frequencies[root] = FamilyFrequency(
                root=root,
                family_numbers=family_numbers,
                total_occurrences=total_occurrences,
                frequency_by_position=frequency_by_position,
                frequency_by_game={game_id: (total_occurrences / total * 100.0) if total > 0 else 0.0},
                frequency_by_window={},  # Will be filled by caller
            )

        return family_frequencies

    def _calculate_temporal_evolution(
        self,
        windows: dict[int, WindowStatistics],
    ) -> list[TemporalChange]:
        """Calculate temporal changes between time windows.

        Args:
            windows: Dictionary of window_days → WindowStatistics

        Returns:
            List of temporal changes
        """
        changes = []
        sorted_windows = sorted(windows.keys())

        for i in range(len(sorted_windows) - 1):
            window_from = sorted_windows[i + 1]  # Larger window
            window_to = sorted_windows[i]  # Smaller window

            stats_from = windows[window_from]
            stats_to = windows[window_to]

            # Map root → percentage
            percentages_from = {d.root: d.percentage for d in stats_from.global_distribution}
            percentages_to = {d.root: d.percentage for d in stats_to.global_distribution}

            for root in ROOT_RANGE:
                pct_from = percentages_from.get(root, 0.0)
                pct_to = percentages_to.get(root, 0.0)
                change = pct_to - pct_from

                if abs(change) < 0.5:  # Less than 0.5 percentage points
                    trend = "stable"
                elif change > 0:
                    trend = "up"
                else:
                    trend = "down"

                changes.append(
                    TemporalChange(
                        root=root,
                        window_from=window_from,
                        window_to=window_to,
                        percentage_change=change,
                        trend=trend,
                        sample_size_from=stats_from.total_numbers_analyzed,
                        sample_size_to=stats_to.total_numbers_analyzed,
                    )
                )

        return changes

    def _calculate_transition_matrices(
        self,
        connection: Any,
        game_id: UUID,
        reference_date: date,
    ) -> dict[int, TransitionMatrix]:
        """Calculate transition matrices between roots in successive draws.

        Args:
            connection: Database connection
            game_id: Game type
            reference_date: Reference date

        Returns:
            Dictionary mapping source_root → transition matrix
        """
        # Get successive draws
        draws = connection.execute(
            """SELECT d.draw_id, d.scheduled_date,
                      dn.number, dn.position
               FROM core.draws d
               JOIN core.draw_versions dv ON dv.draw_id = d.draw_id
               JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
               WHERE d.draw_type_id = %s
                 AND d.scheduled_date < %s
                 AND d.status = 'SETTLED'
                 AND dv.validation_status = 'VALID'
                 AND dn.number_role = 'WINNING'
               ORDER BY d.scheduled_date DESC, dv.version_number DESC, dn.position
               LIMIT 200""",
            (game_id, reference_date),
        ).fetchall()

        # Aggregate by draw
        draws_dict: dict[UUID, dict] = {}
        for row in draws:
            draw_id, scheduled_date, number, position = row
            if draw_id not in draws_dict:
                draws_dict[draw_id] = {
                    "scheduled_date": scheduled_date,
                    "winning_numbers": [],
                }
            draws_dict[draw_id]["winning_numbers"].append(number)

        # Sort by date
        sorted_draws = sorted(
            draws_dict.values(),
            key=lambda d: d["scheduled_date"],
        )

        # Calculate transitions
        transition_counts: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))

        for i in range(len(sorted_draws) - 1):
            current_draw = sorted_draws[i]
            next_draw = sorted_draws[i + 1]

            # Get roots from current draw (first position only for simplicity)
            if current_draw["winning_numbers"]:
                current_root = get_root_fast(current_draw["winning_numbers"][0])

                # Get roots from next draw
                if next_draw["winning_numbers"]:
                    next_root = get_root_fast(next_draw["winning_numbers"][0])
                    transition_counts[current_root][next_root] += 1

        # Build transition matrices
        matrices = {}
        for source_root in ROOT_RANGE:
            target_counts = dict(transition_counts[source_root])
            total = sum(target_counts.values())

            conditional_probs = {}
            if total > 0:
                conditional_probs = {
                    target: (count / total)
                    for target, count in target_counts.items()
                }

            matrices[source_root] = TransitionMatrix(
                source_root=source_root,
                target_counts=target_counts,
                conditional_probabilities=conditional_probs,
                total_observations=total,
            )

        return matrices
