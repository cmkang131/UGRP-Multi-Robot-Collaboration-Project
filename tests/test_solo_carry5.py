"""Carry5: real v4 map/commands plus narrow counterexamples; never physics/render."""
import json
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.audit_solo_carry5 import PLAN, PROFILE, issue, map_controller, replay
from sim.grasp_act_solo_lookaround import SoloLookaround
from sim.grasp_act_solo_teacher import SoloTeacher, primitives
from sim.solo_carry_obstacles import RGBObstacleMemory, PEER_DISC_MAX_M, detections
from sim.solo_carry_pose import CommandPose, task_start
from tests.test_grasp_act_solo_carry import static
from sim.solo_carry_to_zone import CarryToZone

EPISODES = json.loads(PLAN.read_text())['episodes']


@pytest.mark.parametrize('episode', EPISODES, ids=lambda e: str(e['seed']))
def test_actual_v4_command_route_preempts_guard_and_plans_landmark_views(episode):
    # No planner or controller stub, no fabricated pose fix, no physical success assertion.
    row = replay(episode)
    assert row['reason'] == 'pose_budget'
    assert row['hard_guard_open']
    assert row['planned_landmark_views'] > 0
    assert row['planned_landmark_groups']
    assert row['accepted_rgb_fixes'] == 0
    assert row['no_fix_outcome'] == 'carry_relocalization_unconfirmed'


def test_last_accepted_fix_is_only_budget_epoch():
    p = CommandPose(task_start(static()))
    for i in range(60):
        p.issue({'t': p.now, 'wheels': [.35]*4, 'duration_s': [.1]*4}, .1)
    old = p.distance_since_fix
    p.observe_own(np.zeros((480, 640, 3), np.uint8), p.now, camera='r1/robot_cam')
    assert p.distance_since_fix == old
    # Explicit accepted-update port, separate from receiving a frame or starting a skill.
    p.accepted_fix(p.now)
    at = p.now
    p.issue({'t': p.now, 'wheels': [.35]*4, 'duration_s': [.1]*4}, .1)
    assert 0 < p.distance_since_fix < old/10
    assert p.last_fix == at
    assert p.record()['command_only_age_s'] == pytest.approx(.1)


def test_heading_hold_uses_sideways_drive_without_waypoint_turns():
    m = map_controller(EPISODES[0], True)
    for target in [(0., 1.), (-1., 0.), (0., -1.)]:
        drive = m.heading_drive((0., 0., 0.), target, 0.)
        assert drive[2] == 0 and any(drive[:2])


def test_no_route_requests_observation_instead_of_zero_forever():
    m = map_controller(EPISODES[0], True)
    m.rects = [(-.2, -.85, .05, 10., 0.)]
    assert m.pickup_route((1., 0., 0.), (1.2, 0.), 'cyan', 0.) == (0., 0., 0.)
    assert m.recovery_reason == 'pickup_no_route'
    assert not m.failure


def test_newly_blocked_destination_reselects_other_reachable_slot():
    m = CarryToZone(static(), 'A', start=task_start(static()), recovery_profile=PROFILE)
    m.start(0., (.2, 0.)); old = m.goal
    # Compact obstacle covers this slot but leaves another stand-off candidate reachable.
    m.obstacles.update([dict(kind='red', xy=[old[0]-m.loc.pose[0], old[1]], radius=.015, range_error_m=.01)],
                       m.loc.pose, 0.)
    drive, arrived, failed = m.step(0.)
    assert not failed and m.recovery_reason is None
    assert m.goal != old and not arrived


def ob(x, y=0., kind='cyan', error=.38):
    return dict(kind=kind, xy=[x, y], radius=.03, range_error_m=error)


def test_uncertainty_association_and_visible_miss_deletion_not_blind_age():
    m = RGBObstacleMemory(managed=True)
    m.update([ob(1.)], (0., 0., 0.), 0., pose_sigma=(.1, .1, .05))
    m.update([ob(1.35)], (0., 0., 0.), .5, pose_sigma=(.1, .1, .05))
    assert len(m.tracks) == 1 and m.tracks[0]['hits'] == 2
    m.update([], (0., 0., 0.), 100.)
    assert len(m.tracks) == 1
    tid = m.tracks[0]['id']
    for at in (101., 101.5, 102.):
        m.update([], (0., 0., 0.), at, clear_ids=[tid])
    assert not m.tracks and m.deleted[-1]['reason'] == 'three_clear_own_rgb_views'


def test_same_frame_tracks_and_other_target_never_all_removed():
    m = RGBObstacleMemory(managed=True)
    m.update([ob(.4, error=.08), ob(.9, error=.08), ob(.4, .3, 'red')], (0., 0., 0.), 0.)
    assert len(m.tracks) == 3
    discs = m.pickup_discs(0., (0., 0., 0.), 'cyan', (.23, 0.))
    assert len(discs) == 2  # .17m target discrepancy exceeds old .12m rule
    assert any(d[1] == .3 for d in discs)
    m.reanchor((0., 0., 0.), (.2, .1, math.pi/2))
    np.testing.assert_allclose(m.tracks[0]['xy'], (.2, .5))


def test_floor_or_yellow_patch_alone_cannot_be_robot_in_carry5():
    from tests.test_solo_carry4 import colour_shape
    ops = primitives(); pwm = ops.gaze((.8, 0., 0.), ops.folded)
    for hue in (12, 27):
        frame = np.full((480, 640, 3), 140, np.uint8)
        colour_shape(frame, pwm, (1.1, .18, .09), (.25, .20, .06), hue)
        assert not any(o['kind'] == 'robot' for o in detections(frame, pwm, managed=True)[0])


def test_carry5_parking_uses_controller_worst_supported_disc():
    from scripts.make_solo_teacher_plan import parking_clear
    plan = json.loads(Path('experiments/2026-10-15-map-carry-zone/diagnostic-plan-v5.json').read_text())
    assert len(plan['episodes']) == 8
    for e in plan['episodes']:
        cfg = e['parking_check']
        assert cfg['path_clearance_m'] >= .26+PEER_DISC_MAX_M
        assert all(parking_clear(e['spawns'][rid][:2], cfg) for rid in ('r2', 'r3'))
        assert e['carry5_profile'] == PROFILE


def recovery_teacher(*, holding=False):
    m = map_controller(EPISODES[0], True); ops = primitives()
    look = SoloLookaround(m.static, ops=ops, truth_free_v1=True, command_pose=m.loc, carry5=True)
    t = SoloTeacher('cyan', 'west', ops.folded, profile='solo_visible_only_v1',
        held_object_hidden_v1=True, setdown_lookaround_v1=True, lookaround=look,
        rgb_lift_mode='solo_lift_lookback_v1', solo_carry_to_zone_v1=True, carry=m, ops=ops)
    t.phase = 'carry_to_zone' if holding else 'approach'; t.phase_t = 0.; t.skill_started = 0.
    t.holding = holding
    t.low, t.high, _ = t._pick_geometry({'xyz': [.203, 0., .024], 'yaw': 0.})
    if holding:
        # A nominal free station on the real v4 map, counterexample initial condition only.
        m.loc.own.x[:2] = [.2, -2.45]
        t.sink.pwm.update({1:1500, **t.high}); t.arm.commanded.update(t.sink.pwm)
    m.request_recovery(0., 'test_no_route')
    return t, m, look


def test_unloaded_real_lookaround_blank_rgb_rejects_and_does_not_resume():
    t, m, look = recovery_teacher()
    for i in range(500):
        now = i*.1
        if i:
            m.issue(cmd, .1)
        cmd, _ = t.step(now, own_rgb=lambda: np.zeros((480, 640, 3), np.uint8))
        if t.result:
            break
    assert any(e['event']=='view' for e in look.events)
    assert m.loc.fixes == 0
    assert t.result == 'carry_relocalization_unconfirmed'


def test_held_recovery_releases_then_actually_looks_and_keeps_truth_hidden():
    t, m, look = recovery_teacher(holding=True)
    phases = []
    for i in range(600):
        if i:
            m.issue(cmd, .1)
        cmd, _ = t.step(i*.1, own_rgb=lambda: np.zeros((480, 640, 3), np.uint8))
        phases.append(t.phase)
        if t.phase.startswith('carry_recover_') or t.phase == 'carry_reobserve':
            assert not t.context(i*.1)['local_skill_sample']
        if t.result:
            break
    assert 'carry_recover_open' in phases and 'carry_reobserve' in phases
    assert any(e['event']=='view' for e in look.events)
    assert t.result == 'carry_relocalization_unconfirmed' and not t.holding


def test_disabled_queue_flags_and_pilot_barrier(tmp_path):
    from scripts.make_solo_carry_plan import queue
    path = Path('experiments/2026-10-15-map-carry-zone/diagnostic-plan-v5.json')
    q = queue(json.loads(path.read_text()), 'a'*40, 505, plan_path=path)
    assert not any(q[k] for k in ('ready', 'approved', 'runs_enabled'))
    assert q['max_parallel'] == 1 and len(q['runs']) == 8
    assert all(not r['enabled'] and not r['ready'] and not r['approved'] for r in q['runs'])
    assert q['execution_stages'][0]['indices'] == [0]
    assert q['execution_stages'][1]['indices'] == list(range(1,8))


def test_actual_feature_acceptance_resets_epoch_and_reopens_route_without_truth():
    from sim.lookaround_localization import LookaroundLocalizer
    m = map_controller(EPISODES[0], True)
    loc = LookaroundLocalizer(m.static, m.loc.pose)
    # Known static landmark residual fixture: not a simulated camera or success report.
    loc.own = m.loc.own
    m.loc.distance_since_fix = 1.4
    m.request_recovery(0., 'pose_budget')
    prior = loc.own.x.copy(); cov = np.diag(np.square(m.loc.sigmas()))
    loc.own.P = cov*.5
    walls = np.array([l['xy'] for l in loc.landmarks if l['group'] in ('wall_west:e', 'wall_south:n')])
    x, y, a = prior; c, s = math.cos(a), math.sin(a)
    relative = (walls-np.array([x, y]))@np.array([[c, -s], [s, c]])
    assert loc.fix_acceptance(relative, [], [], prior, cov)['accepted']
    m.loc.accepted_fix(0.)
    assert m.finish_recovery(0., 0)
    assert m.loc.distance_since_fix == 0 and m.recovery_reason is None
    assert m.recovery_events[-1]['event'] == 'accepted_replan'


def test_controlled_setdown_is_not_reported_as_uninterrupted_carry():
    from sim.grasp_act_solo_evaluation import ZoneScore
    score = ZoneScore(static()['regions']['zone_A'], active_recovery=True)
    row = dict(min_z=0., support_z=0., tilt_deg=0., finger_forces=(0.,0.), speed=0.,
               open_issued=True, placement_offset=0., weld_active=False)
    for i, phase in enumerate(('carry_recover_lower', 'carry_recover_lower', 'carry_recover_open')):
        score.add(i*.1, phase=phase, footprint_xy=[], **row)
    result = score.record(False)
    assert result['intermediate_controlled_setdowns'] == 1
    assert not result['uninterrupted_carry'] and not result['physical_success']
