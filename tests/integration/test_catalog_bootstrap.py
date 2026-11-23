import os
import unittest
from contextlib import contextmanager
from datetime import date

import psycopg

from lottery_intelligence_platform.catalog import ensure_lotobonheur_catalog
from lottery_intelligence_platform.collectors.lotobonheur import ResultValidationRules

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
class CatalogBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def test_catalog_bootstrap_is_idempotent_and_marks_rule_history_provisional(self):
        with rollback_transaction(self.connection):
            first = ensure_lotobonheur_catalog(self.connection, data_coverage_start=date(2020, 11, 1))
            second = ensure_lotobonheur_catalog(self.connection, data_coverage_start=date(2020, 11, 1))
            rules = ResultValidationRules.from_game_version(self.connection, first.game_version_id)
            stored_rules = self.connection.execute(
                "SELECT rules FROM catalog.game_versions WHERE game_version_id = %s",
                (first.game_version_id,),
            ).fetchone()[0]

            self.assertEqual(first, second)
            self.assertEqual((rules.minimum_number, rules.maximum_number, rules.numbers_per_draw), (1, 90, 5))
            self.assertEqual(stored_rules["historical_effectivity"], "UNVERIFIED")
            self.assertEqual(stored_rules["model_eligibility"], "EXPLORATORY_ONLY")
            self.assertEqual(
                self.connection.execute(
                    "SELECT source_kind FROM ingestion.sources WHERE source_id = %s",
                    (first.source_id,),
                ).fetchone()[0],
                "OFFICIAL",
            )


if __name__ == "__main__":
    unittest.main()
