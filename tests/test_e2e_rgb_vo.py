"""rgb_vo_v1 contracts on synthetic own-camera floor images; no simulator/provider."""
import hashlib
import math
from pathlib import Path
import cv2
import numpy as np
import pytest
from harness import e2e_rgb_vo as vo
from harness.e2e_stall_odometry import Options, VO, RECOVERY, NOISE
from harness.self_pulse_rotation import RotationPulseOdometry
from harness.active_camera import SEARCH, transform

RES = .002;X0, Y0 = -.5, -2.


def texture():
    # Coarse patches (4-8 cm), like floor tiles/tape rather than fine aliasing noise.
    rng = np.random.default_rng(3);im = np.full((2000, 2000), 110, np.uint8)
    for x, y in rng.integers(0, 1990, size=(900, 2)):
        w, h = rng.integers(20, 40, size=2)
        cv2.rectangle(im, (int(x), int(y)), (int(x+w), int(y+h)), int(rng.integers(40, 230)), -1)
    return cv2.GaussianBlur(im, (5, 5), 0)


TEX = texture()


def render(pose, servo=SEARCH, noise_seed=None):
    """Own fisheye view of a textured floor for a robot pose (x, y, yaw) in the texture frame."""
    ys, xs = np.mgrid[0:480, 0:640].astype(np.float64)
    g, depth = vo.ground(servo, np.column_stack((xs.ravel(), ys.ravel())))
    c, s = math.cos(pose[2]), math.sin(pose[2])
    wx = pose[0]+c*g[:, 0]-s*g[:, 1];wy = pose[1]+s*g[:, 0]+c*g[:, 1]
    mx = ((wx-X0)/RES).reshape(480, 640).astype(np.float32);my = ((wy-Y0)/RES).reshape(480, 640).astype(np.float32)
    bad = ~np.isfinite(mx)|~np.isfinite(my);mx[bad] = -1;my[bad] = -1
    gray = cv2.remap(TEX, mx, my, cv2.INTER_LINEAR, borderValue=128)
    if noise_seed is not None:  # fresh renders are never byte-identical
        gray = np.clip(gray+np.random.default_rng(noise_seed).normal(0, 1.5, gray.shape), 0, 255).astype(np.uint8)
    return np.dstack([gray]*3)


def test_ground_inverts_the_fisheye_camera_projection():
    origin, rotation = transform(SEARCH)
    floor = np.array([[.6, .1, 0.], [1.0, -.3, 0.], [.4, 0., 0.]])
    cam = (floor-origin)@np.asarray(rotation)  # base -> camera coordinates
    uv, _ = cv2.fisheye.projectPoints(cam.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), vo.K, vo.D)
    back, depth = vo.ground(SEARCH, uv.reshape(-1, 2))
    np.testing.assert_allclose(back, floor[:, :2], atol=1e-6)
    assert (depth > 0).all()


@pytest.mark.parametrize('delta', [(.013, 0., 0.), (0., 0., .1), (.004, .002, -.02)])
def test_ground_pair_recovers_metric_se2_motion(delta):
    out = vo.ground_pair(render((0., 0., 0.)), render(delta), SEARCH)
    assert out['status'] == 'measured', out
    np.testing.assert_allclose(out['delta'][:2], delta[:2], atol=.0015)
    assert abs(out['delta'][2]-delta[2]) < .004
    assert np.all(np.linalg.eigvalsh(np.asarray(out['covariance'])) > 0)


def test_unknown_is_never_zero_motion():
    im = render((0., 0., 0.))
    assert vo.ground_pair(im, im.copy(), SEARCH)['status'] == 'unknown_identical_rgb'
    blank = np.full_like(im, 120);other = blank.copy();other[0, 0] = 121
    assert vo.ground_pair(blank, other, SEARCH)['status'].startswith('unknown_')


def test_fuse_keeps_consistent_command_and_replaces_on_chi_square_failure():
    Q = np.diag([4e-7, 1.7e-6, 1.4e-5]);R = np.diag([1e-6, 1e-6, 1e-6])
    x, P, nis, how = vo.fuse([.013, 0, 0], Q, [.0125, 0, .001], R)
    assert how == 'fused' and nis < vo.PARAMS['chi2_gate'] and abs(x[0]-.013) < .0005
    assert np.all(np.diag(P) <= np.diag(Q)+1e-15)
    x, P, nis, how = vo.fuse([.013, 0, 0], Q, [0., 0., 0.], R)
    assert how == 'vo_replaced' and nis > vo.PARAMS['chi2_gate']
    np.testing.assert_allclose(x, 0.);np.testing.assert_allclose(P, R)


def pulse(t):
    return dict(t=t, kind='mecanum', forward=.35, left=0., turn=0., duration_s=.1)


def run(observed_delta, frames=8):
    """Driver path used live: VO plan is injected through motion_filter only."""
    d = RotationPulseOdometry();d.command(dict(t=0., kind='initial_servo_command', pulses=SEARCH))
    f = vo.VOFusion(d);active = [False]
    d.motion_filter = lambda delta, var: f.motion_filter(delta, var) if active[0] else (delta, var)
    pose = np.zeros(3);rows = []
    for i in range(frames):
        t = i*.2;pose = vo.compose(pose, observed_delta) if i else pose
        rows.append(f.observe(t=t, frame_id=i, rgb=render(pose, noise_seed=i), servo=SEARCH, sha256=str(i)))
        active[0] = True
        try:
            d.advance(t)
        finally:
            active[0] = False;f.finish_interval()
        f.command(pulse(t));d.command(pulse(t))
    return d, f, rows


def test_stall_is_corrected_through_motion_filter_and_nominal_keeps_running():
    d, f, rows = run((0., 0., 0.))  # rendered robot does not move; commands keep pulsing
    measured = [r for r in rows if r['status'] == 'measured']
    assert measured and all(r['fusion'] == 'vo_replaced' for r in measured)
    # Two camera-settle intervals keep the command (never zero); the rest follow VO.
    assert [r['status'] for r in rows[1:3]] == ['unknown_camera_settling']*2
    assert f.nominal.pose[0] > .08 and abs(d.pose[0]-2*.012917) < .003
    assert f.counts['substep_mismatch'] == 0


def test_normal_motion_stays_near_command():
    d, f, rows = run((.0129, 0., 0.))
    assert abs(d.pose[0]-f.nominal.pose[0]) < .01 and f.counts['substep_mismatch'] == 0


def test_options_and_camera_settle_and_servo_change():
    assert Options(VO).enabled
    for bad in (dict(stall_recovery=RECOVERY), dict(stall_noise=NOISE)):
        with pytest.raises(ValueError):
            Options(VO, **bad)
    d = RotationPulseOdometry();d.command(dict(t=0., kind='initial_servo_command', pulses=SEARCH))
    f = vo.VOFusion(d);im = render((0., 0., 0.))
    assert f.observe(t=0., frame_id=1, rgb=im, servo=SEARCH)['status'] == 'no_previous_frame'
    assert f.observe(t=.2, frame_id=2, rgb=render((.01, 0, 0)), servo=SEARCH)['status'] == 'unknown_camera_settling'
    other = {**SEARCH, 6: 1550}
    assert f.observe(t=.4, frame_id=3, rgb=im, servo=other)['status'] == 'unknown_servo_change'
    with pytest.raises(ValueError):
        f.observe(t=.4, frame_id=3, rgb=im, servo=other)


def test_bundle_registers_v201_and_source():
    from scripts.run_e2e_ownmap_live import bundle
    from sim.workflow_manager import catalog
    b = bundle('a'*40, 61001, 'study_gemma4_31b_v1', enabled=True, path_follow='rpp_v1', stall_odometry=VO)
    assert b['execution_bundle_id'] == 'e2e-rgb-vo-v201' and b['e2e_options']['stall_odometry'] == VO
    assert 'harness/e2e_rgb_vo.py' in b['source_sha256']
    rows, _ = catalog(Path('.'))
    assert any(w['id'] == 'e2e-rgb-vo-v201' and w['version'] == '7.94.0' for w in rows['workflows'])
    off = bundle('a'*40, 61001, 'study_gemma4_31b_v1', enabled=True, path_follow='rpp_v1')
    assert off['execution_bundle_id'] != 'e2e-rgb-vo-v201' and 'stall_odometry' not in off['e2e_options']


@pytest.mark.parametrize('measured', [True, False])
def test_live_robot_wiring_feeds_driver_and_rbpf_cloud(monkeypatch, measured):
    """Real make_goal/install path: VO increment reaches the driver AND the RBPF particles."""
    import base64, json
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options as Study
    result = dict(status='measured', tracks=40, inliers=40, cells=6,
        delta=[0., 0., 0.], covariance=(np.eye(3)*1e-8).tolist(), fit_rms_m=0.) if measured else dict(status='unknown_texture')
    monkeypatch.setattr(vo, 'ground_pair', lambda *a: result)
    cov = json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    r = Robot('r1', 61001, cov, Study(), exploration_progress='frontier_progress_v1',
              pose_fix='innovation', path_follow='rpp_v1', stall_options=Options(VO))
    view = r.goal._pose_continuity_view;assert hasattr(r.goal, 'e2e_vo') and not hasattr(r.goal, 'e2e_stall')
    for i in range(10):
        rgb = np.zeros((480, 640, 3), np.uint8);_, data = cv2.imencode('.jpg', rgb);data = data.tobytes()
        trace = r.receive(dict(frame_id=i+1, sim_time=i*.2, sha256=hashlib.sha256(data).hexdigest(),
                               image=base64.b64encode(data).decode()), rgb)
        if i < 9:
            r.commanded({k: v for k, v in pulse(i*.2).items() if k != 't'}, i*.2)
            # A real scheduler stops a 100 ms pulse between the 5 Hz RGB frames.
            # This must not integrate half of the interval before VO is available.
            r.commanded(dict(kind='hold'), i*.2+.1)
    row = trace['stall_odometry']
    assert row['options']['stall_odometry'] == VO
    assert r.goal.e2e_vo.nominal.pose[0] > .08
    if measured:
        assert row['status'] == 'measured' and row['fusion'] == 'vo_replaced'
        assert abs(view.base.driver.pose[0]) < .03  # only camera-settle intervals kept the command
        assert np.abs(view.base.owner.poses[:, 0]).max() < .06
        assert row['fusion_applied']
    else:
        assert row['status'] == 'unknown_texture' and row['fusion'] == 'command_kept'
        np.testing.assert_allclose(view.base.driver.pose, r.goal.e2e_vo.nominal.pose, atol=1e-12)
    assert r.goal.e2e_vo.counts['substep_mismatch'] == 0
    assert row['command_substeps'] == 4


@pytest.mark.parametrize('n', [0, 1])
def test_ground_accepts_zero_and_one_point(n):
    pts, depth = vo.ground(SEARCH, np.full((n, 2), [320., 400.]))
    assert pts.shape == (n, 2) and depth.shape == (n,)


def test_opencv_none_is_unknown_not_crash_or_zero(monkeypatch):
    """E2E14 v202: cv2.fisheye.undistortPoints returned None -> AttributeError in observe."""
    monkeypatch.setattr(vo.cv2.fisheye, 'undistortPoints', lambda *a, **k: None)
    pts, depth = vo.ground(SEARCH, np.array([[320., 400.], [300., 420.]]))
    assert np.isnan(pts).all() and np.isnan(depth).all()
    out = vo.ground_pair(render((0., 0., 0.)), render((.01, 0., 0.)), SEARCH)
    assert out['status'].startswith('unknown_') and 'delta' not in out


@pytest.mark.parametrize('n', [0, 1])
def test_few_tracked_points_keep_command_increment(monkeypatch, n):
    real = vo.cv2.goodFeaturesToTrack
    monkeypatch.setattr(vo.cv2, 'goodFeaturesToTrack',
                        lambda *a, **k: None if n == 0 else real(*a, **k)[:n])
    d, f, rows = run((0., 0., 0.), frames=5)
    assert all(r['status'].startswith('unknown_') or r['status'] == 'no_previous_frame' for r in rows)
    assert all(r['fusion'] == 'command_kept' for r in rows[1:])
    np.testing.assert_allclose(d.pose, f.nominal.pose, atol=1e-12)  # identical to off


def run_v2(monkeypatch, gate_status, frames=10):
    import harness.e2e_stall_odometry as stall
    monkeypatch.setattr(vo, 'ground_pair', lambda *a: dict(status='unknown_texture', tracks=0, inliers=0, cells=0))
    monkeypatch.setattr(stall, 'flow_pair', lambda *a: dict(status=gate_status, tracks=30, cells=6,
        median_px=0., p90_px=0., mean_abs_diff=0.))
    d = RotationPulseOdometry();d.command(dict(t=0., kind='initial_servo_command', pulses=SEARCH))
    f = vo.VOFusion(d, fallback='pulse_gate');active = [False]
    d.motion_filter = lambda delta, var: f.motion_filter(delta, var) if active[0] else (delta, var)
    rows = []
    for i in range(frames):
        t = i*.2
        rows.append(f.observe(t=t, frame_id=i, rgb=render((0., 0., 0.), noise_seed=i), servo=SEARCH, sha256=str(i)))
        active[0] = True
        try:
            d.advance(t)
        finally:
            active[0] = False;f.finish_interval()
        f.command(pulse(t));d.command(pulse(t))
    return d, f, rows


def test_v2_gate_zeroes_translation_and_inflates_covariance_when_vo_unknown(monkeypatch):
    d, f, rows = run_v2(monkeypatch, 'stationary_view')
    zero = [r for r in rows if r['fusion'] == 'gate_zero']
    assert zero and f.counts['gate_zero'] == len(zero) and f.counts['substep_mismatch'] == 0
    assert all(r['fused_delta'][:2] == [0., 0.] for r in zero)
    assert all(r['fused_variance'][0] > 4e-7 for r in zero)  # inflated above the calibrated pulse variance
    assert d.pose[0] < f.nominal.pose[0]-.05


def test_v2_keeps_command_when_gate_also_cannot_decide(monkeypatch):
    d, f, rows = run_v2(monkeypatch, 'unknown_texture')
    assert f.counts['gate_zero'] == 0 and all(r['fusion'] == 'command_kept' for r in rows[1:])
    np.testing.assert_allclose(d.pose, f.nominal.pose, atol=1e-12)


def test_v2_option_contract_and_no_standalone_bundle():
    from harness.e2e_stall_odometry import VO2
    from scripts.run_e2e_ownmap_live import bundle
    assert Options(VO2).enabled and vo.OPTION_V2 == VO2
    with pytest.raises(ValueError):
        Options(VO2, stall_recovery=RECOVERY)
    with pytest.raises(ValueError, match='RGB_VO_V2_HAS_NO_STANDALONE_BUNDLE'):
        bundle('a'*40, 61001, 'study_gemma4_31b_v1', enabled=True, path_follow='rpp_v1', stall_odometry=VO2)


def test_v2_live_install_dispatch():
    import base64, json
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options as Study
    from harness.e2e_stall_odometry import VO2
    cov = json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    r = Robot('r1', 61001, cov, Study(), exploration_progress='frontier_progress_v1',
              pose_fix='innovation', path_follow='rpp_v1', stall_options=Options(VO2))
    assert r.goal.e2e_vo.fallback == 'pulse_gate'
    rgb = np.zeros((480, 640, 3), np.uint8);_, data = cv2.imencode('.jpg', rgb);data = data.tobytes()
    trace = r.receive(dict(frame_id=1, sim_time=0., sha256=hashlib.sha256(data).hexdigest(),
                           image=base64.b64encode(data).decode()), rgb)
    assert trace['stall_odometry']['options']['stall_odometry'] == VO2 and 'gate' in trace['stall_odometry']
