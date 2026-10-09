"""#403 offline controller/optics regressions. Never starts a simulator."""
import copy
import numpy as np
import pytest

from test_solo_cyan_v106 import (static, cal, FakePose, FakeVision, observation,
                                 rt, c, grasp_postures)
from harness import zone_solo_cyan_camera_v3 as candidate


def make(static, cal, **options):
    return candidate.Runtime(static, None, None,
        provider_factory=lambda *a, **kw: FakePose(cal), vision_factory=FakeVision, **options)


def carry(runtime):
    runtime.initial_commands(0., {'r3': {1: 1500, **rt.high.HIGH}})
    runtime.last_report = runtime.pose.report(1.)
    runtime.last_report.last_fix_t = .25
    runtime.state, runtime.receipt = 'carry', True
    runtime.drive = lambda *a, **kw: ([{'kind': 'hold'}], True)


def test_default_matches_frozen_v106(static, cal):
    old = rt.Runtime(static, None, None,
        provider_factory=lambda *a, **kw: FakePose(cal), vision_factory=FakeVision)
    new = make(static, cal)
    try:
        for r in (old, new):
            carry(r)
            r._control(1., True)
        assert new.record() == old.record()
        assert new.state == 'lower' and new.regrasp and new.route_i == 0
    finally:
        old.close()
        new.close()


@pytest.mark.parametrize('option,profile', [('off', None), ('bad', None), ('on', 'wrong')])
def test_option_rejects_implicit_or_unknown_profile(option, profile):
    with pytest.raises(ValueError):
        candidate.option_record(option, profile)


def test_off_skips_all_checkpoints_but_keeps_final_release(static, cal):
    r = make(static, cal, setdown_relook='off', camera_profile=candidate.camera.PROFILE_ID)
    try:
        carry(r)
        queued = []
        r.queue = lambda target, now, **kw: queued.append(target)
        for i in range(len(r.route)):
            r._control(1.+i, True)
            assert r.route_i == i+1
            assert r.last_report.last_fix_t == .25
            assert not r.regrasp and not r.relooked and not r.pose.relooks
            if i < len(r.route)-1:
                assert r.state == 'carry' and queued == []
        assert r.state == 'lower'
        assert queued and all(p[1] == 1500 for p in queued)
        r._control(5., True)
        assert r.state == 'released' and any(p[1] == 2000 for p in queued)
        r._control(6., True)
        assert r.state == 'done' and not r.pose.relooks
        rec = r.record()
        assert rec['setdown_relook']['skipped_indexes'] == [0, 1, 2]
        assert rec['physical_success'] is None
    finally:
        r.close()


def test_carry_receipt_does_not_require_visible_cyan_and_stale_image_still_fails(static, cal):
    r = make(static, cal, setdown_relook='off', camera_profile=candidate.camera.PROFILE_ID)
    try:
        carry(r)
        r.vision.detect = lambda *a: pytest.fail('carry must not infer grasp from cyan visibility')
        obs, rgb = observation(1.)  # valid grayscale wall, zero cyan pixels
        r.on_frames(1., {'r3': (obs, rgb)})
        assert r.failure is None and r.beam_grasp_confirmed
        assert r.pose.frames == [(480, 640, 3)]
        r.on_frames(3., {'r3': (obs, rgb)})
        assert r.failure == 'INVALID_OWN_IMAGE'
    finally:
        r.close()


def test_rigid_camera_composition_and_input_immutability(cal):
    before = copy.deepcopy(cal)
    derived = candidate.camera_calibration(cal)
    assert cal == before
    old_r = candidate.quat_matrix(candidate.archived.CAMERA_LOCAL_QUAT_WXYZ) @ np.diag([1., -1., -1.])
    new_r = candidate.quat_matrix(candidate.camera.QUAT_WXYZ) @ np.diag([1., -1., -1.])
    for state, table in cal['camera_models'].items():
        for key, rec in table.items():
            a = np.eye(4)
            a[:3, :3], a[:3, 3] = rec['rotation'], rec['origin_m']
            old_mount, new_mount = np.eye(4), np.eye(4)
            old_mount[:3, :3], old_mount[:3, 3] = old_r, candidate.archived.CAMERA_LOCAL_POS_M
            new_mount[:3, :3], new_mount[:3, 3] = new_r, candidate.camera.POSITION_M
            expected = a @ np.linalg.inv(old_mount) @ new_mount
            got = derived['camera_models'][state][key]
            np.testing.assert_allclose(got['rotation'], expected[:3, :3], atol=1e-12)
            np.testing.assert_allclose(got['origin_m'], expected[:3, 3], atol=1e-12)
    assert derived['params'] == cal['params']


def test_off_still_requires_visible_support_before_closing(static, cal):
    r = make(static, cal, setdown_relook='off', camera_profile=candidate.camera.PROFILE_ID)
    try:
        r.initial_commands(0., {'r3': {1: 2000, **grasp_postures()[0]}})
        r.last_report = r.pose.report(1.)
        r.state, r.state_t, r.target_t = 'hover', 0., 0.
        r.target, r.last_obs = [rt.GRASP_RADIUS_M, 0.], {'frame_id': 1}
        r.arm.until = 0.
        r.vision.hover_support = lambda *a: False
        r._control(rt.blind.HOVER_CONFIRM_MAX_S+1., True)
        assert r.failure == 'CYAN_HOVER_UNCONFIRMED'
        assert not r.receipt and r.servo[1] == 2000
    finally:
        r.close()


def test_real_provider_uses_v3_rays_and_own_command_prediction(static):
    new = candidate.build_provider(static, c.ROOT/c.CALIBRATION, c.CALIBRATION_SHA)
    old = rt.build_provider(static, c.ROOT/c.CALIBRATION, c.CALIBRATION_SHA)
    try:
        inner, pf = new.provider, new.provider.loc._pf
        assert new.source == inner.source != old.source
        servo = {**rt.pose_of('search'), 1: 2000}
        a, b = pf.column_model_for(servo), old.provider.loc._pf.column_model_for(servo)
        assert not np.allclose(a.q0, b.q0)
        assert 'camera_v3_derivation' not in old.provider.calibration
        assert inner.carry_yaw_fallback is None and pf.pair_plan is None
        new.init_prior((-.7, -.85, 0.), (.1, .5, .1), source='test public region')
        floor = {**grasp_postures()[1][-1], 1: 2000}
        new.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': floor})
        new.on_command({'t': .2, 'kind': 'arm', 'servo_id': 1, 'pulse': 1500})
        before = new.on_frame(.5, None)
        new.on_command({'t': .6, 'kind': 'mecanum', 'forward': .06, 'left': 0., 'turn': 0., 'duration_s': 1.})
        after = new.on_frame(1.5, None)
        assert pf.load.loaded and after.x_m > before.x_m
        assert after.last_fix_t is None and after.t_est == pytest.approx(1.34)
        assert inner.failure is None
    finally:
        new.close()
        old.close()


def test_offline_cli_has_no_execute(capsys):
    candidate.main(['--setdown-relook', 'off', '--camera-profile', candidate.camera.PROFILE_ID])
    assert '"runtime_admitted": false' in capsys.readouterr().out
    with pytest.raises(SystemExit):
        candidate.main(['--execute'])
