"""CPU-only tests of the pilot stop hook and cap_end bookkeeping."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from audit_cpu import pilot_gate, termination
from future_driver import Guard, instrument


def raw():
    metric = dict(ticks=10, inference_calls=10, discard_calls=10, issued_ticks=10,
        stage_counts={'approach': 10}, skill_counts={'grasp': 10}, state225_nonzero=0,
        nonzero_wheel_ticks=1)
    return dict(status='complete', cap_end=True, sim_s=180., student_eval=dict(finished_t=None,
        barrier_events={'r1': [], 'r2': []}, treatment=dict(mode='arm_c', episode_origin_t=2.2,
            metrics={'r1': metric, 'r2': deepcopy(metric)})))


class AuditTests(unittest.TestCase):
    def test_early_failure_not_batch_cap_end(self):
        r = raw()
        r.update(cap_end=False, sim_s=90.)
        r['student_eval']['finished_t'] = 92.2
        d = termination(r, batch_cap_end=True)
        self.assertEqual(d['termination'], 'learned_finished_early')
        self.assertTrue(d['batch_raw_cap_end_disagreement'])
        self.assertTrue(d['denominator_included'])
        self.assertEqual(d['finished_elapsed_s'], 90.)

    def test_real_cap_remains_in_denominator(self):
        self.assertEqual(termination(raw(), True)['termination'], 'cap_end')
        self.assertTrue(termination(raw())['denominator_included'])

    def test_conflicting_raw_cap_is_unclassified(self):
        r = raw()
        r['sim_s'] = 90.
        self.assertEqual(termination(r)['termination'], 'UNCLASSIFIED')

    def test_host_error_not_episode_failure(self):
        r = raw()
        r['status'] = 'HOST_ERROR'
        self.assertFalse(termination(r)['denominator_included'])

    def test_all_approach_default_continue_after_four(self):
        d = pilot_gate([(i, raw()) for i in range(4)])
        self.assertTrue(d['pass_gate'])
        self.assertTrue(d['all_approach'])
        self.assertEqual(d['nonzero_wheel_robot_ticks'], 8)

    def test_pilot_four_separate_failure_checks(self):
        for kind in ('close', 'no_motion', 'cadence', 'host'):
            rows = [(i, raw()) for i in range(4)]
            if kind == 'close':
                rows[0][1]['student_eval']['barrier_events']['r1'].append(dict(event='proposal_rejected', reason_category='close_before_learned_ready'))
            elif kind == 'no_motion':
                for _, row in rows:
                    for m in row['student_eval']['treatment']['metrics'].values():
                        m['nonzero_wheel_ticks'] = 0
            elif kind == 'cadence':
                rows[0][1]['student_eval']['treatment']['metrics']['r1']['discard_calls'] = 2
            else:
                rows[0][1]['status'] = 'HOST_ERROR'
            self.assertFalse(pilot_gate(rows)['pass_gate'])

    def test_pilot_requires_exactly_four(self):
        with self.assertRaises(ValueError):
            pilot_gate([(0, raw())])

    def test_pinned_runner_ast_compiles_without_import(self):
        here = Path(__file__).parent
        ref = json.loads((here / 'baseline-reference.json').read_text())
        tree, counts = instrument(Path(ref['aliases']['L']).read_text())
        self.assertEqual(counts, dict(completion=1, progress=1))
        compile(tree, 'synthetic_no_exec', 'exec')

    def test_early_all_finished_missing_first30_stops_followup(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            guard = Guard('arm_c')
            self.assertTrue(guard.finalize(Path(folder)))
            record = json.loads((Path(folder) / 'treatment-first30-audit.json').read_text())
            self.assertTrue(record['SPEED_GATE_FAIL'])
            self.assertIsNone(record['median_wall_per_world_SIM'])


if __name__ == '__main__':
    import sys
    from test_cpu import Results
    result = unittest.TextTestRunner(resultclass=Results, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AuditTests))
    with Path(sys.argv[1]).open('x') as out:
        json.dump(dict(tests=result.rows, tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
            gpu_runs=0, simulator_imported=False, launcher_executed=False), out, indent=2)
    sys.exit(0 if result.wasSuccessful() else 1)
