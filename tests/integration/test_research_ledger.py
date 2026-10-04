import os
import unittest
from contextlib import contextmanager

import psycopg

from lottery_intelligence_platform.research import (
    ResearchConflict,
    ResearchError,
    complete_experiment,
    create_experiment,
    create_hypothesis,
    finish_run,
    record_finding,
    record_metric,
    register_feature_version,
    start_run,
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
class ResearchLedgerTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)
        self.dataset_version_id = self.connection.execute(
            "SELECT dataset_version_id FROM datasets.dataset_versions ORDER BY created_at LIMIT 1"
        ).fetchone()[0]

    def tearDown(self):
        self.connection.close()

    def test_full_research_lifecycle_preserves_rejected_hypotheses(self):
        with rollback_transaction(self.connection):
            hypothesis = create_hypothesis(
                self.connection,
                code="frequency_uniformity_test",
                title="Winning numbers are uniformly distributed",
                statement="Observed winning-number frequencies do not differ from a uniform distribution beyond sampling noise.",
            )
            duplicate = create_hypothesis(
                self.connection,
                code="frequency_uniformity_test",
                title="Winning numbers are uniformly distributed",
                statement="Observed winning-number frequencies do not differ from a uniform distribution beyond sampling noise.",
            )
            with self.assertRaises(ResearchConflict):
                create_hypothesis(
                    self.connection,
                    code="frequency_uniformity_test",
                    title="Different title",
                    statement="Different statement.",
                )

            features = register_feature_version(
                self.connection,
                code="number_frequency_v1",
                definition={"kind": "frequency", "number_role": "WINNING"},
            )
            same_features = register_feature_version(
                self.connection,
                code="number_frequency_v1",
                definition={"number_role": "WINNING", "kind": "frequency"},
            )
            next_features = register_feature_version(
                self.connection,
                code="number_frequency_v1",
                definition={"kind": "frequency", "number_role": "MACHINE"},
            )

            experiment = create_experiment(
                self.connection,
                hypothesis_id=hypothesis.hypothesis_id,
                dataset_version_id=self.dataset_version_id,
                feature_version_id=features.feature_version_id,
                configuration={"analysis": "chi_square_frequency"},
                random_seed=42,
            )
            same_experiment = create_experiment(
                self.connection,
                hypothesis_id=hypothesis.hypothesis_id,
                dataset_version_id=self.dataset_version_id,
                feature_version_id=features.feature_version_id,
                configuration={"analysis": "chi_square_frequency"},
                random_seed=42,
            )

            run = start_run(
                self.connection,
                experiment_id=experiment.experiment_id,
                scope="GLOBAL",
            )
            metric_id = record_metric(
                self.connection,
                experiment_id=experiment.experiment_id,
                experiment_run_id=run.experiment_run_id,
                metric_name="chi_square_statistic",
                metric_scope="GLOBAL",
                metric_value=123.45,
            )
            finish_run(self.connection, experiment_run_id=run.experiment_run_id)
            with self.assertRaises(ResearchError):
                finish_run(self.connection, experiment_run_id=run.experiment_run_id)
            complete_experiment(self.connection, experiment_id=experiment.experiment_id)
            finding_id = record_finding(
                self.connection,
                hypothesis_id=hypothesis.hypothesis_id,
                experiment_id=experiment.experiment_id,
                conclusion="Frequencies consistent with uniform within tolerance.",
                status="REJECTED",
                evidence={"chi_square_statistic": 123.45},
            )
            hypothesis_status = self.connection.execute(
                "SELECT status FROM research.hypotheses WHERE hypothesis_id = %s",
                (hypothesis.hypothesis_id,),
            ).fetchone()[0]

            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        "UPDATE research.experiment_metrics SET metric_value = 0 WHERE experiment_metric_id = %s",
                        (metric_id,),
                    )
            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        "DELETE FROM research.findings WHERE finding_id = %s",
                        (finding_id,),
                    )
            with self.assertRaises(Exception):
                with self.connection.transaction():
                    self.connection.execute(
                        "DELETE FROM research.hypotheses WHERE hypothesis_id = %s",
                        (hypothesis.hypothesis_id,),
                    )

            self.assertTrue(hypothesis.created)
            self.assertFalse(duplicate.created)
            self.assertEqual(features.version, 1)
            self.assertFalse(same_features.created)
            self.assertEqual(next_features.version, 2)
            self.assertTrue(experiment.created)
            self.assertFalse(same_experiment.created)
            self.assertEqual(same_experiment.experiment_id, experiment.experiment_id)
            self.assertEqual(run.run_number, 1)
            self.assertEqual(hypothesis_status, "REJECTED")


if __name__ == "__main__":
    unittest.main()
