"""release17 regressions: no simulator, renderer or network."""
import math

import numpy as np
import pytest

from sim import release14, release15, release16, release17 as new
from sim.lookaround_localization import Camera, rotate_plan
from sim.visible_belief import odometry, rates
from tests.test_grasp_act_release_run import fake_backend  # noqa: F401  (pytest fixture)
from tests.test_release15 import near_wall, top_fragment
from tests.test_release_regrasp import teachers


def aligner(*, fov_step='off', profile='native_yaw_v1'):
    t = teachers()['r1']; t.odometry_profile = profile
    issued = []; scheduled = []; loc = near_wall()
    loc.own.x[:2] = [4.6, .4]
    a = new.LineAlign(t, 0., camera=Camera(), undistort=lambda f: f,
                      wheel_command=lambda *v: issued.append(v), clearance=lambda *v: new.map_motion_clear(loc, *v),
                      fov_step=fov_step)
    def schedule(rid, seq, now): scheduled.extend((now+dt, p) for dt, p in seq)
    def tick(now, image):
        while scheduled and scheduled[0][0] <= now+1e-8:
            _, p = scheduled.pop(0); t.pwm.update(p)
        return a.tick(now, lambda *v: image, schedule)
    tick(0., None); tick(1.2, None)
    return a, t, issued, tick


def shifted_fragment(bottom):
    im = np.full((480, 640, 3), 60, np.uint8)
    im[13:bottom, 220:365] = [5, 220, 150]
    im[13:40, 220:365] = [153, 242, 5]
    return im


def test_yaw_cal_profile_sign_magnitude_and_native_preserved():
    assert rates('native_yaw_v1') == (.129, .08, -.35)        # byte-for-byte kept for replay
    assert rates('yaw_cal_v1') == pytest.approx((.129, .08, 3.0*.35))
    ccw = [-.35, .35, -.35, .35]                               # Y>0: counter-clockwise (M1)
    assert odometry(ccw, .1, 'yaw_cal_v1')[2] == pytest.approx(3.0*.035)
    assert odometry(ccw, .1, 'native_yaw_v1')[2] == pytest.approx(-.035)
    for degrees in (90, -90, 45, 180):
        plan = rotate_plan(math.radians(degrees), 'yaw_cal_v1')
        assert sum(odometry([w*d/.1 for w, d in zip(*p)], .1, 'yaw_cal_v1')[2] for p in plan) == pytest.approx(math.radians(degrees), abs=1e-6)
        assert all(max(p[1]) <= .15 and max(map(abs, p[0])) <= .35 for p in plan)
    assert len(rotate_plan(math.pi/2, 'yaw_cal_v1')) == 15 and len(rotate_plan(math.pi/2, 'native_yaw_v1')) == 45
    assert math.copysign(1, rotate_plan(.3, 'yaw_cal_v1')[0][0][1]) == 1.       # CCW needs (-,+,-,+)
    assert rotate_plan(math.pi/2) == rotate_plan(math.pi/2, 'off')


def test_validate_keeps_toggles_independent_and_off_by_default():
    plan = {'end_color_scene': 'grasp_act_teal_blue_v1'}
    opts = dict(release14.SAFE)
    for motion in ('native_yaw_v1', 'yaw_cal_v1'):
        for step in ('off', new.FOV_STEP):
            new.validate(new.PROFILE, False, {**opts, 'command_motion': motion, 'release_fov_step': step}, plan)
    with pytest.raises(ValueError):
        new.validate(new.PROFILE, False, {**opts, 'command_motion': 'off'}, plan)
    with pytest.raises(ValueError):
        new.validate(new.PROFILE, False, {**opts, 'release_fov_step': 'bogus'}, plan)
    for other in ('off', release14.PROFILE, release15.PROFILE, release16.PROFILE):
        with pytest.raises(ValueError):
            new.validate(other, False, {**opts, 'release_fov_step': new.FOV_STEP}, plan)
        if other != 'off':
            with pytest.raises(ValueError):
                new.validate(other, False, {**opts, 'command_motion': 'yaw_cal_v1'}, plan)
        new.validate(other, False, {**opts, 'release_fov_step': 'off'}, plan) if other != 'off' else None
    assert new.PROFILES[-1] == new.PROFILE and new.PROFILES[:-1] == release16.PROFILES


def test_recovery_step_is_one_real_pulse_and_prediction_uses_realized_motion():
    for period, expected in ((.1, .0129), (.15, .01935)):
        wheels, durations = new.recovery_pulse(expected, 0., 'native_yaw_v1', period)
        assert wheels == [.35]*4 and durations == pytest.approx([period]*4)
        assert odometry([w*d/.1 for w, d in zip(wheels, durations)], .1, 'native_yaw_v1')[0] == pytest.approx(expected)
    candidates = new.recovery_candidates('native_yaw_v1', .1)
    assert len(candidates) == 8 and all(max(d) <= .1+1e-9 for _, d, _ in candidates)
    diagonal = candidates[-1]                                   # shared wheels: half of each axis request
    assert diagonal[2] == pytest.approx((.00645, .004))
    assert max(max(d) for _, d, _ in new.recovery_candidates('native_yaw_v1', .15)) <= .15+1e-9


def test_clipped_top_gets_single_pulse_while_release15_micro_pulse_is_unchanged():
    f = release15.line_features(top_fragment(), 'teal')
    camera = Camera(); pwm = aligner()[1].pwm
    old = release15.line_step(f, camera, pwm, clearance=lambda *a: True)
    step = new.line_step(f, camera, pwm, clearance=lambda *a: True)
    assert old['kind'] == step['kind'] == 'recover_fov' and old['forward'] == pytest.approx(.004)
    assert step['forward'] == pytest.approx(.0129) and step['durations'] == pytest.approx([.1]*4)
    assert step['predicted_merit'] < step['merit']
    # An unsafe predicted crossing is never attempted: same fov_blocked failure as release15.
    assert new.line_step(f, camera, pwm, clearance=lambda *a: False)['kind'] == 'fov_blocked'


def test_clipped_edges_use_usable_region_boundary_not_object_end():
    box = [220., 13., 364., 134.]
    assert new.clipped_edges(box) == (False, True, False, False)
    assert new.clipped_edges([5., 100., 300., 300.])[0] is True


def test_edge_progress_separates_real_motion_from_plateau_and_stall():
    camera = Camera(); pwm = aligner()[1].pwm
    f = release15.line_features(top_fragment(), 'teal'); box = f['visible_box_px']
    moved = release15.line_features(shifted_fragment(165), 'teal')
    still = release15.line_features(top_fragment(), 'teal')
    motion = (.0129, 0., 0.)
    assert new.edge_progress(box, f['points'], moved['visible_box_px'], motion, camera, pwm)['kind'] == 'progress'
    assert new.edge_progress(box, f['points'], still['visible_box_px'], motion, camera, pwm)['kind'] == 'stall'
    # merit does not move in the moved frame (top edge pinned at the image edge): merit alone would call it a stall
    assert release15.fov_merit(moved['points']) == release15.fov_merit(f['points'])


def test_one_pulse_loop_stall_escalates_once_then_fails_immediately():
    a, t, issued, tick = aligner(fov_step=new.FOV_STEP)
    assert tick(2.6, top_fragment()) == 'pending'
    assert issued[-1][2] == pytest.approx([.1]*4) and issued[-1][1] == [.35]*4
    assert tick(2.8, top_fragment()) == 'pending'               # no image motion: stall 1 -> 0.15 s next
    assert issued[-1][2] == pytest.approx([.15]*4)
    assert tick(3.0, top_fragment()) == 'failed'                # escalated pulse also no motion: fail at once
    assert a.failure == 'release17_no_recover_fov_progress'
    assert [r['verdict'] for r in a.records if r['event'] == 'fov_step_result'] == ['stall', 'stall']


def test_one_pulse_loop_progress_resets_stall_and_does_not_charge_missing_motion():
    a, t, issued, tick = aligner(fov_step=new.FOV_STEP)
    tick(2.6, top_fragment()); charged = a.motion.copy()
    assert charged[0] == pytest.approx(.0129)
    assert tick(2.8, shifted_fragment(165)) == 'pending'
    result = [r for r in a.records if r['event'] == 'fov_step_result'][-1]
    assert result['verdict'] == 'progress' and a.stall == 0 and not a.failure
    assert issued[-1][2] == pytest.approx([.1]*4)
    assert a.motion[0] == pytest.approx(.0258)                 # progressed steps are charged in full
    # A stalled step is refunded (the image shows no motion) so the cap counts what happened.
    b, _, _, tick_b = aligner(fov_step=new.FOV_STEP)
    tick_b(2.6, top_fragment()); tick_b(2.8, top_fragment())
    assert b.motion[0] == pytest.approx(.01935, abs=.0015)       # first (stalled) step refunded, escalated one charged


def test_toggle_off_keeps_release16_micro_pulse_behaviour():
    a, t, issued, tick = aligner(fov_step='off')
    tick(2.6, top_fragment())
    assert issued[-1][2] == pytest.approx([.031007751937984]*4, rel=1e-6)
    assert a.failure is None and a.sign_state == 'not_applicable'


def test_yaw_pulses_never_shorter_than_40ms_under_yaw_cal_only():
    for yaw in (.014, -.014, .02, .025, -.025, .03):
        for left in (0., .004, -.004):
            w, d, info = new.yaw_pulse_for(0., left, yaw, 'yaw_cal_v1')
            assert all(v == 0. or v >= .04-1e-12 for v in d) and any(d) and max(d) <= .15
            assert all(abs(x) in (0., .35) for x in w) and all((x == 0.) == (v == 0.) for x, v in zip(w, d))
            assert info['mode'] in ('floor', 'single_pulse', 'unchanged')
    # smaller than the dead band on every wheel: exactly one 40 ms pulse, in the requested turn direction
    w, d, info = new.yaw_pulse_for(0., 0., .014, 'yaw_cal_v1')
    assert d == [.04]*4 and info['mode'] == 'single_pulse' and w == [-.35, .35, -.35, .35]
    assert odometry([a*b/.1 for a, b in zip(w, d)], .1, 'yaw_cal_v1')[2] == pytest.approx(.042)
    # one wheel pair under the dead band while the other moves: dropped, not raised
    w, d, info = new.floor_pulse([.35, .35, .35, .35], [.1, .1, .01, .01])
    assert d == [.1, .1, 0., 0.] and w[2:] == [0., 0.] and info['mode'] == 'floor'
    # lateral-only pulses and every other profile are untouched
    assert new.yaw_pulse_for(0., .004, 0., 'yaw_cal_v1')[2] is None
    assert new.yaw_pulse_for(0., .004, .025, 'native_yaw_v1')[2] is None
    assert new.yaw_pulse_for(0., 0., .025, 'native_yaw_v1')[:2] == release14.pulse_for(0., 0., .025, 'native_yaw_v1')


def test_line_align_issues_floored_yaw_pulse_and_sign_check_uses_realized_turn(monkeypatch):
    a, t, issued, tick = aligner(profile='yaw_cal_v1')
    step = dict(kind='line_ibvs', forward=0., left=0., yaw=.006, aligned=False, merit=5., error=[0., 0.])
    monkeypatch.setattr(release15, 'line_step', lambda *args, **kwargs: dict(step))
    monkeypatch.setattr(a, 'features', lambda frame: dict(valid=True, center_error=.1, points=[], line=None, visible_box_px=None))
    tick(2.6, top_fragment())
    assert a.failure is None
    event = [r for r in a.records if r.get('event') == 'line_ibvs'][-1]
    assert event['durations'] == [.04]*4 and event['yaw_floor']['mode'] == 'single_pulse'
    assert event['yaw_floor']['realized_motion'][2] == pytest.approx(.042)
    # the sign check predicts from the 0.042 rad actually issued, not the 0.006 rad requested
    want = new.yaw_expected_shift_px(Camera(), t.pwm, 0., .042)[0]
    assert a.sign_pending['expected_px'] == pytest.approx(want, rel=1e-6)
    a2, t2, issued2, tick2 = aligner(profile='native_yaw_v1')
    monkeypatch.setattr(a2, 'features', lambda frame: dict(valid=True, center_error=.1, points=[], line=None, visible_box_px=None))
    tick2(2.6, top_fragment())
    event2 = [r for r in a2.records if r.get('event') == 'line_ibvs'][-1]
    assert 'yaw_floor' not in event2 and event2['durations'][0] < .04     # native: the old micro pulse, unchanged


def test_rotate_plan_tail_is_dropped_or_40ms_under_yaw_cal_and_native_unchanged():
    rate = rates('yaw_cal_v1')[2]
    assert rotate_plan(.01, 'yaw_cal_v1') == []                    # < 20 ms of turning: dead band
    assert [p[1][0] for p in rotate_plan(.03, 'yaw_cal_v1')] == [.04]
    for deg in (3, 7, 20, 45, 90):
        durations = [p[1][0] for p in rotate_plan(math.radians(deg), 'yaw_cal_v1')]
        assert all(v >= .04-1e-12 for v in durations) and sum(durations)*rate == pytest.approx(math.radians(deg), abs=.0225)
    assert [p[1][0] for p in rotate_plan(.01, 'native_yaw_v1')] == [.04]   # native floor is the old one, byte-for-byte


def test_yaw_sign_verdict_dead_bands():
    v = new.yaw_sign_verdict
    assert v(40., 40., 0., 30.) == 'verified' and v(40., 40., 0., -30.) == 'mismatch'
    assert v(40., 40., 0., 3.) == 'inconclusive' and v(40., 40., 0., -3.) == 'inconclusive'   # JPEG noise
    assert v(5., 5., 0., -30.) == 'inconclusive'                  # prediction too small to decide
    assert v(40., 10., 20., -30.) == 'inconclusive'               # lateral term dominates: not a yaw test


def test_yaw_cal_sign_check_stops_run_as_control_failure_on_reversed_response(monkeypatch):
    a, t, issued, tick = aligner(profile='yaw_cal_v1')
    assert a.sign_state == 'unchecked'
    expected, yaw_px, lateral_px = new.yaw_expected_shift_px(Camera(), t.pwm, 0., .025)
    assert expected > 10. and lateral_px == 0.                    # CCW: object moves right in the image
    a.sign_pending = dict(center_error=0., expected_px=expected, yaw_px=yaw_px, lateral_px=lateral_px)
    f = dict(valid=True, center_error=-expected/640, points=[], line=None)
    monkeypatch.setattr(a, 'features', lambda frame: f)
    assert tick(2.6, top_fragment()) == 'failed'
    assert a.failure == 'release17_yaw_cal_sign_mismatch' and a.sign_state == 'mismatch'
    b, t2, _, tick_b = aligner(profile='yaw_cal_v1')
    b.sign_pending = dict(center_error=0., expected_px=expected, yaw_px=yaw_px, lateral_px=lateral_px)
    b.check_yaw_sign(dict(valid=True, center_error=expected/640*.8), 2.6)
    assert b.sign_state == 'verified'
    b.sign_pending = dict(center_error=0., expected_px=expected, yaw_px=yaw_px, lateral_px=lateral_px)
    b.check_yaw_sign(dict(valid=True, center_error=-expected/640), 2.8)   # already verified: never re-judged
    assert b.sign_state == 'verified'



@pytest.mark.parametrize('motion', ('native_yaw_v1', 'yaw_cal_v1'))
@pytest.mark.parametrize('step', ('off', new.FOV_STEP))
def test_real_runner_accepts_each_toggle_combination(tmp_path, fake_backend, monkeypatch, motion, step):
    """Same actual scheduler/map/pixel lift regression as release15/16, with release17's two toggles injected."""
    from scripts import run_grasp_act_release as runner
    from tests import test_release15 as old_test
    monkeypatch.setattr(old_test, 'new', new)
    real = runner.run; results = []
    def injected(plan, out, **kw):
        results.append(real(plan, out, **{**kw, 'command_motion': motion, 'release_fov_step': step}))
        return results[-1]
    monkeypatch.setattr(runner, 'run', injected)
    old_test.test_runner_real_map_near_wall_and_actual_pixel_barrier(tmp_path, fake_backend, monkeypatch)
    result = results[0]
    assert result['command_motion'] == motion and result['release_fov_step'] == step
    assert result['release_profile'] == new.PROFILE
    assert {r['localizer']['odometry_profile'] for r in result['lookaround_result'].values()} == {motion}
    assert all(c['release17'] == dict(fov_step=step, yaw_sign_state='unchecked' if motion == 'yaw_cal_v1' else 'not_applicable')
               for c in result['line_rechecks'])


def test_valid_line_without_safe_ibvs_step_falls_through_to_one_pulse_or_blocked_never_malformed():
    from tests.test_release_regrasp import stripe
    a, t, issued, tick = aligner(fov_step=new.FOV_STEP)
    f = release16.line_features(stripe(260, .05), 'teal')
    assert f['line'] is not None and f['fov_safe']
    translation_only = lambda dx, dy, da: dx != 0 and da == 0       # IBVS (dx=0) is refused, rear/forward pulses allowed
    step = new.line_step(f, Camera(), t.pwm, clearance=translation_only)
    assert step['kind'] in ('fov_blocked', 'recover_fov')
    if step['kind'] == 'recover_fov':
        assert step['wheels'] and step['durations'] and step['period'] == .1
    a.clearance = translation_only
    assert tick(2.6, stripe(260, .05)) in ('failed', 'pending')   # must not raise KeyError on a step without wheels
