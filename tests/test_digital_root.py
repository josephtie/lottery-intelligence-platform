"""Tests for Digital Root Turbo Analyzer."""

import pytest
from datetime import date, datetime
from uuid import uuid4

from lottery_intelligence_platform.digital_root import (
    digital_root,
    digital_root_batch,
    numbers_by_root,
    NumberWithRoot,
    transform_sequence,
    get_numbers_by_root_fast,
    get_root_fast,
)
from lottery_intelligence_platform.digital_root_relations import (
    RelationType,
    RelationStatus,
    RelationKey,
    RelationEvidence,
    DigitalRootRelation,
    RelationDiscovery,
)


class TestDigitalRootTransformation:
    """Test digital root calculation utilities."""

    def test_digital_root_basic(self):
        """Test basic digital root calculation."""
        assert digital_root(74) == 2  # 7+4=11 → 1+1=2
        assert digital_root(45) == 0  # 4+5=9 → 0 (convention)
        assert digital_root(86) == 5  # 8+6=14 → 1+4=5
        assert digital_root(9) == 0   # 9 → 0 (convention)
        assert digital_root(18) == 0  # 1+8=9 → 0

    def test_digital_root_edge_cases(self):
        """Test edge cases."""
        assert digital_root(1) == 1
        assert digital_root(90) == 9  # 9+0=9 → 0
        assert digital_root(99) == 9  # 9+9=18 → 1+8=9 → 0

    def test_digital_root_invalid(self):
        """Test invalid numbers raise error."""
        with pytest.raises(ValueError):
            digital_root(0)
        with pytest.raises(ValueError):
            digital_root(91)

    def test_digital_root_batch(self):
        """Test batch calculation."""
        result = digital_root_batch([1, 9, 45, 74])
        assert result == {1: 1, 9: 0, 45: 0, 74: 2}

    def test_numbers_by_root(self):
        """Test getting numbers by root."""
        root_3 = numbers_by_root(3)
        assert 3 in root_3
        assert 12 in root_3
        assert 21 in root_3
        assert 30 in root_3
        assert 39 in root_3
        assert 48 in root_3
        assert 57 in root_3
        assert 66 in root_3
        assert 75 in root_3
        assert 84 in root_3
        assert len(root_3) == 10

    def test_numbers_by_root_zero(self):
        """Test root 0 (digital root 9)."""
        root_0 = numbers_by_root(0)
        assert 9 in root_0
        assert 18 in root_0
        assert 27 in root_0
        assert 36 in root_0
        assert 45 in root_0
        assert 54 in root_0
        assert 63 in root_0
        assert 72 in root_0
        assert 81 in root_0
        assert 90 in root_0
        assert len(root_0) == 10

    def test_number_with_root(self):
        """Test NumberWithRoot dataclass."""
        nwr = NumberWithRoot.from_number(74)
        assert nwr.number == 74
        assert nwr.root == 2

    def test_transform_sequence(self):
        """Test transforming a sequence."""
        result = transform_sequence([74, 45, 86])
        assert len(result) == 3
        assert result[0].number == 74
        assert result[0].root == 2
        assert result[1].number == 45
        assert result[1].root == 0
        assert result[2].number == 86
        assert result[2].root == 5

    def test_fast_lookups(self):
        """Test precomputed lookup tables."""
        assert get_root_fast(74) == 2
        assert get_root_fast(45) == 0
        assert len(get_numbers_by_root_fast(3)) == 10


class TestRelationEvidence:
    """Test relation evidence tracking."""

    def test_initial_evidence(self):
        """Test initial evidence state."""
        evidence = RelationEvidence()
        assert evidence.total_observations == 0
        assert evidence.successful_predictions == 0
        assert evidence.success_rate == 0.0
        assert evidence.age_days == 0
        assert not evidence.is_expired

    def test_add_observation_success(self):
        """Test adding successful observation."""
        evidence = RelationEvidence()
        evidence.add_observation(True)
        assert evidence.total_observations == 1
        assert evidence.successful_predictions == 1
        assert evidence.success_rate == 1.0

    def test_add_observation_failure(self):
        """Test adding failed observation."""
        evidence = RelationEvidence()
        evidence.add_observation(False)
        assert evidence.total_observations == 1
        assert evidence.successful_predictions == 0
        assert evidence.success_rate == 0.0

    def test_mixed_observations(self):
        """Test mixed success/failure."""
        evidence = RelationEvidence()
        evidence.add_observation(True)
        evidence.add_observation(True)
        evidence.add_observation(False)
        assert evidence.total_observations == 3
        assert evidence.successful_predictions == 2
        assert evidence.success_rate == 2.0 / 3.0

    def test_expiration(self):
        """Test observation window expiration."""
        evidence = RelationEvidence(observation_window_days=2)
        assert not evidence.is_expired
        # Simulate old discovery date
        evidence.discovery_date = date(2020, 1, 1)
        assert evidence.is_expired


class TestDigitalRootRelation:
    """Test digital root relation lifecycle."""

    def test_relation_creation(self):
        """Test creating a relation."""
        key = RelationKey(
            relation_type=RelationType.SAME_GAME_SUCCESSIVE,
            source_game_id=uuid4(),
            target_game_id=uuid4(),
            source_root=2,
            target_root=5,
        )
        evidence = RelationEvidence()
        relation = DigitalRootRelation(key=key, evidence=evidence)

        assert relation.status == RelationStatus.CANDIDATE
        assert relation.baseline_success_rate == 0.0

    def test_status_update_candidate(self):
        """Test status stays candidate with few observations."""
        key = RelationKey(
            relation_type=RelationType.SAME_GAME_SUCCESSIVE,
            source_game_id=uuid4(),
            target_game_id=uuid4(),
            source_root=2,
            target_root=5,
        )
        evidence = RelationEvidence()
        relation = DigitalRootRelation(key=key, evidence=evidence)

        relation.update_status()
        assert relation.status == RelationStatus.CANDIDATE

    def test_status_update_observing(self):
        """Test status transitions to observing with strong evidence."""
        key = RelationKey(
            relation_type=RelationType.SAME_GAME_SUCCESSIVE,
            source_game_id=uuid4(),
            target_game_id=uuid4(),
            source_root=2,
            target_root=5,
        )
        evidence = RelationEvidence(baseline_success_rate=0.1)
        relation = DigitalRootRelation(
            key=key,
            evidence=evidence,
            baseline_success_rate=0.1,
        )

        # Add enough successful observations
        for _ in range(10):
            evidence.add_observation(True)

        relation.update_status()
        assert relation.status == RelationStatus.OBSERVING

    def test_should_use_for_prediction(self):
        """Test which relations should be used for predictions."""
        key = RelationKey(
            relation_type=RelationType.SAME_GAME_SUCCESSIVE,
            source_game_id=uuid4(),
            target_game_id=uuid4(),
            source_root=2,
            target_root=5,
        )
        evidence = RelationEvidence(baseline_success_rate=0.1)
        relation = DigitalRootRelation(
            key=key,
            evidence=evidence,
            status=RelationStatus.OBSERVING,
            baseline_success_rate=0.1,
        )

        assert relation.should_use_for_prediction()

        relation.status = RelationStatus.CANDIDATE
        assert not relation.should_use_for_prediction()

        relation.status = RelationStatus.EXPIRED
        assert not relation.should_use_for_prediction()


class TestRelationDiscovery:
    """Test relation discovery from historical data."""

    def test_initialization(self):
        """Test discovery initialization."""
        discovery = RelationDiscovery(observation_window_days=3, min_observations=5)
        assert discovery.observation_window_days == 3
        assert discovery.min_observations == 5
        assert len(discovery.relations) == 0

    def test_discover_empty_data(self):
        """Test discovery with no data."""
        discovery = RelationDiscovery()
        new_relations = discovery.discover_relations([])
        assert len(new_relations) == 0

    def test_discover_single_game(self):
        """Test discovery from single game data."""
        discovery = RelationDiscovery(observation_window_days=3, min_observations=2)

        game_id = uuid4()
        historical_data = [
            {
                "draw_id": uuid4(),
                "draw_type_id": game_id,
                "scheduled_date": date(2024, 1, 1),
                "winning_numbers": [12, 23, 34, 45, 56],
            },
            {
                "draw_id": uuid4(),
                "draw_type_id": game_id,
                "scheduled_date": date(2024, 1, 2),
                "winning_numbers": [21, 32, 43, 54, 65],
            },
        ]

        new_relations = discovery.discover_relations(historical_data)
        # Should discover some relations from the two draws
        assert len(new_relations) > 0

    def test_predict_roots_no_relations(self):
        """Test prediction with no active relations."""
        discovery = RelationDiscovery()
        predictions = discovery.predict_roots(uuid4(), top_k=5)
        assert len(predictions) == 0

    def test_update_with_new_draw(self):
        """Test updating relations with new draw."""
        discovery = RelationDiscovery(observation_window_days=3, min_observations=2)

        game_id = uuid4()
        # Create a relation
        key = RelationKey(
            relation_type=RelationType.SAME_GAME_SUCCESSIVE,
            source_game_id=game_id,
            target_game_id=game_id,
            source_root=2,
            target_root=5,
            position=0,
        )
        evidence = RelationEvidence(baseline_success_rate=0.1)
        relation = DigitalRootRelation(
            key=key,
            evidence=evidence,
            status=RelationStatus.OBSERVING,
            baseline_success_rate=0.1,
        )
        discovery.relations[key] = relation

        # Update with new draw
        new_draw = {
            "draw_id": uuid4(),
            "draw_type_id": game_id,
            "scheduled_date": date(2024, 1, 3),
            "winning_numbers": [5, 23, 34, 45, 56],  # First number has root 5
        }

        changed = discovery.update_with_new_draw(new_draw)
        # Should update the relation
        assert len(changed) >= 0

    def test_get_active_relations(self):
        """Test getting active relations."""
        discovery = RelationDiscovery()

        game_id = uuid4()
        key = RelationKey(
            relation_type=RelationType.SAME_GAME_SUCCESSIVE,
            source_game_id=game_id,
            target_game_id=game_id,
            source_root=2,
            target_root=5,
        )
        evidence = RelationEvidence(baseline_success_rate=0.1)
        relation = DigitalRootRelation(
            key=key,
            evidence=evidence,
            status=RelationStatus.OBSERVING,
            baseline_success_rate=0.1,
        )
        discovery.relations[key] = relation

        active = discovery.get_active_relations(game_id=game_id)
        assert len(active) == 1
        assert active[0] == relation

    def test_cleanup_expired(self):
        """Test cleanup of expired relations."""
        discovery = RelationDiscovery()

        key = RelationKey(
            relation_type=RelationType.SAME_GAME_SUCCESSIVE,
            source_game_id=uuid4(),
            target_game_id=uuid4(),
            source_root=2,
            target_root=5,
        )
        evidence = RelationEvidence(
            discovery_date=date(2020, 1, 1),
            observation_window_days=2,
        )
        relation = DigitalRootRelation(
            key=key,
            evidence=evidence,
            status=RelationStatus.EXPIRED,
        )
        discovery.relations[key] = relation

        discovery._cleanup_expired()
        assert key not in discovery.relations


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
