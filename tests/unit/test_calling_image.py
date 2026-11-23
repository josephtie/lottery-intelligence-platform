import random
import unittest

from lottery_intelligence_platform.calling_image import (
    CALLING_EDGES,
    CALLING_IMAGE_EDGES,
    IMAGE_EDGES,
    _edge_pairs,
    _oos_replication,
    calling_edges,
    calling_image_edges,
    evaluate_edges,
    evaluate_family,
    evaluate_positional_edges,
    first_positions,
    image_number,
    image_repr,
    is_self_image,
    predict_calling_image,
    predict_calling_image_position,
    predict_calling_numbers,
    predict_image_numbers,
)


def _uniform_hist(n_draws, seed=7):
    rng = random.Random(seed)
    return [sorted(rng.sample(range(1, 91), 5)) for _ in range(n_draws)]


class TestImageTransform(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(image_number(16), 61)
        self.assertEqual(image_number(57), 75)
        self.assertEqual(image_number(49), 94)
        self.assertEqual(image_number(78), 87)
        self.assertEqual(image_number(79), 97)
        self.assertEqual(image_number(18), 81)

    def test_leading_zero_preserved(self):
        # The zero-padded representation keeps 09/08 distinct from 9/8.
        self.assertEqual(image_repr(90), "09")
        self.assertEqual(image_repr(80), "08")
        self.assertEqual(image_number(90), 9)
        self.assertEqual(image_number(80), 8)

    def test_involution(self):
        # The reversal is an involution on 1..99: image(image(n)) == n
        # whenever the image is itself a valid input (image stays <= 90).
        for n in range(1, 91):
            img = image_number(n)
            if img <= 90:
                self.assertEqual(image_number(img), n)

    def test_out_of_domain_image_kept_but_never_drawable(self):
        # 49 -> 94 and 19 -> 91: valid reversals outside the 1..90 draw
        # domain. They exist in the edge sets but can never hit a draw.
        self.assertEqual(image_number(49), 94)
        self.assertEqual(image_number(19), 91)
        self.assertEqual(IMAGE_EDGES[19], [91])
        self.assertEqual(IMAGE_EDGES[49], [94])

    def test_self_image(self):
        self.assertTrue(is_self_image(11))
        self.assertTrue(is_self_image(55))
        self.assertFalse(is_self_image(57))

    def test_domain_validation(self):
        with self.assertRaises(ValueError):
            image_repr(0)
        with self.assertRaises(ValueError):
            image_repr(91)

    def test_image_edges_are_directed_pairs(self):
        self.assertEqual(IMAGE_EDGES[57], [75])
        self.assertEqual(IMAGE_EDGES[75], [57])
        self.assertEqual(IMAGE_EDGES[90], [9])
        self.assertEqual(IMAGE_EDGES[9], [90])
        self.assertEqual(IMAGE_EDGES[11], [])  # self-image excluded


class TestCallingGrid(unittest.TestCase):
    def test_mandated_example(self):
        # Spec-required: 57 -> 49, 78, 79, 18, 16 (order included).
        self.assertEqual(CALLING_EDGES[57], [49, 78, 79, 18, 16])

    def test_neighbourhood_size_and_no_self(self):
        center = CALLING_EDGES[50]  # grid (3,4): full 8-cell neighbourhood
        self.assertEqual(len(center), 8)
        self.assertNotIn(50, center)
        for a, targets in CALLING_EDGES.items():
            self.assertNotIn(a, targets)
            self.assertEqual(len(targets), len(set(targets)))

    def test_corner_has_three_neighbours(self):
        # 88 sits at grid corner (0,0): S, SE, E in clockwise-from-West order.
        self.assertEqual(CALLING_EDGES[88], [83, 78, 49])

    def test_first_occurrence_anchors_duplicates(self):
        positions = first_positions(
            [(88, 49, 57), (83, 78, 79), (30, 2, 57)])
        self.assertEqual(positions[57], (0, 2))

    def test_custom_grid_is_configuration(self):
        grid = ((1, 2), (3, 4))
        edges = calling_edges(grid)
        self.assertEqual(edges[1], [3, 4, 2])  # S, SE, E from corner (0,0)
        self.assertEqual(edges[4], [3, 2, 1])  # W, N, NW from corner (1,1)

    def test_grid_validation(self):
        with self.assertRaises(ValueError):
            calling_edges([])
        with self.assertRaises(ValueError):
            calling_edges([(1, 2), (3,)])
        with self.assertRaises(ValueError):
            calling_edges([(1, 95)])

    def test_directionality_measured_separately(self):
        # Geometry may be symmetric, but both directed edges are kept.
        pairs = _edge_pairs(CALLING_EDGES)
        self.assertIn((57, 49), pairs)
        self.assertIn((49, 57), pairs)

    def test_calling_image_edges_extend_calling(self):
        for b in CALLING_EDGES[57]:
            self.assertIn(b, CALLING_IMAGE_EDGES[57])
        # image(49) = 94 must also be reachable from 57.
        self.assertIn(94, CALLING_IMAGE_EDGES[57])
        self.assertIn(61, CALLING_IMAGE_EDGES[57])  # image(16)


class TestEdgeEvaluation(unittest.TestCase):
    def test_perfect_same_draw_association(self):
        hist = [[57, 49, 10, 20, 30]] * 30 + [[1, 2, 3, 4, 5]] * 30
        res = evaluate_edges(hist, [(57, 49)], horizon=0, min_support=3)
        edge = res["edges"][0]
        self.assertEqual(edge["n_trigger"], 30)
        self.assertEqual(edge["hits"], 30)
        self.assertAlmostEqual(edge["p_cond"], 1.0)
        self.assertLess(edge["p_value"], 1e-10)

    def test_horizon_separation(self):
        # B strictly follows A on the NEXT draw, never the same draw.
        hist = []
        for i in range(60):
            hist.append([57, 1, 2, 3, 4])
            hist.append([49, 5, 6, 7, 8])
        same = evaluate_edges(hist, [(57, 49)], horizon=0, min_support=3)
        nxt = evaluate_edges(hist, [(57, 49)], horizon=1, min_support=3)
        self.assertEqual(same["edges"][0]["hits"], 0)
        self.assertAlmostEqual(nxt["edges"][0]["p_cond"], 1.0)

    def test_no_lookahead_trailing_trigger_excluded(self):
        # A in the last draw has no next-draw window: it must not count.
        hist = [[57, 1, 2, 3, 4]] * 20 + [[49, 5, 6, 7, 8]] * 5
        hist.append([57, 10, 11, 12, 13])
        res = evaluate_edges(hist, [(57, 49)], horizon=1, min_support=3)
        self.assertEqual(res["edges"][0]["n_trigger"], 20)

    def test_uniform_history_no_strong_signal(self):
        hist = _uniform_hist(400)
        res = evaluate_edges(hist, _edge_pairs(CALLING_EDGES), horizon=0)
        self.assertLess(res["significant_fdr"], res["edges_tested"] * 0.05)

    def test_min_support_filters(self):
        hist = [[57, 49, 10, 20, 30]] * 3 + [[1, 2, 3, 4, 5]] * 50
        res = evaluate_edges(hist, [(57, 49)], horizon=0, min_support=5)
        self.assertEqual(res["edges_tested"], 0)
        self.assertEqual(res["edges_low_support"], 1)

    def test_fdr_q_values_assigned(self):
        hist = _uniform_hist(300, seed=3)
        res = evaluate_edges(hist, _edge_pairs(IMAGE_EDGES), horizon=0)
        self.assertTrue(all("q_fdr" in e for e in res["edges"]))
        for e in res["edges"]:
            self.assertGreaterEqual(e["q_fdr"], 0)
            self.assertLessEqual(e["q_fdr"], 1)

    def test_permutation_null_reproducible(self):
        hist = _uniform_hist(200, seed=11)
        kwargs = dict(horizon=1, min_support=5, permutations=49, seed=99)
        r1 = evaluate_edges(hist, [(57, 49)], **kwargs)
        r2 = evaluate_edges(hist, [(57, 49)], **kwargs)
        self.assertEqual(r1["edges"], r2["edges"])

    def test_permutation_flags_planted_edge(self):
        hist = []
        for _ in range(80):
            hist.append([57, 1, 2, 3, 4])
            hist.append([49, 5, 6, 7, 8])
        res = evaluate_edges(
            hist, [(57, 49)], horizon=1, min_support=3,
            permutations=99, seed=5)
        edge = res["edges"][0]
        self.assertIn("p_perm", edge)
        self.assertLess(edge["p_perm"], 0.05)

    def test_directional_difference(self):
        # A -> B strong, B -> A absent: direction matters.
        hist = [[57, 49, 1, 2, 3]] * 30 + [[49, 10, 11, 12, 13]] * 30
        fwd = evaluate_edges(hist, [(57, 49)], horizon=0, min_support=3)
        rev = evaluate_edges(hist, [(49, 57)], horizon=0, min_support=3)
        self.assertAlmostEqual(fwd["edges"][0]["p_cond"], 1.0)
        self.assertAlmostEqual(rev["edges"][0]["p_cond"], 0.5)


class TestPositionalEvaluation(unittest.TestCase):
    def test_planted_positional_edge(self):
        # When 57 is at pos 1, 49 is always at pos 2; draws without 57 are
        # random — otherwise P(49 at pos 2) = 1 and there is nothing to find.
        rng = random.Random(4)
        hist = []
        for _ in range(60):
            draw = rng.sample(range(1, 91), 5)
            draw[0], draw[1] = 57, 49
            hist.append(draw)
        hist += [rng.sample(range(1, 91), 5) for _ in range(60)]
        res = evaluate_positional_edges(hist, [(57, 49)], min_support=3)
        top = res["edges"][0]
        self.assertEqual((top["a"], top["b"], top["pos_a"], top["pos_b"]),
                         (57, 49, 1, 2))
        # < 1.0: the random half of the history occasionally puts 57 at
        # pos 1 without 49 at pos 2.
        self.assertGreater(top["p_cond"], 0.9)

    def test_positions_never_pooled(self):
        res = evaluate_positional_edges(
            _uniform_hist(200), [(57, 49)], min_support=3)
        for e in res["edges"]:
            self.assertIn("pos_a", e)
            self.assertIn("pos_b", e)


class TestOosReplication(unittest.TestCase):
    def test_persistent_association_survives(self):
        # Planted in 3 draws out of 4 throughout: train and holdout both
        # see the association.
        hist = [
            [57, 49, 10, 20, 30] if i % 4 < 3 else [1, 2, 3, 4, 5]
            for i in range(160)
        ]
        oos = _oos_replication(
            hist, [(57, 49)], horizon=0, oos_fraction=0.25, min_support=3)
        self.assertEqual(oos["train_candidates"], 1)
        self.assertEqual(oos["oos_surviving"], 1)

    def test_train_only_association_does_not_survive(self):
        # Association in the training block; the holdout has A without B.
        hist = ([[57, 49, 10, 20, 30]] * 60 + [[1, 2, 3, 4, 5]] * 40
                + [[57, 1, 2, 3, 4]] * 40)
        oos = _oos_replication(
            hist, [(57, 49)], horizon=0, oos_fraction=0.286, min_support=3)
        self.assertEqual(oos["train_candidates"], 1)
        self.assertEqual(oos["oos_surviving"], 0)


class TestEvaluateFamily(unittest.TestCase):
    def test_four_hypotheses_separate(self):
        res = evaluate_family(_uniform_hist(120), permutations=0, seed=1)
        self.assertEqual(
            set(res["hypotheses"]),
            {"H1_IMAGE", "H2_CALLING", "H3_CALLING_IMAGE",
             "H4_CALLING_IMAGE_POSITION"})
        for code in ("H1_IMAGE", "H2_CALLING", "H3_CALLING_IMAGE"):
            self.assertEqual(set(res["hypotheses"][code]["per_horizon"]),
                             {"0", "1", "3"})
        self.assertIn("position",
                      res["hypotheses"]["H4_CALLING_IMAGE_POSITION"]["per_horizon"])

    def test_deterministic(self):
        hist = _uniform_hist(150)
        self.assertEqual(
            evaluate_family(hist, seed=2), evaluate_family(hist, seed=2))


class TestPickers(unittest.TestCase):
    def test_calling_picker_uses_last_draw(self):
        hist = _uniform_hist(50) + [[57, 10, 20, 30, 40]]
        picks = predict_calling_numbers(hist, random.Random(0), 3)
        self.assertTrue(set(picks) <= {49, 78, 79, 18, 16})
        self.assertEqual(len(picks), 3)
        self.assertEqual(picks, sorted(picks))

    def test_image_picker_uses_last_draw(self):
        hist = _uniform_hist(50) + [[57, 10, 20, 30, 40]]
        picks = predict_image_numbers(hist, random.Random(0), 2)
        self.assertTrue(set(picks) <= {75, 1, 2, 3, 4})

    def test_calling_image_picker_combines(self):
        hist = _uniform_hist(50) + [[57, 10, 20, 30, 40]]
        picks = predict_calling_image(hist, random.Random(0), 6)
        self.assertTrue(set(picks) <= set(CALLING_IMAGE_EDGES[57]))

    def test_position_picker_prefers_planted(self):
        rng = random.Random(8)
        hist = []
        for _ in range(80):
            d = rng.sample(range(1, 91), 5)
            d[0], d[1] = 57, 49
            hist.append(d)
        hist.append([57, 60, 61, 62, 63])
        picks = predict_calling_image_position(hist, random.Random(0), 1)
        self.assertEqual(picks, [49])

    def test_pickers_valid_deterministic(self):
        hist = _uniform_hist(60)
        for fn in (predict_calling_numbers, predict_image_numbers,
                   predict_calling_image, predict_calling_image_position):
            for k in (2, 5):
                a = fn(hist, random.Random(0), k)
                b = fn(hist, random.Random(0), k)
                self.assertEqual(a, b)
                self.assertEqual(len(a), k)
                self.assertTrue(all(1 <= n <= 90 for n in a))

    def test_pickers_empty_history(self):
        for fn in (predict_calling_numbers, predict_image_numbers,
                   predict_calling_image, predict_calling_image_position):
            self.assertEqual(len(fn([], random.Random(0), 2)), 2)

    def test_picker_no_lookahead(self):
        # The pick is a pure function of the supplied history prefix.
        hist = _uniform_hist(80)
        full = predict_calling_numbers(hist, random.Random(0), 3)
        prefixed = predict_calling_numbers(hist[:-1], random.Random(0), 3)
        extended = predict_calling_numbers(
            hist + [[1, 2, 3, 4, 5]], random.Random(0), 3)
        # Dropping the last draw changes the trigger set — and must not
        # leave the output unchanged unless it genuinely coincides.
        self.assertEqual(len(full), 3)
        self.assertNotEqual(full, extended)
        self.assertNotEqual(prefixed, extended)


if __name__ == "__main__":
    unittest.main()
