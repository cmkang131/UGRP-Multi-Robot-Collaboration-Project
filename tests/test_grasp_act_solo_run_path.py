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
@pytest.mark.parametrize('mode,repeated', [('solo_rgb_lift_v2', True),
                                          ('solo_rgb_lift_v3', False), ('solo_rgb_lift_v3', True)])
def test_run_rgb_hold_or_blocks_setdown_and_saves_exact_own_evidence(backend, monkeypatch, visible_colour, mode, repeated):
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
    def capture(self):
        frame = image.copy()
        if not repeated:
            # Distinct saved samples with the same colour part. This is only
            # runner plumbing, not proof of lift in this physics-free backend.
            frame[:64, :64] = int(world.data.time*10)
        jpg = cv2.imencode('.jpg', frame)[1].tobytes()
        return {'image': base64.b64encode(jpg).decode()}
    monkeypatch.setattr(FakePort, 'capture', capture)
    out = runs/'rgb-loop'
    report = runner.run(plan(), out, execution_host='gcp1', profile='solo_visible_only_v1',
                        hidden=True, look=True, cap_s=13.5, rgb_lift_mode=mode)
    assert report['rgb_lift_mode'] == report['teacher']['rgb_lift_mode'] == mode
    assert report['input_audit']['invisible_measurements'] == report['input_audit']['held_world_reads'] == 0
    evidence = report[mode.removeprefix('solo_')]
    samples = evidence['samples']
    assert set(samples) == {'before_lift', 'lift_complete', 'settled_hold'}
    assert samples['settled_hold']['t']-samples['lift_complete']['t'] >= 3.-1e-8
    for sample in samples.values():
        assert hashlib.sha256((out/sample['path']).read_bytes()).hexdigest() == sample['sha256']
        assert sample['shape'] == [480, 640, 3]
    trace = [json.loads(line) for line in (out/'teacher-commands.jsonl').read_text().splitlines()]
    assert all(r['visible_target'] is None for r in trace if r['rgb_confirmation'].get('evidence') == mode)
    phases = [r['phase'] for r in trace]
    if visible_colour and not (mode == 'solo_rgb_lift_v3' and repeated):
        assert 'hold' in phases and 'lower' in phases
        assert evidence['last']['answer'] == 'yes'
    else:
        assert 'lower' not in phases and 'open' not in phases
        assert report['teacher']['command_result'] == 'rgb_lift_unconfirmed'


@pytest.mark.parametrize('kind,case,negative',
    [(k, c, False) for k, c in [('cyan', 'empty'), ('can', 'empty'), ('tile', 'empty'),
                               ('cyan', 'miss'), ('cyan', 'unknown'), ('cyan', 'hold_loss')]] +
    [(k, c, True) for k in ('cyan', 'red', 'green', 'yellow') for c in ('miss', 'unknown', 'empty')])
def test_lookback_real_run_loop_records_pre_pick_and_gates_return_lower_open(backend, monkeypatch, kind, case, negative):
    import hashlib
    import sim.grasp_act_solo_teacher as teacher_module
    import scripts.run_grasp_act_teacher as shared_runner
    from sim.grasp_act_solo_lookback import MODE, regions
    from harness.visual_arm_v3 import forward_grip, solve_grip_site_ik
    from tests.test_grasp_act_solo_lookback import colour
    runner, world, runs = backend
    monkeypatch.setattr(shared_runner, 'compress_logs', lambda out: None)
    x = .172 if kind == 'tile' else .2002
    world.data.bodies['cargo_body'].xpos[:] = (x, 0., .016 if kind in ('cyan', 'red', 'green', 'yellow') else 0.)
    scene = sys.modules['sim.grasp_act_scene'].make_scene({})
    scene.cargo[0].kind = kind
    scene.config['static_map'].update(regions={}, obstacles=[
        {'id': 'wall0', 'kind': 'wall', 'center_m': [0., 1.5], 'half_extents_m': [1., .1]}])
    live = {}
    real_teacher = teacher_module.SoloTeacher
    class ObservedTeacher(real_teacher):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            live['teacher'] = self
    monkeypatch.setattr(teacher_module, 'SoloTeacher', ObservedTeacher)
    low = {1: 1500, **solve_grip_site_ik((x, 0., .009 if kind == 'tile' else .024),
               preferred_pitch_deg=-73 if kind == 'tile' else -66, calibrated_grasp_only=False)}
    def capture(self):
        t = live['teacher']
        frame = np.full((480, 640, 3), 100, np.uint8)
        gp = {1: 1500, **t.low} if t.low is not None else low
        sx, sy, _ = forward_grip(gp)
        site = (sx+t.lookback_m, sy, 0.)
        roi, _, _ = regions(kind, gp, t.sink.pwm, site=site, held=t.holding)
        if not t.holding or case == 'miss':
            frame[roi] = colour(kind)
        if (case == 'unknown' and t.holding) or (case == 'hold_loss' and t.phase == 'hold'):
            frame[:] = 0
        return {'image': base64.b64encode(cv2.imencode('.jpg', frame)[1]).decode()}
    monkeypatch.setattr(FakePort, 'capture', capture)
    out = runs/f'lookback-{kind}-{case}'
    episode = plan(kind)
    if negative:
        episode.update(split='solo_lift_negative_probe', seed=79790, negative_probe=True)
    report = runner.run(episode, out, execution_host='gcp1', profile='solo_visible_only_v1',
                        hidden=True, look=True, cap_s=24., rgb_lift_mode=MODE,
                        teacher_stability='align_relook_v1', reach_mode='pad_window_v2',
                        solo_lift_negative_probe_v1=negative, solo_lift_lookback_margin_v1=negative)
    assert report['status'] == 'complete'
    assert report['input_audit']['invisible_measurements'] == report['input_audit']['held_world_reads'] == 0
    ev = report['lift_lookback_v1']
    assert {'before_pick', 'lookback_complete'} <= ev['samples'].keys()
    for sample in ev['samples'].values():
        assert hashlib.sha256((out/sample['path']).read_bytes()).hexdigest() == sample['sha256']
        assert sample['shape'] == [480, 640, 3]
    trace = [json.loads(line) for line in (out/'teacher-commands.jsonl').read_text().splitlines()]
    phases = [r['phase'] for r in trace]
    assert ev['samples']['before_pick']['t'] < next(r['t'] for r in trace if r['phase'] == 'close')
    assert all(r['visible_target'] is None for r in trace
               if r['phase'] in ('lift_settle', 'lookback_pose', 'lookback', 'lookback_settle', 'verify_lift', 'hold', 'lookback_return'))
    if negative:
        assert report['teacher']['lookback_plan']['backoff_m'] == .150
        assert report['solo_lift_lookback_margin_v1']
        assert not any(r['student_context']['local_skill_sample'] for r in trace)
        assert report['negative_probe'] and not report['gate_eligible'] and not report['data_admitted']
        evaluation = [json.loads(s) for s in (out/'eval-only.jsonl').read_text().splitlines()]
        assert all(e['negative_probe'] for e in evaluation)
        assert 'negative_probe_open' in phases
        lift = next(r['command'] for r in trace if r['phase'] == 'lift')
        assert lift['pwm']['1'] == 2000  # completed opening before any raise
        assert not set(phases) & {'hold', 'lookback_return', 'lower', 'open', 'backoff', 'lookaround', 'complete'}
        probe = report['negative_probe_evaluation']
        assert probe['no_pretend_setdown'] and probe['cargo_remains_at_pickup']
        if case == 'empty':
            assert ev['last']['answer'] == 'yes' and probe['yes_ticks'] == 1
            assert not probe['passed'] and report['teacher']['command_result'] == 'negative_probe_false_positive'
        else:
            assert probe['yes_ticks'] == 0 and probe['passed']
            assert ev['last']['answer'] == ('no' if case == 'miss' else 'unknown')
    elif case == 'empty':
        assert 'lookback_return' in phases and 'lower' in phases and 'open' in phases
        assert 'settled_lookback' in ev['samples']
        assert ev['last']['answer'] == 'yes'
        elapsed = [r['student_context']['skill_elapsed_s'] for r in trace
                   if r['phase'] in ('lookback_return', 'lower', 'open')]
        assert elapsed == sorted(elapsed)  # release clock includes the return
        d = report['teacher']
        assert d['lookback_commanded_backoff_m'] >= d['lookback_plan']['backoff_m']
        assert abs(d['lookback_commanded_backoff_m']-d['lookback_commanded_return_m']) <= .005
    else:
        assert not set(phases) & {'lookback_return', 'lower', 'open'}
        assert report['teacher']['command_result'] in ('rgb_lift_unconfirmed', 'rgb_hold_lost')


def test_zone_carry_real_runner_with_stub_world_never_uses_held_truth_or_legacy_pose(backend, monkeypatch):
    import sim.grasp_act_solo_teacher as tm
    import sim.solo_carry_to_zone as cm
    import scripts.run_grasp_act_teacher as shared
    from scripts.make_solo_carry_plan import prepare
    from harness.zone_final_environment import resolve
    runner, world, runs = backend
    monkeypatch.setattr(shared, 'compress_logs', lambda out: None)
    p = prepare()['episodes'][0]
    scene = sys.modules['sim.grasp_act_scene'].make_scene({})
    scene.config['static_map'] = resolve(p['map_id'])[0]
    scene.config['setup_only']['objects'][p['item_id']] = {'body_name': 'cargo_body'}
    real = tm.SoloTeacher
    class CarryTeacher(real):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.low, self.high, self.descent = self._pick_geometry({'xyz': [.203, 0., .024], 'yaw': 0.})
            self.sink.pwm.update({1: 1500, **self.high})
            self.arm.commanded.update(self.sink.pwm)
            # Start at a permitted estimated pose; sensor substitution only.
            cx, cy = self.carry.region['center_m']
            self.carry.loc.own.x = np.array([cx-.5, cy, 0.])
            self.carry.loc.last_fix = 0.
            self.carry.start(0., (.203, 0.))
            self.carry.loc.own.x = np.array([*self.carry.goal, 0.])
            self.phase, self.phase_t, self.skill_started = 'carry_to_zone', 0., 0.
            self.holding = True
    monkeypatch.setattr(tm, 'SoloTeacher', CarryTeacher)
    # Top bytes may be written to evaluation output, but must never be decoded
    # or passed to a controller. Exercise the real own-frame boundary.
    sentinel = b'TOP_EVALUATION_ONLY_NOT_A_JPEG'
    monkeypatch.setattr(world, 'render_team_jpeg', lambda **kw: sentinel)
    decode = cv2.imdecode
    def own_decode(raw, flags):
        assert raw.tobytes() != sentinel, 'top RGB entered perception'
        return decode(raw, flags)
    monkeypatch.setattr(cv2, 'imdecode', own_decode)
    monkeypatch.setattr(cm.CarryToZone, 'place_visible', lambda *a: True)
    out = runs/'carry'
    report = runner.run(p, out, execution_host='gcp1', profile='solo_visible_only_v1',
        hidden=True, look=True, cap_s=14., rgb_lift_mode='solo_lift_lookback_v1',
        solo_truth_free_lookaround_v1=True, solo_carry_to_zone_v1=True)
    assert report['status'] == 'complete'
    assert not report['physical_success']  # fixture cargo never actually lifted
    assert report['destination_zone'] == p['destination_zone']
    assert report['input_audit']['held_world_reads'] == 0
    assert report['input_audit']['blocked_held'] > 0
    assert report['lookaround']['localizer']['truth_free_v1']
    trace = [json.loads(s) for s in (out/'teacher-commands.jsonl').read_text().splitlines()]
    assert all(r['map_pose']['own_frame']['camera'] == 'r1/robot_cam' for r in trace)
    assert not (out/'map-rgb').exists()
    assert all(p.read_bytes() == sentinel for p in (out/'review-top').glob('*.jpg'))
    assert {'zone_place_view', 'zone_place_advance', 'lower', 'open', 'backoff'} <= {r['phase'] for r in trace}
    assert all(r['visible_target'] is None for r in trace if r['phase'] in
               ('zone_place_view', 'zone_place_advance', 'lower', 'open'))
    ev = [json.loads(s) for s in (out/'eval-only.jsonl').read_text().splitlines()]
    assert all('footprint_xy' in r for r in ev if 'min_z' in r)


@pytest.mark.parametrize('acquire', [False, True])
def test_carry_runner_searches_before_approach_and_logs_own_only_boundary(backend, monkeypatch, acquire):
    import scripts.run_grasp_act_teacher as shared
    from scripts.make_solo_carry_plan import prepare
    from harness.zone_final_environment import resolve
    runner, world, runs = backend
    monkeypatch.setattr(shared, 'compress_logs', lambda out: None)
    p = prepare()['episodes'][0]
    scene = sys.modules['sim.grasp_act_scene'].make_scene({})
    scene.config['static_map'] = resolve(p['map_id'])[0]
    scene.config['setup_only']['objects'][p['item_id']] = {'body_name': 'cargo_body'}
    monkeypatch.setattr(FakeVisibility, 'region_visible',
                        lambda self, data, rid, gids: (7, 7) if acquire and data.time >= 3. else (0, 7))
    monkeypatch.setattr(world, 'render_team_jpeg', lambda **kw: b'TOP_EVAL_ONLY')
    out = runs/'search'
    report = runner.run(p, out, execution_host='gcp1', profile='solo_visible_only_v1',
        hidden=True, look=True, cap_s=4., rgb_lift_mode='solo_lift_lookback_v1',
        solo_truth_free_lookaround_v1=True, solo_carry_to_zone_v1=True)
    assert report['status'] == 'complete'
    rows = [json.loads(s) for s in (out/'teacher-commands.jsonl').read_text().splitlines()]
    searching = [r for r in rows if r['phase'] == 'pickup_search']
    assert searching and all(not any(r['command']['wheels']) for r in searching)
    assert all(not r['student_context']['local_skill_sample'] for r in searching)
    assert all(r['map_pose']['own_frame']['camera'] == 'r1/robot_cam' for r in rows)
    assert len({tuple(sorted(r['command']['pwm'].items())) for r in searching}) > 1
    assert any(r['phase'] == 'approach' for r in rows) == acquire
    if acquire:
        first = next(r for r in rows if r['phase'] == 'approach')
        assert first['visible_target'] is not None and first['t'] >= 3.
    assert report['input_audit']['invisible_measurements'] == report['input_audit']['held_world_reads'] == 0
