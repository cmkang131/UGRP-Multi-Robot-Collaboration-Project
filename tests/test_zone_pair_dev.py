"""Dev admission/provenance/evaluation without physical steps or model calls.

The frozen M2 controller import requires MuJoCo; its fake-world integration
case explicitly skips without it. No test constructs a MuJoCo world.
"""
from __future__ import annotations

import copy
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

from scripts import run_zone_pair_dev as dev
from scripts import evaluate_zone_pair_dev as ev
from scripts.zone_pair_dev_runtime import endpoint, make_scene, queue_snapshot


def config():
    return json.loads(dev.PREREG.read_text())


def arguments(tmp_path, *extra):
    return dev.parser().parse_args(['--run-id', 'dev01', '--output', str(tmp_path / 'new'), *extra])


@pytest.mark.parametrize('run_id,seed', [('dev01', 901), ('dev02', 902)])
def test_prereg_admission(tmp_path, run_id, seed):
    args = arguments(tmp_path, '--run-id', run_id)
    p, case = dev.load_config(args)
    assert case['seed'] == seed
    assert p['planned_run_count'] == 2
    assert p['limits']['model_calls'] == 0


@pytest.mark.parametrize('change', ['unknown_run', 'negative_seed', 'nan_budget', 'infinite_budget', 'wrong_map',
                                    'bad_hash', 'bad_sheet', 'unsupported_fault', 'existing_output'])
def test_invalid_inputs_refused_before_import_or_output(tmp_path, change):
    p = config()
    args = arguments(tmp_path)
    if change == 'unknown_run':
        args.run_id = 'test01'
    elif change == 'negative_seed':
        p['runs'][0]['seed'] = -1
    elif change == 'nan_budget':
        p['limits']['sim_s'] = float('nan')
    elif change == 'infinite_budget':
        p['limits']['wall_s'] = float('inf')
    elif change == 'wrong_map':
        p['environment']['map'] = 'other'
    elif change == 'bad_hash':
        p['inputs']['calibration']['sha256'] = '0' * 64
    elif change == 'bad_sheet':
        p['runs'][0]['coarse_order_sheet']['beam_xyyaw'][0] += .01
    elif change == 'unsupported_fault':
        p['runs'][0]['intervention'] = 'teleport'
    elif change == 'existing_output':
        args.output.mkdir()
    path = tmp_path / 'prereg.json'
    path.write_text(json.dumps(p))
    args.prereg = path
    with pytest.raises(ValueError):
        dev.load_config(args)
    assert not list(args.output.glob('*'))


def test_execution_needs_explicit_full_sha_and_lock(tmp_path):
    args = arguments(tmp_path, '--execute')
    with pytest.raises(ValueError, match='expected-source-sha'):
        dev.load_config(args)
    args.expected_source_sha = 'a' * 40
    with pytest.raises(ValueError, match='lock-owner'):
        dev.load_config(args)
    args.lock_owner = 'codex'
    with pytest.raises(ValueError, match='primary checkout'):
        dev.load_config(args)


def test_prepare_and_help_with_mujoco_import_forbidden(tmp_path):
    # A successful subprocess is stronger than simply mocking the run function:
    # the complete default CLI, source receipt and static inputs must work.
    code = '''
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == "mujoco" or name.startswith("mujoco."):
        raise AssertionError("nonphysical command imported MuJoCo")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from scripts.run_zone_pair_dev import main
raise SystemExit(main(sys.argv[1:]))
'''
    out = tmp_path / 'prepared'
    result = subprocess.run([sys.executable, '-c', code, '--run-id', 'dev01', '--output', str(out)],
                            cwd=dev.ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    m = json.loads((out / 'manifest.json').read_text())
    assert m['applied'] is None and m['state'] == 'prepared_not_executed'
    assert m['physical_success'] is None and m['model_calls'] == 0
    assert not (out / 'eval_only/trace.jsonl').exists()
    assert (out / 'inputs/static.json').is_file()
    result = subprocess.run([sys.executable, '-c', code, '--help'], cwd=dev.ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_applied_manifest_reads_actual_model_and_rejects_mismatch():
    from harness.zone_pair_executor import PairTeam
    host = NS(world=NS(robot_ids=('r1', 'r2', 'r3'), data=NS(eq_active=[False]),
                       model=NS(opt=NS(timestep=.002, noslip_iterations=10))),
              scene=NS(cargo=[NS(item_id='cargoX', kind='long_beam')], config={'setup_only': {'objects': {}}}),
              static={'map_id': dev.EXPECTED['map']}, contact_record={'profile': 'cargo_noslip_v1'},
              pairs=PairTeam.__new__(PairTeam))
    assert dev.applied_settings(host) == dev.EXPECTED
    for key, wrong in [('timestep', .01), ('noslip_iterations', 0)]:
        before = getattr(host.world.model.opt, key)
        setattr(host.world.model.opt, key, wrong)
        with pytest.raises(ValueError, match='actual model'):
            dev.applied_settings(host)
        setattr(host.world.model.opt, key, before)
    host.world.data.eq_active = [True]
    with pytest.raises(ValueError):
        dev.applied_settings(host)


def test_standard_scene_has_only_beam_and_preserves_three_spawn_slots():
    p = config()
    spec = {'map': dev.EXPECTED['map'], 'seed': 901, 'goal': {'B': {'cyan': 1}},
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': p['runs'][0]['setup_beam_xyyaw']}]}
    scene = make_scene(spec)  # configuration only: never constructs/steps a model
    from sim.session_scenes import Scene
    assert isinstance(scene, Scene)
    assert scene.config['setup_only']['objects'] == {}
    assert len(scene.cargo) == 1
    assert set(scene.config['setup_only']['spawns']) == {'r1', 'r2', 'r3'}
    assert scene.config['static_map'] == json.loads(dev.MAP.read_text())


def test_actor_submissions_are_independent_and_do_not_retry():
    a, b = dev.DevActor('r1', 60.), dev.DevActor('r2', 60.)
    calls = {'r1': [], 'r2': []}
    own = NS(job=None)
    def call(rid):
        def capture(*args):
            calls[rid].append(args)
            return {'accepted': False}
        return capture
    a.tick(own, call('r1'), 0.)
    a.tick(own, call('r1'), 60.)
    assert calls['r2'] == [] and not b.submitted
    a.tick(own, call('r1'), 61.)
    b.tick(own, call('r2'), 62.)
    assert calls['r1'] == [('look_around',), ('pair_carry', 'cargoX', 'B', 'r2')]
    assert calls['r2'][-1] == ('pair_carry', 'cargoX', 'B', 'r1')


def test_retained_endpoint_queues_are_audited_after_executor_detaches():
    eps = {r: NS(controller=NS(arm=NS(events=[1]), schedule=[2]), port=NS(commands=[3])) for r in ev.PAIR}
    slots = {r: NS(executor=NS(_pair=None), timeline=[], capture_after=False,
                   port=NS(_servo_targets={}, _motor_commands=[0, 0, 0, 0])) for r in ev.PAIR}
    host = NS(pairs=NS(sessions=[{'endpoints': eps}]), robots=slots)
    assert endpoint(host, 'r1') is eps['r1']
    assert queue_snapshot(host)['r1']['arm'] == 1
    assert queue_snapshot(host)['r2']['carry'] == 1


def wire(state, at, rid='r1'):
    return {'task_id': 'pair-fixture', 'robot_id': rid, 'state': state, 'sent_at_s': at}


def zeros():
    return {r: {'arm': 0, 'carry': 0, 'port_buffer': 0, 'macro': 0, 'capture_after': False,
                'servo_targets': 0, 'motor_nonzero': 0} for r in ev.PAIR}


@pytest.mark.parametrize('fault', ['none', 'late_go', 'missing_go', 'arm', 'carry', 'port_buffer', 'macro',
                                   'servo_targets', 'motor_nonzero', 'capture_after', 'same_tick_motion', 'late_motion', 'short_tail'])
def test_protocol_audit_detects_abort_and_go_faults(fault):
    status = [wire('carry_go_0', 1.), wire('carry_go_0', 1., 'r2'), wire('abort', 1.1)]
    shutdown = [{'t': 1.1, 'aborted': True, 'queues': zeros()}, {'t': 1.7, 'aborted': True, 'queues': zeros()}]
    commands = [{'t': 1.1, 'robot_id': 'r1', 'kind': 'hold', 'after_abort': True}]
    if fault == 'late_go':
        status[1]['sent_at_s'] = 1.002
    elif fault == 'missing_go':
        status.pop(1)
    elif fault in zeros()['r1']:
        shutdown[0]['queues']['r1'][fault] = True if fault == 'capture_after' else 1
    elif fault in ('same_tick_motion', 'late_motion'):
        commands.append({'t': 1.1 if fault == 'same_tick_motion' else 1.2, 'kind': 'arm', 'after_abort': fault == 'same_tick_motion'})
    elif fault == 'short_tail':
        shutdown[-1]['t'] = 1.2
    result = ev.audit_protocol(status, commands, shutdown, ['carry_go_0'], require_abort=True)
    assert result['ok'] is (fault == 'none')


def good_evidence():
    p = config()
    m = dev.build_manifest(p, p['runs'][0], source={}, environment={}, prereg_path=dev.PREREG, applied=dev.EXPECTED)
    m.update(state='completed', source_changed=False, inputs_changed=False, sim_end_s=12.)
    rows = []
    targets = {'r1': [.275, 0., 0.], 'r2': [1.725, 0., math.pi]}
    for i in range(241):
        t = round(i * .05, 8)
        x = 1. if t < 2 else (min(3.3, 1. + (t - 2) * 1.) if t < 5 else min(4.6, 3.3 + (t - 5) * .65))
        y = .05 if t < 5 else max(-2.1, .05 - (t - 5) * 1.075)
        z = .05 if 1.5 <= t < 8 else 0.
        state = 'approach' if t < 1 else ('grasp' if t < 1.5 else ('carry' if t < 8 else ('lower' if t < 9 else 'done')))
        corners = [[x + a * .3, y + b * .02, z + .016 + c * .016] for a, b, c in itertools.product((-1, 1), repeat=3)]
        rows.append({'t': t, 'states': {r: state for r in ev.PAIR}, 'beam_xyz': [x, y, z], 'beam_corners': corners, 'tilt_deg': 0.,
                     'finger_n': {r: [2., 2.] if 1 <= t < 9 else [0., 0.] for r in ev.PAIR},
                     'robots': {**targets, 'r3': [-.7, -2., 0.]}, 'prestations': targets,
                     'approach_go_s': {r: .5 if t >= .5 else None for r in ev.PAIR}})
    contacts = {'physics_steps': 6000, 'counts': {k: 0 for k in ('robot_robot', 'robot_wall', 'beam_wall', 'robot_beam_approach', 'r3_interference')},
                'max_eq_active': 0, 'r3_max_displacement_m': 0., 'r3_motion_commands': 0, 'r3_api_calls': 0}
    return m, p, rows, contacts, {'ok': True, 'go_seen': True}


def test_complete_synthetic_evidence_can_pass_but_needs_video():
    args = good_evidence()
    no_review = ev.score(*args)
    assert not no_review['physical_success']
    assert [k for k, v in no_review['checks'].items() if not v] == ['video']
    result = ev.score(*args, video_review={'verified': True})
    assert result['physical_success'], result


@pytest.mark.parametrize('fault', ['only_sequence_done', 'missing_trace', 'trace_gap', 'nan', 'no_grip', 'no_lift',
                                   'door_miss', 'outside_B', 'not_released', 'drop', 'contact', 'r3_motion',
                                   'weld', 'source_changed', 'wall_limit', 'abort_trial', 'wrong_applied'])
def test_physical_score_fails_closed(fault):
    m, p, rows, contacts, protocol = good_evidence()
    if fault == 'only_sequence_done':
        rows = []
        m.update(outcome='PAIR_SEQUENCE_DONE', confirmation='unconfirmed')
    elif fault == 'missing_trace':
        rows = []
    elif fault == 'trace_gap':
        del rows[20:25]
    elif fault == 'nan':
        rows[0]['tilt_deg'] = float('nan')
    elif fault == 'no_grip':
        for row in rows:
            row['finger_n']['r2'] = [0., 0.]
    elif fault == 'no_lift':
        for row in rows:
            for corner in row['beam_corners']:
                corner[2] = 0.
    elif fault == 'door_miss':
        for row in rows:
            if 3 < row['t'] < 4:
                row['beam_corners'][0][1] = .5
    elif fault == 'outside_B':
        rows[-1]['beam_corners'][0][0] = 5.
    elif fault == 'not_released':
        rows[-1]['finger_n']['r2'] = [2., 2.]
    elif fault == 'drop':
        rows[90]['beam_corners'][0][2] = 0.
    elif fault == 'contact':
        contacts['counts']['beam_wall'] = 1
    elif fault == 'r3_motion':
        contacts['r3_motion_commands'] = 1
    elif fault == 'weld':
        contacts['max_eq_active'] = 1
    elif fault == 'source_changed':
        m['source_changed'] = True
    elif fault == 'wall_limit':
        m['state'] = 'interrupted'
    elif fault == 'abort_trial':
        m['intervention'] = 'abort_after_carry_go'
    elif fault == 'wrong_applied':
        m['applied'] = {**dev.EXPECTED, 'timestep_s': .01}
    assert not ev.score(m, p, rows, contacts, protocol, video_review={'verified': True})['physical_success']


def test_ci_and_common_workflow_collect_driver_and_static_input_receipts(tmp_path):
    from scripts.run_ci_tests import TEST_PATTERNS
    from sim import workflow_manager as wm
    assert any(Path('tests/test_zone_pair_dev.py').match(pattern) for pattern in TEST_PATTERNS)
    args = ['--prereg', str(dev.PREREG), '--run-id', 'dev01', '--output', str(tmp_path / 'new')]
    plan = wm.plan(dev.ROOT, dev.WORKFLOW, args)
    assert not plan['execution_started']
    paths = {p['path'] for p in plan['inputs']}
    assert {str(dev.MAP), str(dev.CALIBRATION), str(dev.PREREG)} <= paths


def test_real_pairteam_fake_host_abort_is_auditable_without_physics():
    pytest.importorskip('mujoco', reason='frozen M2 controller imports MuJoCo; this case uses a fake world, no physical steps')
    from tests.test_zone_pair_executor import setup, start
    host, exs = setup()
    assert start(host)['accepted']
    host.call('r2', 'abort', 'dev_fixture')
    eps = host.pairs.sessions[-1]['endpoints']
    assert all(ep.terminal and not ep.controller.arm.events and not ep.controller.schedule and not ep.port.commands for ep in eps.values())
    assert all(exs[r]._pair is None for r in ev.PAIR)
    assert all(not host.robots[r].timeline for r in ev.PAIR)


@pytest.mark.parametrize('case_index', [0, 1])
def test_physical_entry_finalizes_real_host_pair_scheduler_on_fake_world(tmp_path, monkeypatch, case_index):
    pytest.importorskip('mujoco', reason='frozen M2 import required; physical world/observer replaced with fakes')
    import mujoco
    from harness.zone_own_team_host import OwnCamTeamHost
    from scripts import zone_pair_dev_runtime as runtime
    from tests.test_zone_pair_executor import setup, PhasedM2, PairFakeHost
    from sim.workflow_manager import source_fingerprint

    p = config()
    p['limits'].update(sim_s=8., submit_at_s=.03, post_terminal_s=.6, wall_s=30.)
    case = p['runs'][case_index]
    out = tmp_path / 'physical-entry-fake-world'
    out.mkdir()
    (out / 'eval_only').mkdir()
    dev.write_json(out / 'prereg.json', p)
    m = dev.build_manifest(p, case, source={'execution_tree': source_fingerprint(dev.ROOT)}, environment={}, prereg_path=dev.PREREG)
    dev.write_json(out / 'manifest.json', m)
    def fake_init(self, *args, **kwargs):
        fake, _ = setup(factory=PhasedM2)
        self.__dict__.update(fake.__dict__)
        self.world.robot_ids = ('r1', 'r2', 'r3')
        self.world.model.opt.noslip_iterations = 10
        self.world.model.opt.timestep = .002
        self.world.data.eq_active = [False]
        self.scene = NS(cargo=[NS(item_id='cargoX', kind='long_beam')], config={'setup_only': {'objects': {}}},
                        manifest={'scene_xml_sha256': 'fixture-only'}, record=lambda: {'fixture': True})
        self.static = {'map_id': dev.EXPECTED['map']}
        for slot in self.robots.values():
            slot.port._servo_targets = {}
            slot.port._motor_commands = [0, 0, 0, 0]
    class NoPhysicsObserver:
        def __init__(self, host, output, criteria):
            self.output = output
            (output / 'eval_only/trace.jsonl').touch()
        def tick(self):
            pass
        def close(self):
            dev.write_json(self.output / 'eval_only/contacts.json', {})
    def bootstrapped_actor(rid, submit):
        actor = dev.DevActor(rid, submit)
        actor.look_sent = True  # own-frame fixtures already localize each robot
        return actor
    monkeypatch.setattr(OwnCamTeamHost, '__init__', fake_init)
    monkeypatch.setattr(OwnCamTeamHost, '_physics_until', PairFakeHost._physics_until)
    monkeypatch.setattr(OwnCamTeamHost, '_capture_raw', PairFakeHost._capture_raw)
    monkeypatch.setattr(runtime, 'make_scene', lambda spec: None)
    monkeypatch.setattr(runtime, 'DevActor', bootstrapped_actor)
    monkeypatch.setattr(runtime, 'EvalObserver', NoPhysicsObserver)
    monkeypatch.setattr(mujoco, 'mj_saveLastXML', lambda path, model: Path(path).write_text('<fake/>'))
    args = NS(output=out)
    assert runtime.run_physical(args, p, case, m) == 0
    final = json.loads((out / 'manifest.json').read_text())
    assert final['state'] == 'completed', final
    assert final['applied'] == dev.EXPECTED
    records = json.loads((out / 'pair_records.json').read_text())
    assert set(records[0]['submissions']) == {'r1', 'r2'}
    assert ev.load_lines(out / 'status.jsonl')
    assert not json.loads((out / 'eval_only/result.json').read_text())['physical_success']
    assert (out / 'artifacts.sha256.json').is_file()
    if case_index == 1:
        assert (out / 'intervention.json').is_file()
        assert ev.load_lines(out / 'shutdown.jsonl')[-1]['aborted']
        assert not any(c['kind'] in ev.MOTION and c['after_abort'] for c in ev.load_lines(out / 'commands.jsonl'))
