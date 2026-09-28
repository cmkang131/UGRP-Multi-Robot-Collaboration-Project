"""PR #246 review 3: long real-condition regressions (no physics, no model calls).

Scenario tests drive the real endpoint/driver/guard/align with a command-response
plant, delayed and intermittently failing own fixes, and ray-cast bars that show
their near end face. Saved own JPEGs are replayed with their own input records;
their ground-truth grip is used only in assertions (evaluation), never as input.
"""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from harness.owncam_pair_beam_v2 import pose_of
from harness.zone_own_guards import BACKOFF_GAIN_MAX, K_SIGMA, OwnPose
from harness.zone_pair_global import SCHEDULED_REOBSERVE, GlobalEnvelope
from tests.test_zone_pair_v6 import good
from tests.test_zone_pair_v6_review1 import image_at
from tests.test_zone_pair_v6_review2 import Scenario

FIXTURES = Path(__file__).parent/'fixtures'
REALISTIC = dict(fix_delay_s=.2, fail_every=2, fail_s=1.)  # half of the settled views give no fix


# ------------------------------------------------------------ P1-1 envelope / budgets

def _integrate(start, cmd, seconds, gain, heading_error, turn_gain):
    x, y, yaw = start
    yaw += heading_error
    f, l, w = cmd
    for _ in range(200):
        h = seconds/200
        x += gain*h*(math.cos(yaw)*f-math.sin(yaw)*l)
        y += gain*h*(math.sin(yaw)*f+math.cos(yaw)*l)
        yaw += turn_gain*w*h
    return x, y, yaw


@pytest.mark.parametrize('cmd', [(.1, 0., 0.), (0., .08, 0.), (.08, 0., .4), (0., 0., .5)])
def test_envelope_counts_command_once_and_encloses_every_gain(cmd):
    from dataclasses import replace
    env = GlobalEnvelope(); env.pose(good(), 0.)
    env.command(dict(kind='drive', t=0., forward=cmd[0], left=cmd[1], turn=cmd[2], duration_s=1.))
    nominal = _integrate((.6, 0., 0.), cmd, 1., 1., 0., 1.)  # PF dead reckoning at gain 1 from good()
    report = replace(good(1.), x_m=nominal[0], y_m=nominal[1], yaw_rad=nominal[2],
                     last_fix_t=0., fix_age_s=1., observation_quality={})
    p = env.pose(report, 1.)
    travel = math.hypot(cmd[0], cmd[1])
    # Old formula added the PF displacement AND 1.6x travel (review 3).
    assert p.std_xy <= .01+(travel+BACKOFF_GAIN_MAX*travel+.002+.01)/2-(.3*travel if travel else 0.)
    for gain in (0., .5, 1., 1.47, BACKOFF_GAIN_MAX):
        for err in (-2*.01, 0., 2*.01):
            for turn_gain in (0., 1., BACKOFF_GAIN_MAX):
                x, y, yaw = _integrate((.6, 0., 0.), cmd, 1., gain, err, turn_gain)
                assert math.dist((x, y), (p.x, p.y)) <= K_SIGMA*p.std_xy+1e-9
                assert abs((yaw-p.yaw+math.pi) % (2*math.pi)-math.pi) <= K_SIGMA*p.std_yaw+1e-9


def test_ten_cm_forward_is_no_longer_high():
    from dataclasses import replace
    env = GlobalEnvelope(); env.pose(good(), 0.)
    env.command(dict(kind='drive', t=0., forward=.1, duration_s=1.))
    p = env.pose(replace(good(1.), x_m=.7, last_fix_t=0., fix_age_s=1., observation_quality={}), 1.)
    assert p.std_xy < .08  # unloaded HIGH; previously HIGH after ~5 cm


def test_scheduled_budget_spills_only_excess_into_high_recovery():
    from harness.zone_pair_guards import _PairRecheck
    r = _PairRecheck()
    assert r.begin_scheduled() and r.scheduled_count == 1
    assert r.begin_scheduled() and r.scheduled_count == 1  # same active look
    r.check_gate(0., ready=False); r.check_gate(4., ready=False)
    assert r.waited_s == 0. and r.scheduled['waited_s'] == 4.
    r.check_gate(9., ready=False)
    assert r.scheduled['waited_s'] == SCHEDULED_REOBSERVE['per_look_s'] and r.waited_s == pytest.approx(3.)
    r.end_scheduled(9.)
    r.scheduled_total_s = SCHEDULED_REOBSERVE['total_s']
    assert not r.begin_scheduled()
    r2 = _PairRecheck(); r2.scheduled_count = SCHEDULED_REOBSERVE['max_count']
    assert not r2.begin_scheduled()


@pytest.mark.parametrize('goal', [(.40, -.85, 0.), (.40, -.35, 0.)])
def test_spawn_to_prestation_over_one_metre_with_delayed_failing_fixes(goal):
    s = Scenario(goal=goal, **REALISTIC)
    s.pose = np.array([-.65, -.85, 0.]); s.ctl.driver.path = None
    env = s.ep.command_guard.global_envelope
    s.capture(0.); env.__init__(); env.pose(s.own.last_report, 0.)
    s.run_until(lambda: s.ctl.state == 'wait_approach', limit=200.)
    assert s.ctl.driver.outcome == 'arrived' and math.dist(s.pose[:2], (-.65, -.85)) >= 1.
    r = s.ep.command_guard.recheck
    assert 5 <= r.scheduled_count <= SCHEDULED_REOBSERVE['max_count']
    assert r.waited_s < 10.  # HIGH recovery budget is not spent by planned looks
    assert r.scheduled_total_s <= SCHEDULED_REOBSERVE['total_s']


def test_in_place_ninety_degree_turn_with_delayed_failing_fixes():
    s = Scenario(goal=(.6, -1., math.pi/2), **REALISTIC)
    s.run_until(lambda: s.ctl.state == 'wait_approach', limit=200.)
    from harness.pair_owncam_approach import ARRIVE_TOL_YAW_RAD
    assert s.ctl.driver.outcome == 'arrived'
    assert abs(s.pose[2]-math.pi/2) <= ARRIVE_TOL_YAW_RAD
    assert s.ep.command_guard.recheck.waited_s < 10.


def test_scheduled_look_limit_is_an_explicit_abort():
    s = Scenario(goal=(1.2, -1., 0.))
    s.ep.command_guard.recheck.scheduled_count = SCHEDULED_REOBSERVE['max_count']
    with pytest.raises(AssertionError):
        s.run_until(lambda: s.ctl.state == 'wait_approach', limit=30.)
    assert s.own.jobs_done[-1]['outcome'] == 'PAIR_SCHEDULED_REOBSERVE_LIMIT'


# ------------------------------------------------------------ P2-2 thin static gap

def test_thin_static_gap_does_not_retrigger_looks_without_envelope_growth():
    s = Scenario(goal=(-.83, -.70, math.pi/2))
    guard = s.ep.command_guard
    start = (-.83, -.85, math.pi/2)
    cert = guard.sweep_guard().certificate(s.own.servo, OwnPose(*start, .015, .01), reducible=False)
    assert .03 < cert['clearance_m'] < .04 and cert['reserve_gap_low'] and not cert['relook_reserve_low']
    assert guard.sweep_guard().certificate(s.own.servo, OwnPose(*start, .015, .01))['relook_reserve_low']
    s.pose = np.array(start); s.ctl.driver.path = None
    env = guard.global_envelope; s.capture(0.); env.__init__(); env.pose(s.own.last_report, 0.)
    for i in range(1, 400):
        try:
            s.tick(round(i*.05, 6))
        except AssertionError:
            break
    # Terminates with an explicit outcome instead of 160 looks and no drive.
    assert s.ep.terminal or s.ctl.state == 'wait_approach'
    assert guard.recheck.scheduled_count <= 1


# ------------------------------------------------------------ P1-2 align entry distance

def _align(grip, limit=90.):
    s = Scenario(state='align', beam_grip=grip, **REALISTIC)
    s.run_until(lambda: s.ctl.state == 'pregrasp_descend', limit=limit)
    return s


@pytest.mark.parametrize('grip', [.43, .44, .462, .55])
def test_align_from_normal_entry_distances_reaches_pregrasp(grip):
    from harness.owncam_pair_beam import GRASP_RADIUS_M
    s = _align(grip)
    true_grip = s.beam_x-s.pose[0]
    assert .145 <= true_grip <= .18
    closes = [e for e in s.ep.events if e['event'] == 'relative_close_in']
    for e in closes:  # worst-case gain never commands inside the standoff
        c = e['command']
        assert e['grip_base_m'][0]-e['bound_m']-BACKOFF_GAIN_MAX*c['forward']*c['duration'] >= GRASP_RADIUS_M-1e-9
    if grip >= .55:
        assert closes
    assert not any(r['kind'] in ('drive', 'mecanum') and r.get('forward', 0.) < 0 for r in s.commands)


def test_relative_view_attempts_expire_with_the_multiview_window():
    from harness.zone_pair_relative import MULTIVIEW_KEEP_S
    s = Scenario(state='align', beam_grip=.36)
    ctl = s.ctl
    ctl.relative_views_tried = {'search': 0., 'p45': .5, 'inspect': 1.}
    report = type('R', (), dict(ready=lambda self, t: False, closing_ready=lambda self, t: False,
                                reasons=('END_CLIPPED',), frame_id=9, sha256='x'))()
    chosen = []
    ctl.look = lambda t: None
    ctl.relative_report = lambda t, o: report
    ctl._set_look = lambda name, t, **kw: chosen.append(name)
    ctl.look_name = 'inspect'; ctl.next_look = 0.; ctl.state_t = 0.
    ctl._align(1.+MULTIVIEW_KEEP_S+.1, True)  # search/p45 images can no longer be fused
    assert chosen == ['search']
    ctl.relative_views_tried = {'search': 5.}
    ctl.state = 'align_relook_return'; ctl.align_look_started_at = 4.; ctl.align_look_total_s = 0.
    ctl._align_fix_checks = lambda now: {'ok': True}
    ctl._align_relook_return(6., True)
    assert ctl.relative_views_tried == {}


def test_closing_step_requires_fresh_identified_shape():
    from harness.zone_pair_relative import RelativeBeamTrack
    tr = RelativeBeamTrack(); o, s = image_at(.55)
    r = tr.observe(o, s, 0, now=0.)
    assert not r.ready(0.) and r.closing_ready(0.)
    cmd = r.closing_command()
    assert cmd['forward'] > 0 and cmd['left'] == cmd['turn'] == 0.
    tr.command(dict(kind='drive', t=0., forward=cmd['forward'], duration_s=cmd['duration']), s)
    o2, s2 = image_at(.55-cmd['forward']*cmd['duration'], 'p45', fid=2, t=.4)
    later = tr.observe(o2, s2, 0, now=.4)  # propagated / partial: not a fresh fit
    assert not later.closing_ready(.4)


# ------------------------------------------------------------ P1-3 real renders

def _real(name):
    manifest = json.loads((FIXTURES/'zone_pair_v6_review3/manifest.json').read_text())
    row = next(r for r in manifest['frames'] if r['file'] == name)
    data = (FIXTURES/'zone_pair_v6_review3'/name).read_bytes()
    servo = {int(k): int(v) for k, v in row['observation']['actuator_state']['servo_pulses'].items()}
    return data, servo, row


@pytest.mark.parametrize('name', ['v5h_dev13_r1_01344.jpg', 'v5h_dev13_r1_00593.jpg', 'v5h_dev14_r1_01257.jpg',
                                  'v5h_dev14_r1_01239.jpg', 'v5b_dev09_r2_01491.jpg'])
def test_real_render_shape_fit_error_within_reported_bound(name):
    import hashlib
    from harness.zone_pair_relative import shape_fit
    data, servo, row = _real(name)
    assert hashlib.sha256(data).hexdigest() == row['observation']['sha256']
    fitted, reasons = shape_fit(data, servo)
    assert fitted is not None, reasons
    truth = row['eval_only']['grip_base_m']  # evaluation only
    assert math.dist(fitted['grip_base_m'], truth) <= fitted['std_xy_m']+fitted['bias_bound_m']
    if 'dev09' in name:
        assert 'SEPARATE_COMPONENT_EXCLUDED' in reasons  # peer robot's yellow parts


def test_real_dev09_frame_through_relative_track_is_ready_and_separates_peer():
    from harness.zone_pair_relative import RelativeBeamTrack
    data, servo, row = _real('v5b_dev09_r2_01491.jpg')
    obs = dict(frame_id=1491, sha256=row['observation']['sha256'], sim_time=1., image=data,
               actuator_state={'servo_pulses': servo})
    report = RelativeBeamTrack().observe(obs, servo, 0, now=1.)
    assert report.ready(1.) and 'SEPARATE_COMPONENT_EXCLUDED' in report.reasons
    assert math.dist(report.grip_base_m, row['eval_only']['grip_base_m']) <= report.std_xy_m+report.bias_bound_m


def test_real_dev08_adjacent_peer_is_occluder_candidate_and_align_switches_view():
    from harness.zone_pair_relative import shape_fit
    manifest = json.loads((FIXTURES/'zone_pair_v5/manifest.json').read_text())
    obs = next(v['observation'] for v in manifest['frames'].values() if v['file'] == 'dev08_r2_last_tag.jpg')
    data = (FIXTURES/'zone_pair_v5/dev08_r2_last_tag.jpg').read_bytes()
    servo = {int(k): int(v) for k, v in obs['actuator_state']['servo_pulses'].items()}
    fitted, reasons = shape_fit(data, servo)
    assert fitted is None and 'ADJACENT_OCCLUDER_CANDIDATE' in reasons
    s = Scenario(state='align', beam_grip=.36); ctl = s.ctl
    from harness.zone_pair_relative import BeamRelativeReport
    unknown = BeamRelativeReport(frame_id=1, sha256='a', captured_at_s=0., segment=0, camera_pwm=(),
                                 reasons=reasons)
    chosen = []
    ctl.look = lambda t: None
    ctl.relative_report = lambda t, o: unknown
    ctl._set_look = lambda name, t, **kw: chosen.append(name)
    ctl.look_name = 'search'; ctl.next_look = 0.; ctl.state_t = 0.
    ctl._align(.1, True)
    assert chosen == ['p45'] and not s.ep.terminal


def test_multiview_missing_extent_uses_robust_fit_extent_not_outlier_ptp():
    from harness.zone_pair_relative import RelativeBeamTrack
    from tests.test_zone_pair_v6_review1 import box_pixels
    import hashlib

    def view(name, t, fid, patch):
        servo = pose_of(name)
        x, y, top, end = box_pixels(servo, [(.306, .906)], face_at=.306)
        if patch:  # small same-colour speck beyond the far end
            _, _, speck, _ = box_pixels(servo, [(.95, .955)])
            top |= speck
        frame = np.full((480, 640, 3), 100, np.uint8)
        frame[y[top], x[top]] = [0, 220, 120]; frame[y[end], x[end]] = [0, 160, 88]
        return dict(frame_id=fid, sha256=hashlib.sha256(frame.tobytes()).hexdigest(), sim_time=t, image=frame,
                    actuator_state={'servo_pulses': servo}), servo
    bounds = []
    for patch in (False, True):
        tr = RelativeBeamTrack(); o, s = image_at(.36); tr.observe(o, s, 0, now=0.)
        tr.command(dict(kind='drive', t=0., forward=.08, duration_s=.3), s)
        o, s = view('search', .3, 2, patch); tr.observe(o, s, 0, now=.3)
        o, s = view('p45', 1., 3, patch); r = tr.observe(o, s, 0, now=1.)
        bounds.append(None if r.std_xy_m is None else r.std_xy_m+r.bias_bound_m)
    assert bounds[0] is not None
    assert bounds[1] is None or bounds[1] >= bounds[0]-1e-9


# ------------------------------------------------------------ literature recipe: PF isolated in align

def test_align_pf_is_reference_only_while_object_anchored():
    s = _align(.40)
    anchors = [e for e in s.ep.events if e['event'] == 'object_anchor']
    assert anchors and anchors[0]['anchor']['std_xy'] < .10
    safety = [e for e in s.ep.events if e['event'] == 'global_safety'
              and e['certificate'].get('pose_source') == 'object_anchored']
    assert safety and all(e['certificate']['clear'] for e in safety)
    assert all(e['pf_reference'] is not None or e['absolute_fix_t'] is None for e in safety)
    # Stops in align come only from the safety bound's reserve, never PF HIGH alone.
    assert sum(e['event'] == 'align_relook_trigger' for e in s.ep.events) <= 2


def test_object_anchor_keeps_clearance_certified_after_global_fix_ages_out():
    s = Scenario(state='align', beam_grip=.40)
    s.run_until(lambda: s.ctl.state == 'pregrasp_descend', limit=60.)
    guard = s.ep.command_guard
    assert guard.object_anchor is not None
    later = s.t+31.  # stationary wait (e.g. peer READY); the global anchor is now older than 30 s
    assert guard.global_envelope.pose(s.own.last_report, later) is None
    cert = guard.global_certificate(later)
    assert cert['clear'] and cert['pose_source'] == 'object_anchored'


@pytest.mark.parametrize('policy', ['v5h', 'b-only'])
def test_object_anchor_is_a_plus_b_only(policy):
    from harness.zone_pair_v6_policy import pair_policy
    s = Scenario(state='align', beam_grip=.40)
    s.ep.policy = pair_policy(policy)
    report = type('R', (), dict(ready=lambda self, t: True))()
    s.ep.command_guard._anchor_object(0., report)
    assert s.ep.command_guard.object_anchor is None and s.ep.command_guard.object_pose(0.) is None
