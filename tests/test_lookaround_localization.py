import math

import numpy as np
import pytest

from harness import zone_pair_highpose_contract as contract
from sim.lookaround_localization import (LookaroundLocalizer, ScriptRunner, look_servo, map_landmarks, rotate_plan,
                                         pan_pulse, LOOK_ARM, VIEW_SETTLE_S)
from sim.visible_belief import odometry


@pytest.fixture(scope='module')
def static():
    return contract.resolve('zone_wide_two_doors_final_v3')[0]


def body(pose, xy):
    dx, dy = xy[0]-pose[0], xy[1]-pose[1]; c, s = math.cos(pose[2]), math.sin(pose[2])
    return [c*dx+s*dy, -s*dx+c*dy]


def test_landmarks_cover_walls_zones_doors(static):
    lms = map_landmarks(static)
    kinds = {l['type'] for l in lms}
    assert kinds == {'wall', 'zone_edge', 'door'}
    assert {l['group'] for l in lms if l['type'] == 'door'} == {'door_narrow', 'door_wide'}
    lo_x, hi_x, lo_y, hi_y = static['bounds_m']
    assert all(lo_x-.05 <= l['xy'][0] <= hi_x+.05 and lo_y-.05 <= l['xy'][1] <= hi_y+.05 for l in lms)


def test_plan_is_deterministic_canonical_and_uses_own_estimate_only(static):
    est = [3.0, .10, -math.pi/2]
    a = LookaroundLocalizer(static, est).make_plan(); b = LookaroundLocalizer(static, est).make_plan()
    assert a == b and a['views']
    pans = [v['pan_deg'] for v in a['views']]
    assert pans == sorted(pans) and a['expected_gain_nats'] > 1
    assert all(500 <= v['pan_pulse'] <= 2500 for v in a['views'])
    other = LookaroundLocalizer(static, [4.6, -.55, math.pi/2]).make_plan()
    assert other['expected_landmarks'] != a['expected_landmarks']        # directions follow the pose estimate and map


def synthetic_detections(loc, truth, pan_deg, rng):
    """What the OpenCV adapters return, generated from the truth pose (test only): wall base points and zone lines."""
    from harness.zone_solo_cyan_landmarks import hue
    walls, floors = [], []
    c, s = math.cos(truth[2]), math.sin(truth[2])
    seen = [l for l in loc.landmarks if loc.visible(truth, 0., pan_deg, l)]
    for l in seen:
        t = (-l['normal'][1], l['normal'][0]) if 'normal' in l else None
        if l['type'] == 'wall':
            for f in np.linspace(-.12, .12, 7):
                walls.append(body(truth, (l['xy'][0]+f*t[0], l['xy'][1]+f*t[1])))
        elif l['type'] == 'zone_edge':
            region = loc.static['regions'][l['group'].split(':')[0]]
            rgba = np.fromstring(region['rgba'], sep=' ') if isinstance(region['rgba'], str) else region['rgba']
            ends = [body(truth, (l['xy'][0]+f*t[0], l['xy'][1]+f*t[1])) for f in (-.09, .09)]
            n = (c*l['normal'][0]+s*l['normal'][1], -s*l['normal'][0]+c*l['normal'][1])
            floors.append({'kind': 'floor_line', 'hue': hue(rgba[:3]), 'endpoints': (np.asarray(ends)+rng.normal(0, .01, (2, 2))).tolist(),
                           'normal': list(n)})
    walls = np.asarray(walls)+rng.normal(0, .01, (len(walls), 2)) if walls else np.zeros((0, 2))
    return walls, floors


@pytest.mark.parametrize('truth', [(4.6, -.55, math.pi/2), (3.0, .10, -math.pi/2)])
def test_grid_update_reduces_error_on_planned_views(static, truth):
    est = [truth[0]+.04, truth[1]-.035, truth[2]+math.radians(1.5)]
    loc = LookaroundLocalizer(static, est); rng = np.random.default_rng(0)
    views = loc.make_plan()['views']
    for view in views:
        walls, floors = synthetic_detections(loc, truth, view['pan_deg'], rng)
        if len(walls) or floors:
            loc._grid_update(walls, floors, {})
    before = math.hypot(est[0]-truth[0], est[1]-truth[1])
    after = math.hypot(loc.own.x[0]-truth[0], loc.own.x[1]-truth[1])
    assert after < before*.75          # zone lines use the existing sigma_line 0.1 m: weaker than walls
    assert abs(loc.own.x[2]-truth[2]) < math.radians(1.5)


def test_rotate_plan_matches_own_odometry_mix():
    plan = rotate_plan(math.radians(90))
    total = sum(odometry(w, d[0])[2] for w, d in plan)
    assert total == pytest.approx(math.radians(90), abs=math.radians(1.5))
    assert all(max(d) <= .15 for _, d in plan)


def test_script_runner_fixed_timing():
    steps = [{'servo': look_servo(-30), 'wait': 1., 'capture': False, 'label': 'arm'},
             {'servo': look_servo(0), 'wait': VIEW_SETTLE_S, 'capture': True, 'label': 'v0'},
             {'servo': look_servo(30), 'wait': VIEW_SETTLE_S, 'capture': True, 'label': 'v1'}]
    servo, shots = [], []
    r = ScriptRunner(steps, 0.); t = 0.
    while not r.done and t < 10:
        r.tick(t, set_servo=lambda s, now: servo.append((round(now, 2), s[6])), set_wheels=None,
               wheels_idle=lambda: True, capture=lambda now: shots.append(round(now, 2)))
        t = round(t+.1, 2)
    assert [p for _, p in servo] == [pan_pulse(-30), 1500, pan_pulse(30)]
    assert shots == [1.8, 2.6] and r.end == pytest.approx(2.6)
    assert all(look_servo(0)[k] == v for k, v in LOOK_ARM.items())
