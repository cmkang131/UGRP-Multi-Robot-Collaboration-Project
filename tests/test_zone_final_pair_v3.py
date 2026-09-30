"""V88 fake/offline regressions. No physics, render, network or real model."""
import copy
import errno
import json
import math
import socket
import sys
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_final_pair_contract as c
from harness import zone_final_pair_skill as skill
from scripts import run_final_pair_v3 as run

MAPS = tuple(c.registry()['maps'])
SERVO = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for module in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):
        monkeypatch.setitem(sys.modules, module, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))
    from harness.vision_loc_client import VisionWorkerClient
    monkeypatch.setattr(VisionWorkerClient, '__init__', lambda *a, **kw: pytest.fail('real worker forbidden'))


def synthetic(tmp_path):
    """Fabricated test fixture, never a measured/published calibration asset."""
    from harness.owncam_localizer import DEFAULT_PARAMS
    params = copy.deepcopy(DEFAULT_PARAMS)
    params['particles'] = 100
    params['motion']['tau_stop_s'] = .02
    params['motion_loaded'] = copy.deepcopy(params['motion'])
    params['motion_loaded'].update(yaw_bias_std_rad_s=.01, drift_ratio_std=.01,
        deadband={'c0': [0., 0., 0.], 'u1': [0., 0., 0.]},
        load_transition={'scale_std': [.02, .02, .01], 'unloaded_scale_std': .05})
    params['motion_profiles'] = {'fine': copy.deepcopy(params['motion'])}
    rec = {'frame': 'optical_to_actual_chassis', 'chassis_to_floor': {'origin_m': [0.,0.,.03236], 'rotation': np.eye(3).tolist()}, 'origin_m': [.15, 0., .2], 'rotation': [[0., 0., 1.], [-1., 0., 0.], [0., -1., 0.]]}
    cal = {'schema': 'ugrp.final_environment_measured_calibration.v1', 'status': 'MEASURED_SIM',
        'contract_sha256': c.base.sha(c.ROOT/c.CALIBRATION_CONTRACT), 'maps': c.resolve(MAPS[0])[2]['maps'],
        'robot_model': 'masterpi_v3', 'render_profile': 'floor_light_v1',
        'source_sha': 'a'*40, 'measurement_manifest_sha256': 'b'*64, 'params': params,
        'pan_base_yaw': {'loaded': 0., 'unloaded': 0.},
        'pair_model': {'slope_to_yaw_ratio': 1., 'b_rad_s': {'': .04, 'pm': .03, 'edge': .02, 'pm+edge': .01}},
        'camera_models': {state: {'740,2320,1320,1500': copy.deepcopy(rec)} for state in ('loaded', 'unloaded')}}
    from harness.zone_final_pair_vision import required_camera_poses
    from harness.vision_pose_source_final import camera_key
    for state, poses in required_camera_poses().items():
        for pose in poses:
            cal['camera_models'][state][camera_key(pose)] = copy.deepcopy(rec)
    path = tmp_path/'SYNTHETIC-TEST-ONLY.json'
    run.write(path, cal)
    return path, cal


@pytest.mark.parametrize('map_id', MAPS)
def test_standard_scene_task_and_route_offline(map_id):
    from sim.final_pair_v3 import make_scene
    from sim.session_scenes import Scene
    static, _, _ = c.resolve(map_id)
    task = skill.task(static)
    plan = skill.make_plan(static, task['sheet'], task['target'])
    assert 1 < len(plan['route'])-1 <= 8
    assert plan['sheet'] == task['sheet']
    assert plan['passage']['envelope'] == skill.ENVELOPE
    assert plan['map_sha256'] == c.base.digest(static)
    before = plan['route'][plan['checkpoint_segments']['before_door']][0]
    after = plan['route'][plan['checkpoint_segments']['after_door']][0]
    x0, x1 = plan['passage']['x_range_m']
    assert before+skill.ENVELOPE['x_m'][1] <= x0-.049999
    assert after+skill.ENVELOPE['x_m'][0] >= x1+.049999
    bundle = c.bundle(map_id, 'p03')
    scene = make_scene(bundle, 911)
    assert isinstance(scene, Scene)
    assert scene._render_profile_name == 'floor_light_v1'
    assert scene.config['static_map'] == static
    assert 'teacher_measurement_stations' not in scene.config['setup_only']
    measurement = make_scene({**bundle, 'check': 'calibration-loaded'}, 911)
    for rid in c.ROBOTS:
        x, y, z, yaw = measurement.config['setup_only']['spawns'][rid]
        assert z == scene.config['setup_only']['spawns'][rid][2]
        assert abs(yaw) == (0. if rid == 'r1' else math.pi)


def test_bundle_closure_and_workflow_registration():
    from sim import workflow_manager as wm
    bundle = c.bundle(MAPS[0], 'carry')
    for name in ('harness/zone_final_pair_scan.py', 'harness/zone_final_pair_skill.py',
                 'harness/zone_pair_executor.py', 'harness/owncam_localizer.py',
                 'harness/vision_pose_source_p03.py', 'harness/zone_study_pose_delay_p03.py',
                 c.WORKFLOW, c.CALIBRATION_CONTRACT):
        assert bundle['source_sha256'][name] == c.base.sha(c.ROOT/name)
    row, _ = wm._row(c.ROOT, c.WORKFLOW_ID)
    assert row['version'] == '3.1.0'
    plan = wm.plan(c.ROOT, c.WORKFLOW_ID, ['--check', 'p03', '--expected-source-sha', 'a'*40])
    assert not plan['execution_started']
    assert plan['command'][1:3] == ['-m', 'scripts.run_final_pair_v3']


@pytest.mark.parametrize('mutation', ['hash', 'render', 'map', 'singular', 'camera', 'missing_loaded', 'pair', 'axis_lag'])
def test_calibration_mutations_fail_closed(tmp_path, mutation):
    path, cal = synthetic(tmp_path)
    digest = c.base.sha(path)
    assert c.measured_calibration(path, digest, MAPS[0]) == cal
    if mutation == 'hash':
        path.write_bytes(path.read_bytes()+b'\n')
    else:
        if mutation == 'render': cal['render_profile'] = 'default'
        if mutation == 'map': cal['maps'][MAPS[0]] = '0'*64
        if mutation == 'singular': cal['params']['motion']['gain'] = [[1., 1., 1.]]*3
        if mutation == 'camera': cal['camera_models']['loaded']['740,2320,1320,1500']['rotation'][0][0] = 2.
        if mutation == 'missing_loaded': del cal['params']['motion_loaded']
        if mutation == 'pair': del cal['pair_model']['b_rad_s']['edge']
        if mutation == 'axis_lag': cal['params']['motion_loaded']['tau_axis_s'] = [.12, -.1, .2]
        run.write(path, cal)
        digest = c.base.sha(path)
    with pytest.raises(ValueError):
        c.measured_calibration(path, digest, MAPS[0])


def provider(tmp_path):
    from harness.vision_loc_client import InProcessWorker
    from harness.vision_pose_source_pair_v3 import build_provider
    path, cal = synthetic(tmp_path)
    worker = InProcessWorker(lambda *a: pytest.fail('no worker call in lifecycle test'))
    return build_provider(c.resolve(MAPS[0])[0], path, c.base.sha(path), worker=worker)


def test_provider_keeps_pf_commands_uncertainty_and_delay_at_each_checkpoint(tmp_path):
    p = provider(tmp_path)
    try:
        p.init_prior([-.8, -.85, 0.], source='synthetic public dock')
        p.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SERVO})
        for t in (1., 3., 5.):
            p.report(t)
            pf = p.provider.loc._pf
            before = pf.px.copy()
            p.begin_relocalization(t, SERVO)
            assert pf is p.provider.loc._pf
            np.testing.assert_array_equal(before, pf.px)
            rec = p.provider.lifecycle[-1]
            assert rec['before']['particles_sha256'] == rec['after']['particles_sha256']
            assert pf.last_scan_t is None
        assert p.delay['wrapper_count'] == 1 and p.delay['effective_sim_s'] == .16
        with pytest.raises(RuntimeError, match='prior'):
            p.init_prior([999, 999, 0], source='late teacher injection')
        with pytest.raises(ValueError, match='UNMEASURED_V3_CAMERA_POSTURE'):
            pf.column_model_for({**SERVO, 6: 700})
        np.testing.assert_allclose(pf.column_model_for(SERVO).origin, [.15, 0., .23236])
    finally:
        p.close()
    assert p.provider._closed


def test_pair_latent_states_follow_resampled_particle_indices(tmp_path):
    from harness.zone_final_pair_scan import resample
    p = provider(tmp_path)
    try:
        p.init_prior([0, 0, 0], source='test')
        pf = p.provider.loc._pf
        pf.logw[:] = -1e4
        pf.logw[7] = 0.
        for name in ('yaw_bias', 'yaw_extra'):
            setattr(pf, name, np.arange(pf.n, dtype=float))
        pf.drift = np.repeat(np.arange(pf.n, dtype=float)[:, None], 2, axis=1)
        before = pf.px[7].copy()
        resample(pf)
        np.testing.assert_array_equal(pf.px, np.repeat(before[None], pf.n, axis=0))
        assert np.all(pf.yaw_bias == 7.) and np.all(pf.yaw_extra == 7.) and np.all(pf.drift == 7.)
    finally:
        p.close()


class FakePhysics:
    truth = {'success': True, 'peer_pose': [999, -999, 4.]}
    failure = None
    def __init__(self, bundle, out, *, seed):
        self.now, self.closed, self.deadline = 0., False, None
        self.actions, self.samples, self.frames = [], [], []
        self.commands = {r: dict(SERVO) for r in c.ROBOTS}
    def reset(self, cap):
        self.now = 1.
        return self.now
    def set_deadline(self, t): self.deadline = t
    def advance_to(self, t):
        assert self.now <= t <= self.deadline
        self.now = t
    def issue(self, rid, action):
        self.actions.append((self.now, rid, copy.deepcopy(action)))
    def capture(self):
        if self.failure: raise self.failure
        self.frames.append(self.now)
        return {'r1': 'own-r1-pixels', 'r2': 'own-r2-pixels'}
    def eval_sample(self):
        self.samples.append(self.now)
        return copy.deepcopy(self.truth)
    def close(self): self.closed = True


class FakeRuntime:
    def __init__(self, *a, **kw): self.closed, self.commands = False, []
    def initial_commands(self, now, commands): self.initial = copy.deepcopy(commands)
    def on_frames(self, now, frames): assert frames == {'r1': 'own-r1-pixels', 'r2': 'own-r2-pixels'}
    def step(self, now): return [('r1', {'kind': 'hold'})]
    def arm_step(self, now): return []
    def on_command(self, rid, now, action): self.commands.append((rid, now, action))
    def record(self): return {'pair': []}
    def close(self): self.closed = True


@pytest.mark.parametrize('check', c.CHECKS)
def test_fake_full_protocol_preserves_120_second_caps_and_ignores_truth(tmp_path, check, monkeypatch):
    # Fake scheduler with the real mandatory collection preflight.
    case = c.cases(check)[0]
    b = {**c.bundle(case['map_id'], check), 'case': case}
    receipts = []
    for mutation in (False, True):
        instances = []
        def factory(*a, **kw):
            obj = FakePhysics(*a, **kw)
            obj.truth = {'success': mutation, 'peer_pose': [1e9 if mutation else -1e9]*3}
            instances.append(obj)
            return obj
        result = run.run_case(b, tmp_path/str(mutation), seed=911, backend_factory=factory, runtime_factory=FakeRuntime)
        backend = instances[0]
        assert result['protocol_complete'] and result['status'] == 'COLLECTED_UNQUALIFIED'
        assert result['physical_success'] is None
        assert backend.closed and backend.now == backend.deadline == 1.+b['case']['sim_cap_s']
        assert len(backend.samples) == round(b['case']['sim_cap_s']/.05)+1
        receipts.append(backend.actions)
        if check == 'p03': assert result['checkpoint']['status'] == 'NOT_REACHED'
    assert receipts[0] == receipts[1]


@pytest.mark.parametrize('failure', [RuntimeError('camera failed'), OSError(errno.ENOSPC, 'full')])
def test_failure_keeps_partial_record_and_closes_owner(tmp_path, failure, monkeypatch):
    # Fake owner lifecycle with real collection admission.
    case = c.cases('calibration-fine')[0]
    b = {**c.bundle(case['map_id'], 'calibration-fine'), 'case': case}
    owners = []
    def factory(*a, **kw):
        obj = FakePhysics(*a, **kw)
        obj.failure = failure
        owners.append(obj)
        return obj
    result = run.run_case(b, tmp_path/'fail', seed=911, backend_factory=factory)
    assert result['status'] == 'HOST_ERROR' and not result['protocol_complete']
    assert owners[0].closed
    assert (tmp_path/'fail/artifacts.sha256.json').exists()
    if isinstance(failure, OSError): assert result['failure']['class'] == 'ENOSPC'


def test_collection_has_real_grasp_attempt_fine_pulses_and_per_pose_labels():
    from harness.zone_final_pair_calibration import schedule
    from harness.visual_arm_v3 import tool_pose
    loaded, fine, unloaded = [schedule(k) for k in ('calibration-loaded', 'calibration-fine', 'calibration-unloaded')]
    for rid in c.ROBOTS:
        closes = [e for e in loaded if e['robot_id'] == rid and e['action'].get('servo_id') == 1]
        assert [(e['t'], e['action']['pulse']) for e in closes] == [(0., 2000), (2., 1500), (362., 2000)]
    f = [e['action'] for e in fine if e['action']['kind'] == 'mecanum']
    u = [e['action'] for e in unloaded if e['action']['kind'] == 'mecanum']
    assert len(f) == len(u) == 5040
    assert sorted({abs(a['forward']) for a in f}) == [0., .004, .016, .028]
    assert sorted({abs(a['forward']) for a in u}) == [0., .01, .02, .03]
    assert max(e['t'] for e in fine) < 370
    assert {'camera_p45', 'camera_inspect', 'camera_search'} <= {e['phase'] for e in fine}


def test_cli_missing_calibration_is_plan_only(tmp_path, capsys):
    args = ['--check', 'p03', '--expected-source-sha', 'a'*40, '--output', str(tmp_path/'out')]
    assert run.main(args) == 0
    plan = json.loads(capsys.readouterr().out)
    assert not plan['runnable'] and plan['blocked_on'] == ['MEASURED_V3_CALIBRATION_REQUIRED']
    assert len(plan['cases']) == plan['denominator'] == 3
    assert not (tmp_path/'out').exists()


def test_private_bind_never_changes_registered_globals(tmp_path):
    from harness.zone_final_pair_binding import bind
    from harness import zone_pair_executor as pair
    old = pair.make_plan
    custom = bind(pair.PairTeam.start, make_plan=lambda *a: None)
    assert pair.make_plan is old
    assert pair.PairTeam.start.__globals__['make_plan'] is old
    assert custom.__code__ is pair.PairTeam.start.__code__
    assert custom.__globals__ is not pair.PairTeam.start.__globals__


def test_motor_schedule_inverts_calibrated_deadband(tmp_path):
    _, cal = synthetic(tmp_path)
    profile = cal['params']['motion_loaded']
    profile['deadband'] = {'c0': [.02, .01, .005], 'u1': [.05, .04, .03]}
    for velocity in ([.01, -.01, .005], [.08, -.08, .1], [0., 0., 0.]):
        raw = skill.motor_command(profile, velocity)
        c0, u1 = [np.array(profile['deadband'][k]) for k in ('c0', 'u1')]
        effective = raw*np.clip((abs(raw)-c0)/(u1-c0), 0., 1.)
        np.testing.assert_allclose(np.asarray(profile['gain'])@effective, velocity, atol=1e-12)


def test_pair_predictor_applies_deadband_to_partner_before_yaw_mean(tmp_path):
    from harness.vision_pose_source_pair_v3 import pair_motion_module
    _, cal = synthetic(tmp_path)
    mp = cal['params']['motion_loaded']
    mp['gain'] = [[1., 0., 0.], [0., 1., 0.], [.2, 0., 1.]]
    mp['deadband'] = {'c0': [.02, .01, .005], 'u1': [.05, .04, .03]}
    pf = pair_motion_module().OwnCamLocalizer(c.resolve(MAPS[0])[0], cal['params'], seed=7)
    raw = skill.motor_command(mp, [.04, 0., 0.])
    pf.load.loaded = True  # synthetic command-state fixture, no physical load claim
    pf.pair_plan = {'t0': 0., 't1': 1., 'own': raw, 'partner': -raw}
    pf.command({'t': 0., 'kind': 'mecanum', 'forward': raw[0], 'left': raw[1],
                'turn': raw[2], 'duration_s': .15})
    pf.predict_to(.1)
    assert pf.pair_matched == 1
    assert pf.vel[0] > 0
    assert pf.vel[2] == pytest.approx(0., abs=1e-12)


def test_fake_scan_can_issue_informative_receipt_but_blank_scan_cannot(tmp_path):
    from harness import vision_loc_protocol as vp
    from harness.zone_final_pair_scan import quality
    from tests.test_vision_pose_source import truth_obs
    p = provider(tmp_path)
    try:
        p.init_prior([1., .05, 0.], (.03, .03, .02), source='SYNTHETIC TEST ONLY')
        p.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SERVO})
        p.report(.8)
        pf = p.provider.loc._pf
        vl, _ = vp.load_vis3()
        obs = truth_obs(pf, [1., .05, 0.])
        assert quality(vl, pf, obs, SERVO)['informative']
        pf.update_obs(1., obs, SERVO)
        assert pf.last_scan_t == 1. and pf.v3_last_fix_quality['t'] == 1.
        blank = copy.deepcopy(obs)
        blank.b_kind[:] = blank.t_kind[:] = vl.NONE
        pf.update_obs(2., blank, SERVO)
        assert pf.last_scan_t == 1.  # missing geometry cannot refresh a fix
    finally:
        p.close()


def test_standoff_uses_only_measured_projection(monkeypatch):
    from harness import zone_pair_beam_track as track
    from harness.zone_final_pair_vision import PairVision
    vision = PairVision({})
    calls = []
    vision.v2_observe = lambda *a: calls.append('measured') or {'visible': False}
    monkeypatch.setattr(track, 'observe_beam', lambda *a: pytest.fail('v2 camera fallback'))
    assert vision.beam_track()._standoff({'image': 'fake'}, SERVO) is None
    assert calls == ['measured']


def test_fixed_grasp_catalogue_covers_accepted_alignment_and_acquisition():
    from harness.zone_final_pair_vision import PairVision, GRASP_RADIUS_M, grasp_postures, required_camera_poses
    from harness.vision_pose_source_final import camera_key
    from harness.zone_final_pair_calibration import schedule
    from harness import visual_arm_v3 as arm
    from scripts.study_owncam_pair_beam import GRASP_Z_M, HOVER_Z_M
    vision = PairVision({})
    for dx in (-.0029, 0., .0029):
        for dy in (-.0029, 0., .0029):
            assert vision.align_command({'grip_base_m': [GRASP_RADIUS_M+dx, dy], 'axis_heading_rad': 0.}) is None
            hover, path = grasp_postures()
            assert arm.tool_pose(path[-1]).z_m == pytest.approx(GRASP_Z_M, abs=.001)
            assert arm.tool_pose(hover).z_m == pytest.approx(HOVER_Z_M, abs=.001)
    assert vision.align_command({'grip_base_m': [.2102, 0.], 'axis_heading_rad': 0.}) is not None
    # Enumerate held issued postures in the collection, with the same own-
    # command LoadState used by the provider; no teacher labels manufacture
    # camera coverage in this test.
    from harness.vision_pose_source_pair_v3 import pair_motion_module
    seen = {'unloaded': set(), 'loaded': set()}
    for check in c.CHECKS[2:]:
        state = pair_motion_module().OwnCamLocalizer(c.resolve(MAPS[0])[0], seed=1).load
        state.command({'t': 0., 'kind': 'initial_servo_command', 'pulses': SERVO})
        events = [e for e in schedule(check) if e['robot_id'] == 'r1' and e['action']['kind'] != 'mecanum']
        for i, e in enumerate(events):
            state.command({'t': e['t'], **e['action']})
            next_t = events[i+1]['t'] if i+1 < len(events) else 370.
            if next_t-e['t'] >= .4:
                seen['loaded' if state.loaded else 'unloaded'].add(camera_key(state.servo))
    for load, poses in required_camera_poses().items():
        assert {camera_key(p) for p in poses} <= seen[load]


def test_checkpoint_cannot_be_claimed_by_opening_or_old_lift_only():
    plan = skill.make_plan(c.resolve(MAPS[0])[0], skill.SHEET, 'B')
    seg = plan['checkpoint_segments']['after_door']
    events = [{'event': 'checkpoint_open', 'seg': seg-1, 'sim_s': 30.},
              {'event': 'state', 'state': 'wait_carry', 'seg': seg-1, 'sim_s': 20.}]
    record = {'pair': [{'plan': plan, 'robots': {rid: {'events': copy.deepcopy(events)} for rid in c.ROBOTS}}]}
    assert run.checkpoint_record(record, 'after_door')['status'] == 'NOT_REACHED'
    for robot in record['pair'][0]['robots'].values():
        robot['events'].append({'event': 'state', 'state': 'wait_carry', 'seg': seg, 'sim_s': 40.})
    got = run.checkpoint_record(record, 'after_door')
    assert got['status'] == 'SEQUENCE_OBSERVED_UNQUALIFIED' and got['physical_success'] is None


def test_real_controller_constructs_with_v3_projection_and_same_dispatch(tmp_path):
    from harness.zone_final_pair_runtime import Runtime
    from harness.vision_pose_source_pair_v3 import build_provider
    from harness.vision_loc_client import InProcessWorker
    from harness.owncam_pose_source import PoseReport
    from tests.test_zone_pair_executor import pair_obs
    path, cal = synthetic(tmp_path)
    def factory(static, path, digest, seed):
        return build_provider(static, path, digest, seed, worker=InProcessWorker(lambda *a: None))
    runtime = Runtime(c.resolve(MAPS[0])[0], path, c.base.sha(path), seed=911, provider_factory=factory)
    try:
        runtime.initial_commands(0., {r: dict(SERVO) for r in c.ROBOTS})
        for rid, own in runtime.actors.items():
            own.last_obs = pair_obs(rid, 1, 0., SERVO)
            own.last_report = PoseReport(0., True, x_m=0., y_m=0., yaw_rad=0., std_xy_m=.01,
                std_yaw_rad=.01, source=own.pose.source)
            own.gate.state = 'ok'
            ack = runtime.team.start(rid, 'cargoX', 'B', next(r for r in c.ROBOTS if r != rid), now=0.)
            assert ack['accepted'], ack
            ep = own._pair
            assert isinstance(ep.controller, skill.V3Controller)
            assert ep.controller.driver.loc is own.pose.loc
            assert ep.command_guard.sweep_guard().mount[0] > 0.
        ctl = runtime.actors['r1']._pair.controller
        ctl.grasp_estimate = [0., .05, 0.]
        ctl.v3_params['motion_loaded']['tau_axis_s'] = [.9, .7, .5]
        schedule = ctl.door_schedule(10.)
        assert schedule[-1][1] > schedule[-1][0]
        from harness.owncam_carry_v6e import lag_travel
        duration = schedule[-1][1]-schedule[-1][0]
        speed = abs(schedule[-1][2]['forward']*ctl.v3_params['motion_loaded']['gain'][0][0])
        distance = math.dist(*ctl.v3_plan['route'][:2])
        assert lag_travel(duration, speed, .9, .02) == pytest.approx(distance)
        assert abs(lag_travel(duration, speed, .12, .02)-distance) > .02
        pf = runtime.providers['r1'].provider.loc._pf
        np.testing.assert_array_equal(pf.pair_plan['partner'], -pf.pair_plan['own'])
        before = id(pf)
        ctl._cp_open(20., True)
        assert ctl.state == 'align_relook_stop' and ctl.seg == 1
        assert id(runtime.providers['r1'].provider.loc._pf) == before
    finally:
        runtime.close()
