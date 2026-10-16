"""Offline model checks; synthetic inputs, no local raws, renderer, or physics.

May also run via unittest to avoid starting the heavyweight shared pytest suite.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

EXP = Path(__file__).resolve().parents[1] / 'experiments/2026-09-30-l1-lateral-error'


def load(name):
    spec = importlib.util.spec_from_file_location('lateral_' + name, EXP / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


a, ex = load('analyze'), load('extract')


class LateralModelTests(unittest.TestCase):
    def test_signed_route_coordinates_rotate_without_losing_side(self):
        self.assertEqual(ex.signed_errors((0, 0), (1, 0), (1.03, -.04)), (.030000000000000027, -.04))
        along, cross = ex.signed_errors((0, 0), (0, -1), (.04, -1.03))
        self.assertAlmostEqual(along, .03)
        self.assertAlmostEqual(cross, .04)
        with self.assertRaises(ValueError):
            ex.signed_errors((0, 0), (0, 0), (0, 1))

    def test_both_leg_euclidean_gate_and_inclusive_boundary(self):
        al = np.array([[60., 0.], [60., 0.], [0., 0.]])
        lat = np.array([[80., 99.], [80.00001, 0.], [0., 101.]])
        np.testing.assert_array_equal(a.pass_mask(al, lat), [True, False, False])

    def test_fit_recovers_two_outputs_and_rejects_singular_data(self):
        x = np.column_stack([np.ones(6), np.arange(6)])
        b = np.array([[5., -3.], [2., 8.]])
        actual, res = a.fit(x, x @ b)
        np.testing.assert_allclose(actual, b, atol=1e-12)
        np.testing.assert_allclose(res, 0, atol=1e-12)
        with self.assertRaises(ValueError):
            a.fit(np.ones((6, 2)), np.zeros((6, 2)))
        with self.assertRaises(ValueError):
            a.fit(x[:2], np.zeros((2, 2)))

    def test_holdout_target_never_enters_its_fit(self):
        x = np.column_stack([np.ones(12), np.tile(np.arange(4), 3)])
        g = np.repeat(['A', 'B', 'C'], 4)
        y = np.column_stack([x[:, 1], 2 * x[:, 1]]) + np.repeat([0, 10, 30], 4)[:, None]
        first = a.crossfit_residuals(x, y, g)
        changed = y.copy()
        changed[g == 'C'] += 1000
        second = a.crossfit_residuals(x, changed, g)
        np.testing.assert_allclose(second[g == 'C'] - first[g == 'C'], 1000)
        np.testing.assert_allclose(y[g == 'C'] - first[g == 'C'], changed[g == 'C'] - second[g == 'C'])

    def test_holdout_purges_repeated_geometry_across_families(self):
        groups = np.array(['C', 'C', 'R', 'X'])
        poses = np.array([[.9298, -.0204, -3.901], [1., 0., 0.],
                          [.9298392, -.0204454, -3.9014938], [1.05, .1, 4.]])
        train, test = a.holdout_train(groups, 'R', poses)
        np.testing.assert_array_equal(train, [False, True, False, True])
        np.testing.assert_array_equal(test, [False, False, True, False])

    def test_new_sheet_does_not_create_a_new_station_placement(self):
        rows = []
        for cohort, cell, lag, sheet in [('b-v6h-gain-69c2a99a-cB', 'F_hR2_04', 0., 1.),
                                         ('b-v6h-gain-f5d83fdb-tX1', 'X00_F_hR2_04', 1., .9)]:
            for leg in (0., 1.):
                rows.append({'cohort': cohort, 'stage': 'chain', 'cell': cell, 'seed': 911., 'leg': leg,
                             'place_x': .9298, 'place_y': -.0204, 'place_yaw_deg': -3.901, 'sheet_x': sheet,
                             'prior_id': 'hR2_04', 'lateral_mm': 10., 'axial_mm': 0., 'axial_lag': lag,
                             'setup': 'ENVS' if lag else 'ENV'})
        units, excluded = a.select_model_units(rows)
        self.assertEqual([r['unit'] for r in units], ['X/X00_F_hR2_04'])
        self.assertEqual(excluded[0]['excluded_unit'], 'C/F_hR2_04')

    def test_duplicate_seeds_are_one_unit_and_incomplete_chains_are_excluded(self):
        rows = []
        for seed in (911., 913.):
            for leg in (0., 1.):
                rows.append({'cohort': 'raw', 'stage': 'chain', 'cell': 'p1', 'seed': seed, 'leg': leg,
                             'place_x': 1., 'place_y': .05, 'place_yaw_deg': 0., 'sheet_x': 1.,
                             'prior_id': 'q1', 'lateral_mm': seed - 911 + 10 * leg, 'axial_mm': 0.})
        rows.append({**rows[0], 'cell': 'unfinished'})
        units = a.make_units(rows, {'raw': 'C'})
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]['n_seeds'], 2)
        self.assertEqual(units[0]['y'], [1., 11.])
        bad = [dict(r) for r in rows]
        bad[2]['place_x'] = 9
        with self.assertRaises(ValueError):
            a.make_units(bad, {'raw': 'C'})

    def test_residual_draw_preserves_pair_and_shared_prior(self):
        res = np.array([[1., 10.], [2., 20.], [3., 30.], [4., 40.]])
        families = np.array(['A', 'A', 'B', 'B'])
        got = a.draw_residuals(res, families, ['p1', 'p2', 'p1'], np.random.default_rng(11), 'shared_cohort_prior')
        np.testing.assert_array_equal(got[0], got[2])
        np.testing.assert_array_equal(got[:, 1], got[:, 0] * 10)
        self.assertTrue(np.all(got[:, 0] <= 2) or np.all(got[:, 0] >= 3))

    def test_joint_probability_is_not_product_of_leg_marginals(self):
        al = np.zeros((1, 1, 2))
        mu = np.zeros((1, 2))
        res = np.array([[0., 101.], [101., 0.]])
        p = a.expected_probabilities(al, mu, res, np.array(['A', 'A']))
        self.assertEqual(p[0], 0.)  # multiplying two marginal 0.5s would incorrectly give 0.25

    def test_equal_family_weight_not_duplicate_row_weight(self):
        al, mu = np.zeros((1, 1, 2)), np.zeros((1, 2))
        res = np.array([[0., 0.], [0., 0.], [0., 0.], [101., 101.]])
        p = a.expected_probabilities(al, mu, res, np.array(['A', 'A', 'A', 'B']))
        self.assertEqual(p[0], .5)

    def test_seed_mean_is_not_treated_as_a_single_seed_forecast(self):
        delta = a.seed_deviations([[[0., 0.], [2., 4.]], [[3., 3.], [3., 3.]]])
        np.testing.assert_array_equal(delta, [[-1., -2.], [1., 2.], [0., 0.], [0., 0.]])
        bank, groups = a.convolve_seed_variation(np.array([[10., 20.]]), np.array(['A']), delta)
        np.testing.assert_array_equal(bank, [[9., 18.], [11., 22.], [10., 20.], [10., 20.]])
        np.testing.assert_array_equal(groups, ['A'] * 4)

    def test_phase_compression_retains_original_tick_weights(self):
        # Three of four phases pass, even though only two distinct arrays occur.
        al = np.array([[[0., 0.]], [[0., 0.]], [[0., 0.]], [[101., 0.]]])
        prob = a.expected_probabilities(al, np.zeros((1, 2)), np.zeros((1, 2)), np.array(['A']))
        self.assertEqual(prob[0], .75)

    def test_cohort_bootstrap_is_reproducible_and_omits_whole_families(self):
        g = np.repeat(['A', 'B', 'C'], 6)
        ix = a.group_bootstrap_indices(g, np.random.default_rng(2))
        np.testing.assert_array_equal(ix, a.group_bootstrap_indices(g, np.random.default_rng(2)))
        self.assertEqual(len(ix), 18)
        self.assertLess(len(set(g[ix])), 3)
        for block in ix.reshape(3, 6):
            self.assertEqual(len(set(g[block])), 1)

    def test_hash_verifies_exact_bytes_and_detects_input_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / 'case.json'
            p.write_bytes(b'{"n":1}')
            reader = ex.Reader(root)
            reader.read(p, ex.digest(p.read_bytes()))
            with self.assertRaises(ValueError):
                reader.read(p, '0' * 64)
            p.write_bytes(b'{"n":2}')
            with self.assertRaises(ValueError):
                reader.read(p)


if __name__ == '__main__':
    unittest.main()
