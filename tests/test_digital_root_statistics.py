"""Tests for Digital Root Statistics module."""

import pytest
from datetime import date, timedelta
from uuid import uuid4

from lottery_intelligence_platform.digital_root_statistics import (
    DigitalRootStatistics,
    GameStatistics,
    WindowStatistics,
    RootDistribution,
    PositionDistribution,
    DrawSignature,
    TemporalChange,
    FamilyFrequency,
    TransitionMatrix,
)


class TestWindowStatistics:
    """Test WindowStatistics dataclass."""

    def test_window_creation(self):
        """Test creating a window statistics object."""
        window = WindowStatistics(
            window_days=30,
            reference_date=date(2024, 1, 31),
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            draw_count=10,
            total_numbers_analyzed=50,
        )

        assert window.window_days == 30
        assert window.draw_count == 10
        assert window.total_numbers_analyzed == 50
        assert window.data_quality_score == 1.0


class TestGameStatistics:
    """Test GameStatistics dataclass."""

    def test_game_stats_creation(self):
        """Test creating game statistics."""
        game_id = uuid4()
        stats = GameStatistics(
            game_id=game_id,
            game_name="Test Game",
            reference_date=date(2024, 1, 31),
        )

        assert stats.game_id == game_id
        assert stats.game_name == "Test Game"
        assert len(stats.windows) == 0


class TestDigitalRootStatistics:
    """Test DigitalRootStatistics analyzer."""

    def test_initialization(self):
        """Test analyzer initialization."""
        analyzer = DigitalRootStatistics()
        assert analyzer.time_windows == [10, 30, 45, 60, 90]
        assert len(analyzer._cache) == 0

    def test_custom_time_windows(self):
        """Test custom time windows."""
        analyzer = DigitalRootStatistics(time_windows=[7, 14, 30])
        assert analyzer.time_windows == [7, 14, 30]

    def test_calculate_window_bounds(self):
        """Test calculation of window date bounds."""
        analyzer = DigitalRootStatistics()
        reference_date = date(2024, 1, 31)

        # For 10-day window
        end_date = reference_date - timedelta(days=1)  # Jan 30
        start_date = end_date - timedelta(days=9)  # Jan 21

        assert end_date == date(2024, 1, 30)
        assert start_date == date(2024, 1, 21)


class TestRootDistribution:
    """Test RootDistribution dataclass."""

    def test_root_distribution(self):
        """Test root distribution creation."""
        dist = RootDistribution(
            root=3,
            occurrences=25,
            percentage=11.11,
            draws_containing=8,
            deviation_from_reference=1.11,
        )

        assert dist.root == 3
        assert dist.occurrences == 25
        assert dist.percentage == 11.11
        assert dist.deviation_from_reference == 1.11


class TestPositionDistribution:
    """Test PositionDistribution dataclass."""

    def test_position_distribution(self):
        """Test position distribution creation."""
        dist = PositionDistribution(
            position=0,
            root_counts={0: 5, 1: 3, 2: 2},
            root_percentages={0: 50.0, 1: 30.0, 2: 20.0},
            most_frequent_root=0,
            sample_size=10,
        )

        assert dist.position == 0
        assert dist.most_frequent_root == 0
        assert dist.sample_size == 10


class TestDrawSignature:
    """Test DrawSignature dataclass."""

    def test_draw_signature(self):
        """Test draw signature creation."""
        signature = DrawSignature(
            draw_id=uuid4(),
            draw_type_id=uuid4(),
            scheduled_date=date(2024, 1, 15),
            original_numbers=[12, 23, 34, 45, 56],
            root_sequence=[3, 5, 7, 0, 2],
            distinct_roots=5,
            root_repetitions={},
        )

        assert signature.distinct_roots == 5
        assert len(signature.root_sequence) == 5
        assert len(signature.original_numbers) == 5


class TestTemporalChange:
    """Test TemporalChange dataclass."""

    def test_temporal_change(self):
        """Test temporal change creation."""
        change = TemporalChange(
            root=3,
            window_from=30,
            window_to=10,
            percentage_change=2.5,
            trend="up",
            sample_size_from=300,
            sample_size_to=100,
        )

        assert change.root == 3
        assert change.trend == "up"
        assert change.percentage_change == 2.5


class TestFamilyFrequency:
    """Test FamilyFrequency dataclass."""

    def test_family_frequency(self):
        """Test family frequency creation."""
        family = FamilyFrequency(
            root=3,
            family_numbers=[3, 12, 21, 30, 39, 48, 57, 66, 75, 84],
            total_occurrences=50,
            frequency_by_position={0: 20.0, 1: 15.0},
            frequency_by_game={},
            frequency_by_window={},
        )

        assert family.root == 3
        assert len(family.family_numbers) == 10
        assert family.total_occurrences == 50


class TestTransitionMatrix:
    """Test TransitionMatrix dataclass."""

    def test_transition_matrix(self):
        """Test transition matrix creation."""
        matrix = TransitionMatrix(
            source_root=3,
            target_counts={0: 5, 1: 3, 2: 2},
            conditional_probabilities={0: 0.5, 1: 0.3, 2: 0.2},
            total_observations=10,
        )

        assert matrix.source_root == 3
        assert matrix.total_observations == 10
        assert matrix.conditional_probabilities[0] == 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
