"""Carry4 counterexamples. Pure geometry/RGB/commands; no physics or rendering."""
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from sim.solo_carry_pose import CommandPose, task_start
from sim.solo_carry_obstacles import RGBObstacleMemory, detections, held_mask
from tests.test_grasp_act_solo_carry import command, localized_map, static, make_teacher


def test_parking_rejects_reported_bad_positions_and_all_new_plans_clear():
    from scripts.make_solo_teacher_plan import parking_clear, carry_parking_constraints
    from scripts.make_solo_carry_plan import prepare
    from harness.zone_final_environment import resolve
    from harness.static_keepouts import rect_distance, keepout_rects
    plan = prepare()
    for e in plan['episodes']:
        s = resolve(e['map_id'])[0]
        cfg = e['parking_check']
        assert cfg['path_clearance_m'] == pytest.approx(.59)
        assert cfg['region_clearance_m'] == pytest.approx(.33)
        for rid in ('r2', 'r3'):
            p = e['spawns'][rid][:2]
            assert parking_clear(p, cfg)
            assert all(rect_distance(p, r) >= .18 for r in keepout_rects(s, perimeter=True))
        for p in ((4.87, -2.41), (2.88, -.21), (4.1, -2.1), (1.32, -2.25)):
            assert not parking_clear(p, cfg)
    # A parking plan cannot quietly claim a carry route through a 0.50 m door
    # with the unchanged 0.52 m diameter envelope.
    s = resolve('zone_wide_door_geometry_v3')[0]
    with pytest.raises(ValueError, match='narrower'):
        carry_parking_constraints(s, (-.7, -.85), (.2, -2.45), 'B')


def test_memorized_pre_lift_obstacle_changes_route_and_unseen_is_not_free():
    m = localized_map()
    m.start(0., (.2, 0.))
    direct = m.path
    memory = m.obstacles
    memory.update([dict(kind='robot', xy=[.85, 0.], radius=.17, range_error_m=.03)],
                  m.loc.pose, 0.)
    memory.update([], m.loc.pose, 30., holding=True, kind='cyan', grip_xy=(.2, 0.))
    assert len(memory.discs(30.)) == 1
    m.path = None; m.loc.now = 30.; m.start(30., (.2, 0.))
    assert m.path and m.path != direct
    from sim.grasp_act_visible_route import segment_free
    assert all(segment_free(a, b, memory.discs(30.), m.rects, m.radius)
               for a, b in zip(m.path, m.path[1:]))
    # A newly observed peer occupying the actual stand-off must stop arrival.
    memory.update([dict(kind='robot', xy=[m.goal[0]+1., m.goal[1]], radius=.17, range_error_m=.03)],
                  m.loc.pose, 30.)
    assert m.step(30.) == ((0., 0., 0.), False, 'carry_goal_obstructed')


def test_only_held_track_removed_and_same_colour_peer_cargo_survives():
    mem = RGBObstacleMemory()
    obs = [dict(kind='cyan', xy=[x, 0.], radius=.03, range_error_m=.01) for x in (.2, .8)]
    mem.update(obs, (0., 0., 0.), 0.)
    mem.update([], (0., 0., 0.), 1., holding=True, kind='cyan', grip_xy=(.2, 0.))
    assert [t['xy'] for t in mem.tracks] == [[.8, 0.]]
    mem.update([dict(kind='robot', xy=[1., .3], radius=.17, range_error_m=.05)],
               (0., 0., 0.), 2., holding=True, kind='cyan', grip_xy=(.2, 0.))
    assert {t['kind'] for t in mem.tracks} == {'cyan', 'robot'}


def colour_shape(frame, pwm, xyz, dims, hue):
    from sim.grasp_act_solo_lookback import project
    points = np.array([[xyz[0]+a, xyz[1]+b, xyz[2]+c]
                       for a in (-dims[0]/2, dims[0]/2) for b in (-dims[1]/2, dims[1]/2)
                       for c in (-dims[2]/2, dims[2]/2)])
    uv, front = project(points, pwm)
    assert front.all()
    color = cv2.cvtColor(np.uint8([[[hue, 210, 180]]]), cv2.COLOR_HSV2BGR)[0, 0]
    cv2.fillConvexPoly(frame, cv2.convexHull(np.rint(uv).astype(np.int32)), color.tolist())


def test_actual_rgb_detector_sees_box_and_robot_without_scene_state():
    from sim.grasp_act_solo_teacher import primitives
    ops = primitives(); pwm = ops.gaze((.8, 0., 0.), ops.folded)
    frame = np.full((480, 640, 3), 100, np.uint8)
    colour_shape(frame, pwm, (.8, -.12, .016), (.034, .040, .032), 0)
    colour_shape(frame, pwm, (1.1, .18, .09), (.25, .20, .06), 20)
    obs, mask = detections(frame, pwm)
    assert mask == 0 and {'red', 'robot'} <= {o['kind'] for o in obs}
    assert any(math.dist(o['xy'], (.8, -.12)) < .15 for o in obs if o['kind'] == 'red')
    assert any(math.dist(o['xy'], (1.1, .18)) < .25 for o in obs if o['kind'] == 'robot')
    assert detections(np.zeros_like(frame), pwm)[0] == []


def test_held_rgb_mask_is_local_and_other_same_colour_remains(monkeypatch):
    from sim.grasp_act_solo_teacher import primitives
    ops = primitives(); pwm = ops.gaze((.8, 0., 0.), ops.folded)
    frame = np.full((480, 640, 3), 100, np.uint8)
    colour_shape(frame, pwm, (.8, -.12, .016), (.034, .040, .032), 90)
    colour_shape(frame, pwm, (.8, .12, .016), (.034, .040, .032), 90)
    obs, _ = detections(frame, pwm)
    assert len([o for o in obs if o['kind'] == 'cyan']) == 2
    one = next(o for o in obs if o['kind'] == 'cyan')
    x, y, w, h = one['pixel_bbox']; mask = np.zeros((480, 640), bool)
    mask[y-3:y+h+3, x-3:x+w+3] = True
    monkeypatch.setattr('sim.solo_carry_obstacles.held_mask', lambda *a: mask)
    remaining, _ = detections(frame, pwm, held_kind='cyan', grasp_pwm=pwm)
    assert len([o for o in remaining if o['kind'] == 'cyan']) == 1


def test_real_held_mask_uses_only_command_geometry():
    t = make_teacher(localized_map())
    low, high, _ = t._pick_geometry({'xyz': [.203, 0., .024], 'yaw': 0.})
    mask = held_mask('cyan', {1: 1500, **low}, {1: 1500, **high})
    assert mask.dtype == bool and 0 < mask.sum() < mask.size


def propagate(schedule):
    p = CommandPose(task_start(static()))
    for dt in schedule:
        issued = command(p.now); issued['duration_s'] = [dt]*4
        p.issue(issued, dt)
    return p


def test_actual_irregular_tick_integration_and_correlated_budget():
    a = propagate([.08, .12]*40)
    b = propagate([.1]*80)
    np.testing.assert_allclose(a.pose, b.pose, atol=1e-10)
    np.testing.assert_allclose(a.sigmas(), b.sigmas(), atol=1e-10)
    assert a.last_dt == .12 and a.ready(a.now)
    # Within the diagnostic's 300 seconds the guard now stops issued travel.
    c = propagate([.1]*150)
    assert not c.ready(c.now)
    assert c.record()['uncertainty_calibrated'] is False
    # A finite duty pulse expires, even if the next tick arrives late.
    p = CommandPose(task_start(static())); q = CommandPose(task_start(static()))
    p.issue(command(), .2); q.issue(command(), .1)
    np.testing.assert_allclose(p.pose, q.pose)
    assert p.now == .2
    with pytest.raises(ValueError, match='actual tick'):
        p.issue(command(0.), .1)


def test_rotation_budget_stops_and_only_accepted_fix_resets_it():
    p = CommandPose(task_start(static()))
    for i in range(150):
        c = command(p.now); c['wheels'] = [-.35, .35, -.35, .35]
        p.issue(c, .1)
        if not p.ready(p.now):
            break
    assert i < 149 and not p.ready(p.now)
    before = p.sigmas()
    p.observe_own(np.zeros((480, 640, 3), np.uint8), p.now, camera='r1/robot_cam')
    assert p.sigmas() == before and p.fixes == 0
    p.accepted_fix(p.now)
    assert p.ready(p.now) and p.fixes == 1


def test_grid_acceptance_rejects_one_wall_outliers_and_large_innovation():
    from sim.lookaround_localization import LookaroundLocalizer
    from harness.zone_final_environment import resolve
    loc = LookaroundLocalizer(resolve('zone_wide_two_doors_final_v3')[0], [0., 0., 0.])
    prior, cov = loc.own.x.copy(), loc.own.P.copy()
    loc.own.P = cov*.5
    # Two perpendicular wall faces, multiple samples per face, full pose rank.
    west = [l for l in loc.landmarks if l['group'] == 'wall_west:e'][:4]
    south = [l for l in loc.landmarks if l['group'] == 'wall_south:n'][:4]
    assert west and south
    walls = np.array([l['xy'] for l in west+south])
    assert loc.fix_acceptance(walls, [], [], prior, cov)['accepted']
    assert not loc.fix_acceptance(walls[:4], [], [], prior, cov)['accepted']
    assert not loc.fix_acceptance(walls+100., [], [], prior, cov)['accepted']
    assert not loc.fix_acceptance(walls, [], [], prior+np.array([2., 0., 0.]), cov)['accepted']


def test_rejected_grid_cannot_change_pose_covariance_or_fix_time():
    from sim.grasp_act_solo_teacher import primitives
    from sim.grasp_act_solo_lookaround import SoloLookaround
    from harness.zone_final_environment import resolve
    s = resolve('zone_wide_two_doors_final_v3')[0]; p = CommandPose(task_start(s)); ops = primitives()
    look = SoloLookaround(s, ops=ops, truth_free_v1=True, command_pose=p); look.arm()
    before, covariance = p.own.x.copy(), p.own.P.copy()
    def bad_observation(*a):
        p.own.x[:] = 99.; p.own.P[:] = 0.
        return {'status': 'measured', 'grid': {'poses': 400}, 'fix_acceptance': {'accepted': False}}
    look.loc.observe = bad_observation; look.start(0., 1500); pwm = dict(ops.folded)
    for i in range(400):
        cmd, done = look.step(i*.1, pwm, lambda: np.zeros((480, 640, 3), np.uint8))
        pwm.update({int(k): v for k, v in cmd['pwm'].items()})
        if done: break
    assert look.measured_views > 0 and p.fixes == 0 and p.last_fix is None
    np.testing.assert_array_equal(p.own.x, before); np.testing.assert_array_equal(p.own.P, covariance)


def test_de8c2412_search_fov_covers_far_cells_and_minus54_degrees():
    from scripts.audit_solo_pickup_search import scan_views, projection
    from harness.zone_final_environment import resolve
    s = resolve('zone_wide_door_geometry_v3')[0]
    pose = task_start(s)['pose_m_rad']; views = scan_views(s)
    assert max(math.dist(pose[:2], v['floor_xy']) for v in views) > 2.8
    for v in views:
        assert projection([[*v['floor_xy'], 0.]], pose, v['pwm'], margin=8.)['in_frame_n'] == 1
    target = [pose[0]+2.3*math.cos(math.radians(-54)), pose[1]+2.3*math.sin(math.radians(-54)), .016]
    assert any(projection([target], pose, v['pwm'], margin=8.)['in_frame_n'] for v in views)


def off_trace(teacher_class):
    from sim.grasp_act_solo_teacher import primitives
    ops = primitives()
    teacher = teacher_class('cyan', 'west', ops.folded, profile='solo_visible_only_v1',
                            held_object_hidden_v1=True, ops=ops)
    rows = []
    for i in range(900):
        target = None if teacher.holding else {'xyz': [ops.station, 0., .024], 'yaw': 0.}
        cmd, done = teacher.step(i*.1, measurement=target, rgb_holding='yes')
        teacher.remember_applied(cmd)
        rows.append([cmd, teacher.context(i*.1), teacher.diagnostic()])
        if done: break
    assert done
    return json.dumps(rows, allow_nan=False).encode()


def test_default_off_actions_and_records_match_pre_carry_bytes():
    from sim.grasp_act_solo_teacher import SoloTeacher
    fixture = json.loads(Path('tests/fixtures/solo_carry4_off.json').read_text())
    assert hashlib.sha256(off_trace(SoloTeacher)).hexdigest() == fixture['sha256']
    from sim.grasp_act_solo_lookaround import SoloLookaround
    from types import SimpleNamespace
    look = SoloLookaround({}, ops=None, localizer_factory=lambda *a: None, runner_factory=lambda *a: None)
    look.loc = SimpleNamespace(record=lambda: {'test': 'legacy'})
    assert json.dumps(look.record()) == fixture['lookaround_record']
