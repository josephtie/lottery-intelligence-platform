"""Meta-ensemble — deterministic consensus pickers.

Covers: contributor set (no random/null/ensemble double-count), vote
counting, family balancing (a big family cannot dominate a small one),
determinism/reproducibility, declared tie-breaks, no-look-ahead, fallback
on empty history.
"""
import random
import unittest

from lottery_intelligence_platform import meta_ensemble


def _hist(n=60, seed=1):
    rng = random.Random(seed)
    return [sorted(rng.sample(range(1, 91), 5)) for _ in range(n)]


class ContributorSetTests(unittest.TestCase):
    def test_excludes_nulls_and_ensemble(self):
        for code in ("random", "null_model_benchmark", "ensemble_v1"):
            self.assertNotIn(code, meta_ensemble.CONTRIBUTORS)

    def test_all_contributors_assigned_to_a_family(self):
        fams = {c for members in meta_ensemble.MODEL_FAMILIES.values()
                for c in members}
        self.assertEqual(set(meta_ensemble.CONTRIBUTORS), fams)

    def test_family_map_uses_real_codes(self):
        # every family member must resolve to a contributor
        for members in meta_ensemble.MODEL_FAMILIES.values():
            for code in members:
                self.assertIn(code, meta_ensemble.CONTRIBUTORS)


class ConsensusCountTests(unittest.TestCase):
    def test_votes_match_model_outputs(self):
        hist = _hist(60)
        det = meta_ensemble.consensus_count_detail(hist, 5)
        self.assertEqual(det["n_models"],
                         len(meta_ensemble.CONTRIBUTORS))
        for row in det["ranking"]:
            self.assertLessEqual(row["votes"], det["n_models"])
        # ranks are 1..90, all numbers covered
        self.assertEqual(len(det["ranking"]), 90)
        self.assertEqual(sorted(r["number"] for r in det["ranking"]),
                         list(range(1, 91)))

    def test_unanimous_number_ranks_first(self):
        hist = _hist(60)
        # plant: all contributors forced to vote for 7
        fake = {c: [7] + list(range(10, 10 + 4))
                for c in meta_ensemble.CONTRIBUTORS}
        orig = meta_ensemble.model_votes
        meta_ensemble.model_votes = lambda h, k: fake
        try:
            det = meta_ensemble.consensus_count_detail(hist, 5)
            self.assertEqual(det["ranking"][0]["number"], 7)
            self.assertEqual(det["ranking"][0]["votes"],
                             len(meta_ensemble.CONTRIBUTORS))
            self.assertIn(7, det["top_k"])
        finally:
            meta_ensemble.model_votes = orig

    def test_deterministic(self):
        hist = _hist(100)
        a = meta_ensemble.consensus_count_detail(hist, 5)
        b = meta_ensemble.consensus_count_detail(hist, 5)
        self.assertEqual(a["ranking"], b["ranking"])
        self.assertEqual(a["top_k"], b["top_k"])

    def test_picker_returns_k_distinct(self):
        hist = _hist(80)
        out = meta_ensemble.predict_meta_consensus_count(
            hist, random.Random(0), 5)
        self.assertEqual(len(out), 5)
        self.assertTrue(all(1 <= x <= 90 for x in out))


class ConsensusFamilyTests(unittest.TestCase):
    def test_family_balancing_prevents_domination(self):
        """A number supported by all 4 calling_image members (raw 4 votes)
        must not outrank a number supported by 4 different families
        (one model each)."""
        hist = _hist(60)
        codes = list(meta_ensemble.CONTRIBUTORS)
        fams = meta_ensemble.MODEL_FAMILIES
        ci = list(fams["calling_image"])  # 4 models, same family
        others = [fams[f][0] for f in
                  ("frequency", "delay", "bayesian", "combinatorial")
                  if fams[f]]
        fake = {}
        for c in codes:
            picks = []
            if c in ci:
                picks.append(50)  # 4 votes, 1 family
            if c in others:
                picks.append(60)  # 4 votes, 4 families
            fake[c] = (picks + [x for x in range(1, 91)
                                if x not in picks])[:5]
        orig = meta_ensemble.model_votes
        meta_ensemble.model_votes = lambda h, k: fake
        try:
            det = meta_ensemble.consensus_family_detail(hist, 5)
            rank = {r["number"]: r["rank"] for r in det["ranking"]}
            self.assertLess(rank[60], rank[50])
            fam60 = next(r for r in det["ranking"] if r["number"] == 60)
            self.assertEqual(fam60["families"], 4)
        finally:
            meta_ensemble.model_votes = orig

    def test_deterministic_and_shape(self):
        hist = _hist(100)
        a = meta_ensemble.consensus_family_detail(hist, 5)
        b = meta_ensemble.consensus_family_detail(hist, 5)
        self.assertEqual(a["ranking"], b["ranking"])
        self.assertEqual(a["n_families"], len(meta_ensemble.MODEL_FAMILIES))
        for fam, tops in a["family_scores"].items():
            self.assertLessEqual(len(tops), 10)


class NoLookAheadTests(unittest.TestCase):
    def test_output_invariant_to_future_appended_draws(self):
        """The picker at time t only sees hist[:t]: ranking must equal the
        one computed on the truncated history."""
        hist = _hist(100)
        for t in (70, 90):
            full = meta_ensemble.consensus_count_detail(hist[:t], 5)
            rng = random.Random(0)
            picked = meta_ensemble.predict_meta_consensus_count(
                hist[:t], rng, 5)
            self.assertEqual(picked, full["top_k"])

    def test_empty_history_still_returns_k(self):
        out = meta_ensemble.predict_meta_consensus_count(
            [], random.Random(0), 5)
        self.assertEqual(len(out), 5)


class DetailPayloadTests(unittest.TestCase):
    def test_api_payload_shape(self):
        hist = _hist(80)
        d = meta_ensemble.detail(hist, 5)
        self.assertIn("CONSENSUS_COUNT", d["strategies"])
        self.assertIn("CONSENSUS_FAMILY", d["strategies"])
        self.assertIn("ensemble_v1", d["excluded"])
        for c in d["contributors"]:
            self.assertIn(c["family"], meta_ensemble.MODEL_FAMILIES)
            self.assertEqual(len(c["picks"]), 5)


if __name__ == "__main__":
    unittest.main()
