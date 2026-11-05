"""Pure recorded-row checks; optional pinned local evaluator, no physics/model."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from harness.pair_carry_certification import certify

SNAP = Path('/home/ubuntu/UGRP/experiments/2026-11-04-astra-strict-eval-v1/snapshot')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class OptOut(unittest.TestCase):
    def test_does_not_add_keys_or_mutate_original(self):
        saved = {'success': True, 'nested': [1]}
        out = certify([], {}, [], evaluator=None, geometry=None, stored_result=saved)
        self.assertEqual(out, saved)
        out['nested'].append(2)
        self.assertEqual(saved['nested'], [1])


@unittest.skipUnless((SNAP / 'harness/pair_carry_eval.py').is_file(), 'local pinned evaluation source unavailable')
class Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geom = load(SNAP / 'harness/pair_carry_teacher_warp.py', '_cert_test_teacher')
        with patch.dict(sys.modules, {'harness.pair_carry_teacher_warp': cls.geom}):
            cls.ev = load(SNAP / 'harness/pair_carry_eval.py', '_cert_test_evaluator')
        cls.map = json.loads((SNAP / 'maps/zones_final_v3/zone_wide_two_doors_final_v3.json').read_text())

    def rows(self, x=4.6):
        return [{'t': k * .1, 'beam': {'pose': [x, -2.1, 1.5707963267948966],
            'xyz': [x, -2.1, .02], 'min_z': 0., 'tilt_deg': 0.},
            'robots': {'r1': {'pose': [x, -2.7, 0.]}, 'r2': {'pose': [x, -1.5, 3.141592653589793]}},
            'contacts': {'r1': [0., 0.], 'r2': [0., 0.]}} for k in range(30)]

    def check(self, rows, **kwargs):
        args = dict(evaluator=self.ev, geometry=self.geom, handover_t=-.1,
            lower_start_t=0., registration={'cohort_id': 'synthetic-tests', 'version': 'v1'},
            parent_ids=['fixture:raw'], input_kind='SYNTHETIC_COUNTEREXAMPLE_NOT_REAL_RUN', opt_in=True)
        args.update(kwargs)
        return certify(rows, self.map, ['r1', 'r2'], **args)

    def test_preplaced_zero_m(self):
        rows = self.rows()
        self.assertTrue(self.ev.evaluate(rows, self.map, ['r1', 'r2'], lower_start_t=0.)['success'])
        result = self.check(rows)
        self.assertEqual(result['axes']['D']['status'], 'refused')
        self.assertEqual(result['verdict'], 'refused')

    def test_east_start_and_no_grasp(self):
        rows = self.rows(3.)
        for k, r in enumerate(rows):
            x = 3. + 1.6 * min(k, 10) / 10
            r['beam']['pose'][0] = r['beam']['xyz'][0] = x
            for robot in r['robots'].values():
                robot['pose'][0] = x
        r = self.check(rows, lower_start_t=1.5)
        self.assertEqual(r['axes']['A']['status'], 'refused')
        self.assertEqual(r['axes']['B']['status'], 'refused')

    def test_negative_height_stays_unknown(self):
        rows = self.rows()
        for r in rows:
            r['beam']['min_z'] = -1.
        self.assertEqual(self.check(rows)['axes']['F']['status'], 'unknown')

    def test_release_duration_stays_unknown(self):
        self.assertEqual(self.check(self.rows())['axes']['G']['status'], 'unknown')

    def test_contradictory_saved_report_refused(self):
        rows = self.rows()
        saved = self.ev.evaluate(rows, self.map, ['r1', 'r2'], lower_start_t=0.)
        saved['drop_events'] = [{'kind': 'synthetic'}]
        self.assertEqual(self.check(rows, stored_result=saved)['axes']['E']['status'], 'refused')

    def test_changed_saved_window_is_unknown(self):
        saved = {'success': False, 'handover_t': 9., 'lower_start_t': 10.}
        report = self.check(self.rows(), stored_result=saved)
        self.assertEqual(report['axes']['E']['status'], 'unknown')
        self.assertTrue(report['axes']['E']['boundary_mismatch'])

    def test_boundary_mismatch_does_not_hide_internal_contradiction(self):
        saved = {'success': True, 'placed_in_zone': False, 'handover_t': 9.}
        self.assertEqual(self.check(self.rows(), stored_result=saved)['axes']['E']['status'], 'refused')

    def test_unavailable_geometry_refuses_without_throwing(self):
        for error in (KeyError('door'), StopIteration(), NotImplementedError()):
            with self.subTest(error=type(error).__name__):
                with patch.object(self.geom, 'door_of', side_effect=error):
                    report = self.check(self.rows(), lower_start_t=None)
                self.assertEqual(report['axes']['A']['status'], 'refused')

    def test_unavailable_recomputation_refuses_without_throwing(self):
        with patch.object(self.ev, 'evaluate', side_effect=KeyError('zone')):
            report = self.check(self.rows())
        self.assertEqual(report['axes']['E']['status'], 'refused')

    def test_single_interval_jump_refused(self):
        rows = self.rows(3.)
        for r in rows[1:]:
            r['beam']['pose'][0] = 4.6
        self.assertEqual(self.check(rows)['axes']['D']['status'], 'refused')

    def test_timestamp_disorder_refused(self):
        rows = self.rows()
        rows[1]['t'] = rows[0]['t']
        self.assertEqual(self.check(rows)['verdict'], 'refused')

    def test_missing_registration_is_unknown(self):
        self.assertEqual(self.check(self.rows(), registration=None)['axes']['C']['status'], 'unknown')

    def test_missing_boundary_is_unknown(self):
        self.assertEqual(self.check(self.rows(), handover_t=None)['verdict'], 'unknown')

    def test_invalid_nonfinite_data_refused(self):
        rows = self.rows()
        rows[0]['beam']['pose'][0] = float('nan')
        self.assertEqual(self.check(rows)['verdict'], 'refused')

    def test_inputs_and_legacy_result_unmodified(self):
        rows = self.rows()
        before = copy.deepcopy(rows)
        saved = {'success': True}
        self.check(rows, stored_result=saved)
        self.assertEqual(rows, before)
        self.assertEqual(saved, {'success': True})


if __name__ == '__main__':
    unittest.main()
