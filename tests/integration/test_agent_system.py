"""Integration tests for the autonomous agent system.

Tests cover:
- Agent creation and configuration
- Virtual capital management
- Decision making and sealing
- Decision settlement
- Memory compartment persistence
- Collective memory
- Agent lifecycle (evolution, generations)
- Append-only constraints
"""

import os
import unittest
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

import psycopg

from lottery_intelligence_platform.agent_engine import (
    Agent,
    AgentCapital,
    AgentDecision,
    DecisionOutcome,
    create_agent,
    get_agent,
    get_agent_capital,
    list_active_agents,
    make_decision,
    record_reflection,
    settle_decision,
    InsufficientCapitalError,
    DecisionSealedError,
)
from lottery_intelligence_platform.agent_memory import (
    IdentityMemory,
    HypothesisMemory,
    ExperimentMemory,
    SuccessMemory,
    FailureMemory,
    ChangeMemory,
    CalibrationMemory,
    RiskMemory,
    record_identity_memory,
    record_hypothesis,
    record_experiment,
    record_success,
    record_failure,
    record_change,
    record_calibration,
    record_risk,
    update_hypothesis_status,
    complete_experiment,
    get_agent_memory_summary,
)
from lottery_intelligence_platform.collective_memory import (
    CollectiveKnowledge,
    adopt_knowledge,
    discover_knowledge,
    publish_knowledge,
    validate_knowledge_adoption,
)
from lottery_intelligence_platform.agent_lifecycle import (
    AgentVersion,
    create_agent_version,
    propose_new_agent,
    upgrade_operational_level,
    validate_agent_version,
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
class AgentSystemTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

        # Get a draw type and draw ID for testing
        self.draw_type_id = self.connection.execute(
            "SELECT draw_type_id FROM catalog.draw_types LIMIT 1"
        ).fetchone()
        if self.draw_type_id:
            self.draw_type_id = self.draw_type_id[0]

        self.draw_id = self.connection.execute(
            "SELECT draw_id FROM core.draws WHERE status = 'SETTLED' LIMIT 1"
        ).fetchone()
        if self.draw_id:
            self.draw_id = self.draw_id[0]

    def tearDown(self):
        self.connection.close()

    def test_agent_creation_with_capital(self):
        """Test creating an agent with initial virtual capital."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_EXPLORER",
                display_name="Test Explorer",
                mission="Test autonomous decision-making",
                specialties=["frequency", "pattern_detection"],
                objectives=["improve_prediction_accuracy"],
                preferred_methods=["bayesian_shrinkage"],
                operational_level="DECISION",
                initial_capital=Decimal("100000.00"),
            )

            self.assertIsInstance(agent, Agent)
            self.assertEqual(agent.code, "TEST_EXPLORER")
            self.assertEqual(agent.generation, 1)
            self.assertEqual(agent.status, "ACTIVE")

            capital = get_agent_capital(self.connection, agent.agent_id)
            self.assertIsNotNone(capital)
            self.assertEqual(capital.initial_capital, Decimal("100000.00"))
            self.assertEqual(capital.current_capital, Decimal("100000.00"))

    def test_agent_identity_memory_persistence(self):
        """Test that identity memory is recorded and append-only."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_IDENTITY",
                display_name="Test Identity",
                mission="Test identity memory",
                initial_capital=Decimal("50000.00"),
            )

            memory = record_identity_memory(
                self.connection,
                agent_id=agent.agent_id,
                mission="Updated mission",
                specialties=["new_specialty"],
                objectives=["new_objective"],
                preferred_methods=["new_method"],
                constraints={"max_stake": 1000},
                version_summary="Version 2: Updated mission and constraints",
            )

            self.assertIsInstance(memory, IdentityMemory)
            self.assertEqual(memory.agent_id, agent.agent_id)

            # Verify append-only constraint
            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        "DELETE FROM edge_lab.memory_identity WHERE memory_id = %s",
                        (memory.memory_id,),
                    )

    def test_hypothesis_memory_lifecycle(self):
        """Test hypothesis creation, status updates, and append-only."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_HYPOTHESIS",
                display_name="Test Hypothesis",
                mission="Test hypothesis memory",
                initial_capital=Decimal("50000.00"),
            )

            hypothesis = record_hypothesis(
                self.connection,
                agent_id=agent.agent_id,
                code="test_freq_signal",
                title="Frequency provides predictive signal",
                statement="Historical frequency of numbers predicts future draws",
                justification="Previous analysis showed correlation",
                refutation_criteria=["p_value > 0.05", "out_of_sample_lift < 1.0"],
                confidence_level=0.7,
            )

            self.assertIsInstance(hypothesis, HypothesisMemory)
            self.assertEqual(hypothesis.status, "OPEN")

            update_hypothesis_status(
                self.connection,
                hypothesis_id=hypothesis.hypothesis_id,
                status="TESTING",
            )

            # Verify append-only
            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        "DELETE FROM edge_lab.memory_hypotheses WHERE hypothesis_id = %s",
                        (hypothesis.hypothesis_id,),
                    )

    def test_decision_making_and_sealing(self):
        """Test making a decision and enforcing seal constraints."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_DECISION",
                display_name="Test Decision",
                mission="Test decision making",
                initial_capital=Decimal("100000.00"),
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
                reasoning="Frequency analysis suggests these numbers",
                confidence_score=0.6,
                expected_outcome={"expected_hits": 1},
                risk_assessment={"capital_at_risk": 0.01},
            )

            self.assertIsInstance(decision, AgentDecision)
            self.assertTrue(decision.is_sealed)
            self.assertEqual(decision.decision_type, "BET")

            # Verify capital was deducted
            capital = get_agent_capital(self.connection, agent.agent_id)
            self.assertEqual(capital.current_capital, Decimal("99000.00"))

    def test_insufficient_capital_raises_error(self):
        """Test that betting more than available capital raises error."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_CAPITAL",
                display_name="Test Capital",
                mission="Test capital constraints",
                initial_capital=Decimal("1000.00"),
            )

            if not self.draw_type_id or not self.draw_id:
                self.skipTest("No draw data available")

            with self.assertRaises(InsufficientCapitalError):
                make_decision(
                    self.connection,
                    agent_id=agent.agent_id,
                    draw_id=self.draw_id,
                    draw_type_id=self.draw_type_id,
                    decision_type="BET",
                    selected_numbers=[1, 2, 3],
                    stake_amount=Decimal("2000.00"),
                    reasoning="Attempt to overbet",
                    confidence_score=0.5,
                )

    def test_decision_settlement_updates_capital(self):
        """Test that settling a decision updates capital correctly."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_SETTLEMENT",
                display_name="Test Settlement",
                mission="Test decision settlement",
                initial_capital=Decimal("100000.00"),
            )

            if not self.draw_type_id or not self.draw_id:
                self.skipTest("No draw data available")

            # Make a decision
            decision = make_decision(
                self.connection,
                agent_id=agent.agent_id,
                draw_id=self.draw_id,
                draw_type_id=self.draw_type_id,
                decision_type="BET",
                selected_numbers=[1, 2, 3],
                stake_amount=Decimal("1000.00"),
                reasoning="Test bet",
                confidence_score=0.5,
            )

            # Get a draw version ID
            draw_version_id = self.connection.execute(
                "SELECT draw_version_id FROM core.draw_versions WHERE draw_id = %s LIMIT 1",
                (self.draw_id,),
            ).fetchone()

            if not draw_version_id:
                self.skipTest("No draw version available")

            # Settle as a win
            outcome = settle_decision(
                self.connection,
                decision_id=decision.decision_id,
                draw_version_id=draw_version_id[0],
                winning_numbers=[1, 2, 3],
                hit_count=3,
                payout=Decimal("5000.00"),
                settlement_details={"multiplier": 5},
            )

            self.assertIsInstance(outcome, DecisionOutcome)
            self.assertEqual(outcome.outcome_type, "WIN")
            self.assertEqual(outcome.net_result, Decimal("4000.00"))

            # Verify capital updated
            capital = get_agent_capital(self.connection, agent.agent_id)
            self.assertEqual(capital.current_capital, Decimal("104000.00"))
            self.assertEqual(capital.winning_bets, 1)
            self.assertEqual(capital.net_profit, Decimal("4000.00"))

    def test_reflection_recording(self):
        """Test recording agent reflections."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_REFLECTION",
                display_name="Test Reflection",
                mission="Test reflection recording",
                initial_capital=Decimal("50000.00"),
            )

            reflection_id = record_reflection(
                self.connection,
                agent_id=agent.agent_id,
                reflection_type="PRE_DECISION",
                content="Analyzing frequency patterns before decision",
                context={"draw_id": str(self.draw_id) if self.draw_id else None},
                action_taken="Proceed with frequency-based selection",
                next_steps=["Record outcome", "Update calibration"],
            )

            self.assertIsNotNone(reflection_id)

    def test_experiment_memory_with_validation(self):
        """Test experiment recording and validation status."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_EXPERIMENT",
                display_name="Test Experiment",
                mission="Test experiment memory",
                initial_capital=Decimal("50000.00"),
            )

            # Get a dataset version
            dataset_version = self.connection.execute(
                "SELECT dataset_version_id FROM datasets.dataset_versions LIMIT 1"
            ).fetchone()

            if not dataset_version:
                self.skipTest("No dataset available")

            experiment = record_experiment(
                self.connection,
                agent_id=agent.agent_id,
                dataset_version_id=dataset_version[0],
                test_period_start=date(2024, 1, 1),
                test_period_end=date(2024, 6, 30),
                parameters={"window_size": 200, "method": "frequency"},
                results={"roi": 0.05, "hit_rate": 0.3},
                scope="HISTORICAL",
                reproducible=True,
            )

            self.assertIsInstance(experiment, ExperimentMemory)
            self.assertEqual(experiment.validation_status, "PENDING")

            complete_experiment(
                self.connection,
                experiment_id=experiment.experiment_id,
                validation_status="VALIDATED",
            )

            # Verify status updated
            updated = self.connection.execute(
                "SELECT validation_status FROM edge_lab.memory_experiments WHERE experiment_id = %s",
                (experiment.experiment_id,),
            ).fetchone()[0]

            self.assertEqual(updated, "VALIDATED")

    def test_collective_memory_publish_and_discover(self):
        """Test publishing and discovering collective knowledge."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_COLLECTIVE",
                display_name="Test Collective",
                mission="Test collective memory",
                initial_capital=Decimal("50000.00"),
            )

            knowledge = publish_knowledge(
                self.connection,
                code="freq_baseline_verified",
                title="Frequency baseline verified across markets",
                knowledge_type="VALIDATED_METHOD",
                content="Frequency-based selection provides consistent baseline performance",
                evidence={"markets_tested": 5, "roi_range": [-0.02, 0.01]},
                originating_agent_id=agent.agent_id,
                proof_level="VALIDATED",
            )

            self.assertIsInstance(knowledge, CollectiveKnowledge)
            self.assertEqual(knowledge.proof_level, "VALIDATED")

            # Discover knowledge
            discovered = discover_knowledge(
                self.connection,
                knowledge_type="VALIDATED_METHOD",
                min_validations=0,
            )

            self.assertTrue(len(discovered) > 0)
            self.assertEqual(discovered[0].knowledge_id, knowledge.knowledge_id)

    def test_agent_version_creation_and_validation(self):
        """Test creating agent versions and validation."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_VERSION",
                display_name="Test Version",
                mission="Test version management",
                initial_capital=Decimal("50000.00"),
            )

            version = create_agent_version(
                self.connection,
                agent_id=agent.agent_id,
                change_reason="Updated frequency window size",
                configuration_changes={"window_size": 200, "previous": 100},
                performance_before={"roi": 0.02},
                validation_criteria={"required_metrics": ["roi", "hit_rate"], "min_roi": 0.03},
            )

            self.assertIsInstance(version, AgentVersion)
            self.assertEqual(version.version_number, 2)
            self.assertEqual(version.validation_status, "PENDING")

            validate_agent_version(
                self.connection,
                agent_version_id=version.agent_version_id,
                performance_after={"roi": 0.04, "hit_rate": 0.35},
                validation_status="VALIDATED",
            )

            # Verify agent generation updated
            updated_agent = get_agent(self.connection, agent.agent_id)
            self.assertEqual(updated_agent.generation, 2)

    def test_memory_summary_aggregation(self):
        """Test getting memory summary for an agent."""
        with rollback_transaction(self.connection):
            agent = create_agent(
                self.connection,
                code="TEST_SUMMARY",
                display_name="Test Summary",
                mission="Test memory summary",
                initial_capital=Decimal("50000.00"),
            )

            # Record some memory entries
            record_hypothesis(
                self.connection,
                agent_id=agent.agent_id,
                code="test_h1",
                title="Test hypothesis 1",
                statement="Test statement",
                justification="Test justification",
            )

            summary = get_agent_memory_summary(self.connection, agent.agent_id)

            self.assertIsNotNone(summary)
            self.assertGreater(summary["hypothesis_records"], 0)

    def test_list_active_agents(self):
        """Test listing all active agents."""
        with rollback_transaction(self.connection):
            create_agent(
                self.connection,
                code="TEST_LIST_1",
                display_name="Test List 1",
                mission="Test listing",
                initial_capital=Decimal("50000.00"),
            )

            create_agent(
                self.connection,
                code="TEST_LIST_2",
                display_name="Test List 2",
                mission="Test listing",
                initial_capital=Decimal("50000.00"),
            )

            agents = list_active_agents(self.connection)

            self.assertGreaterEqual(len(agents), 2)
            self.assertTrue(any(a.code == "TEST_LIST_1" for a in agents))
            self.assertTrue(any(a.code == "TEST_LIST_2" for a in agents))


if __name__ == "__main__":
    unittest.main()
