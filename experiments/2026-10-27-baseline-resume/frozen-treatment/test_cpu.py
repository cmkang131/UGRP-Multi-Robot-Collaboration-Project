"""Synthetic proposals/JSON IPC only. No simulator, actor inference or GPU."""
import base64
from copy import deepcopy
import importlib.abc
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import unittest

os.environ['CUDA_VISIBLE_DEVICES'] = ''
sys.dont_write_bytecode = True


class NoSimulator(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('mujoco', 'warp'):
            raise ImportError('CPU synthetic validation forbids simulator import: ' + fullname)


sys.meta_path.insert(0, NoSimulator())
HERE = Path(__file__).resolve().parent
REF = json.loads((HERE / 'baseline-reference.json').read_text())
sys.path.insert(0, REF['aliases']['S'])
from harness import grasp_act_contract as c
from harness import pairact_r1 as p
from harness import pairact_r1_student as s
from controller import ORIGINAL_CONTROLLER, TreatmentBarrier, TreatmentController

ROLES = {'r1': 'teal', 'r2': 'blue'}
INIT = {r: dict(t=0., wheels=[0.] * 4, duration_s=[0.] * 4,
               pwm={str(k): 2000 if k == 1 else 1500 for k in c.SERVOS}) for r in ROLES}
MEASUREMENTS = {}


class Script:
    def __init__(self, fn):
        self.fn, self.calls = fn, []

    def __call__(self, obs, jpegs):
        self.calls.append(deepcopy(obs))
        stage, done = self.fn(obs)
        action = dict(t=obs['t'], wheels=[.31] * 4, duration_s=[.1] * 4,
                      pwm={str(k): 1800 if k == 1 else 1500 for k in c.SERVOS})
        logits = [[float(k == p.STAGES.index(stage)) for k in range(len(p.STAGES))]] * c.CHUNK
        return dict(chunk=[c.encode_action(action, done=done)] * c.CHUNK, stage_logits=logits)


def tick(ctrl, t, *, permits=None, previous=None):
    robots = {r: dict(jpeg=('own-' + r).encode(), issued=deepcopy((previous or INIT)[r])) for r in ROLES}
    proposed = ctrl.propose(t, robots)
    issued = ctrl.issue(t, permits if permits is not None else {r: False for r in ROLES})
    return proposed, issued


class TreatmentTests(unittest.TestCase):
    def test_c_close_passes_all_withdraw_stages(self):
        for stage in p.WITHDRAW_STAGES:
            ctrl = TreatmentController(Script(lambda o: (stage, False)), ROLES, 'ep', INIT, mode='arm_c')
            proposed, out = tick(ctrl, 0.)
            for r in ROLES:
                self.assertFalse(out[r]['blocked'])
                self.assertEqual(out[r]['command']['pwm']['1'], 1800)
                self.assertEqual(out[r]['command']['wheels'], [.31] * 4)
            self.assertFalse(any(e['event'] == 'proposal_rejected' for b in ctrl.barriers.values() for e in b.events))
        MEASUREMENTS['c_close_robot_cases'] = len(p.WITHDRAW_STAGES) * len(ROLES)

    def test_c_execute_carry_place_complete_without_permit(self):
        for stage in p.POST_GO_STAGES:
            ctrl = TreatmentController(Script(lambda o: (stage, False)), ROLES, 'ep', INIT, mode='arm_c')
            _, out = tick(ctrl, 0.)
            for row in out.values():
                self.assertFalse(row['blocked'])
                self.assertFalse(row['permit'])
                self.assertFalse(row['software_hold'])
                self.assertEqual(row['command']['wheels'], [.31] * 4)
        MEASUREMENTS['c_no_permit_robot_cases'] = len(p.POST_GO_STAGES) * len(ROLES)

    def test_c_one_done_releases_only_that_robot(self):
        ctrl = TreatmentController(Script(lambda o: ('execute', o['robot_id'] == 'r1')), ROLES, 'ep', INIT, mode='arm_c')
        for k in range(48):
            tick(ctrl, round(k * c.PERIOD_S, 8))
            if k == 30:
                self.assertEqual(ctrl.segments, dict(r1='release', r2='grasp'))
                self.assertEqual(ctrl.release_t, dict(r1=3., r2=None))
        self.assertIsNotNone(ctrl.robot_finish_t['r1'])
        self.assertIsNone(ctrl.robot_finish_t['r2'])
        self.assertFalse(ctrl.finished)
        self.assertEqual(ctrl._token('r1'), ('grasp', 'B'))
        self.assertEqual(ctrl._token('r2'), ('grasp', 'none'))
        MEASUREMENTS['c_independent'] = dict(release_t=ctrl.release_t, robot_finish_t=ctrl.robot_finish_t, ticks=48)

    def test_c_peer_permits_cannot_change_actions_or_tokens(self):
        fn = lambda o: (p.STAGES[int(round(o['t'] * 10)) % len(p.STAGES)], o['robot_id'] == 'r1' and o['t'] >= 1.)
        a = TreatmentController(Script(fn), ROLES, 'ep', INIT, mode='arm_c')
        b = TreatmentController(Script(fn), ROLES, 'ep', INIT, mode='arm_c')
        pa, pb = deepcopy(INIT), deepcopy(INIT)
        for k in range(80):
            qa, xa = tick(a, k * .1, permits={r: False for r in ROLES}, previous=pa)
            qb, xb = tick(b, k * .1, permits={r: True for r in ROLES}, previous=pb)
            self.assertEqual(qa, qb)
            for r in ROLES:
                self.assertEqual({key: v for key, v in xa[r].items() if key != 'permit'},
                                 {key: v for key, v in xb[r].items() if key != 'permit'})
            pa, pb = {r: v['command'] for r, v in xa.items()}, {r: v['command'] for r, v in xb.items()}
        self.assertEqual(a.summary(), b.summary())
        MEASUREMENTS['c_permit_counterfactual_robot_ticks'] = 160

    def test_c_ready_is_diagnostic_no_pending_no_started(self):
        ctrl = TreatmentController(Script(lambda o: ('ready', False)), ROLES, 'ep', INIT, mode='arm_c')
        for k in range(3):
            proposed, out = tick(ctrl, k * .1, permits={r: k == 2 for r in ROLES})
            self.assertTrue(all(row['ready'] for row in proposed.values()))
            self.assertTrue(all(row['command']['wheels'] == [.31] * 4 for row in out.values()))
        for b in ctrl.barriers.values():
            self.assertIsNone(b.pending)
            self.assertFalse(b.ready)
            self.assertFalse(b.started)
            self.assertEqual(b.events, [])

    def test_s_close_passes_all_withdraw_stages(self):
        for stage in p.WITHDRAW_STAGES:
            ctrl = TreatmentController(Script(lambda o: (stage, False)), ROLES, 'ep', INIT, mode='arm_s')
            _, out = tick(ctrl, 0.)
            self.assertTrue(all(not v['blocked'] and v['command']['wheels'] == [.31] * 4 for v in out.values()))
        MEASUREMENTS['s_close_robot_cases'] = 6

    def test_s_execute_still_requires_permit_and_ready(self):
        for stage in p.POST_GO_STAGES:
            ctrl = TreatmentController(Script(lambda o: (stage, False)), ROLES, 'ep', INIT, mode='arm_s')
            _, out = tick(ctrl, 0.)
            self.assertTrue(all(v['command']['wheels'] == [0.] * 4 and v['software_hold'] for v in out.values()))
        MEASUREMENTS['s_held_robot_cases'] = 8

    def test_s_ready_pending_release_and_rearm_original(self):
        action = dict(INIT['r1'], wheels=[.31] * 4, duration_s=[.1] * 4)
        a, b = TreatmentBarrier(mode='arm_s'), p.PairActBarrier()
        for k, (stage, permit) in enumerate([('ready', False), ('execute', False), ('execute', True),
                                            ('carry', True), ('recover', False), ('complete', False)]):
            value = dict(deepcopy(action), t=k * .1)
            a.propose(value, False, INIT['r1'], stage=stage)
            b.propose(value, False, INIT['r1'], stage=stage)
            self.assertEqual(a.issue(k * .1, INIT['r1'], value, False, permit),
                             b.issue(k * .1, INIT['r1'], value, False, permit))
            self.assertEqual(a.ready, b.ready)
            self.assertEqual(a.events, b.events)

    def test_s_joint_done_and_continuity_preserved(self):
        ctrl = TreatmentController(Script(lambda o: ('ready' if o['t'] == 0 else 'execute', o['t'] > 0 and o['robot_id'] == 'r1')),
                                   ROLES, 'ep', INIT, mode='arm_s')
        for k in range(60):
            tick(ctrl, k * .1, permits={r: True for r in ROLES})
        self.assertEqual(ctrl.segment, 'grasp')
        self.assertIsNone(ctrl.switch_t)
        ctrl.done_since = dict(r1=0., r2=.5)
        ctrl._sequence(3.4)
        self.assertEqual(ctrl.segment, 'grasp')
        ctrl._sequence(3.5)
        self.assertEqual(ctrl.segment, 'release')
        self.assertEqual(ctrl.switch_t, 3.5)

    def test_common_exact_tick_discard_inference_stage_grasp_role(self):
        for mode in ('arm_c', 'arm_s'):
            policy = Script(lambda o: ('ready', False) if o['t'] == 0 else ('execute', True))
            ctrl = TreatmentController(policy, ROLES, 'ep', INIT, mode=mode)
            for k in range(60):
                proposed, _ = tick(ctrl, k * .1, permits={r: True for r in ROLES})
                for r, row in proposed.items():
                    self.assertEqual(row['observation']['skill'], 'grasp')
                    self.assertEqual(row['observation']['role'], ROLES[r])
                    self.assertEqual(c.context(row['observation'])[225], 0.)
            self.assertTrue(ctrl.finished)
            for metric in ctrl.summary()['treatment']['metrics'].values():
                self.assertEqual(metric['ticks'], 60)
                self.assertEqual(metric['discard_calls'], 60)
                self.assertEqual(metric['inference_calls'], 60)
                self.assertEqual(sum(metric['stage_counts'].values()), 60)
                self.assertEqual(metric['skill_counts'], dict(grasp=60))
                self.assertEqual(metric['state225_nonzero'], 0)
            MEASUREMENTS[mode + '_cadence'] = ctrl.summary()['treatment']['metrics']

    def test_none_barrier_exact_original_randomized(self):
        rng = random.Random(20261026)
        a, b = TreatmentBarrier(), p.PairActBarrier()
        for k in range(1024):
            stage, done, permit = rng.choice(p.STAGES), rng.choice((False, True)), rng.choice((False, True))
            previous = deepcopy(INIT['r1'])
            proposal = dict(deepcopy(previous), t=k * .1, wheels=[.31] * 4, duration_s=[.1] * 4)
            proposal['pwm']['1'] = rng.choice((1800, 2000, 2200))
            self.assertEqual(a.propose(proposal, done, previous, stage=stage), b.propose(proposal, done, previous, stage=stage))
            self.assertEqual(a.issue(k * .1, previous, proposal, done, permit), b.issue(k * .1, previous, proposal, done, permit))
            self.assertEqual(a.ready, b.ready)
            self.assertEqual(a.events, b.events)
        MEASUREMENTS['none_barrier_equal_transitions'] = 1024

    def test_none_controller_exact_original_feedback(self):
        fn = lambda o: ('ready', False) if o['t'] < 1. else ('execute', True)
        a = TreatmentController(Script(fn), ROLES, 'ep', INIT)
        b = ORIGINAL_CONTROLLER(Script(fn), ROLES, 'ep', INIT)
        pa, pb = deepcopy(INIT), deepcopy(INIT)
        for k in range(100):
            permits = {r: k >= 5 for r in ROLES}
            qa, xa = tick(a, k * .1, permits=permits, previous=pa)
            qb, xb = tick(b, k * .1, permits=permits, previous=pb)
            self.assertEqual((qa, xa, a.summary()), (qb, xb, b.summary()))
            pa, pb = {r: v['command'] for r, v in xa.items()}, {r: v['command'] for r, v in xb.items()}
        MEASUREMENTS['none_controller_equal_robot_ticks'] = 200

    def test_allowlist_and_invalid_mode(self):
        for mode in ('arm_c', 'arm_s'):
            ctrl = TreatmentController(Script(lambda o: ('approach', False)), ROLES, 'ep', INIT, mode=mode)
            with self.assertRaisesRegex(ValueError, 'own camera'):
                ctrl.propose(0., {r: dict(jpeg=b'x', issued=INIT[r], truth={}) for r in ROLES})
            with self.assertRaisesRegex(ValueError, 'protocol permits'):
                ctrl.issue(0., dict(r1=1, r2=0))
        with self.assertRaises(ValueError):
            TreatmentBarrier(mode='invalid')

    def test_original_worker_serve_uses_injected_class(self):
        import bootstrap
        from scripts import pairact_r1_student_worker as worker
        config = dict(done_recovery=p.RECOVERY_MODE, place_sync='off', issued_clock_deadband=2)
        lines = [dict(op='reset', roles=ROLES, episode_id='ep', initial=INIT),
            dict(op='propose', t=0., robots={r: dict(jpeg=base64.b64encode(b'x').decode(), issued=INIT[r]) for r in ROLES}),
            dict(op='issue', t=0., permits={r: False for r in ROLES}), dict(op='summary')]
        try:
            for mode in ('arm_c', 'arm_s', 'none'):
                bootstrap.install(mode)
                out = []
                worker.serve(Script(lambda o: ('approach', False)), [json.dumps(v) for v in lines], out.append, config=config)
                replies = [json.loads(v) for v in out]
                self.assertEqual(replies[0], dict(ok=True))
                if mode == 'none':
                    self.assertNotIn('treatment', replies[-1])
                    self.assertTrue(replies[2]['robots']['r1']['blocked'])
                else:
                    self.assertEqual(replies[-1]['treatment']['mode'], mode)
                    self.assertFalse(replies[2]['robots']['r1']['blocked'])
        finally:
            bootstrap.install('none')
        MEASUREMENTS['worker_serve_modes'] = 3

    def test_eval_six_keys_only_python_changes(self):
        original = json.loads(Path(REF['aliases']['EVAL']).read_text())
        for arm in ('c', 's'):
            cfg = json.loads((HERE / ('student-eval-arm-' + arm + '.json')).read_text())
            self.assertEqual(set(cfg), {'mode', 'python', 'source', 'model', 'config', 'device'})
            self.assertEqual([k for k in cfg if cfg[k] != original[k]], ['python'])
        MEASUREMENTS['eval_non_python_equal_keys'] = 10

    def test_wrapper_original_interpreter_mode_and_no_simulator(self):
        for executable, mode in [('eval-python', 'none'), ('eval-python-arm-c', 'arm_c'), ('eval-python-arm-s', 'arm_s')]:
            env = dict(os.environ)
            env.pop('UGRP_BASELINE_TREATMENT', None)
            result = subprocess.run([str(HERE / executable), '--treatment-inspect'], env=env, text=True, capture_output=True, check=True)
            row = json.loads(result.stdout)
            self.assertEqual(row['mode'], mode)
            self.assertEqual(Path(row['python']).resolve(), Path('/home/ugrp/e2emin-20261021/venv/bin/python').resolve())
            self.assertEqual(row['simulator_modules'], [])
            self.assertEqual(row['cuda_visible_devices'], '')
        MEASUREMENTS['wrapper_subprocess_modes'] = 3


class Results(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []

    def startTest(self, test):
        self.started = time.monotonic()
        super().startTest(test)

    def addSuccess(self, test):
        self.rows.append(dict(test=test.id(), status='PASS', wall_s=time.monotonic() - self.started))
        super().addSuccess(test)

    def addFailure(self, test, err):
        self.rows.append(dict(test=test.id(), status='FAIL', error=self._exc_info_to_string(err, test)))
        super().addFailure(test, err)

    def addError(self, test, err):
        self.rows.append(dict(test=test.id(), status='ERROR', error=self._exc_info_to_string(err, test)))
        super().addError(test, err)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TreatmentTests)
    result = unittest.TextTestRunner(resultclass=Results, verbosity=2).run(suite)
    report = dict(tests=result.rows, tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        metrics=MEASUREMENTS, synthetic_predictor_only=True, gpu_runs=0, model_forward_calls=0,
        simulator_modules=[m for m in sys.modules if m == 'mujoco' or m == 'warp'])
    with Path(sys.argv[1]).open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    sys.exit(0 if result.wasSuccessful() else 1)
