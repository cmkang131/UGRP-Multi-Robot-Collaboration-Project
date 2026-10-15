"""No physics/render: capability boundary, route, lifecycle and eval counterexamples."""
from copy import deepcopy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from sim.solo_carry_to_zone import CarryToZone, RGBCommandPose, TRAVEL_PHASES, chassis_candidates
from sim.grasp_act_solo_teacher import SoloTeacher, primitives, InputAudit
from sim.grasp_act_solo_evaluation import ZoneScore


def static():
    return {'bounds_m': [-3., 3., -3., 3.], 'obstacles': [], 'regions': {
        'zone_A': {'center_m': [1., 0.], 'half_extents_m': [.5, .5]}}, 'top_cameras': []}


def command(t=0., forward=.35):
    return {'t': t, 'wheels': [forward]*4, 'duration_s': [.1]*4,
            'pwm': {'1': 1500, '3': 500, '4': 2500, '5': 1500, '6': 1500}}


def test_pose_requires_unique_rgb_motion_and_stale_fix_does_not_renew():
    p = RGBCommandPose()
    for i in range(6):
        p.issue(command(), .1)
        p.observe([(1., 1.), (2., 2.)], i*.5)
    assert p.pose is None  # command odometry alone cannot anchor the map
    p = RGBCommandPose()
    for i in range(24):
        p.issue(command(), .1)
        p.observe([(1.+p.odom[0], 1.), (-1., -1.)], i*.1)
    assert p.pose is not None and p.pose[2] == pytest.approx(0.)
    assert p.ready(2.3)
    p.observe([], 4.5)
    assert not p.ready(4.5)
    assert p.last_fix == pytest.approx(2.3)


def test_two_movers_cannot_bootstrap_own_identity():
    p = RGBCommandPose()
    for i in range(24):
        p.issue(command(), .1)
        p.observe([(1.+p.odom[0], 1.), (-1.+p.odom[0], -1.)], i*.1)
    assert p.pose is None


def test_rgb_chassis_group_uses_calibration_and_rejects_compact_box():
    s = static()
    camera = {'name': 'top', 'position_m': [0., 0., 2.], 'quaternion_wxyz': [1, 0, 0, 0], 'fov_y_deg': 60.}
    s['top_cameras'] = [camera]
    frame = np.zeros((480, 640, 3), np.uint8)
    for x, y in ((300, 220), (340, 220), (300, 260), (340, 260)):
        cv2.rectangle(frame, (x-4, y-4), (x+4, y+4), (0, 220, 220), -1)
    cv2.rectangle(frame, (100, 100), (108, 110), (0, 220, 220), -1)
    points = chassis_candidates({'top': cv2.imencode('.jpg', frame)[1].tobytes()}, s)
    assert len(points) == 1 and math.dist(points[0], (0., 0.)) < .01


def localized_map():
    m = CarryToZone(static(), 'A')
    m.loc.pose = [-1., 0., 0.]; m.loc.last_fix = 0.
    return m


def test_route_stops_on_missing_pose_blocked_goal_and_stale_rgb():
    m = CarryToZone(static(), 'A'); m.start(0., (.2, 0.))
    assert m.step(0.)[2] == 'carry_self_pose_unavailable'
    m = localized_map(); m.start(0., (.2, 0.))
    assert m.path and m.slot is not None
    assert m.step(2.1)[2] == 'carry_self_pose_stale'
    s = static(); s['obstacles'] = [{'id': 'zone_wall', 'center_m': [1., 0.], 'half_extents_m': [1., 1.]}]
    m = CarryToZone(s, 'A'); m.loc.pose = [-2., 0., 0.]; m.loc.last_fix = 0.
    m.start(0., (.2, 0.)); assert m.failure == 'carry_no_static_route'


def make_teacher(carry=None, enabled=True):
    ops = primitives()
    return SoloTeacher('cyan', 'west', ops.folded, profile='solo_visible_only_v1',
        held_object_hidden_v1=True, rgb_lift_mode='solo_lift_lookback_v1',
        solo_carry_to_zone_v1=enabled, carry=carry, ops=ops)


def prepared_teacher(carry):
    t = make_teacher(carry)
    t.low, t.high, t.descent = t._pick_geometry({'xyz': [.203, 0., .024], 'yaw': 0.})
    t.phase = 'hold'; t.phase_t = -3.; t.skill_started = -10.; t.holding = True
    t.verify_t = -4.
    t.sink.pwm.update({1: 1500, **t.high})
    t.arm.commanded.update(t.sink.pwm)
    return t


def test_default_off_and_held_measurement_rejected_at_carry_boundary():
    with pytest.raises(ValueError, match='requires box'):
        make_teacher()
    t = make_teacher(localized_map(), enabled=False)
    assert t.carry is None
    t = prepared_teacher(localized_map())
    t.step(0., rgb_holding='yes')
    assert t.phase == 'carry_prepare' and t.holding
    with pytest.raises(ValueError, match='held target'):
        t.step(.1, measurement={'xyz': [9., 9., .024], 'yaw': 0.})
    a = InputAudit()
    assert a.measure('carry_to_zone', visible_n=9, probe_N=9, holding=True,
                     read_relative=lambda: pytest.fail('held world read')) is None


def test_full_carry_to_new_zone_lifecycle_keeps_travel_out_of_local_labels():
    m = localized_map(); t = prepared_teacher(m)
    saw = set()
    for i in range(600):
        now = i*.1
        # Sensor substitute only: the map estimate reaches its planned stand-off.
        # No physics or evaluation success is supplied to the teacher.
        m.loc.last_fix = now
        if t.phase == 'carry_to_zone':
            m.loc.pose = [*m.goal, 0.]
        _, done = t.step(now, rgb_holding='yes', place_visible=True)
        saw.add(t.phase)
        if t.phase in TRAVEL_PHASES:
            assert not t.context(now)['local_skill_sample']
        if t.phase in ('zone_place_view', 'zone_place_advance', 'lower', 'open'):
            assert t.context(now)['local_skill_sample'] and t.skill == 'release'
        if done:
            break
    assert done and {'carry_to_zone', 'zone_place_view', 'zone_place_advance', 'lower', 'open', 'backoff'} <= saw
    assert 'lookback_return' not in saw and not t.holding
    assert t.diagnostic()['physical_success'] is None


def test_destination_floor_must_be_seen_before_lowering():
    m = localized_map(); t = prepared_teacher(m)
    t.phase = 'zone_place_view'; t.phase_t = 0.; t.skill = 'release'
    for i in range(32):
        t.step(i*.1, place_visible=False)
    assert t.result == 'destination_floor_not_visible'
    assert not any(e['to'] in ('lower', 'open') for e in t.events)


@pytest.mark.parametrize('zone,hue', [('A', 12), ('B', 110), ('C', 145)])
def test_real_own_fk_floor_mask_requires_destination_paint(zone, hue):
    s = static(); s['regions']['zone_'+zone] = s['regions']['zone_A']
    m = CarryToZone(s, zone)
    t = make_teacher(m)
    t.low, t.high, _ = t._pick_geometry({'xyz': [.203, 0., .024], 'yaw': 0.})
    from harness.visual_arm_v3 import forward_grip
    m.grip_xy = forward_grip({1: 1500, **t.low})[:2]; m.slot = (1., 0.)
    pwm = {1: 1500, **t.high}
    colour = cv2.cvtColor(np.uint8([[[hue, 180, 180]]]), cv2.COLOR_HSV2BGR)[0, 0]
    assert m.place_visible(np.full((480, 640, 3), colour, np.uint8), pwm, t.low, 'cyan')
    assert not m.place_visible(np.zeros((480, 640, 3), np.uint8), pwm, t.low, 'cyan')


def score_run(*, boundary=False, drop=False, tilt=False, contact=False):
    s = ZoneScore({'center_m': [1., 0.], 'half_extents_m': [.3, .3]})
    for i in range(90):
        release = i >= 60
        phase = 'open' if release else 'carry_to_zone' if i >= 35 else 'hold'
        min_z = 0. if release or (drop and i == 45) else .03
        s.add(i*.1, phase=phase, footprint_xy=[(1.31 if boundary else 1.02, .02), (.98, -.02)],
              min_z=min_z, support_z=0., tilt_deg=4. if tilt and release else 0.,
              finger_forces=[1., 1.] if not release or contact else [0., 0.],
              speed=0., open_issued=release, placement_offset=2., weld_active=False)
    return s.record(True)


def test_new_zone_success_ignores_pickup_offset_but_checks_retention_whole_footprint_and_release():
    good = score_run()
    assert good['physical_success'] and good['no_drop_during_carry']
    assert good['carry_sim_s'] > 0 and good['task_sim_s'] == pytest.approx(8.9)
    for kw in ({'boundary': True}, {'drop': True}, {'tilt': True}, {'contact': True}):
        assert not score_run(**kw)['physical_success']
    assert not score_run(drop=True)['no_drop_during_carry']


def test_fresh_plan_and_queue_are_v6_balanced_disabled_and_truth_free():
    from scripts.make_solo_carry_plan import prepare, queue
    from scripts.run_solo_grasp_act_teacher import validate_carry
    from harness.grasp_act_seed_splits import registry, split_of
    p = prepare(); q = queue(p, 'f'*40, 123)
    assert p['distribution'] == dict.fromkeys(('cyan', 'red', 'green', 'yellow'), 2)
    for e in p['episodes']:
        assert e['scenario_id'].endswith('_v6') and 'handoff_pose_error' not in e
        assert split_of(e['seed'], registry()) == 'solo_carry_diagnostic_v1'
        validate_carry(e, enabled=True, training_rgb=False, truth_free=True, lift='solo_lift_lookback_v1', negative=False)
        for change in ({'enabled': False}, {'training_rgb': True}, {'truth_free': False}):
            args = dict(enabled=True, training_rgb=False, truth_free=True, lift='solo_lift_lookback_v1', negative=False)
            with pytest.raises(ValueError):
                validate_carry(e, **{**args, **change})
    assert not q['runs_enabled'] and not q['coordinator_approval']['approved']
    assert q['gate_promotion_authorized_if_all_conditions_pass'] is False
    assert len(q['runs']) == 8 and all(not r['enabled'] and '--training-rgb' not in r['command'] for r in q['runs'])


def test_recorder_destination_and_local_labels_follow_carry_boundary(tmp_path):
    from harness.grasp_act_solo_recording import SoloRecorder
    from scripts.make_solo_carry_plan import prepare
    p = prepare()['episodes'][0]
    c = command()
    recorder = SoloRecorder(tmp_path, p, c, handoff=lambda *a: .4)
    frame = np.full((480, 640, 3), 90, np.uint8)
    jpg = cv2.imencode('.jpg', frame)[1].tobytes()
    phases = ('approach', 'carry_prepare', 'carry_to_zone', 'zone_place_view', 'zone_place_advance', 'lower')
    for i, phase in enumerate(phases):
        skill = 'release' if i >= 3 else 'grasp'
        recorder.observe(i*.1, jpg, frame, skill=skill, phase=phase, previous=c)
        c = {**c, 't': i*.1}
        recorder.target(c, skill_after=skill, phase_after=phase, complete=False)
    recorder.close()
    labels = [json.loads(s) for s in (tmp_path/'teacher-r1.jsonl').read_text().splitlines()]
    assert [r['local_skill_sample'] for r in labels] == [True, False, False, True, True, True]
    assert [r['segment'] for r in labels] == ['approach', 'carry', 'carry', 'release', 'release', 'release']
    rows = [json.loads(s) for s in (tmp_path/'student-r1.jsonl').read_text().splitlines()]
    assert all(r['destination_zone'] == p['destination_zone'] for r in rows[3:])
    assert all('pose_estimate' not in r and 'map_rgb' not in r for r in rows)


def test_zero_force_contact_is_not_gripper_detachment():
    s = ZoneScore({'center_m': [1., 0.], 'half_extents_m': [.3, .3]})
    for i in range(90):
        release = i >= 60
        s.add(i*.1, phase='open' if release else 'carry_to_zone', footprint_xy=[(1., 0.)],
              finger_contacts=True, min_z=0. if release else .03, support_z=0., tilt_deg=0.,
              finger_forces=[0., 0.] if release else [1., 1.], speed=0., open_issued=release,
              placement_offset=2., weld_active=False)
    assert not s.record(True)['zone_placement_success']


def test_disabled_recording_profile_preserves_pickup_site_destination(tmp_path):
    from harness.grasp_act_solo_recording import SoloRecorder
    p = {'episode_id': 'legacy', 'robot_id': 'r1', 'kind': 'cyan', 'role': 'west', 'destination_zone': 'A'}
    c = command()
    recorder = SoloRecorder(tmp_path, p, c)
    frame = np.full((480, 640, 3), 90, np.uint8)
    row = recorder.observe(0., cv2.imencode('.jpg', frame)[1].tobytes(), frame,
                           skill='release', phase='lower', previous=c)
    recorder.target(c, skill_after='release', phase_after='lower', complete=False)
    recorder.close()
    assert row['destination_zone'] == 'pickup_site'
