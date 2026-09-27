"""PR #234 adversarial regressions; saved own-camera inputs, no MuJoCo."""
import base64
import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

from tests.test_owncam_memory_v3 import controller, fix, memory, params, static_map
from harness.owncam_drive import CARRY_POSTURE, LOOK_P20, SEARCH_POSE, WIDE_LOOK_PANS
from harness.owncam_drive_mem_v3 import LegDriverMemV3, MAX_UNVERIFIED_LOOKS
from harness.owncam_memory_v3 import BoxTrackV3
from harness.owncam_pose_source import PoseReport
from harness.visual_attachment import compare_box_comotion
from harness.wrist_zone_skill import BOX_SKILL_OPTIONS
from harness.wrist_zone_skill_v9 import WristOnlyBoxSkillV9

FIXTURES = Path(__file__).parent/'fixtures/owncam_memory_v3_place'
SAVED = json.loads((FIXTURES/'provenance.json').read_text())['items']


def saved_place(item):
    ctl = controller()
    cur, ref = item['current'], item['reference']
    now = cur['t']
    def image(row):
        data = (FIXTURES/row['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        return base64.b64encode(data).decode()
    before, after = image(ref), image(cur)
    ctl.slot_xy, ctl.slot_id = tuple(item['slot_xy']), item['slot_id']
    ctl.servo = {int(k): v for k, v in cur['commanded_servo'].items()}
    ctl.last_obs = dict(robot_id='r1', frame_id=cur['frame_id'], sim_time=now,
                        image=after, sha256=cur['sha256'], camera='robot_cam',
                        actuator_state={'servo_pulses': cur['commanded_servo']})
    xy = cur['report']['xyyaw']
    sx, sy = cur['report']['std_xy_m'], cur['report']['std_yaw_rad']
    rep = PoseReport(t_est=now, initialized=True, x_m=xy[0], y_m=xy[1], yaw_rad=xy[2],
                     std_xy_m=sx, std_yaw_rad=sy, since_tag_s=0.,
                     cov=tuple(map(tuple, np.diag([sx*sx/2]*2 + [sy*sy]))))
    ctl.pose.report = lambda t: rep
    ctl.verification['place'] = {'since': now-.5, 'looks': 0}
    fix(ctl.memory, now, xy[:2])  # Explicit v3 consistency precondition, not inferred from v2.
    box = WristOnlyBoxSkillV9(robot_id='r1', **BOX_SKILL_OPTIONS)
    box.phase, box.held = 'carry', True
    box._attachment_image = before
    box._carry_previous_image = before
    box._hover = {int(k): v for k, v in item['release_posture_command']['action']['pulses'].items()}
    box._grasp = dict(box._hover)
    ctl.skill = SimpleNamespace(box=box, phase='pre_release', _preplace_goal=lambda: item['preplace_goal'])
    return ctl, now, xy, before, after


def explicit_empty_slot_evidence(ctl, now):
    """Synthetic, separate floor evidence; the saved v2 RGB alone cannot give it."""
    mask = ctl.memory.slot_cells(ctl.slot_xy, ctl._slot_half())
    ctl.memory.log_odds[mask] = -2.
    ctl.memory.free_observed_at[mask] = now
    ctl.memory.free_frame_ids[mask] = 5000


@pytest.mark.parametrize('item', SAVED, ids=lambda i: f"s{i['seed']}")
def test_saved_release_evidence_plus_separate_empty_slot_observation_passes(item):
    ctl, now, xy, before, after = saved_place(item)
    # Actual saved pose + fixed camera model: no possible loaded floor proof.
    slot = np.all(np.abs(ctl.memory.view.cells - ctl.slot_xy) <= ctl._slot_half(), axis=1)
    for posture in (LOOK_P20, CARRY_POSTURE):
        for pan in WIDE_LOOK_PANS:
            idx, _ = ctl.memory.view.floor_footprint(xy, {**posture, 6: pan}, True, max_range=1.1)
            assert not slot[idx].any()
    assert compare_box_comotion(before, after, min_saturation=150)['attached']
    explicit_empty_slot_evidence(ctl, now)
    with mock.patch.object(ctl, '_gate_look', return_value={'mode': 'capture'}):
        assert ctl._boundary_gate(now, 'place') is None
    assert ctl.slot_record['state'] == 'free'


def leg_fixture(loaded, yaw=.08, mode='full'):
    mem = memory()
    est = dict(initialized=True, x=-.47, y=-.85, yaw=0., std_xy_m=.02,
               std_yaw_rad=yaw, cov=np.diag([.0002, .0002, yaw*yaw]), since_tag_s=0.)
    loc = SimpleNamespace(t=2., estimate=lambda: est, predict_to=lambda t: None)
    leg = LegDriverMemV3(mem, loc, static_map(), params(), loaded=loaded,
                        goal_xy=(1., -.85), door_xy=(2., 0.), initial_servo=SEARCH_POSE)
    leg.look_mode, leg.current_look_since = mode, 1.
    return leg, loc, est


@pytest.mark.parametrize('loaded', [False, True])
@pytest.mark.parametrize('mode', ['short', 'full'])
def test_p1_yaw_only_no_progress_look_loop_stops(loaded, mode):
    leg, loc, _ = leg_fixture(loaded, mode=mode)
    for attempt in range(6):
        loc.t = 2. + attempt
        fix(leg.memory, loc.t)
        if leg._should_refix(True):
            leg._start_look(loc.t, 'refix')
        if leg.outcome:
            break
    assert leg.outcome == 'pose_unverified'
    assert attempt + 1 <= MAX_UNVERIFIED_LOOKS


def track_at(x=.65, y=0.):
    mem = memory()
    tr = BoxTrackV3('fixture', 'cyan', np.array([x, y]), np.eye(2)*.0001, 0., 1, 'near', .0001)
    mem._frame_pose_good = True
    return mem, tr


def test_p1_yaw_interval_out_of_fov_is_not_absence_evidence():
    mem, tr = track_at()
    pose = (0., 0., 0.)
    cov = np.diag([.0001, .0001, .5**2])
    assert mem.view.point_in_view(pose, SEARCH_POSE, False, (*tr.x, .016))
    assert not mem.view.point_in_view((0., 0., 1.), SEARCH_POSE, False, (*tr.x, .016))
    assert not mem._visible_for_absence(tr, pose, cov, SEARCH_POSE, [])


def test_p2_self_gripper_possible_occlusion_defers_miss():
    mem, tr = track_at(.42)
    pose = (0., 0., 0.)
    cov = np.diag([.000001, .000001, .000001])
    assert mem.view.point_in_view(pose, SEARCH_POSE, False, (*tr.x, .016))
    # Camera is above the tool axis; this near floor ray descends through the
    # forward gripper region. Geometric FOV alone cannot certify an absence.
    assert not mem._visible_for_absence(tr, pose, cov, SEARCH_POSE, [])


@pytest.mark.parametrize('failure', ['occupied', 'no_cargo', 'wrong_posture', 'wrong_position',
                                   'wrong_heading', 'stale_image', 'future_image', 'old_fix',
                                   'uninitialized', 'large_sigma'])
def test_place_gate_rejects_missing_or_contradictory_release_evidence(failure):
    ctl, now, _, _, _ = saved_place(SAVED[0])
    explicit_empty_slot_evidence(ctl, now)
    rep = ctl.pose.report(now)
    if failure == 'occupied':
        _, tr = track_at(*ctl.slot_xy)
        tr.t = tr.last_seen_t = now
        ctl.memory.tracks.append(tr)
    elif failure == 'no_cargo':
        import cv2
        image = cv2.imencode('.jpg', np.zeros((480, 640, 3), np.uint8))[1].tobytes()
        ctl.last_obs['image'] = base64.b64encode(image).decode()
        ctl.last_obs['sha256'] = hashlib.sha256(image).hexdigest()
    elif failure == 'wrong_posture':
        ctl.last_obs['actuator_state'] = {'servo_pulses': {str(k): v for k, v in CARRY_POSTURE.items()}}
    elif failure == 'wrong_position':
        rep = replace(rep, x_m=rep.x_m-.10)
    elif failure == 'wrong_heading':
        rep = replace(rep, yaw_rad=.08)
    elif failure == 'stale_image':
        ctl.last_obs['sim_time'] = now-.251
    elif failure == 'future_image':
        ctl.last_obs['sim_time'] = now+.01
    elif failure == 'old_fix':
        ctl.memory.last_look_fix['t'] = now-1.
    elif failure == 'uninitialized':
        rep = replace(rep, initialized=False, x_m=None, y_m=None, yaw_rad=None)
    else:
        rep = replace(rep, std_xy_m=.051)
    ctl.pose.report = lambda t: rep
    with mock.patch.object(ctl, '_gate_look', return_value={'mode': 'capture'}):
        assert ctl._boundary_gate(now, 'place') is not None
    assert not any(e['event'] == 'boundary_verified' for e in ctl.events)


def test_release_reanchor_runs_before_gate_without_consuming_release_action():
    ctl, now, _, _, _ = saved_place(SAVED[0])
    ctl.reanchor_needed = True
    with mock.patch.object(ctl, '_boundary_gate') as gate:
        result = ctl._skill(now)
    assert result == {'mode': 'capture'}
    assert not ctl.reanchor_needed
    assert ctl.skill.box.phase == 'carry'
    gate.assert_not_called()
    # The already consumed image cannot execute the release on a retry.
    ctl.reanchor_needed = True
    assert ctl._skill(now) == {'mode': 'capture'}


@pytest.mark.parametrize('item', SAVED, ids=lambda i: f"s{i['seed']}")
def test_saved_release_pose_reaches_skill_dispatch(item):
    from harness.wrist_zone_skill import PoseEstimate
    ctl, now, _, _, _ = saved_place(item)
    explicit_empty_slot_evidence(ctl, now)
    ctl.last_look_t = now
    ctl.pose_estimate_cls = PoseEstimate
    ctl.skill.decide = mock.Mock(return_value={'kind': 'wait', 'duration': .05})
    assert ctl._skill(now) == {'mode': 'macro', 'action': {'kind': 'wait', 'duration': .05}}
    ctl.skill.decide.assert_called_once()
    assert ctl.slot_record['state'] == 'free'
    assert ctl.outcome is None


def test_busy_leg_cannot_bypass_place_gate_via_reanchor_branch():
    ctl, now, _, _, _ = saved_place(SAVED[0])
    ctl.reanchor_needed = True
    ctl.leg = SimpleNamespace(state='look_pan')
    assert ctl._skill(now) == {'mode': 'capture'}
    assert ctl.skill.box.phase == 'carry'


@pytest.mark.parametrize('loaded', [False, True])
def test_yaw_retries_stop_in_actual_driver_tick(loaded):
    leg, loc, _ = leg_fixture(loaded)
    for attempt in range(MAX_UNVERIFIED_LOOKS):
        loc.t = 2.+attempt
        fix(leg.memory, loc.t)
        leg.state, leg.state_since, leg.look_queue, leg.arm_target = 'look_pan', 0., [], {}
        cmds = leg.tick(loc.t)
        assert all(c['kind'] == 'hold' for c in cmds)
    assert leg.outcome == 'pose_unverified'
    assert leg.tick(loc.t) == []


@pytest.mark.parametrize('loaded', [False, True])
def test_yaw_threshold_and_recovery_reset_budget_only_when_drive_ready(loaded):
    from harness.owncam_drive import LOOK_IF_STD_YAW_RAD
    leg, loc, est = leg_fixture(loaded)
    fix(leg.memory, loc.t)
    assert leg._should_refix(True)
    assert leg.unverified_looks == 1
    est['std_yaw_rad'] = LOOK_IF_STD_YAW_RAD
    est['cov'][2, 2] = LOOK_IF_STD_YAW_RAD**2
    assert not leg._should_refix(True)
    assert leg.unverified_looks == 0
    est['std_yaw_rad'] += 1e-6
    est['cov'][2, 2] = est['std_yaw_rad']**2
    assert leg._should_refix(True)
    assert leg.unverified_looks == 1
    assert leg.outcome is None


@pytest.mark.parametrize('yaw_sigma', [0., .005, .02])
def test_clear_open_search_view_still_provides_negative_evidence(yaw_sigma):
    mem, tr = track_at()
    cov = np.diag([.000001, .000001, yaw_sigma**2])
    assert mem._visible_for_absence(tr, (0., 0., 0.), cov, SEARCH_POSE, [])
    # Independently sample the continuous interval as a cross-check, including
    # interior headings, not as the implementation's visibility guarantee.
    for yaw in np.linspace(-2*yaw_sigma, 2*yaw_sigma, 61):
        assert mem.view.point_in_view((0., 0., yaw), SEARCH_POSE, False, (*tr.x, .016))


def test_yaw_arc_interior_extrema_are_enclosed_even_when_endpoints_wrap():
    from harness.owncam_visibility_v3 import yaw_enclosure_radius
    assert yaw_enclosure_radius(.65, 2*math.pi) == pytest.approx(1.3)
    mem, tr = track_at()
    cov = np.diag([.000001, .000001, math.pi**2])
    # Endpoints at +/- 2*pi look identical; the intermediate headings do not.
    assert mem.view.point_in_view((0., 0., 2*math.pi), SEARCH_POSE, False, (*tr.x, .016))
    assert not mem._visible_for_absence(tr, (0., 0., 0.), cov, SEARCH_POSE, [])


def test_thin_foreground_between_support_rays_defers_absence():
    mem, tr = track_at()
    cov = np.diag([.000001, .000001, .01**2])
    assert mem._visible_for_absence(tr, (0., 0., 0.), cov, SEARCH_POSE, [])
    # A thin static post can intersect an interior ray without covering corners.
    mem.view.occluders.append((np.array([.4, .015]), np.array([.002, .002]), .4))
    assert not mem._visible_for_absence(tr, (0., 0., 0.), cov, SEARCH_POSE, [])


@pytest.mark.parametrize('servo', [CARRY_POSTURE, {**SEARCH_POSE, 1: 1500}, {**SEARCH_POSE, 3: 741}])
def test_uncertified_arm_posture_defers_absence(servo):
    mem, tr = track_at()
    assert not mem._visible_for_absence(tr, (0., 0., 0.), np.zeros((3, 3)), servo, [])


def test_uncertain_or_arm_hidden_misses_leave_existence_unchanged():
    for x, yaw_sigma in ((.65, .5), (.42, .001)):
        mem, tr = track_at(x)
        mem.tracks = [tr]
        mem._detect = lambda image, servo: []
        tr.existence_p = .9994
        for frame in range(1, 5):
            mem._observe_boxes(frame*.5, frame, None, (0., 0., 0.),
                               np.diag([1e-6, 1e-6, yaw_sigma**2]), SEARCH_POSE)
        assert tr.misses == 0
        assert tr.existence_p == .9994  # Time survival decay belongs to observe_frame.


def test_new_visibility_code_is_frozen_by_runner_and_tests_are_collected():
    from scripts.run_m1_owncam_memory_v3 import MEMORY_FILES
    from scripts.run_ci_tests import TEST_PATTERNS
    assert 'harness/owncam_visibility_v3.py' in MEMORY_FILES
    assert 'tests/test_owncam_memory_v3_review.py' in TEST_PATTERNS


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -.001])
def test_invalid_yaw_covariance_cannot_certify_absence(bad):
    mem, tr = track_at()
    cov = np.diag([.000001, .000001, bad])
    assert not mem._visible_for_absence(tr, (0., 0., 0.), cov, SEARCH_POSE, [])


@pytest.mark.parametrize('slope,clear', [(0., True), (.5, True), (-.001, False), (.501, False)])
def test_self_clear_cone_edges(slope, clear):
    from harness.owncam_visibility_v3 import self_arm_clear
    from harness.visual_arm import tool_pose
    wrist = tool_pose(SEARCH_POSE, tool_length_cm=0.)
    pitch = math.radians(wrist.pitch_deg)
    ex = np.array([math.cos(pitch), 0., math.sin(pitch)])
    ez = np.array([-math.sin(pitch), 0., math.cos(pitch)])
    pt = np.array([wrist.x_m, wrist.y_m, wrist.z_m]) + .567*ex + (.0136 + slope*.5)*ez
    assert self_arm_clear((0., 0., 0.), SEARCH_POSE, np.array([pt])) == clear
