"""CPU regression/condition suites. No GPU, episodes, model or launcher exec.

Existing test modules are byte-preserved. Their shared pilot fixture gains
synthetic evaluation motion through the new optional argument, in memory only.
"""
import importlib.abc
import sys


class NoRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('torch', 'mujoco', 'warp'):
            raise ImportError('condition tests forbid model/simulator imports: ' + fullname)


sys.meta_path.insert(0, NoRuntime())
import test_cpu as base
import test_audit_cpu as legacy
from audit_cpu import MOTION_SCHEMA, TRANSLATION_THRESHOLD_M, physical_motion, pilot_gate, read_physical_motion
from future_driver import Guard
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest


def eval_rows(distance=TRANSLATION_THRESHOLD_M * 2, spin=False, count=3, origin=2.2):
    return [dict(t=origin + i * .1,
        robots={r: dict(pose=[distance * i / (count - 1), 0., i * .8 if spin else 0.])
                for r in base.ROLES}) for i in range(count)]


def measured(distance=TRANSLATION_THRESHOLD_M * 2):
    return physical_motion(eval_rows(distance))


def completions():
    return [(i, legacy.raw()) for i in range(4)]


def motion_records(rows, distance=TRANSLATION_THRESHOLD_M * 2):
    return {i: measured(distance) for i, _ in rows}


def pilot_fixture(rows):
    return pilot_gate(rows, motion_records(rows))


# The nine old assertions remain intact; only their newly required input is
# supplied. Separate tests below prove absence/invalidity must fail closed.
legacy.pilot_gate = pilot_fixture


def make_lane(out, world, distance=TRANSLATION_THRESHOLD_M * 2):
    directory = out / f'world-{world:03d}' / 'raw'
    directory.mkdir(parents=True)
    data = ''.join(json.dumps(row) + '\n' for row in eval_rows(distance)).encode()
    (directory / 'eval-only.jsonl').write_bytes(data)
    raw = legacy.raw()
    raw.update(sim_s=.3, cap_end=False)
    return raw


class ConditionsTests(unittest.TestCase):
    def test_command_only_without_eval_motion_fails(self):
        decision = pilot_gate(completions())
        self.assertFalse(decision['pass_gate'])
        self.assertEqual(len(decision['motion_issues']), 4)

    def test_translation_passes_even_all_approach(self):
        rows = completions()
        decision = pilot_gate(rows, motion_records(rows))
        self.assertTrue(decision['pass_gate'])
        self.assertTrue(decision['all_approach'])
        self.assertEqual(decision['physical_motion_column'], 'max_xy_excursion_m')

    def test_rotation_in_place_is_not_translation(self):
        rows = completions()
        motion = physical_motion(eval_rows(0., spin=True))
        self.assertGreater(motion['robots']['r1']['yaw_path_rad'], 0.)
        decision = pilot_gate(rows, {i: motion for i, _ in rows})
        self.assertFalse(decision['pass_gate'])
        self.assertEqual(decision['translated_robot_worlds'], [])

    def test_baseline_envelope_is_strict(self):
        rows = completions()
        for value in (0., TRANSLATION_THRESHOLD_M / 2, TRANSLATION_THRESHOLD_M):
            with self.subTest(value=value):
                self.assertFalse(pilot_gate(rows, motion_records(rows, value))['pass_gate'])
        above = math.nextafter(TRANSLATION_THRESHOLD_M, math.inf)
        self.assertTrue(pilot_gate(rows, motion_records(rows, above))['pass_gate'])

    def test_missing_robot_or_world_fails(self):
        rows = completions()
        for kind in ('world', 'robot'):
            records = motion_records(rows)
            if kind == 'world':
                del records[0]
            else:
                del records[0]['robots']['r2']
            self.assertFalse(pilot_gate(rows, records)['pass_gate'])

    def test_invalid_excursion_fails(self):
        rows = completions()
        for value in (None, float('nan'), float('inf'), -1., True, '0.5'):
            records = motion_records(rows)
            records[0]['robots']['r1']['max_xy_excursion_m'] = value
            with self.subTest(value=value):
                self.assertFalse(pilot_gate(rows, records)['pass_gate'])

    def test_path_and_net_are_separate_from_excursion(self):
        rows = eval_rows(0.)
        for rid in base.ROLES:
            rows[1]['robots'][rid]['pose'][0] = .2
        metric = physical_motion(rows)['robots']['r1']
        self.assertEqual(metric['net_xy_displacement_m'], 0.)
        self.assertEqual(metric['max_xy_excursion_m'], .2)
        self.assertEqual(metric['xy_path_m'], .4)

    def test_plain_and_zstd_logs_have_same_derived_motion_and_raw_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            raw = make_lane(out, 0)
            directory = out / 'world-000/raw'
            path = directory / 'eval-only.jsonl'
            data = path.read_bytes()
            plain = read_physical_motion(directory, raw)
            self.assertEqual(plain['status'], 'MEASURED')
            self.assertEqual(plain['sha256'], hashlib.sha256(data).hexdigest())
            path.unlink()  # synthetic fixture only
            packed = subprocess.check_output(['zstd', '-q', '-c'], input=data)
            compressed = directory / 'eval-only.jsonl.zst'
            compressed.write_bytes(packed)
            zipped = read_physical_motion(directory, raw)
            self.assertEqual(zipped['robots'], plain['robots'])
            self.assertEqual(zipped['decoded_sha256'], plain['decoded_sha256'])
            self.assertEqual(compressed.read_bytes(), packed)

    def test_missing_or_ambiguous_or_corrupt_log_is_unmeasured(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            raw = legacy.raw()
            self.assertEqual(read_physical_motion(directory, raw)['status'], 'UNMEASURED')
            (directory / 'eval-only.jsonl').write_text('invalid JSON\n')
            self.assertEqual(read_physical_motion(directory, raw)['status'], 'UNMEASURED')
            (directory / 'eval-only.jsonl.zst').write_bytes(b'invalid zstd')
            self.assertEqual(read_physical_motion(directory, raw)['status'], 'UNMEASURED')

    def test_invalid_pose_time_gap_and_one_sample_fail(self):
        variants = [eval_rows(), eval_rows(), eval_rows(), eval_rows()[:1]]
        variants[0][1]['robots']['r1']['pose'][0] = float('nan')
        variants[1][1]['t'] = variants[1][0]['t']
        variants[2][1]['t'] += 5.
        for rows in variants:
            with self.assertRaises(ValueError):
                physical_motion(rows)

    def test_episode_coverage_required(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            raw = make_lane(out, 0)
            raw['sim_s'] = 180.
            record = read_physical_motion(out / 'world-000/raw', raw)
            self.assertEqual(record['status'], 'UNMEASURED')
            self.assertIn('cover_episode', record['reason'])

    def test_finalize_zero_through_three_completed_fails_even_with_speed_measurement(self):
        for count in range(4):
            with self.subTest(completed=count), tempfile.TemporaryDirectory() as folder:
                out = Path(folder)
                args = SimpleNamespace(out=out)
                guard = Guard('arm_c')
                guard.speed_checked = True
                for i in range(count):
                    self.assertFalse(guard.completed(i, make_lane(out, i), args, {}))
                self.assertTrue(guard.finalize(out))
                record = json.loads((out / 'pilot-gate.json').read_text())
                self.assertFalse(record['pass_gate'])
                self.assertFalse(record['followup_allowed'])
                self.assertEqual(record['observed_completed_episodes'], count)
                self.assertEqual(record['reason'], 'fewer_than_four_completed_episodes')

    def test_finalize_short_without_speed_writes_both_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            guard = Guard('arm_c')
            self.assertTrue(guard.finalize(out))
            self.assertFalse(json.loads((out / 'pilot-gate.json').read_text())['pass_gate'])
            self.assertTrue(json.loads((out / 'treatment-first30-audit.json').read_text())['SPEED_GATE_FAIL'])

    def test_fourth_completion_persists_gate_and_order_without_changing_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            guard = Guard('arm_c')
            guard.speed_checked = True
            order = [7, 2, 12, 0]
            for i in order:
                raw = make_lane(out, i)
                original = deepcopy(raw)
                self.assertFalse(guard.completed(i, raw, SimpleNamespace(out=out), {}))
                self.assertEqual(raw, original)
            path = out / 'pilot-gate.json'
            data = path.read_bytes()
            record = json.loads(data)
            self.assertTrue(record['pass_gate'])
            self.assertEqual(record['completed_worlds'], order)
            self.assertFalse(guard.finalize(out))
            self.assertEqual(path.read_bytes(), data)

    def test_four_completed_without_translation_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            guard = Guard('arm_c')
            for i in range(4):
                stopped = guard.completed(i, make_lane(out, i, 0.), SimpleNamespace(out=out), {})
            self.assertTrue(stopped)
            self.assertFalse(json.loads((out / 'pilot-gate.json').read_text())['pass_gate'])

    def test_exception_then_finalize_records_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            guard = Guard('arm_c')
            guard.speed_checked = True
            try:
                guard.completed(0, make_lane(out, 0), SimpleNamespace(out=out), {})
                raise RuntimeError('synthetic host exception; no launcher invoked')
            except RuntimeError:
                pass
            finally:
                guard.finalize(out)
            self.assertFalse(json.loads((out / 'pilot-gate.json').read_text())['pass_gate'])

    def test_arm_s_does_not_fabricate_arm_c_pilot(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            guard = Guard('arm_s')
            guard.speed_checked = True
            self.assertFalse(guard.finalize(out))
            self.assertFalse((out / 'pilot-gate.json').exists())

    def test_f07_s_cases_are_computed_from_original_stage_sets(self):
        counts = {}
        for key, stages in [('s_close_robot_cases', base.p.WITHDRAW_STAGES),
                            ('s_held_robot_cases', base.p.POST_GO_STAGES)]:
            observed = 0
            for stage in stages:
                ctrl = base.TreatmentController(base.Script(lambda o, value=stage: (value, False)),
                    base.ROLES, 'ep', base.INIT, mode='arm_s')
                _, issued = base.tick(ctrl, 0.)
                for value in issued.values():
                    self.assertEqual(value['software_hold'], key == 's_held_robot_cases')
                    observed += 1
            self.assertEqual(observed, len(stages) * len(base.ROLES))
            counts[key] = observed
        base.MEASUREMENTS.update(counts)

    def test_f07_diagnostic_ready_ticks_recorded(self):
        frames = [0., .1, .2]  # Existing c_ready diagnostic fixture, not an acceptance threshold.
        ctrl = base.TreatmentController(base.Script(lambda o: ('ready', False)),
            base.ROLES, 'ep', base.INIT, mode='arm_c')
        count = 0
        for t in frames:
            proposed, _ = base.tick(ctrl, t)
            count += sum(row['ready'] for row in proposed.values())
        self.assertEqual(count, len(frames) * len(base.ROLES))
        self.assertTrue(all(not b.ready and b.pending is None and not b.started for b in ctrl.barriers.values()))
        base.MEASUREMENTS['c_ready_diagnostic'] = dict(ticks=len(frames), robot_N=len(base.ROLES),
            ready_robot_ticks=count, formula='len(frames)*len(ROLES)',
            skill_counts={rid: metric['skill_counts'] for rid, metric in ctrl.summary()['treatment']['metrics'].items()})


if __name__ == '__main__':
    out = Path(sys.argv[1])
    all_ok = True
    for case, name in [(base.TreatmentTests, 'cpu-tests-conditions-v3.json'),
                       (legacy.AuditTests, 'audit-tests-regression-v3.json'),
                       (ConditionsTests, 'conditions-tests-v1.json')]:
        result = unittest.TextTestRunner(resultclass=base.Results, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(case))
        report = dict(tests=result.rows, tests_run=result.testsRun,
            failures=len(result.failures), errors=len(result.errors), metrics=base.MEASUREMENTS,
            gpu_runs=0, episodes_started=0, model_forward_calls=0, launcher_executed=False,
            simulator_modules=[n for n in sys.modules if n.split('.')[0] in ('mujoco', 'warp')],
            model_modules=[n for n in sys.modules if n.split('.')[0] == 'torch'],
            legacy_pilot_fixture='unchanged assertions; in-memory optional physical_motion_records added')
        with (out / name).open('x') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
        all_ok = all_ok and result.wasSuccessful()
    sys.exit(0 if all_ok else 1)
