"""Anti-lookahead tests for the autonomous agent system.

These tests ensure that:
1. Agents cannot access data after the temporal cutoff
2. Decisions are sealed before the draw time
3. Sealed decisions cannot be modified
4. Memory references are temporally consistent
5. No data leakage from future into past decisions
"""

import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal

import psycopg

from lottery_intelligence_platform.agent_engine import (
    create_agent,
    make_decision,
    CutoffViolationError,
)
from lottery_intelligence_platform.agent_memory import (
    record_experiment,
    record_hypothesis,
)

TEST_DATABASE_URL = os.getenv("LOTTERY_TEST_DATABASE_URL")


class RollbackProbe(Exception):
    pass


@contextmanager
def rollback_transaction(connection):
    try:
        with connection.transaction():
            yield
            raise RollbackProbe
    except RollbackProbe:
        pass


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class AgentAntiLookaheadTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

        # Get a draw type and draw ID for testing
        self.draw_type_id = self.connection.execute(
            "SELECT draw_type_id FROM catalog.draw_types LIMIT 1"
        ).fetchone()
        if self.draw_type_id:
            self.draw_type_id = self.draw_type_id[0]

        self.draw_id = self.connection.execute(
            "SELECT draw_id, scheduled_date FROM core.draws WHERE status = 'SETTLED' LIMIT 1"
        ).fetchone()
        if self.draw_id:
            self.draw_id, self.scheduled_date = self.draw_id

    def tearDown(self):
        self.connection.close()

    def test_cutoff_violation_raises_error(self):
        """Test that decisions after cutoff time are rejected."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_CUTOFF",
                display_name="Test Cutoff",
                mission="Test temporal cutoff enforcement",
                initial_capital=Decimal("50000.00"),
            )

            if not self.draw_type_id or not self.draw_id:
                self.skipTest("No draw data available")

            # Set cutoff in the past
            past_cutoff = datetime.now() - timedelta(hours=1)

            with self.assertRaises(CutoffViolationError):
                make_decision(
                    self.connection,
                    agent_id=agent.agent_id,
                    draw_id=self.draw_id,
                    draw_type_id=self.draw_type_id,
                    decision_type="BET",
                    selected_numbers=[1, 2, 3],
                    stake_amount=Decimal("1000.00"),
                    reasoning="This should be rejected",
                    confidence_score=0.5,
                    cutoff_at=past_cutoff,
                )

    def test_sealed_decision_prevents_modification(self):
        """Test that sealed decisions cannot be modified."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_SEALED",
                display_name="Test Sealed",
                mission="Test decision sealing",
                initial_capital=Decimal("50000.00"),
            )

            if not self.draw_type_id or not self.draw_id:
                self.skipTest("No draw data available")

            # Create a sealed decision
            decision = make_decision(
                self.connection,
                agent_id=agent.agent_id,
                draw_id=self.draw_id,
                draw_type_id=self.draw_type_id,
                decision_type="BET",
                selected_numbers=[1, 2, 3],
                stake_amount=Decimal("1000.00"),
                reasoning="Original decision",
                confidence_score=0.5,
            )

            # Attempt to modify the sealed decision
            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        """UPDATE edge_lab.agent_decisions
                           SET selected_numbers = %s
                           WHERE decision_id = %s""",
                        ([4, 5, 6], decision.decision_id),
                    )

            # Attempt to modify stake amount
            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        """UPDATE edge_lab.agent_decisions
                           SET stake_amount = %s
                           WHERE decision_id = %s""",
                        (Decimal("2000.00"), decision.decision_id),
                    )

            # Verify original values are intact
            original = self.connection.execute(
                """SELECT selected_numbers, stake_amount
                   FROM edge_lab.agent_decisions
                   WHERE decision_id = %s""",
                (decision.decision_id,),
            ).fetchone()

            self.assertEqual(original[0], [1, 2, 3])
            self.assertEqual(original[1], Decimal("1000.00"))

    def test_sealed_decision_prevents_deletion(self):
        """Test that sealed decisions cannot be deleted."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_DELETE",
                display_name="Test Delete",
                mission="Test decision immutability",
                initial_capital=Decimal("50000.00"),
            )

            if not self.draw_type_id or not self.draw_id:
                self.skipTest("No draw data available")

            decision = make_decision(
                self.connection,
                agent_id=agent.agent_id,
                draw_id=self.draw_id,
                draw_type_id=self.draw_type_id,
                decision_type="BET",
                selected_numbers=[1, 2, 3],
                stake_amount=Decimal("1000.00"),
                reasoning="Test deletion prevention",
                confidence_score=0.5,
            )

            # Attempt to delete the sealed decision
            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        "DELETE FROM edge_lab.agent_decisions WHERE decision_id = %s",
                        (decision.decision_id,),
                    )

    def test_memory_append_only_constraint(self):
        """Test that memory records cannot be modified or deleted."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_MEMORY",
                display_name="Test Memory",
                mission="Test memory append-only",
                initial_capital=Decimal("50000.00"),
            )

            # Record a hypothesis
            hypothesis = record_hypothesis(
                self.connection,
                agent_id=agent.agent_id,
                code="test_append_only",
                title="Test append-only constraint",
                statement="Memory should be immutable",
                justification="Testing append-only constraint",
            )

            # Attempt to modify
            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        """UPDATE edge_lab.memory_hypotheses
                           SET statement = %s
                           WHERE hypothesis_id = %s""",
                        ("Modified statement", hypothesis.hypothesis_id),
                    )

            # Attempt to delete
            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        "DELETE FROM edge_lab.memory_hypotheses WHERE hypothesis_id = %s",
                        (hypothesis.hypothesis_id,),
                    )

    def test_experiment_temporal_consistency(self):
        """Test that experiments respect temporal boundaries."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_TEMPORAL",
                display_name="Test Temporal",
                mission="Test temporal consistency",
                initial_capital=Decimal("50000.00"),
            )

            # Get a dataset version
            dataset_version = self.connection.execute(
                "SELECT dataset_version_id, cutoff_at FROM datasets.dataset_versions LIMIT 1"
            ).fetchone()

            if not dataset_version:
                self.skipTest("No dataset available")

            dataset_version_id, cutoff_at = dataset_version

            # Experiment period should not extend beyond dataset cutoff
            from datetime import date

            if cutoff_at:
                cutoff_date = cutoff_at.date()
                invalid_end = cutoff_date + timedelta(days=30)

                # This should be allowed (before cutoff)
                valid_experiment = record_experiment(
                    self.connection,
                    agent_id=agent.agent_id,
                    dataset_version_id=dataset_version_id,
                    test_period_start=date(2024, 1, 1),
                    test_period_end=cutoff_date - timedelta(days=1),
                    parameters={"window": 100},
                    results={"roi": 0.01},
                    scope="HISTORICAL",
                )

                self.assertIsNotNone(valid_experiment)

    def test_no_bet_decision_preserves_capital(self):
        """Test that NO_BET decisions do not affect capital."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_NO_BET",
                display_name="Test No Bet",
                mission="Test NO_BET capital preservation",
                initial_capital=Decimal("100000.00"),
            )

            if not self.draw_type_id or not self.draw_id:
                self.skipTest("No draw data available")

            from lottery_intelligence_platform.agent_engine import get_agent_capital

            initial_capital = get_agent_capital(self.connection, agent.agent_id).current_capital

            # Make a NO_BET decision
            decision = make_decision(
                self.connection,
                agent_id=agent.agent_id,
                draw_id=self.draw_id,
                draw_type_id=self.draw_type_id,
                decision_type="NO_BET",
                selected_numbers=[],
                stake_amount=Decimal("0"),
                reasoning="Insufficient confidence",
                confidence_score=0.3,
            )

            # Capital should remain unchanged
            final_capital = get_agent_capital(self.connection, agent.agent_id).current_capital
            self.assertEqual(initial_capital, final_capital)

    def test_decision_references_exist_at_creation_time(self):
        """Test that decision references (hypotheses, models) exist when decision is made."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_REFERENCES",
                display_name="Test References",
                mission="Test reference validity",
                initial_capital=Decimal("50000.00"),
            )

            if not self.draw_type_id or not self.draw_id:
                self.skipTest("No draw data available")

            # Create a hypothesis to reference
            hypothesis = record_hypothesis(
                self.connection,
                agent_id=agent.agent_id,
                code="test_ref",
                title="Test reference",
                statement="Test statement",
                justification="Test justification",
            )

            # Make decision referencing the hypothesis
            decision = make_decision(
                self.connection,
                agent_id=agent.agent_id,
                draw_id=self.draw_id,
                draw_type_id=self.draw_type_id,
                decision_type="BET",
                selected_numbers=[1, 2, 3],
                stake_amount=Decimal("1000.00"),
                reasoning="Based on hypothesis",
                confidence_score=0.5,
                hypothesis_ids=[hypothesis.hypothesis_id],
            )

            # Verify the reference is stored
            stored_hypotheses = self.connection.execute(
                """SELECT hypothesis_ids FROM edge_lab.agent_decisions
                   WHERE decision_id = %s""",
                (decision.decision_id,),
            ).fetchone()[0]

            self.assertIn(hypothesis.hypothesis_id, stored_hypotheses)

    def test_outcome_cannot_modify_decision(self):
        """Test that recording an outcome cannot modify the original decision."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_OUTCOME",
                display_name="Test Outcome",
                mission="Test outcome immutability",
                initial_capital=Decimal("50000.00"),
            )

            if not self.draw_type_id or not self.draw_id:
                self.skipTest("No draw data available")

            decision = make_decision(
                self.connection,
                agent_id=agent.agent_id,
                draw_id=self.draw_id,
                draw_type_id=self.draw_type_id,
                decision_type="BET",
                selected_numbers=[1, 2, 3],
                stake_amount=Decimal("1000.00"),
                reasoning="Test outcome",
                confidence_score=0.5,
            )

            # Get a draw version
            draw_version_id = self.connection.execute(
                "SELECT draw_version_id FROM core.draw_versions WHERE draw_id = %s LIMIT 1",
                (self.draw_id,),
            ).fetchone()

            if not draw_version_id:
                self.skipTest("No draw version available")

            from lottery_intelligence_platform.agent_engine import settle_decision

            # Settle the decision
            settle_decision(
                self.connection,
                decision_id=decision.decision_id,
                draw_version_id=draw_version_id[0],
                winning_numbers=[1, 2, 3],
                hit_count=3,
                payout=Decimal("5000.00"),
            )

            # Verify original decision is unchanged
            original = self.connection.execute(
                """SELECT selected_numbers, stake_amount, reasoning
                   FROM edge_lab.agent_decisions
                   WHERE decision_id = %s""",
                (decision.decision_id,),
            ).fetchone()

            self.assertEqual(original[0], [1, 2, 3])
            self.assertEqual(original[1], Decimal("1000.00"))
            self.assertEqual(original[2], "Test outcome")


if __name__ == "__main__":
    unittest.main()
