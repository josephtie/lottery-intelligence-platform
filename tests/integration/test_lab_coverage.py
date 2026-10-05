import os
import unittest

import psycopg

from lottery_intelligence_platform.lab_coverage import (
    CoverageRuleError, coverage_laboratory, resolve_payout_rule)

TEST_DATABASE_URL = os.getenv("LOTTERY_TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DATABASE_URL, "set LOTTERY_TEST_DATABASE_URL to run PostgreSQL integration tests")
class CoverageLaboratoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(TEST_DATABASE_URL)

    def tearDown(self):
        self.connection.close()

    def test_rule_resolved_from_catalog(self):
        rule = resolve_payout_rule(self.connection)
        self.assertEqual(rule["code"], "turbo_fixed_odds")
        self.assertEqual(rule["verification_status"], "VERIFIED_OFFICIAL")
        self.assertIn("turbo_2", rule["positions_by_variant"])
        self.assertIn(str(rule["positions_by_variant"]["turbo_2"]),
                      rule["payout_multipliers"])

    def test_explicit_rule_version(self):
        rule = resolve_payout_rule(self.connection,
                                   "official-turbo-position-2026-10")
        self.assertEqual(rule["version"], "official-turbo-position-2026-10")

    def test_unknown_version_rejected(self):
        with self.assertRaises(CoverageRuleError):
            resolve_payout_rule(self.connection, "nonexistent-v0")

    def test_end_to_end_with_catalog_rule(self):
        rule = resolve_payout_rule(self.connection)
        result = coverage_laboratory(
            rule=rule, budget_fcfa=2000, stake=100, pick_size=2,
            variant="turbo_5", seed=0, baselines=10, mc_sims=1000)
        self.assertEqual(result["payout_rule"]["version"], rule["version"])
        self.assertIn("probability_at_least_one_win", result["optimized"])
        self.assertIn("EV", str(result["disclaimer"]).upper())
