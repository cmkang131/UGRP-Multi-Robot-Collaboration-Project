"""Glue for the post-set-down look-around (``setdown_lookaround_v1``) in the crate teacher.

The view planner and the EKF are Opus' ``sim.active_lookaround`` (PR #491 work, imported
lazily: it is uncommitted/unmerged when this file was written, so the toggle raises a clear
error if it is missing). This module only supplies what that interface asks for:
- static-map landmarks (wall-rectangle corners, door posts, zone corners),
- a visibility predictor built from the own pose estimate, issued pan/yaw and a nominal
  camera cone (no simulator state),
- wheel pulses for a body rotation (nominal turn rate, issued commands only),
- the pan servo pulse for a pan angle.
No simulator import. Truth only enters the runner, which gates which landmarks are really
visible (ray check) and supplies their body-frame bearings; truth also scores the pose
error before and after, in evaluation-only fields.
"""
from __future__ import annotations
import importlib
import math
from harness.visual_arm import PULSE_PER_DEGREE

CAMERA_HALF_FOV_RAD = math.radians(35.)   # conservative cone inside the calibrated image (cf. sim/grasp_act_visible_gaze)
MAX_RANGE_M = 4.
DWELL_S = .8
TURN_LEVEL = .35
PULSE_S = .1
NOMINAL_YAW_RATE = .35        # rad/s at wheel level .35 (sim/visible_belief provisional value; free robot unmeasured)


def load_module():
    try:
        return importlib.import_module('sim.active_lookaround')
    except ImportError as error:   # pragma: no cover - environment dependent
        raise RuntimeError('setdown_lookaround_v1 needs sim/active_lookaround.py (not in this tree)') from error


def landmarks_from_map(static):
    """Static-map landmarks: wall-rectangle corners, door posts, zone corners (world xy)."""
    out = []
    for o in static.get('obstacles', ()):
        (cx, cy), (hx, hy) = o['center_m'], o['half_extents_m']
        if o.get('kind') == 'wall':
            for k, (sx, sy) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
                out.append({'id': f"{o['id']}#c{k}", 'type': 'wall_corner', 'xy': (cx+sx*hx, cy+sy*hy)})
    for p in static.get('passages', ()):
        (cx, cy), (hx, hy) = p['center_m'], p['half_extents_m']
        if p.get('axis') == 'x':      # opening along y: posts at the two y ends
            out += [{'id': f"{p['id']}#a", 'type': 'door_post', 'xy': (cx, cy-hy)},
                    {'id': f"{p['id']}#b", 'type': 'door_post', 'xy': (cx, cy+hy)}]
        else:
            out += [{'id': f"{p['id']}#a", 'type': 'door_post', 'xy': (cx-hx, cy)},
                    {'id': f"{p['id']}#b", 'type': 'door_post', 'xy': (cx+hx, cy)}]
    for name, r in static.get('regions', {}).items():
        if not name.startswith('zone_'):
            continue
        (cx, cy), (hx, hy) = r['center_m'], r['half_extents_m']
        for k, (sx, sy) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
            out.append({'id': f'{name}#c{k}', 'type': 'zone_corner', 'xy': (cx+sx*hx, cy+sy*hy)})
    return out


def wrap(a):
    return (a+math.pi) % (2*math.pi)-math.pi


def visible_predictor(half_fov=CAMERA_HALF_FOV_RAD, max_range=MAX_RANGE_M):
    """visible_fn(pose, body_yaw_deg, pan_deg, landmark) for ``plan_views``; own estimate only."""
    def visible(pose, body_yaw_deg, pan_deg, landmark):
        dx, dy = landmark['xy'][0]-pose[0], landmark['xy'][1]-pose[1]
        if math.hypot(dx, dy) > max_range:
            return False
        heading = pose[2]+math.radians(body_yaw_deg+pan_deg)
        return abs(wrap(math.atan2(dy, dx)-heading)) < half_fov
    return visible


def pan_pulse(pan_deg):
    return max(500, min(2500, round(1500+pan_deg*PULSE_PER_DEGREE)))


def rotation_plan(delta_yaw_rad, rate=NOMINAL_YAW_RATE):
    """Wheel pulses [(wheels, durations)] turning the body by ``delta_yaw_rad`` (positive = left)."""
    remaining = abs(delta_yaw_rad)/rate
    sign = 1. if delta_yaw_rad > 0 else -1.
    wheels = [-sign*TURN_LEVEL, sign*TURN_LEVEL, -sign*TURN_LEVEL, sign*TURN_LEVEL]   # wheel_mix(0, 0, turn)
    plan = []
    while remaining > 1e-6:
        on = min(PULSE_S, remaining)
        plan.append((list(wheels), [on]*4))
        remaining -= on
    return plan


def execution_script(plan):
    """Ordered steps from a ``plan_views`` result: [{'body_yaw_deg', 'pan_deg', 'landmarks'}, ...]."""
    return [{'body_yaw_deg': v['body_yaw_deg'], 'pan_deg': v['pan_deg'], 'landmarks': list(v['landmarks'])}
            for v in plan['views']]
