import copy
import json
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_s3_no_prior as m
from harness import zone_s3_no_prior_contract as c


def test_new_scenario_and_source_contract():
    b = c.bundle('a'*40)
    c.verify(b)
    assert b['weld'] == 'off' and b['known_start_information'] is False
    assert b['seed'] == 14201 and b['preregistration']['run_limit'] == 1
    assert b['controller_inputs'] == ['own_rgb', 'static_map', 'own_command_history']
    assert b['idle_robot_contacts'] == 'off'
    assert all(o['destination_zone'] == 'B' for o in c.inputs()[2]['orders'])
    bad = copy.deepcopy(b)
    bad['controller_config']['options']['start_prior'] = 'off'
    with pytest.raises(ValueError):
        c.verify(bad)


def test_new_host_heading_contract_keeps_v142_and_physical_mount_boundary(monkeypatch, capsys):
    from harness import zone_s3_host_heading_contract as new
    from scripts import run_s3_host_heading as runner
    baseline = c.bundle('a'*40)
    b = new.bundle('a'*40)
    new.verify(b)
    assert c.bundle('a'*40) == baseline
    assert 's3_camera_binding' not in baseline
    assert b['execution_bundle_id'] == 'zone-s3-host-heading-v146'
    assert b['s3_camera_binding'] == 'v3_persistent_v1' and b['eval_render_camera']
    assert b['options']['heading_mode'] == 'path_tangent_v1'
    assert b['options']['localization_certification'] == 'posterior_consensus_v1'
    assert b['options'].get('recorded_camera_mount', 'off') == 'off'
    assert not b['particle_recovery_changed'] and not b['convergence_thresholds_changed']
    assert b['preregistration']['run_limit'] == 1
    pending = copy.deepcopy(b)
    pending['preregistration']['heading_dependency_sha'] = None
    with pytest.raises(ValueError, match='not admitted yet'):
        runner.require_heading_source(pending)
    monkeypatch.setattr(runner, 'run', lambda *a, **k: pytest.fail('plan started runtime'))
    assert runner.main(['--expected-source-sha', 'a'*40, '--output', '/nonexistent/s3-next-plan']) == 0
    assert json.loads(capsys.readouterr().out)['execution_started'] is False
    for key, bad in [('s3_camera_binding', 'off'), ('eval_render_camera', False)]:
        changed = copy.deepcopy(b)
        changed[key] = bad
        with pytest.raises(ValueError):
            new.verify(changed)


def test_three_real_localizers_never_call_dock_prior(monkeypatch):
    from sim import zone_model_conventions
    def forbidden(*a, **k):
        raise AssertionError('dock prior forbidden')
    monkeypatch.setattr(zone_model_conventions, 'spawn_layout', forbidden)
    static = c.hp.resolve(c.old.solo.MAP_ID)[0]
    runtime = m.Runtime(static, c.inputs()[2]['orders'], c.ROOT/c.old.solo.CALIBRATION,
        c.old.solo.CALIBRATION_SHA, seed=14201, config=c.controller_config())
    try:
        commands = {r: {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500} for r in m.ROBOTS}
        runtime.initial_commands(0., commands)
        clouds = []
        for rid, own in runtime.localizers.items():
            assert not hasattr(own, 'heading_mode')  # historical v142 omitted option
            pf = own.pose.provider.loc._pf
            clouds.append(pf.px)
            assert pf.n == 100000 and np.ptp(pf.px[:, 2]) > 6.2
            assert own.pose.provider.prior['known_own_dock'] is False
            assert own.record()['start_prior']['dock_prior_calls'] == 0
            assert own.destination == 'B'
            assert len(own.commands) == 1
        assert not any(np.shares_memory(clouds[i], clouds[j]) for i in range(3) for j in range(i))
        for rid in ('r1', 'r2'):
            assert runtime.pair.actors[rid].pose.localizer is runtime.localizers[rid]
            runtime.on_command(rid, .05, dict(kind='mecanum', forward=.35, left=0., turn=0., duration_s=.1))
            assert runtime.localizers[rid].pose.provider.loc._pf.n == 2000
            assert len(runtime.localizers[rid].commands) == 2
        assert runtime.localizers['r3'].pose.provider.loc._pf.n == 100000
        # Exercise the real own-frame path on both sides of the startup handoff.
        # Synthetic pixels test transport/filter ownership, not localization accuracy.
        from tests.test_solo_cyan_v106 import observation
        runtime.on_frames(.2, {r: observation(.2, 1, rid=r) for r in m.ROBOTS})
        for rid, action in runtime.step(.2):
            runtime.on_command(rid, .2, action)
        assert all(v == 0 for v in runtime.wait_robot_s.values())
        runtime.boot_finished_at = .2
        runtime.on_frames(.4, {r: observation(.4, 2, rid=r) for r in m.ROBOTS})
        for rid in ('r1', 'r2'):
            assert runtime.pair.actors[rid].last_report.t_est == runtime.localizers[rid].last_report.t_est
            assert len(runtime.localizers[rid].pose_log) == 2
        # S2 explicitly stores None here. Both runtime and trial call this
        # serializer, including failed runs; absence must be JSON-serializable.
        yaw = runtime.pair.team._carry_yaw_record()
        assert all(q['availability_frames'] == {} for q in yaw.values())
        json.dumps(runtime.record())
    finally:
        runtime.close()


def test_new_s3_runtime_applies_shared_heading_and_records_result(tmp_path):
    from harness import zone_s3_host_heading_contract as new
    from harness.path_heading_policy import DEFAULT
    from scripts.run_final_environment_checks import write
    b = new.bundle('a'*40)
    static = c.hp.resolve(c.old.solo.MAP_ID)[0]
    runtime = m.Runtime(static, c.inputs()[2]['orders'], c.ROOT/c.old.solo.CALIBRATION,
        c.old.solo.CALIBRATION_SHA, seed=14201, config=b['controller_config'])
    try:
        assert b['options']['heading_mode'] == DEFAULT
        for own in runtime.localizers.values():
            assert own.record()['heading_mode']['option'] == DEFAULT
            assert own.record()['start_prior']['dock_prior_calls'] == 0
            # Only the test substitutes an own estimate and skips startup.
            # Exercise the actual cooperative drive chain (no simulator).
            own.start_prior = 'off'
            own.last_report = SimpleNamespace(initialized=True, x_m=.3, y_m=-2.15, yaw_rad=0.,
                std_xy_m=.01, std_yaw_rad=.01, last_fix_t=0.)
            action, arrived = own.drive((.3, -.85), 1.)
            assert not arrived and action[0]['turn'] > 0
            assert action[0]['forward'] == action[0]['left'] == 0
            own.last_report.yaw_rad = np.pi/2
            action, arrived = own.drive((.3, -.85), 2.)
            assert not arrived and action[0]['forward'] > 0
            assert action[0]['turn'] == action[0]['left'] == 0
        # This does not assert independent heading control during coupled carry.
        assert b['heading_scope']['r1+r2'].endswith('coupled beam controller retained')
        write(tmp_path/'bundle.json', b)
        write(tmp_path/'result.json', dict(status='HOST_ERROR'))
        assert json.loads((tmp_path/'result.json').read_text())['heading_mode'] == DEFAULT
    finally:
        runtime.close()


def test_new_host_requires_actual_speedups_after_standard_reset(monkeypatch, tmp_path):
    from sim.zone_s3_no_prior import PhysicsBackend
    from sim.solo_cyan_v106 import PhysicsBackend as SoloBackend
    from scripts import run_zone_study_integration
    monkeypatch.setattr(SoloBackend, 'reset', lambda self, cap: 1.3)
    monkeypatch.setattr(run_zone_study_integration, 'placements_match', lambda *args: None)
    host = SimpleNamespace(out=tmp_path, scene=SimpleNamespace(spec={}),
        world=SimpleNamespace(drive_profile_record={}, v7_speedups_record={
            'mode': 'relay-cache-v1', 'enabled': True}),
        bundle={'runtime_speedups_required': 'relay-cache-v1'})
    assert PhysicsBackend.reset(host, 5.) == 1.3
    host.world.v7_speedups_record['enabled'] = False
    with pytest.raises(ValueError, match='not applied'):
        PhysicsBackend.reset(host, 5.)


def test_pose_port_refuses_prior_and_cross_robot_frame():
    own = SimpleNamespace(robot_id='r1')
    port = m.OwnPosePort(own)
    with pytest.raises(AssertionError):
        port.init_prior((0, 0, 0), (1, 1, 1))
    port.frame = (dict(robot_id='r2', sim_time=0.), None)
    with pytest.raises(ValueError):
        port.on_frame(0., np.zeros((2, 2, 3)))


def test_prior_present_frozen_runtime_and_config_bytes_unchanged():
    paths = ['harness/zone_s3_host.py', 'harness/zone_s3_door_yield.py', 'scripts/run_s3_host.py',
        'sim/zone_s3_host.py', 'configs/zone_study_dev/dev_s1lite.json', 'configs/simulation_workflows.json']
    for p in paths:
        frozen = subprocess.check_output(['git', 'show', 'd3393847f763a9b67db2789de434d47ec7ae1fdc:'+p], cwd=c.ROOT)
        assert (c.ROOT/p).read_bytes() == frozen, p


def test_default_cli_does_not_construct_or_execute(monkeypatch, capsys):
    from scripts import run_s3_no_prior as runner
    monkeypatch.setattr(runner, 'run', lambda *a, **k: pytest.fail('plan started runtime'))
    assert runner.main(['--expected-source-sha', 'a'*40, '--output', '/nonexistent/s3-plan']) == 0
    assert json.loads(capsys.readouterr().out)['no_prior'] == 'off'
    with pytest.raises(ValueError, match='explicit'):
        runner.main(['--expected-source-sha', 'a'*40, '--output', '/nonexistent/s3-plan', '--execute'])


def test_posthoc_does_not_accept_wrong_mode_or_unfinished_commands(tmp_path):
    from scripts.evaluate_s3_no_prior import metrics
    result = dict(status='DEV_NOT_DELIVERED', evaluation={'orders': {
        'order-1': {'complete': True}, 'order-5': {'complete': True}}}, wall_s=10, check_sim_s=1)
    student = dict(localizers={}, pair={'robots': {}})
    for rid in m.ROBOTS:
        path = tmp_path/f'eval_only/{rid}'
        path.mkdir(parents=True)
        (path/'trajectory.jsonl').write_text('\n'.join(json.dumps(dict(t=t, robot_xyz_m=[0, 0, 0],
            robot_yaw_rad=0)) for t in (0., 1.))+'\n')
        student['localizers'][rid] = dict(state='search' if rid == 'r3' else 'done', poses=[
            dict(t=.5, t_est=.34, x=1. if rid == 'r1' else 0., y=0., yaw=0., std_xy_m=.04)])
        student['pair']['robots'][rid] = {'jobs': [dict(kind='pair_carry', confirmation='unconfirmed')]}
    (tmp_path/'result.json').write_text(json.dumps(result))
    (tmp_path/'student_record.json').write_text(json.dumps(student))
    q = metrics(tmp_path)
    assert q['robots']['r1']['first_convergence']['wrong_mode'] is True
    assert q['robots']['r1']['success'] is False
    assert q['robots']['r2']['success'] is True
    assert q['robots']['r3']['delivery_complete'] is True
    assert q['robots']['r3']['success'] is False
    assert q['door_deadlocks'] == []
    student['localizers']['r2']['poses'][0]['convergence_certificate'] = {'qualified': False}
    (tmp_path/'student_record.json').write_text(json.dumps(student))
    assert metrics(tmp_path)['robots']['r2']['first_convergence'] is None


def test_carry_yaw_record_preserves_existing_statistics(monkeypatch):
    from harness import owncam_carry_v6e
    inner = SimpleNamespace(loc=SimpleNamespace(pair_matched=3, pair_unmatched=2),
        carry_yaw_fallback={'level_frames': {'visual': 7}},
        beam_edge=SimpleNamespace(stats={'accepted': 4}, total_rad=.12))
    monkeypatch.setattr(owncam_carry_v6e, '_inner', lambda _: inner)
    team = SimpleNamespace(executors={'r1': SimpleNamespace(pose=None)})
    row = m.carry_yaw_record(team)['r1']
    assert row == dict(partner_plan_matched=3, partner_plan_unmatched=2,
        availability_frames={'visual': 7}, beam_edge={'accepted': 4, 'total_rad': .12})
    row['availability_frames']['visual'] = 0
    assert inner.carry_yaw_fallback['level_frames']['visual'] == 7


def test_referee_height_uses_world_inertial_position_without_clamping(monkeypatch):
    from sim.zone_s3_no_prior import referee_truth
    from scripts.run_zone_study_integration import StudyTeamHost
    from harness.zone_study_referee import Referee, ContractViolation
    row = dict(kind='long_beam', x=1.275, y=.05, yaw=0., z=-.000543678,
        held=False, speed=0.)
    monkeypatch.setattr(StudyTeamHost, 'referee_truth', lambda _: {'beam_1': copy.deepcopy(row)})
    body = SimpleNamespace(xipos=[1.275, .05, .015456322])
    host = SimpleNamespace(objects={'beam_1': {'body_name': 'cargo_beam_1'}},
        world=SimpleNamespace(data=SimpleNamespace(body=lambda _: body)))
    corrected = referee_truth(host)
    assert corrected['beam_1'] == {**row, 'z': .015456322}
    referee = Referee(c.inputs()[2]['orders'], c.hp.resolve(c.old.solo.MAP_ID)[0])
    referee.observe(0., corrected)
    # A truly underground/nonfinite COM is still rejected by the same contract.
    for bad in (-.001, float('nan')):
        body.xipos[2] = bad
        with pytest.raises(ContractViolation):
            referee.observe(1., referee_truth(host))


def test_convergence_certificate_rejects_small_covariance_with_distant_mode():
    from harness.zone_s3_localization_certification import attach, certificate
    from harness.owncam_pose_source import PoseReport
    from dataclasses import replace
    runtime = object()
    assert attach(runtime) is runtime  # default off is an identity operation
    report = PoseReport(t_est=13.75, initialized=True, std_xy_m=.028,
        std_yaw_rad=.012, last_fix_t=13.75,
        observation_quality={'diagnostics': {'pose_estimate': {'cluster_count': 2}}})
    particles = np.array([[0., 0., 0.]]*2000+[[3.5, 0., 0.]])
    before = particles.tobytes()
    row = certificate(report, particles)
    assert row['covariance_ok'] and not row['qualified'] and not row['all_particles_compact']
    assert particles.tobytes() == before and report.std_xy_m == .028
    one = replace(report, observation_quality={'diagnostics': {'pose_estimate': {'cluster_count': 1}}})
    assert certificate(one, particles[:2000])['qualified']
    # One connected but broad global component, absent diagnostics and yaw
    # ambiguity cannot be certified either.
    assert not certificate(one, particles)['qualified']
    assert not certificate(replace(one, observation_quality=None), particles[:2000])['qualified']
    assert not certificate(replace(one, std_yaw_rad=.2), particles[:2000])['qualified']

    log = []
    fake = SimpleNamespace(last_report=one, pose_log=log,
        pose=SimpleNamespace(provider=SimpleNamespace(loc=SimpleNamespace(_pf=SimpleNamespace(px=particles[:2000])))),
        on_frames=lambda now, _: log.append({'t': now}), record=lambda: {'poses': copy.deepcopy(log)})
    attach(fake, localization_certification='posterior_consensus_v1')
    fake.on_frames(14., {})
    assert fake.record()['poses'][0]['convergence_certificate']['qualified']
    assert fake.record()['localization_certification']['distribution_changed'] is False


def test_recorded_camera_rigid_composition_round_trip_and_off_identity():
    from harness.zone_solo_cyan_camera_v3 import camera_calibration
    from harness.zone_s3_recorded_camera import calibration_for_recorded_mount, attach
    original = dict(camera_models={'unloaded': {'pose': dict(frame='optical_to_actual_chassis',
        origin_m=[.1, -.2, .3], rotation=np.eye(3).tolist(),
        chassis_to_floor={'origin_m': [0., 0., .0325], 'rotation': np.eye(3).tolist()})}})
    before = copy.deepcopy(original)
    back = calibration_for_recorded_mount(camera_calibration(original))
    row = back['camera_models']['unloaded']['pose']
    assert np.allclose(row['origin_m'], [.1, -.2, .3], atol=1e-14)
    assert np.allclose(row['rotation'], np.eye(3), atol=1e-14)
    assert original == before and row['chassis_to_floor'] == original['camera_models']['unloaded']['pose']['chassis_to_floor']
    runtime = object()
    assert attach(runtime) is runtime


def test_persistent_v3_binding_survives_real_legacy_refresh_without_physics(monkeypatch):
    import mujoco
    from contextlib import nullcontext
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    from sim import masterpi_camera_review_v3 as v3, masterpi_camera_profile as old
    from sim.s3_camera_binding import attach
    # Real legacy methods, fake arrays: constructor/renderer/physics never run.
    monkeypatch.setattr(mujoco, 'mj_forward', lambda *a: None)
    model = SimpleNamespace(cam_pos=np.zeros((3, 3)), cam_quat=np.zeros((3, 4)),
        cam_resolution=np.zeros((3, 2)), cam_sensorsize=np.zeros((3, 2)),
        cam_intrinsic=np.zeros((3, 4)))
    controllers = {}
    for i, rid in enumerate(m.ROBOTS):
        robot = MasterPiDynamicsV2.__new__(MasterPiDynamicsV2)
        robot.model, robot.data, robot.robot_cam_cid = model, object(), i
        robot.width, robot.height, robot.renderer = 640, 480, None
        robot._configure_measured_robot_camera()
        controllers[rid] = robot
    world = SimpleNamespace(controllers=controllers, physics_lock=nullcontext())
    before = model.cam_pos.tobytes(), model.cam_quat.tobytes()
    assert attach(world) is world and before == (model.cam_pos.tobytes(), model.cam_quat.tobytes())
    assert np.allclose(model.cam_pos, old.CAMERA_LOCAL_POS_M)
    attach(world, camera_binding='v3_persistent_v1')
    for robot in controllers.values():
        robot._configure_measured_robot_camera()
        robot._sync_real_camera_mount()
    assert np.allclose(model.cam_pos, v3.POSITION_M, atol=1e-14)
    assert np.allclose(model.cam_quat, v3.QUAT_WXYZ, atol=1e-14)
