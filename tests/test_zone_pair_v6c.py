"""v6c: exact PF fix clock and grasp-range pre-grasp entry (no physics, no models).

Frames are exact own RGB + own issued PWM recorded by the PR #260 stage probes
(align-tolerance boundary set). ``setup_offset_eval_only`` is only a label.
"""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from harness.owncam_pose_source import OwnCamPoseSource
from harness.owncam_recovery_v6 import RecoveryLocalizer, enable_provider as enable_v6
from harness import owncam_recovery_v6c as v6c_clock
from harness.owncam_time import accepted_fix_checks
from harness.zone_pair_beam_track import RestingBeamTrack, standoff_estimate
from harness.zone_pair_grasp_entry_v6c import (BEAM_WIDTH_M, FINAL_DESCENT_SETTLE_S, MIN_WIDTH_FRACTION,
                                               GraspRangeBeamTrack, cross_section, grasp_range_points,
                                               standoff_estimate_v6c)
from harness.zone_pair_v6_policy import POLICIES, REVISION_POLICIES, pair_policy

ROOT = Path(__file__).resolve().parents[1]
V6 = json.loads((ROOT/'tests/fixtures/zone_pair_v6/reports.json').read_text())
FIX = ROOT/'tests/fixtures/zone_pair_v6c'
MAN = json.loads((FIX/'manifest.json').read_text())
# Recorded times (PR #260 Run A raw, r1): previous fix frame and the next own frame.
PREV_T, FRAME_T = 1.300250000000018, 1.5002500000000847


def source(v6c):
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=628)
    (v6c_clock.enable_provider if v6c else enable_v6)(p)
    loc = p.loc
    loc.initialized = True
    loc.px[:] = [.6, 0., 0.]
    return p


def frame(label):
    rec = MAN['frames'][label]
    data = (FIX/rec['file']).read_bytes()
    assert len(data) == rec['bytes'] < 1024*1024 and hashlib.sha256(data).hexdigest() == rec['sha256']
    obs = {'image': base64.b64encode(data).decode(), 'frame_id': rec['frame_id'], 'sha256': rec['sha256'],
           'sim_time': rec['sim_time'], 'robot_id': rec['robot_id']}
    return obs, {int(k): v for k, v in rec['servo_pulses'].items()}


# ------------------------------------------------------------ exact fix clock
def test_recorded_times_reproduce_negative_age_and_v6c_stamps_the_frame_time():
    ages = {}
    for v6c in (False, True):
        p = source(v6c)
        loc = p.loc
        loc.predict_to(PREV_T)
        loc.predict_to(FRAME_T)
        loc.last_informative_t = loc.last_tag_t = FRAME_T   # an informative fix at this frame
        ages[v6c] = loc.estimate()['fix_age_s']
        report = p.report(FRAME_T)
        checks = accepted_fix_checks(report, FRAME_T, FRAME_T - 1., strict_start=True)
        assert checks['fix_age_valid'] is v6c
        if v6c:
            assert loc.t == FRAME_T and all(checks.values())
    # Exactly the value recorded in Run A (r1 frame t=1.5003): -6.66e-14 s.
    assert ages[False] == pytest.approx(-6.661338147750939e-14, abs=1e-16) and ages[True] == 0.


def test_exact_clock_never_moves_backwards_or_beyond_tolerance():
    p = source(True)
    loc = p.loc
    loc.predict_to(2.)
    loc.predict_to(1.9)          # older frame: the clock stays; its fix age would be positive
    assert loc.t == 2.
    loc.predict_to(2.3)
    assert loc.t == pytest.approx(2.3, abs=1e-12) and loc.t >= 2.3 - 1e-9


def test_exact_clock_keeps_posterior_identity_and_v6_policies_unchanged():
    p = source(False)
    loc, before = p.loc, p.loc.px.copy()
    v6c_clock.enable_provider(p)
    assert p.loc is loc and isinstance(loc, v6c_clock.ExactClockRecoveryLocalizer)
    assert isinstance(loc, RecoveryLocalizer) and np.array_equal(loc.px, before)
    assert p.recovery_v6 and p.exact_fix_clock_v6c and p.source.endswith(':recovery_v6')
    for name in ('v5h', 'b-only', 'a+b'):
        assert not POLICIES[name].exact_fix_clock and not POLICIES[name].grasp_range_entry
    b = pair_policy('b-v6c')
    assert b.posterior_relook and b.exact_fix_clock and b.grasp_range_entry and not b.beam_relative
    assert REVISION_POLICIES['v6c'] == ('v5h', 'b-only', 'b-v6c')


def test_pair_team_uses_the_v6c_enable_only_for_the_flag(monkeypatch):
    from harness import owncam_recovery_v6 as v6
    from harness.zone_pair_executor import PairTeam
    calls = []
    monkeypatch.setattr(v6, 'enable_provider', lambda p: calls.append(('v6', p)))
    monkeypatch.setattr(v6c_clock, 'enable_provider', lambda p: calls.append(('v6c', p)))
    ex = type('Ex', (), {'pose': object()})()
    for policy, expected in (('b-only', 'v6'), ('b-v6c', 'v6c'), ('v5h', None)):
        calls.clear()
        PairTeam({'r1': ex}, {}, {}, cancel_scheduled=lambda *a: None, contact_profile='cargo_noslip_v1',
                 policy=policy)
        assert [c[0] for c in calls] == ([] if expected is None else [expected])


# ------------------------------------------------------------ standoff fit
@pytest.mark.parametrize('label', ['standoff_ex-12mm_r1', 'standoff_ex+8mm_r1', 'standoff_ey-4mm_r2'])
def test_grasp_range_standoff_fit_on_boundary_frames(label):
    obs, servo = frame(label)
    beam = standoff_estimate_v6c(obs, servo)
    assert beam is not None and beam['axis_fit'] == 'equal_length_paired_edges'
    ex, ey, _ = MAN['frames'][label]['setup_offset_eval_only']
    # Label check only (eval): the read grip follows the staged offset; the
    # known +3...+4 mm band-centre read bias of v2 stays (not recalibrated).
    assert beam['grip_base_m'][0] - (.162 + ex) == pytest.approx(.0035, abs=.003)
    assert abs(beam['grip_base_m'][1] - ey) < .004 and abs(beam['axis_heading_rad']) < beam['std_yaw_rad']


def test_lime_fit_fails_where_v6c_passes_and_support_filter_is_needed():
    # Root cause replay: ex-12 r1 lime -> half-fit disagreement 0.068 rad (> 3 deg).
    obs, servo = frame('standoff_ex-12mm_r1')
    assert standoff_estimate(obs, servo) is None
    # ey-4 r2: grasp-range colour alone keeps a partly covered boundary strip.
    obs, servo = frame('standoff_ey-4mm_r2')
    assert standoff_estimate(obs, servo, points=grasp_range_points) is None
    assert standoff_estimate(obs, servo, points=grasp_range_points, min_strip_support=.25) is not None


def test_dev06_standoff_fixtures_still_fit_with_v6c():
    rec = json.loads((ROOT/'tests/fixtures/zone_pair_standoff/manifest.json').read_text())['frames']['standoff']
    data = (ROOT/'tests/fixtures/zone_pair_standoff'/rec['file']).read_bytes()
    obs = {**copy.deepcopy(rec['observation']), 'image': base64.b64encode(data).decode()}
    servo = {int(k): v for k, v in obs['actuator_state']['servo_pulses'].items()}
    old, new = standoff_estimate(obs, servo), standoff_estimate_v6c(obs, servo)
    assert old is not None and new is not None
    assert math.dist(old['grip_base_m'], new['grip_base_m']) < 1e-9  # same band-centre grip
    assert abs(old['axis_heading_rad'] - new['axis_heading_rad']) < math.radians(1.)


# ------------------------------------------------------------ pre-close patch
def anchored(track_cls, label='standoff_ex+8mm_r1'):
    obs, servo = frame(label)
    track = track_cls()
    assert track.observe_standoff(obs, servo, 3)
    return track, obs['sim_time']


def test_grasp_pose_view_renews_only_the_v6c_track():
    grasp, servo = frame('grasp_pose_ex+8mm_r1')
    # v1 lime sees < MIN_POINTS at the lowered open-jaw pose (beam top renders yellow).
    base = RestingBeamTrack()
    beam = standoff_estimate(*frame('standoff_ex+8mm_r1'))
    assert beam is not None
    base.beam = {**beam, 'anchor_time_s': grasp['sim_time'] - 2., 'prediction_time_s': grasp['sim_time'] - 2.}
    base.segment, base.t = 3, grasp['sim_time'] - 2.
    assert base.estimate(grasp['sim_time'], grasp, servo, 3) is None
    track, _ = anchored(GraspRangeBeamTrack)
    got = track.estimate(grasp['sim_time'], grasp, servo, 3)
    assert got is not None and got['partial_support_fraction'] >= .95
    assert got['partial_reason'] == 'GRASP_RANGE_BEAM_COLOUR' and len(grasp_range_points(grasp['image'], servo)) > 5000
    assert got['anchor_frame_id'] == MAN['frames']['standoff_ex+8mm_r1']['frame_id']  # no pose/age reset


@pytest.mark.parametrize('shift', [(.15, 0.), (0., .12), (-.7, 0.)])  # axial slides inside the bar length are
# not refused by this patch test (unchanged design); READY also requires grip_view_m2 (band between jaws).
def test_grasp_pose_patch_outside_the_tracked_footprint_is_refused(shift):
    grasp, servo = frame('grasp_pose_ex+8mm_r1')
    track, _ = anchored(GraspRangeBeamTrack)
    gx, gy = track.beam['grip_base_m']
    track.beam['grip_base_m'] = [gx + shift[0], gy + shift[1]]
    assert track.estimate(grasp['sim_time'], grasp, servo, 3) is None


def _narrow_mark_without_beam(half_width_m):
    """Adversarial review: keep only beam-colour pixels within half_width_m of the tracked axis,
    paint every other beam/band pixel as dark floor -> a narrow yellow mark, no beam."""
    import cv2
    from harness import owncam_pair_beam as v1
    from harness import owncam_pair_beam_v2 as v2
    from harness.owncam_view import base_rays
    grasp, servo = frame('grasp_pose_ex+8mm_r1')
    track, _ = anchored(GraspRangeBeamTrack)
    img = v1.decode(grasp['image']).copy()
    origin, rays, xs, ys, valid = base_rays(servo, 1)
    xi, yi = xs.astype(int), ys.astype(int)
    down = valid & (rays[:, 2] < -1e-6)
    s = np.where(down, (v1.BEAM_TOP_Z_M - origin[2]) / np.where(down, rays[:, 2], -1.), np.nan)
    pts = origin[:2] + s[:, None] * rays[:, :2]
    b = track.beam
    u = np.array([math.cos(b['axis_heading_rad']), math.sin(b['axis_heading_rad'])])
    n = (pts - np.asarray(b['grip_base_m'])) @ np.array([-u[1], u[0]])
    keep = np.zeros(img.shape[:2], bool)
    keep[yi[down & (np.abs(n) <= half_width_m)], xi[down & (np.abs(n) <= half_width_m)]] = True
    colour = v2.beam_colour_mask(img)
    img[colour & ~keep] = (28, 28, 28)                     # dark floor where the beam was
    ok, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    data = jpg.tobytes()
    obs = {**grasp, 'image': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest()}
    return track, obs, servo


def test_grasp_range_patch_needs_the_beam_cross_section():
    grasp, servo = frame('grasp_pose_ex+8mm_r1')
    track, _ = anchored(GraspRangeBeamTrack)
    real = track.estimate(grasp['sim_time'], grasp, servo, 3)
    assert real is not None and real['partial_cross_section_m'] >= MIN_WIDTH_FRACTION * BEAM_WIDTH_M
    # 12 mm yellow mark on the tracked axis, no beam: inside the footprint (the colour-only
    # footprint test of RestingBeamTrack alone would accept it) but not the beam cross-section.
    track, obs, servo = _narrow_mark_without_beam(.006)
    pts = grasp_range_points(obs['image'], servo)
    assert len(pts) > 500 and cross_section(pts, track.beam) < MIN_WIDTH_FRACTION * BEAM_WIDTH_M
    assert RestingBeamTrack.estimate(track, obs['sim_time'], obs, servo, 3) is not None  # footprint alone passes
    track, obs, servo = _narrow_mark_without_beam(.006)
    assert track.estimate(obs['sim_time'], obs, servo, 3) is None


def test_reused_v6c_provider_is_refused_for_baseline_policies():
    from harness.zone_pair_executor import PairTeam
    bound = source(True)
    assert v6c_clock.exact_clock_bound(bound) and not v6c_clock.exact_clock_bound(source(False))
    for policy in ('v5h', 'b-only', 'a+b'):
        ex = type('Ex', (), {'pose': bound})()
        with pytest.raises(ValueError, match='fresh provider'):
            PairTeam({'r1': ex}, {}, {}, cancel_scheduled=lambda *a: None, contact_profile='cargo_noslip_v1',
                     policy=policy)
    ex = type('Ex', (), {'pose': bound})()
    PairTeam({'r1': ex}, {}, {}, cancel_scheduled=lambda *a: None, contact_profile='cargo_noslip_v1',
             policy='b-v6c')                               # same policy may reuse its own provider
    fresh = type('Ex', (), {'pose': source(False)})()
    PairTeam({'r1': fresh}, {}, {}, cancel_scheduled=lambda *a: None, contact_profile='cargo_noslip_v1',
             policy='b-only')
    assert not v6c_clock.exact_clock_bound(fresh.pose)


def test_every_policy_has_a_unique_probe_view_abbreviation():
    import importlib.util
    spec = importlib.util.spec_from_file_location('views', ROOT/'scripts/build_pair_stage_probe_views.py')
    views = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(views)
    from harness.pair_stage_probe import POLICIES as PROBE_POLICIES
    assert set(PROBE_POLICIES) <= set(views.POLICY_SHORT) and set(POLICIES) <= set(views.POLICY_SHORT)
    assert len(set(views.POLICY_SHORT.values())) == len(views.POLICY_SHORT)
    assert views._pol('b-v6c') == 'C-'


def test_track_limits_are_unchanged_for_v6c():
    grasp, servo = frame('grasp_pose_ex+8mm_r1')
    track, _ = anchored(GraspRangeBeamTrack)
    assert track.estimate(grasp['sim_time'], grasp, servo, 4) is None      # other segment
    track, _ = anchored(GraspRangeBeamTrack)
    track.beam['std_yaw_rad'] = math.radians(3.1)
    assert track.estimate(grasp['sim_time'], grasp, servo, 3) is None      # sigma gate
    track, t0 = anchored(GraspRangeBeamTrack)
    assert track.estimate(t0 + 31., grasp, servo, 3) is None               # MAX_AGE_S


# ------------------------------------------------------------ wiring
def test_guard_and_final_descent_settle_follow_the_flag():
    from tests.test_zone_pair_grasp import real_pair
    from harness.zone_pair_guards import PairCommandGuard
    for policy, cls, settle in (('b-only', RestingBeamTrack, 0.), ('b-v6c', GraspRangeBeamTrack, FINAL_DESCENT_SETTLE_S)):
        _, _, eps = real_pair()
        ep = eps['r1']
        ep.policy = pair_policy(policy)
        guard = PairCommandGuard(ep)
        assert type(guard.beam_track) is cls
        ctl = ep.controller
        ctl.grip_base = [.162, 0.]
        ctl._queue_open_descent(10.)
        assert ctl.state == 'pregrasp_descend'
        last_event = max(t for t, _, _ in ctl.arm.events)
        assert ctl.arm.until == pytest.approx(last_event + settle, abs=1e-9)
