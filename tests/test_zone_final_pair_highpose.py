"""V93 fake/own-pixel regressions; no simulator, renderer or learned model."""
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_contract as c
from harness.zone_pair_highpose_runtime import HighController, Runtime, CommandGuard
from harness.vision_pose_source_final import camera_key
from harness.vision_pose_source_highpose import HighPoseSource
from scripts import run_pair_highpose as run
from tests.test_zone_final_pair_v3 import offline_only, synthetic as old_synthetic, MAPS


def synthetic(tmp_path):
    path, cal = old_synthetic(tmp_path)
    cal.update(schema='ugrp.final_pair_highpose_measured_calibration.v1',
        contract_sha256=c.base.sha(c.ROOT/c.CALIBRATION_CONTRACT),
        loaded_measurement_bundle_id='zone-final-pair-v92', loaded_pose_id=pose.POSE_ID,
        loaded_camera_scope='high_only', loaded_schedule_sha256='c'*64,
        criterion_sha256='d'*64, assembler_sha256='e'*64)
    rec = next(iter(cal['camera_models']['loaded'].values()))
    cal['camera_models']['loaded'] = {camera_key(pose.HIGH): rec}
    run.write(path, cal)
    return path, cal


def test_p03_missing_v92_gate_before_any_output_or_backend(tmp_path, capsys):
    out = tmp_path/'must-not-exist'
    argv = ['--check', 'p03', '--expected-source-sha', 'a'*40, '--output', str(out)]
    assert run.main(argv) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['execution_bundle_id'] == c.BUNDLE_ID
    assert plan['runnable'] is False and plan['blocked_on'] == [c.PRECONDITION]
    assert plan['denominator'] == 3
    assert [r['checkpoint'] for r in plan['cases']] == list(c.previous.CHECKPOINTS)
    assert sum(r['sim_cap_s'] for r in plan['cases']) == 360.
    with pytest.raises(ValueError, match=c.PRECONDITION):
        run.main(argv+['--execute'])
    b = {**c.bundle(MAPS[0], 'p03'), 'source_sha': 'a'*40, 'case': c.cases('p03')[0]}
    with pytest.raises(ValueError, match=c.PRECONDITION):
        run.run_case(b, out, seed=911, backend_factory=lambda *a, **k: pytest.fail('backend started'))
    assert not out.exists()


@pytest.mark.parametrize('mutation', ['v88', 'low_pose', 'floor_camera', 'no_high', 'nan',
                                     'gain', 'schedule', 'criterion', 'status', 'hash'])
def test_wrong_calibration_rejected(tmp_path, mutation):
    path, cal = synthetic(tmp_path)
    digest = c.base.sha(path)
    assert c.measured_calibration(path, digest, MAPS[0]) == cal
    if mutation == 'v88': cal['loaded_measurement_bundle_id'] = 'zone-final-pair-v88'
    elif mutation == 'low_pose': cal['loaded_pose_id'] = 'old_hover'
    elif mutation == 'floor_camera':
        cal['camera_models']['loaded'][camera_key(pose.grasp_postures()[1][-1])] = next(iter(cal['camera_models']['loaded'].values()))
    elif mutation == 'no_high': cal['camera_models']['loaded'] = {}
    elif mutation == 'nan': cal['params']['motion_loaded']['noise_abs'][0] = float('nan')
    elif mutation == 'gain': cal['params']['motion_loaded']['gain'] = [[1., 1., 1.]]*3
    elif mutation in ('schedule', 'criterion'): cal.pop(mutation+'_sha256' if mutation == 'criterion' else 'loaded_schedule_sha256')
    elif mutation == 'status': cal['status'] = 'COLLECTED_UNQUALIFIED'
    elif mutation == 'hash': digest = 'f'*64
    path.write_text(json.dumps(cal))
    if mutation != 'hash': digest = c.base.sha(path)
    with pytest.raises((ValueError, KeyError)):
        c.measured_calibration(path, digest, MAPS[0])


def test_registry_closure_and_workflow():
    from sim import workflow_manager as wm
    b = c.bundle(MAPS[0], 'carry')
    assert b['runnable'] is False and b['weld'] == 'off'
    assert b['timing']['pose_delay_s'] == .16
    assert b['provider_id'] == c.PROVIDER_ID
    for name in ('harness/zone_pair_highpose_runtime.py', 'harness/zone_pair_highpose.py',
                 'harness/vision_pose_source_highpose.py', 'harness/opencv_wall_observation.py',
                 'harness/own_beam_edge.py', 'harness/zone_final_pair_skill.py',
                 'harness/zone_study_pose_delay_p03.py', c.REGISTRY, c.WORKFLOW, c.CALIBRATION_CONTRACT):
        assert b['source_sha256'][name] == c.base.sha(c.ROOT/name)
    row, _ = wm._row(c.ROOT, c.WORKFLOW_ID)
    assert row['version'] == '3.5.0' and row['runner'] == 'scripts.run_pair_highpose'


def test_high_pose_matches_v92_ik_and_reverse_path():
    from harness.visual_arm_v3 import solve_grip_ik, tool_pose
    assert solve_grip_ik(.2032, 0., .15, -40.) == pose.HIGH
    assert solve_grip_ik(.2032, 0., .11, -55.) == pose.VIA_110
    assert solve_grip_ik(.2032, 0., .13, -45.) == pose.VIA_130
    p = tool_pose(pose.HIGH)
    assert abs(p.x_m-.2032) < .001 and abs(p.z_m-.15) < .001
    assert [row[0] for row in pose.lower_path()][:2] == [pose.VIA_130, pose.VIA_110]
    assert pose.required_camera_poses()['loaded'] == [pose.HIGH]


class LowLift:
    def set(self, state, now, **kw): self.state, self.state_t = state, now

    def _lift(self, now, idle):
        if idle:
            self.set('wait_carry', now)  # stand-in for inherited low-view RGB success


class FakeController(HighController, LowLift):
    def __init__(self):
        from scripts.zone_teacher import ArmSequence
        self.events, self.commands = [], []
        self.rid, self.seg, self.state = 'r1', 0, 'lift'
        self.port = SimpleNamespace(apply=lambda a, t: self.commands.append((t, a)))
        self.arm = ArmSequence(self.port, {1: 1500, **pose.grasp_postures()[0]})

    def fail(self, reason, now): self.failure = reason; self.set('failed', now)
    def _wait(self, key, nxt, now, go): go(now); self.set(nxt, now)
    def look(self, now): return {'image': 'fake', 'actuator_state': {'servo_pulses': self.arm.commanded}}
    def pose_of(self, obs): return obs['actuator_state']['servo_pulses']
    def log(self, *a, **kw): self.events.append((a, kw))


def test_low_lift_raise_high_own_view_then_reverse_lower(monkeypatch):
    from harness import zone_pair_highpose_runtime as h
    ctl = FakeController()
    ctl._lift(2., False)
    assert not ctl.arm.events
    ctl._lift(2., True)
    assert ctl.state == 'lift' and ctl.high_raising and not ctl.high_ready
    assert ctl.arm.until == pytest.approx(19.2)
    assert pose.at_high(ctl.arm.commanded) and ctl.arm.commanded[1] == 1500
    ctl._lift(3., False)
    assert not ctl.events
    monkeypatch.setattr(h.m2.study.ob, 'decode', lambda image: np.zeros((480, 640, 3), np.uint8))
    monkeypatch.setattr(h, 'edge_line', lambda rgb: (0., 170., 90))
    monkeypatch.setattr(h.m2.study.ob, 'held_signature', lambda image: 'HIGH-own-anchor')
    monkeypatch.setattr(h.m2.hv3, 'hold_view_mask', lambda image: 'HIGH-own-full')
    ctl.arm.tick(19.2)
    ctl._lift(19.2, True)
    assert ctl.state == 'wait_carry' and ctl.high_ready
    assert ctl.anchor == 'HIGH-own-anchor' and ctl.anchor_full == 'HIGH-own-full'
    ctl._wait_lower(20., True)
    assert ctl.state == 'lower' and not ctl.high_ready
    assert ctl.arm.commanded == {1: 1500, **pose.grasp_postures()[1][-1]}
    assert all(e[2] == 1500 for e in ctl.arm.events if e[1] == 1)


def test_high_frame_missing_edge_fails(monkeypatch):
    from harness import zone_pair_highpose_runtime as h
    ctl = FakeController(); ctl._lift(0., True); ctl.arm.tick(ctl.arm.until)
    monkeypatch.setattr(h.m2.study.ob, 'decode', lambda image: np.zeros((480, 640, 3), np.uint8))
    monkeypatch.setattr(h, 'edge_line', lambda rgb: None)
    ctl._lift(20., True)
    assert ctl.failure == 'HIGH_CARRY_EDGE_NOT_SEEN'


def test_opencv_real_provider_no_model_and_transit_skip(tmp_path):
    path, _ = synthetic(tmp_path)
    provider = HighPoseSource(c.resolve(MAPS[0])[0], path, c.base.sha(path))
    assert provider.worker.record()['learned_segmentation'] is False
    provider.init_prior((1., 0., 0.), (.1, .1, .1), source='synthetic public dock')
    floor = pose.grasp_postures()[1][-1]
    provider.on_command({'kind': 'initial_servo_command', 't': 0., 'pulses': {1: 2000, **floor}})
    provider.on_command({'kind': 'arm', 't': .1, 'servo_id': 1, 'pulse': 1500})
    assert provider.loc.load.loaded
    provider.on_frame(2., np.zeros((480, 640, 3), np.uint8))
    assert provider.failure is None and provider.counts['worker_calls'] == 0
    for sid, pulse in pose.HIGH.items():
        provider.on_command({'kind': 'arm', 't': 3., 'servo_id': sid, 'pulse': pulse})
    provider.on_frame(10., np.zeros((480, 640, 3), np.uint8))
    assert provider.counts['worker_calls'] == 0
    provider.on_frame(12., np.zeros((480, 640, 3), np.uint8))
    assert provider.counts['worker_calls'] == 1 and provider.failure is None
    pf = provider.loc._pf
    before = pf.px.copy()
    provider.begin_relocalization(12., provider.servo)
    assert provider.loc._pf is pf
    np.testing.assert_array_equal(pf.px, before)
    provider.on_frame(11., np.zeros((480, 640, 3), np.uint8))
    assert provider.counts['rejected_frames'] == 1 and provider.counts['worker_calls'] == 1
    provider.close()


def test_runtime_selects_highpose_opencv_team(tmp_path):
    path, _ = synthetic(tmp_path)
    runtime = Runtime(c.resolve(MAPS[0])[0], path, c.base.sha(path), seed=911)
    try:
        assert type(runtime.team).__module__ == 'harness.zone_pair_highpose_runtime'
        for provider in runtime.providers.values():
            assert isinstance(provider.provider, HighPoseSource)
            assert provider.delay['effective_sim_s'] == .16
    finally:
        runtime.close()


def test_loaded_motion_outside_high_rejected_before_parent(monkeypatch):
    from harness.zone_pair_highpose_runtime import PreviousGuard
    guard = object.__new__(CommandGuard)
    reasons = []
    guard.ep = SimpleNamespace(own=SimpleNamespace(servo=pose.grasp_postures()[0]),
                              abort=lambda now, reason: reasons.append(reason))
    monkeypatch.setattr(CommandGuard, 'carrying_beam', property(lambda self: True))
    monkeypatch.setattr(PreviousGuard, 'check', lambda *a: pytest.fail('unmeasured loaded motion reached parent'))
    assert guard.check(1., [{'kind': 'mecanum', 'forward': .01}]) == [{'kind': 'hold'}]
    assert reasons == ['LOADED_BASE_MOTION_REQUIRES_HIGH']


def test_managed_v93_case_ignores_eval_truth_and_preserves_p03_clock(tmp_path):
    from tests.test_zone_final_pair_v3 import FakePhysics, FakeRuntime
    path, _ = synthetic(tmp_path)
    case = c.cases('p03')[0]
    b = {**c.bundle(case['map_id'], 'p03'), 'case': case, 'source_sha': 'a'*40}
    receipts = []
    for value in (False, True):
        owners = []
        def backend(*a, **kw):
            obj = FakePhysics(*a, **kw)
            obj.truth = {'success': value, 'pose': [1e9 if value else -1e9]*3}
            owners.append(obj)
            return obj
        result = run.run_case(b, tmp_path/str(value), seed=911, backend_factory=backend,
            runtime_factory=FakeRuntime, calibration=path, calibration_sha=c.base.sha(path))
        obj = owners[0]
        assert result['protocol_complete'] and result['physical_success'] is None
        assert result['checkpoint']['status'] == 'NOT_REACHED'
        assert len(obj.frames) == len(obj.samples) == 2401
        assert obj.now == obj.deadline == 121. and obj.closed
        receipts.append(obj.actions)
    assert receipts[0] == receipts[1]


def test_classical_opencv_observation_rejects_multiple_bands_and_coloured_occlusion():
    from harness import vision_loc_protocol as vp
    from harness.opencv_wall_observation import observations
    vl, _ = vp.load_vis3()
    scan = SimpleNamespace(columns=np.array([100, 200, 300]),
        vb=np.array([[250., np.nan], [250., 100.], [250., np.nan]]),
        vt=np.array([[100., np.nan], [100., 50.], [100., np.nan]]))
    proxy = SimpleNamespace(mp=SimpleNamespace(undistort=lambda bgr: bgr,
        detect_boundaries=lambda *a: scan), EDGE=vl.EDGE, ColumnObs=vl.ColumnObs)
    bgr = np.full((480, 640, 3), 100, np.uint8)
    bgr[130:190, 295:305] = [0, 255, 0]
    obs = observations(proxy, bgr, object())
    assert obs.informative.tolist() == [True, False, False]
    assert obs.b_lo[0] == obs.b_hi[0] == 250.
