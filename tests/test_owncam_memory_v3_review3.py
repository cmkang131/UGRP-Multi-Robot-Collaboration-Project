"""Review 3 scenarios: static geometry/own RGB only, never a physics run."""
import base64
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cv2
import numpy as np
import pytest

from harness.map_goto import plan_path, UNLOADED_ENVELOPE
from harness.owncam_drive import CARRY_POSTURE, LOOK_P20, WIDE_LOOK_PANS
from harness.owncam_memory_v3 import BoxTrackV3
from tests.test_owncam_memory_v3 import controller, params, report, static_map
from tests.test_owncam_memory_v3_review import SAVED, saved_place, leg_fixture


def door_map():
    smap = json.loads(Path('maps/zones/zone_wide_door_tags_v2.json').read_text())
    for wall in smap['obstacles']:
        wall['height_m'] = .40
    return smap


def test_p1_leg_relook_filters_jamb_collision_pan():
    leg, _, est = leg_fixture(True, yaw=.005)
    est.update(x=2.08, y=.18, std_xy_m=.001)
    leg.map, leg.servo = door_map(), dict(CARRY_POSTURE)
    leg._start_look(2., 'refix')
    assert 2030 not in leg.look_queue


def test_p1_slot_sweep_checks_posture_and_pan_collision():
    ctl, now, _, _, _ = saved_place(SAVED[0])
    ctl.map, ctl.servo = door_map(), dict(CARRY_POSTURE)
    ctl.pose.report = lambda t: report(t, x=2.08, y=.18, sigma=.001)
    ctl.slot_inspection = {'stage': 'inspect'}
    ctl._start_sweep(now, 'slot_inspection', LOOK_P20, WIDE_LOOK_PANS, CARRY_POSTURE, 'test')
    assert ctl.sweep is None or 2030 not in ctl.sweep['queue']


def test_p1_aged_slot_blocker_stays_in_driving_keepouts():
    ctl, now, xy, _, _ = saved_place(SAVED[0])
    tr = BoxTrackV3('obstacle', 'red', np.array([4.02, -2.5]), np.eye(2)*.0001,
                    now-225., 1, 'far_coarse', .001)
    tr.evidence(now-225., detected=True, range_class='far_coarse', pose_sigma=.02)
    ctl.memory.tracks.append(tr)
    ctl.memory._decay_to(now)
    assert tr.existence_p < .20 and tr.slot_blocking
    keepouts = ctl.memory.keepouts()
    assert tr.track_id in [k['id'] for k in keepouts]
    # The remembered obstacle must be supplied to the actual return planner.
    ctl._start_leg((3.65, -2.5), loaded=True)
    assert tr.track_id in [k['id'] for k in ctl.leg.keepouts]


@pytest.mark.parametrize('stage', ['outbound', 'return'])
def test_p1_inspection_cargo_disappearance_stops_before_next_move(stage):
    ctl, now, _, _, image = saved_place(SAVED[0])
    ctl.skill.box._carry_previous_image = image
    ctl.slot_inspection = {'stage': stage, 'goal': [3.65, -2.5]}
    ctl.verification['place']['slot_deadline'] = now+120.
    ctl.leg = SimpleNamespace(state='drive', on_command=lambda row: None)
    jpeg = cv2.imencode('.jpg', np.zeros((480, 640, 3), np.uint8))[1].tobytes()
    obs = {**ctl.last_obs, 'frame_id': ctl.last_obs['frame_id']+1, 'sim_time': now+.2,
           'image': base64.b64encode(jpeg).decode(), 'sha256': hashlib.sha256(jpeg).hexdigest()}
    with mock.patch.object(ctl.pose, 'on_frame', return_value=ctl.pose.report(now)), \
         mock.patch.object(ctl.memory, 'observe_frame'), \
         mock.patch.object(ctl, '_drive_leg', return_value=([{'kind': 'mecanum', 'forward': -.05}], None)) as drive, \
         mock.patch.object(ctl.skill.box, '_carry', wraps=ctl.skill.box._carry) as carry:
        ctl.pose.last_raw_report = ctl.pose.report(now)
        ctl.on_frame(now+.2, obs, np.zeros((480, 640, 3), np.uint8))
        result = ctl.decide(now+.2)
    assert result['mode'] == 'done'
    assert 'VISUAL_LOAD_DROPPED_OR_OCCLUDED' in result['handoff']['reason']
    assert carry.call_count == 1
    drive.assert_not_called()


def test_p2_blind_search_retreat_is_projected_to_reachable_body_clear_point():
    ctl = controller()
    ctl.viewpoints, ctl.view_index = [(-.47, .75)], 0
    ctl.pose.report = lambda t: report(t, x=-.47, y=.75)
    with mock.patch.object(ctl, '_start_leg') as start:
        ctl._search_decide(1.)
    assert ctl.outcome is None
    goal = start.call_args.args[0]
    assert goal[0] < -.47
    assert plan_path(ctl.map, [-.47, .75], goal, UNLOADED_ENVELOPE, obstacles=ctl._keepouts()) is not None


def test_external_sim_limit_persists_pending_slot_handoff(tmp_path):
    from scripts import run_m1_owncam_memory_v3 as runner
    from scripts import run_m1_owncam as base_runner
    ctl, now, _, _, _ = saved_place(SAVED[0])
    ctl.slot_inspection = {'stage': 'outbound', 'goal': [3.65, -2.5]}
    ctl.skill.events = []
    ctl.verification['place'].update(slot_deadline=now+120., slot_attempts=1)
    def fake_run(spec, out, student):
        out.mkdir()
        result = {'outcome': 'SIM_LIMIT', 'sim_s': now+5., 'controller': ctl.summary()}
        (out/'result.json').write_text(json.dumps(result))
        (out/'manifest.json').write_text('{}')
        return result, {}
    out = tmp_path/'stopped'
    caps = {k: '1' for k in runner.THREAD_VARS}
    with mock.patch.dict('os.environ', caps), mock.patch.object(base_runner, 'run', side_effect=fake_run), mock.patch.object(runner, 'free_gib', return_value=100.):
        result, _, rec = runner.run_episode({'episode_id': 'unit-limit'}, out, {}, 'memory_v3', prereg_sha256='test')
    handoff = result['controller']['slot_handoff_v3']
    assert handoff is not None
    assert handoff['reason'] == 'external_stop:SIM_LIMIT'
    assert handoff['stage'] == 'outbound' and handoff['attempts'] == 1
    assert handoff['requires_upper_level_decision'] and not handoff['release_started']
    assert json.loads((out/'result.json').read_text())['controller']['slot_handoff_v3'] == handoff
    assert rec['runner_files_sha256']['result.json'] == hashlib.sha256((out/'result.json').read_bytes()).hexdigest()


def test_shared_body_model_matches_calibrated_source_and_door_counterexample():
    from harness.owncam_sweep_collision import BODY_MOUNT_XYZ_M, BODY_COVERAGE_RESIDUAL_M, OwnPose, SweepGuard, body_spheres
    record = json.loads(Path('experiments/2026-09-27-zone-owncam-memory-v3/review3-fixes/body_model_calibration_499e4fd6.json').read_text())
    assert tuple(record['mount_xyz_m']) == BODY_MOUNT_XYZ_M
    assert record['coverage_residual_max_m'] <= BODY_COVERAGE_RESIDUAL_M
    for row in record['rows']:
        assert len(body_spheres(row['servo'], loaded=False)) == row['n_sphere']
    guard = SweepGuard(door_map())
    pose = OwnPose(2.08, .18, 0., 0., 0.)
    servo = {**CARRY_POSTURE, **LOOK_P20, 6: 2030}
    # Review's geometric -27.5 mm, plus guard's 35 mm safety+calibration margin.
    clearance, hit = guard.arm_clearance(servo, pose, loaded=True)
    assert hit == 'wall_divider_2'
    assert clearance == pytest.approx(-.0274568916-.035, abs=1e-8)
    guard.boxes = [b for b in guard.boxes if 'post' in b['id']]
    clearance, hit = guard.arm_clearance(servo, pose, loaded=True)
    assert clearance < 0 and hit is not None


def test_shared_sweep_keeps_safe_pans_and_checks_every_possible_restore():
    from harness.owncam_sweep_collision import OwnPose, SweepGuard, plan_safe_sweep, transition_clear
    pose, smap = OwnPose(2.08, .18, 0., .001, .005), door_map()
    plan = plan_safe_sweep(smap, CARRY_POSTURE, LOOK_P20, WIDE_LOOK_PANS, pose, loaded=True, restore=CARRY_POSTURE)
    assert plan['pans'] and 2030 not in plan['pans']
    guard, prev = SweepGuard(smap), {**CARRY_POSTURE, **LOOK_P20}
    for pan in plan['pans']:
        assert transition_clear(guard, prev, {6: pan}, pose, loaded=True)
        prev[6] = pan
        assert transition_clear(guard, prev, CARRY_POSTURE, pose, loaded=True)
    open_plan = plan_safe_sweep(static_map(), CARRY_POSTURE, LOOK_P20, WIDE_LOOK_PANS,
                                OwnPose(0., 0., 0., .001, .005), loaded=True, restore=CARRY_POSTURE)
    assert open_plan['pans'] == list(WIDE_LOOK_PANS)


def test_transition_collision_between_safe_endpoints_is_rejected():
    from harness.owncam_sweep_collision import OwnPose, SweepGuard, transition_clear
    guard = SweepGuard({})
    # Thin forbidden pan interval between safe endpoints models a post in a sweep.
    guard.arm_clearance = lambda servo, pose, loaded: (-.01 if 1517 <= servo[6] <= 1543 else .1, 'post')
    # Propagate the same oracle to the padded guards used between samples.
    with mock.patch.object(SweepGuard, 'arm_clearance', side_effect=guard.arm_clearance):
        assert not transition_clear(guard, CARRY_POSTURE, {6: 1560}, OwnPose(0., 0., 0., 0., 0.), loaded=True)


def test_no_safe_transition_unknown_pose_or_unsafe_restore_never_falls_back_to_home():
    from harness.owncam_sweep_collision import OwnPose, SweepGuard, plan_safe_sweep
    guard = SweepGuard({})
    pose = OwnPose(0., 0., 0., 0., 0.)
    args = ({}, CARRY_POSTURE, LOOK_P20, [1500])
    assert plan_safe_sweep(*args, None, loaded=True, restore=CARRY_POSTURE)['pans'] == []
    assert plan_safe_sweep(*args, replace(pose, std_xy=-1.), loaded=True, restore=CARRY_POSTURE)['pans'] == []
    # Safe at initial/looking posture but restoring servo 3 into an authored obstruction fails.
    with mock.patch.object(SweepGuard, 'arm_clearance', side_effect=lambda servo, pose, loaded:
                           (-.01 if servo[3] <= 600 else .1, 'wall')):
        plan = plan_safe_sweep(*args, pose, loaded=True, restore={**CARRY_POSTURE, 3: 550}, guard=guard)
    assert not plan['pans'] and plan['reason'] == 'no_clear_pan'


def test_command_guard_rechecks_changed_pose_before_arm_motion():
    leg, loc, est = leg_fixture(True, yaw=.005)
    from tests.test_owncam_memory_v3 import consistent
    consistent(leg.memory.guard, 2.)
    leg.servo = dict(CARRY_POSTURE)
    leg._start_look(2., 'refix')
    assert leg.look_queue
    # Own estimate now puts the robot in a wall, after the sweep was planned.
    est.update(x=2., y=.5, std_xy_m=.001)
    leg.map = door_map()
    commands = leg._arm_step()
    assert leg.outcome == 'look_collision_unverified'
    assert commands == [{'kind': 'hold'}]


@pytest.mark.parametrize('state', ['tentative', 'absent', 'placed'])
def test_slot_and_drive_share_observation_blocking_rule_even_after_expiry(state):
    ctl, now, _, _, _ = saved_place(SAVED[0])
    tr = BoxTrackV3('block', 'red', np.array(ctl.slot_xy), np.eye(2)*.0001, now, 1, 'near', .001)
    ctl.memory.tracks.append(tr)
    tr.state = state
    assert ctl.memory.keepouts()[0]['id'] == tr.track_id
    assert ctl.memory.slot_state(now, ctl.slot_xy, ctl._slot_half())['state'] == 'occupied'
    assert ctl.memory.keepouts(exclude=[tr.track_id]) == []
    tr.slot_blocking = False  # observation-qualified absence is the shared release condition
    assert ctl.memory.keepouts() == []
    assert ctl.memory.slot_state(now, ctl.slot_xy, ctl._slot_half())['state'] != 'occupied'
    tr.slot_blocking, tr.state = True, 'held'
    assert ctl.memory.keepouts() == []
    assert ctl.memory.slot_state(now, ctl.slot_xy, ctl._slot_half())['state'] != 'occupied'


def test_aged_obstacle_actual_planner_does_not_cut_through_it():
    from harness.owncam_drive import LOADED_ENVELOPE
    from harness.map_goto import envelope_overlaps, MARGIN_M, _segment_samples
    ctl, now, xy, _, _ = saved_place(SAVED[0])
    tr = BoxTrackV3('obstacle', 'red', np.array([4.02, -2.5]), np.eye(2)*.0001, now-225., 1, 'far_coarse', .001)
    tr.evidence(now-225., detected=True, range_class='far_coarse', pose_sigma=.02)
    ctl.memory.tracks.append(tr)
    ctl.memory._decay_to(now)
    obstacles = ctl.memory.keepouts()
    path = plan_path(ctl.map, xy[:2], [3.65, -2.5], LOADED_ENVELOPE, obstacles=obstacles)
    # A conservative uncertain obstacle may leave no path; driving through is never allowed.
    if path is not None:
        for a, b in zip(path['waypoints_m'], path['waypoints_m'][1:]):
            for point in _segment_samples(a, b, .01):
                assert not any(envelope_overlaps(point, LOADED_ENVELOPE, obstacle, MARGIN_M) for obstacle in obstacles)


def test_carry_guard_consumes_all_frames_during_look_not_only_controller_ticks():
    ctl, now, _, _, image = saved_place(SAVED[0])
    ctl.slot_inspection = {'stage': 'return'}
    ctl.verification['place']['slot_deadline'] = now+120.
    ctl.leg = SimpleNamespace(state='look_pan')
    ctl.skill.box._carry_previous_image = image
    ctl.skill.box._attachment_image = image
    ctl.pose.last_raw_report = ctl.pose.report(now)
    # Keep the actual comparison/box.decide. A surface-height fit is unrelated
    # here: this scenario isolates attachment preservation over repeated images.
    with mock.patch.object(ctl.pose, 'on_frame', return_value=ctl.pose.report(now)), \
         mock.patch.object(ctl.memory, 'observe_frame'), \
         mock.patch('harness.visual_box_skill.observe_known_box_top', return_value={'visible': False}), \
         mock.patch.object(ctl.skill.box, '_carry', wraps=ctl.skill.box._carry) as carry:
        for n in range(3):
            obs = {**ctl.last_obs, 'frame_id': 8000+n, 'sim_time': now+n*.2}
            ctl.on_frame(now+n*.2, obs, np.zeros((480, 640, 3), np.uint8))
        assert carry.call_count == 3
        ctl._slot_carry_frame(now+.4, obs)
        assert carry.call_count == 3  # decision path cannot consume a frame twice
    assert ctl.outcome is None and ctl.skill.box.phase == 'carry'


def test_stale_roundtrip_frame_holds_until_finite_deadline():
    ctl, now, _, _, _ = saved_place(SAVED[0])
    ctl.slot_inspection = {'stage': 'outbound'}
    ctl.verification['place']['slot_deadline'] = now+120.
    with mock.patch.object(ctl, '_drive_leg') as drive:
        assert ctl.decide(now+1.) == ctl._hold()
        drive.assert_not_called()
    assert ctl.decide(now+120.)['handoff']['reason'] == 'inspection_timeout'


def test_blind_projection_is_clear_and_still_exposes_the_blind_strip():
    from harness.owncam_search_projection_v3 import project_reachable_viewpoint
    from harness.map_goto import envelope_overlaps, authored_obstacles, MARGIN_M
    from harness.owncam_drive import SEARCH_POSE
    ctl = controller()
    projection = project_reachable_viewpoint(ctl.map, [-.47, .75], [-.92, .75], [-.47, .75], UNLOADED_ENVELOPE)
    point = projection['point']
    assert not any(envelope_overlaps(point, UNLOADED_ENVELOPE, o, MARGIN_M) for o in authored_obstacles(ctl.map))
    assert ctl.memory.view.point_in_view((*point, 0.), SEARCH_POSE, False, (-.2, .75, .016))


def test_unreachable_blind_projection_finishes_without_starting_another_leg():
    ctl = controller()
    ctl.viewpoints, ctl.view_index = [(-.47, .75)], 0
    ctl.pose.report = lambda t: report(t, x=-.47, y=.75)
    # Authored wall blocks the entire candidate region west of the current view.
    ctl.map = copy.deepcopy(ctl.map)
    ctl.map['obstacles'].append({'id': 'blocked_retreat', 'center_m': [-.85, 0.],
                                'half_extents_m': [.25, 10.], 'height_m': .4})
    with mock.patch.object(ctl, '_start_leg') as start:
        result = ctl._search_decide(1.)
    assert result['outcome'] == 'SEARCH_BLIND_SPOT_UNREACHABLE'
    start.assert_not_called()


def test_external_finalization_does_not_replace_specific_failure_or_invent_pending_slot():
    from scripts.run_m1_owncam_memory_v3 import finalize_slot_handoff
    specific = {'controller': {'slot_handoff_v3': {'reason': 'cargo_lost'}, 'slot_pending_handoff_v3': {'stage': 'return'}}}
    assert not finalize_slot_handoff(specific)
    assert specific['controller']['slot_handoff_v3']['reason'] == 'cargo_lost'
    assert not finalize_slot_handoff({'outcome': 'SIM_LIMIT', 'controller': {}})
