"""run() is executed through its real loop with a stub simulation backend (no MuJoCo physics).

The 2026-10-14 diagnostics all died 3.7 s in with ``NameError: base`` on a line of
run() that no unit test reached. This drives run() for a few ticks so every name on
the per-tick path (visibility, measurement, obstacle refresh, teacher step, eval row,
review frames, report) is resolved at least once.
"""
import base64
import json
import sys
import types

import cv2
import numpy as np
import pytest

RID = 'r1'


class Body:
    def __init__(self, xy, z=.016):
        self.xpos = np.array([xy[0], xy[1], z])
        self.xmat = np.eye(3).reshape(9)


class Geom:
    def __init__(self, name, gid):
        self.name, self.id = name, gid


class FakeModel:
    ngeom = 3
    geom_bodyid = np.array([0, 1, 2])
    geom_contype = np.array([0, 1, 0])
    geom_type = np.array([6, 6, 6])
    geom_rbound = np.array([.5, .03, .03])
    geom_size = np.array([[1., .1, .1], [.017, .02, .016], [.05, .05, .05]])
    vis = types.SimpleNamespace(map=types.SimpleNamespace(znear=.01))
    stat = types.SimpleNamespace(extent=1.)
    names = {'wall_0': 0, 'cargo_geom': 1, RID+'__left_finger': 3, RID+'__right_finger': 4}

    def camera(self, name):
        return types.SimpleNamespace(id=0)

    def body(self, name):
        return types.SimpleNamespace(id={'cargo_body': 1}.get(name, 2))

    def geom(self, key):
        if isinstance(key, str):
            return Geom(key, self.names.get(key, 5))
        return Geom(['wall_0', 'cargo_geom', 'other'][key], key)


class FakeData:
    def __init__(self):
        self.time = 0.
        self.eq_active = np.zeros(1)
        self.ncon = 0
        self.contact = []
        self.geom_xpos = np.array([[0., 1.5, .1], [.5, 0., .016], [0., 0., 0.]])
        self.geom_xmat = np.tile(np.eye(3).reshape(9), (3, 1))
        self.cam_xpos, self.cam_xmat = np.zeros((1, 3)), np.tile(np.eye(3).reshape(9), (1, 1))
        self.bodies = {'cargo_body': Body((.5, 0.)), 'r2__robot': Body((1.5, 1.)), 'r3__robot': Body((-1.5, 1.)),
                       'other_cargo': Body((.2, .6))}

    def body(self, name):
        return self.bodies[name]


class FakeController:
    robot_cam_cid = 0


class FakeRobot:
    def base_xyz(self):
        return np.array([0., 0., .03])

    def base_rpy(self):
        return np.array([0., 0., 0.])


class FakeWorld:
    def __init__(self):
        self.model, self.data = FakeModel(), FakeData()
        self.controllers = {RID: FakeController()}
        self.scene_xml = '<mujoco/>'
        self.closed = False

    def robot(self, rid):
        return FakeRobot()

    def _physics_step_for(self, robot):
        self.data.time += .01

    def render_team_jpeg(self, camera=None):
        return cv2.imencode('.jpg', np.zeros((24, 32, 3), np.uint8))[1].tobytes()

    def close(self):
        self.closed = True


class FakePort:
    def __init__(self, world, rid, **kwargs):
        self._servo_pulses = {1: 1500, 3: 500, 4: 2500, 5: 1000, 6: 1500}
        self.actions = []

    def capture(self):
        jpg = cv2.imencode('.jpg', np.full((480, 640, 3), 90, np.uint8))[1].tobytes()
        return {'image': base64.b64encode(jpg).decode()}

    def apply(self, action, now):
        self.actions.append(action)

    def stop(self):
        self.actions.append({'kind': 'stop'})

    def tick(self, now):
        pass


class FakeVisibility:
    visible = True

    def region_visible(self, data, rid, gids):
        return (7, 7) if FakeVisibility.visible else (0, 7)

    def _body_geoms(self, bid):
        return [1]


def module(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    return m


@pytest.fixture
def backend(monkeypatch, tmp_path):
    import scripts.run_solo_grasp_act_teacher as runner
    world = FakeWorld()
    scene = types.SimpleNamespace(
        config={'setup_only': {'spawns': {}, 'objects': {'item1': {'body_name': 'cargo_body'},
                                                         'item2': {'body_name': 'other_cargo'}}},
                'static_map': {'bounds_m': [-2, 2, -2, 2], 'obstacles': [], 'top_cameras': [{'name': 'top0'}]}},
        engine_layout=None, manifest={}, cargo=[types.SimpleNamespace(item_id='item1', kind='can', body='cargo_body')], setup=lambda w: None)
    monkeypatch.setattr(runner.platform, 'system', lambda: 'Linux')
    real = runner.subprocess.check_output
    monkeypatch.setattr(runner.subprocess, 'check_output',
                        lambda cmd, **kw: 'f' * 40 + '\n' if cmd[:2] == ['git', 'rev-parse'] else
                        b'' if cmd[:2] == ['git', 'status'] else real(cmd, **kw))
    runs = tmp_path/'ugrp-sim/runs'
    runs.mkdir(parents=True)
    fakes = {
        'scripts.grasp_act_host': module('scripts.grasp_act_host', identity=lambda host: {'host': host},
                                         require_run_root=lambda out: None),
        'sim.grasp_act_scene': module('sim.grasp_act_scene', make_scene=lambda plan: scene),
        'sim.masterpi_drive_friction_v7': module('sim.masterpi_drive_friction_v7',
                                                 build_world=lambda *a, **k: world, PROFILE='fake'),
        'sim.s2_realism_camera_binding': module('sim.s2_realism_camera_binding', bind_camera=lambda c: None),
        'scripts.audit_grasp_act_visibility': module('scripts.audit_grasp_act_visibility',
                                                     BandVisibility=FakeVisibility),
    }
    import sim.grasp_act_port
    monkeypatch.setattr(sim.grasp_act_port, 'DutyActPort', FakePort)
    for name, fake in fakes.items():
        monkeypatch.setitem(sys.modules, name, fake)
    return runner, world, runs


def plan(kind='cyan'):
    return {'role': 'any' if kind == 'can' else 'west', **{'episode_id': 'stub', 'batch': 'stub', 'seed': 1, 'kind': kind, 'robot_id': RID,
            'item_id': 'item1', 'spawns': {}, 'handoff_pose_error': [.03, -.02, .01]}}


def test_run_loop_executes_every_per_tick_name_with_stubbed_backend(backend):
    runner, world, runs = backend
    out = runs/'stub-run'
    report = runner.run(plan(), out, execution_host='gcp1', profile='solo_visible_only_v1',
                        hidden=True, look=True, cap_s=.3,
                        teacher_stability='align_relook_v1', reach_mode='pad_window_v2')
    assert report['status'] == 'complete', report
    rows = [json.loads(line) for line in (out/'eval-only.jsonl').read_text().splitlines()]
    assert len(rows) >= 2 and all(len(r['base_xyz']) == 3 for r in rows)
    assert (out/'review-own/000000.jpg').exists() and (out/'progress.json').exists()
    assert json.loads((out/'result.json').read_text())['status'] == 'complete'
    assert report['teacher_stability'] == report['teacher']['teacher_stability'] == 'align_relook_v1'
    assert report['reach_mode'] == report['teacher']['reach_mode'] == 'pad_window_v2'
    trace = [json.loads(line) for line in (out/'teacher-commands.jsonl').read_text().splitlines()]
    assert all(r['visible_target'] is not None for r in trace)
    assert world.closed


def test_run_loop_survives_a_target_that_is_never_visible(backend):
    runner, world, runs = backend
    FakeVisibility.visible = False
    try:
        report = runner.run(plan('can'), runs/'blind-run', execution_host='gcp1',
                            profile='solo_visible_only_v1', hidden=True, look=True, cap_s=.3)
    finally:
        FakeVisibility.visible = True
    assert report['status'] == 'complete' and report['input_audit']['invisible_measurements'] == 0


def test_run_loop_enters_stationary_relook_when_fake_base_cannot_progress(backend):
    runner, world, runs = backend
    # No physics: the base stays fixed despite issued wheel commands. The
    # real runner must exercise align -> relook and persist the new diagnostics.
    world.data.bodies['cargo_body'].xpos[0] = .215
    out = runs/'stalled-align'
    report = runner.run(plan(), out, execution_host='gcp1', profile='solo_visible_only_v1',
                        hidden=True, look=True, cap_s=4.2,
                        teacher_stability='align_relook_v1', reach_mode='pad_window_v2')
    assert report['status'] == 'complete' and report['teacher']['alignment_relooks'] == 1
    assert report['input_audit']['invisible_measurements'] == report['input_audit']['held_world_reads'] == 0
    trace = [json.loads(line) for line in (out/'teacher-commands.jsonl').read_text().splitlines()]
    align = [r['command'] for r in trace if r['phase'] == 'align' and any(r['command']['wheels'])]
    assert align and all(.04 <= d <= .15 for c in align for w, d in zip(c['wheels'], c['duration_s']) if w)
    relook = [r['command'] for r in trace if r['phase'] == 'relook']
    assert relook and all(not any(c['wheels']) for c in relook)


@pytest.mark.parametrize('visible_colour', [True, False])
def test_run_v2_reaches_rgb_hold_or_blocks_setdown_and_saves_exact_own_evidence(backend, monkeypatch, visible_colour):
    import hashlib
    from harness.zone_own_perception import APPEARANCE
    runner, world, runs = backend
    # Keep the trace directly readable; compression is independently covered
    # by the existing runner. This stub verifies the RGB/command lifecycle.
    import scripts.run_grasp_act_teacher as shared_runner
    monkeypatch.setattr(shared_runner, 'compress_logs', lambda out: None)
    world.data.bodies['cargo_body'].xpos[0] = .2002
    lo, hi = APPEARANCE['cyan']['hue'][0]
    colour = cv2.cvtColor(np.uint8([[[(lo+hi)//2, 210, 200]]]), cv2.COLOR_HSV2BGR)[0, 0]
    image = np.full((480, 640, 3), colour if visible_colour else 0, np.uint8)
    jpg = cv2.imencode('.jpg', image)[1].tobytes()
    monkeypatch.setattr(FakePort, 'capture', lambda self: {'image': base64.b64encode(jpg).decode()})
    out = runs/'v2-loop'
    report = runner.run(plan(), out, execution_host='gcp1', profile='solo_visible_only_v1',
                        hidden=True, look=True, cap_s=13.5, rgb_lift_mode='solo_rgb_lift_v2')
    assert report['rgb_lift_mode'] == report['teacher']['rgb_lift_mode'] == 'solo_rgb_lift_v2'
    assert report['input_audit']['invisible_measurements'] == report['input_audit']['held_world_reads'] == 0
    samples = report['rgb_lift_v2']['samples']
    assert set(samples) == {'before_lift', 'lift_complete', 'settled_hold'}
    assert samples['settled_hold']['t']-samples['lift_complete']['t'] >= 3.-1e-8
    for sample in samples.values():
        assert hashlib.sha256((out/sample['path']).read_bytes()).hexdigest() == sample['sha256']
        assert sample['shape'] == [480, 640, 3]
    trace = [json.loads(line) for line in (out/'teacher-commands.jsonl').read_text().splitlines()]
    assert all(r['visible_target'] is None for r in trace if r['rgb_confirmation'].get('evidence') == 'solo_rgb_lift_v2')
    phases = [r['phase'] for r in trace]
    if visible_colour:
        assert 'hold' in phases and 'lower' in phases
        assert report['rgb_lift_v2']['last']['answer'] == 'yes'
    else:
        assert 'lower' not in phases and 'open' not in phases
        assert report['teacher']['command_result'] == 'rgb_lift_unconfirmed'
