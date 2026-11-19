import json
import contextlib
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest import mock

import numpy as np

from harness.exec_opt import DecisionTrace, DeliveryAudit
from harness.grasp_act_rollout import SoloScore
from scripts import bench_exec_opt as bench, compare_exec_opt as compare


def save(path, data):
    path.write_text(json.dumps(data))


def lines(path, data):
    path.write_text(''.join(json.dumps(r) + '\n' for r in data))


class AuditTest(unittest.TestCase):
    def test_decision_audit_forwards_arguments_and_records_before_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'trace'
            brain = mock.Mock()
            brain.decide.return_value = {'option': 'box:0'}
            audit = DecisionTrace(brain, path)
            facts = {'seen_boxes': [{'entry': 1, 'colour': 'red'}]}
            options = [{'key': 'box:0', 'text': 'red box'}]
            audit.tell('r1', facts)
            self.assertEqual(audit.decide('r1', .1, 'pick', options), {'option': 'box:0'})
            brain.tell.assert_called_once_with('r1', facts)
            brain.decide.assert_called_once_with('r1', .1, 'pick', options)
            self.assertEqual(list(compare.rows(path))[0]['boxes'], facts['seen_boxes'])
            self.assertIs(audit.poll, brain.poll)

    def test_settling_clock_resets_under_finger_load_or_motion(self):
        ident = np.eye(3).reshape(1, 9)
        m = NS(geom_bodyid=np.array([0, 1, 2]), geom_contype=np.ones(3), geom_size=np.array([[.01] * 3] * 3),
               body=lambda name: NS(id=0), geom=lambda name: NS(id=1 if 'left' in name else 2))
        d = NS(ncon=0, contact=[NS(geom1=0, geom2=1)], xpos=np.array([[0., 0., .01]]),
               xmat=ident, geom_xmat=np.tile(ident, (3, 1)), geom_xpos=np.array([[0., 0., .01]] * 3))
        world = NS(model=m, data=d, controllers={'r1': None})
        audit = DeliveryAudit(world, [{'body': 'cargo_red_1', 'id': 'b'}], {'z': (-1., 1., -1., 1.)},
                              SoloScore.RELEASE_CRITERIA, {'cargo_red_1': 'red_1'})
        mj = NS(mjtObj=NS(mjOBJ_BODY=1), mj_contactForce=lambda m, d, i, out: out.fill(1.),
                mj_objectVelocity=lambda m, d, t, b, out, local: out.fill(0.))
        with mock.patch.dict('sys.modules', mujoco=mj):
            audit.sample(world, 0.)
            audit.sample(world, 3.1)
            self.assertEqual(audit.record()['settled']['b']['at_s'], 3.)
            d.ncon = 1
            audit.sample(world, 3.2)
            self.assertFalse(audit.record()['settled'])
            d.ncon = 0
            audit.sample(world, 3.3)
            mj.mj_objectVelocity = lambda m, d, t, b, out, local: out.fill(.1)
            audit.sample(world, 6.4)
            self.assertFalse(audit.record()['settled'])


def team_case(path):
    run = path / 'run'
    run.mkdir(parents=True)
    robots = ['r1', 'r2', 'r3']
    log = [dict(rid=r, t=1., point='pick', option='box:0') for r in robots]
    team = dict(status='complete', scene='P2_N03_S01', robots=robots, finished=robots, seed=42, starts={}, knows={},
                brain={'kind': 'fixed_plan', 'decisions': log, 'targets': {r: {'box': r} for r in robots},
                       'assignment': {r: ['red', 'z'] for r in robots}, 'after': {'r2': ['r1']}},
                orders=[dict(id='o', count=3, met=3)], required_boxes=3, correct_boxes=3, wrong_place_boxes=0, end_s=40.,
                boxes={r: {'zone': 'z', 'correct': True, 'wrong_place': False} for r in robots},
                events={r: {'door_passed': 8., 'carry_finished': {'outcome': 'arrived'}} for r in robots},
                delivery_audit=dict(samples=401, last_s=40., scoring_keys={r: r for r in robots}, settled={
                    r: {'zone': 'z', 'at_s': 20. + i} for i, r in enumerate(robots)}))
    save(run / 'team.json', team)
    save(path / 'receipt.json', dict(mode='team', inputs={'scene': 'abc'}, exit_code=0, frozen_source='test', cap_s=900., wall_s=600.))
    lines(run / 'decision-inputs.jsonl', [dict(rid=r, point='pick', t=1., boxes=[], options=[{'key': 'box:0'}]) for r in robots])
    for rid in robots:
        out = run / ('out-' + rid)
        out.mkdir()
        save(out / 'summary.json', dict(status='complete', complete=True, termination='student_done', seed=42,
             robot_tags={'enabled': True, 'signs_seen': {}, 'frames_with_a_tag': 0}, lift_success=True,
             done_times={'grasp': 10., 'release': 14.}, carry_v1={'started_at_s': 5.},
             layout=[{'id': r, 'body': 'cargo_' + r} for r in robots]))
        lines(out / 'commands.jsonl', [dict(command={'t': t}, source=s) for t, s in
                                       [(0., 'code'), (2., 'act'), (5., 'carry_code'), (10., 'release_code')]])
    return run


class ComparisonTest(unittest.TestCase):
    def test_streams_reject_identical_truncation_against_runner_counts_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            off, on = (Path(tmp) / n for n in ('off', 'on'))
            for root in (off, on):
                run = team_case(root)
                for out in run.glob('out-*'):
                    inputs = out / 'student-inputs.jsonl'
                    commands = out / 'commands.jsonl'
                    lines(inputs, [{'rgb': [{'sha256': 'abc'}]}] * 4)
                    s = compare.read(out / 'summary.json')
                    s.update(funnel={'actions': 4, 'valid_inputs': 4},
                             artifacts={p.name: bench.sha(p) for p in (commands, inputs)})
                    save(out / 'summary.json', s)
            args = NS(robots=3, off=off, on=on, exact=True, min_s=25.)
            self.assertTrue(compare.streams(args)['byte_identical'])
            for root in (off, on):
                lines(root / 'run/out-r2/student-inputs.jsonl', [{'rgb': [{'sha256': 'abc'}]}] * 3)
            with self.assertRaisesRegex(ValueError, 'truncated or altered'):
                compare.streams(args)

    def test_benchmark_uses_actual_source_and_preserves_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('cover-dev20/episode/seed90721/plan.json', 'cover-dev20/episode/seed90721/protocol.json',
                         'gseg-actor/model.safetensors', 'gseg-actor/config.json', 'gseg-actor/adapter.json',
                         'speed/dev_run13_speed.py', 'scenes-p2gate/P2_N09_S01.json'):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('{}')
            case = root / 'trial'
            env = {'EXEC_OPT_HYBRID': tmp, 'EXEC_OPT_TREE': tmp, 'SPEED_SKIP_RGB_WRITES': '1'}
            for mode, target in [('team', 'N09'), ('grasp', str(root / 'cover-dev20/episode/seed90721/plan.json'))]:
                out = case / mode
                argv = ['bench', mode, str(out), target, '30', '--noslip-iterations', '0']
                with mock.patch.dict(os.environ, env, clear=True), mock.patch('sys.argv', argv), \
                     mock.patch.object(bench, 'revision', return_value='actual-head'), contextlib.redirect_stdout(io.StringIO()), \
                     mock.patch.object(bench.subprocess, 'run', return_value=NS(returncode=3)) as run:
                    self.assertEqual(bench.main(), 3)
                    receipt = compare.read(out / 'receipt.json')
                    self.assertEqual(receipt['exit_code'], 3)
                    self.assertEqual(receipt['source'], 'actual-head')
                    self.assertEqual(receipt['switches'], ['--noslip-iterations', '0'])
                    self.assertNotIn('SPEED_SKIP_RGB_WRITES', run.call_args.kwargs['env'])
                    self.assertIn('--fixed' if mode == 'team' else '--audit-grasp-start', run.call_args.args[0])
                    with self.assertRaises(FileExistsError):
                        bench.main()

    def test_full_gate_catches_physical_order_swap_even_with_equal_scores_and_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            off, on = (Path(tmp) / n for n in ('off', 'on'))
            team_case(off)
            run = team_case(on)
            args = NS(mode='team', robots=3, off=off, on=on)
            self.assertTrue(compare.compare_team(args)['ok'])
            team = compare.read(run / 'team.json')
            team['delivery_audit']['settled']['r2']['at_s'] = 19.
            save(run / 'team.json', team)
            result = compare.compare_team(args)
            self.assertFalse(result['ok'])
            self.assertFalse(result['on']['precedence']['r1<r2'])
            team['delivery_audit']['settled'].pop('r3')
            save(run / 'team.json', team)
            with self.assertRaisesRegex(ValueError, 'unconfirmed'):
                compare.compare_team(args)

    def test_sign_at_decision_and_missing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            off, on = (Path(tmp) / n for n in ('off', 'on'))
            team_case(off)
            run = team_case(on)
            path = run / 'out-r2/summary.json'
            s = compare.read(path)
            s['robot_tags']['signs_seen'] = {'11': 1}
            save(path, s)
            args = NS(mode='decisions', robots=3, off=off, on=on)
            with self.assertRaisesRegex(ValueError, 'missing marker log'):
                compare.compare_team(args)
            lines(path.parent / 'signs-seen.jsonl', [{'t': 1., 'signs': [{'sign': 11}]}])
            result = compare.compare_team(args)
            self.assertEqual(result['mismatches'], 1)
            self.assertEqual(result['first']['key'], ('r2', 'pick', 0))
            self.assertFalse(result['ok'])

    def test_grasp_loss_excludes_intended_release_and_requires_real_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp)
            run = case / 'run'
            run.mkdir()
            plan = {'item_id': 'b'}
            save(run / 'plan.json', plan)
            s = dict(status='complete', complete=True, student_execution=True, teacher_assisted=False,
                     inference_latency_s={'n': 1}, weld='off', act_start={'item': 'b'}, lift_success=True,
                     first_pass_sim_t={'grasp': 0., 'lift_confirmation': .1})
            save(run / 'summary.json', s)
            cmds = [dict(command={'t': i / 10}, source=v) for i, v in enumerate(('act', 'act', 'carry_code', 'release_code'))]
            ev = [dict(t=i / 10, weld=False, clearance=.03, forces=([0., 0.] if i == 3 else [1., 1.])) for i in range(4)]
            lines(run / 'commands.jsonl', cmds)
            lines(run / 'eval-only.jsonl', ev)
            self.assertFalse(compare.grasp_result(case, plan)[1]['drop'])
            ev[2].update(clearance=.003, forces=[0., 0.])
            lines(run / 'eval-only.jsonl', ev)
            self.assertTrue(compare.grasp_result(case, plan)[1]['drop'])
            s['inference_latency_s']['n'] = 0
            save(run / 'summary.json', s)
            with self.assertRaisesRegex(ValueError, 'ACT attempt'):
                compare.grasp_result(case, plan)
