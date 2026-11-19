"""GCP-only staged solo student evaluation. No teacher/IK/GT policy correction.

This is a component probe, not navigation or E2E completion. The setup
owner reads static initial poses; the isolated worker sees only the v6 contract.
Evaluation truth is written after action selection and cannot change commands.
"""
from __future__ import annotations
import argparse
import base64
import json
import math
from pathlib import Path
import re
import selectors
import subprocess
import time

import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import importlib.util as _ilu
# solo_green_v1 hook (default off): loaded by file path, stdlib only, before the dependency_modules() swap.
_SOLO_APPEARANCE_SPEC = _ilu.spec_from_file_location('solo_appearance_v1', str(Path(__file__).resolve().parent / 'solo_appearance_v1.py'))
solo_appearance_v1 = _ilu.module_from_spec(_SOLO_APPEARANCE_SPEC)
_SOLO_APPEARANCE_SPEC.loader.exec_module(solo_appearance_v1)
from harness import grasp_act_contract as c
from harness import exec_opt as execution_options
from harness.grasp_act_data import sha256, write_json, write_summary
from harness.grasp_act_policy import ChunkExecutor
from harness.grasp_act_inference import private_url
from harness.grasp_act_rollout import OwnHistory, SoloSequence, SoloScore, InputAudit, evaluation_gates, GraspTransitionRule, ACT_DONE_EXIT_ROWS, act_done_exit_row
from scripts.grasp_act_training_guard import ROOT, require_gcp, source_sha


def _load_gaze_class():
    # Resolved before dependency_modules() swaps `harness` for the frozen scene
    # package, which has no gaze_correction module. Only called with the flag on.
    from harness.gaze_correction import GazeCorrection
    return GazeCorrection


_gaze_class = None


def validate_plan(plan, protocol, *, teacher_start_v1=False):
    if (plan['seed'] not in protocol['closed_loop_seeds'] or plan['skill'] not in ('grasp', 'grasp_release')
            or plan['object_kind'] not in ('cyan', 'red', 'green', 'yellow')
            or plan['role'] != 'west' or plan['robot_id'] not in ('r1', 'r2', 'r3')):
        raise ValueError('pilot supports registered fresh-seed solo boxes only')
    if set(protocol['closed_loop_seeds']) & set(protocol['train_seeds'] + protocol['validation_seeds']):
        raise ValueError('closed-loop seed leak')
    distance = math.dist(plan['spawns'][plan['robot_id']][:2], plan['target_setup_xy'])
    # ACT14 reuses the frozen 6f057f7e make_solo_teacher_plan.START_RANGE_M;
    # this is setup parity, not a new acceptance tolerance. Legacy stays default.
    low, high = (.6, 1.1) if teacher_start_v1 else (.4, .8)
    if not low <= distance <= high:
        raise ValueError('staged near-field initial distance must be 0.4..0.8 m')


def response(process, timeout=120.):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout):
            raise TimeoutError('student inference timeout')
    line = process.stdout.readline()
    if not line:
        raise RuntimeError('student worker exited')
    return json.loads(line)


# carry_v1: own-frame carry between the lift and the release replay. Measured on the work VM with the box
# held (ten development runs, 0.10 s pulses at 0.35): forward 10/20/40 pulses 0.136/0.279/0.546-0.564 m,
# back 10/20 pulses 0.136/0.271-0.280 m, turns with nothing touched 10 pulses 0.86-0.90 rad and 19 pulses
# 1.68-1.69 rad in both directions. (The first seven runs turned 0.28 m behind the pickup point and brushed
# a neighbouring box, which read as a slow turn of 0.071-0.083 rad per pulse.)
CARRY_PULSE = (.35, .10)
CARRY_UNIT = {'fwd': .01394, 'back': .01379, 'left': .0885, 'right': .0885}
CARRY_WHEELS = {'fwd': [1, 1, 1, 1], 'back': [-1, -1, -1, -1], 'left': [-1, 1, -1, 1], 'right': [1, -1, 1, -1]}
CARRY_GAP_ROWS = 5
# 'arm:far' raises the arm to the look-around posture with the gripper kept closed, so the camera sees
# ahead over the held box; 'arm:hold' lowers it back. The move is spread over CARRY_ARM_ROWS rows.
CARRY_FAR_POSTURE = {'3': 740, '4': 2320, '5': 1320, '6': 1500}
CARRY_ARM_ROWS = 15


def carry_rows(spec, level=0.):
    """'back:0.28,left:90,fwd:0.55,hold:5' -> (rows, segments). Rows are (wheels, pulse seconds).

    fwd/back take metres, left/right degrees, hold/pause seconds; a trailing 'p' gives whole pulses
    ('left:30p'). Motion is whole 0.10 s pulses only (shorter pulses are not proportional), so the
    request is rounded and both values are recorded. The destination is in the robot's own frame at
    the moment the carry starts; no map or pose is read.
    """
    import math
    rows, segments, arm = [], [], []
    for item in [x.strip() for x in spec.split(',') if x.strip()]:
        kind, _, text = item.partition(':')
        arm += [level] * (len(rows) - len(arm))
        if kind == 'arm':
            if text not in ('far', 'hold'):
                raise ValueError('arm segment must be far or hold')
            goal = 1. if text == 'far' else 0.
            segments.append({'kind': 'arm', 'to': text, 'rows': CARRY_ARM_ROWS + CARRY_GAP_ROWS, 'first_row': len(rows)})
            arm += [level + (goal - level) * (i + 1) / CARRY_ARM_ROWS for i in range(CARRY_ARM_ROWS)] + [goal] * CARRY_GAP_ROWS
            rows += [([0.] * 4, 0.)] * (CARRY_ARM_ROWS + CARRY_GAP_ROWS)
            level = goal
            continue
        if kind in ('hold', 'pause'):
            n = int(round(float(text) / c.PERIOD_S))
            if n < 0:
                raise ValueError('negative hold')
            segments.append({'kind': kind, 'requested_s': float(text), 'rows': n, 'first_row': len(rows)})
            rows += [([0.] * 4, 0.)] * n
            continue
        if kind not in CARRY_UNIT:
            raise ValueError('carry segment must be fwd, back, left, right, hold or pause')
        unit = CARRY_UNIT[kind]
        if text.endswith('p'):
            n, requested = int(text[:-1]), None
        else:
            requested = math.radians(float(text)) if kind in ('left', 'right') else float(text)
            n = int(round(requested / unit))
        if not 0 <= n <= 400:
            raise ValueError('carry segment out of range')
        segments.append({'kind': kind, 'requested': requested, 'pulses': n, 'nominal': n * unit,
                         'unit': 'rad' if kind in ('left', 'right') else 'm', 'first_row': len(rows)})
        rows += [([CARRY_PULSE[0] * w for w in CARRY_WHEELS[kind]], CARRY_PULSE[1])] * n
        rows += [([0.] * 4, 0.)] * CARRY_GAP_ROWS
    rows += [([0.] * 4, 0.)] * CARRY_GAP_ROWS
    arm += [level] * (len(rows) - len(arm))
    return rows, segments, arm


def carry_pwm(hold, level):
    """Servo row for a carry tick: the hold posture, blended toward the look-around posture by level 0..1."""
    return {k: (int(round(v + (CARRY_FAR_POSTURE[k] - v) * level)) if k in CARRY_FAR_POSTURE else int(v))
            for k, v in hold.items()}


def carry_navigation_command(nav, jpeg, previous_pwm, hold_pwm, state, now):
    """Return the next carry command, a final hold on failed confirmation, or None to hand control to release."""
    row = nav.step(jpeg, {int(k): int(v) for k, v in previous_pwm.items()})
    if row is None:
        if nav.outcome == 'zone_unconfirmed':
            return c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous_pwm)}), nav.outcome
        return None
    wheels, duration, level = row
    hold = hold_pwm if hold_pwm is not None else state.setdefault('hold_pwm', dict(previous_pwm))
    state['arm_level'] = level
    return c.command({'t': now, 'wheels': list(wheels), 'duration_s': [duration if w else 0. for w in wheels],
                      'pwm': carry_pwm(hold, level)}), 'carry_code'


def return_start_pose(measured, nominal, fallback):
    """Where the way back starts, list frame: (pose dict, used_fallback). `measured`: the ceiling-camera pose (x, y, yaw) when it is fresh, else None.
    `nominal`: the carry's own estimate (last measured pose plus the planned rows), used only with --return-pose-fallback. None: no start (the run ends)."""
    if measured is not None:
        return dict(zip(('x', 'y', 'yaw'), measured[:3])), False
    if fallback and nominal is not None:
        return dict(nominal), True
    return None


def return_or_stand_command(nav, jpeg, previous_pwm, return_hold, now, *, speaking, waiting):
    """Hold both wheels and arm without consuming a return row. A completed return yields no command."""
    if speaking or waiting:
        return c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous_pwm)}), ('talk_stand' if speaking else 'next_wait')
    row = nav.step(jpeg, {int(k): int(v) for k, v in previous_pwm.items()})
    if row is None:
        return None, None
    wheels, duration, level = row
    return c.command({'t': now, 'wheels': list(wheels), 'duration_s': [duration if w else 0. for w in wheels],
                      'pwm': carry_pwm(return_hold, level)}), 'return_code'


# carry_to: where the held box sits relative to the base centre (forward, metres) while carried (0.198-0.208
# measured) and after the release replay has driven forward and set it down (0.304-0.325 measured).
# The robot turns where it stands when every other listed box is at least CARRY_SWEEP_M from its centre
# (the held box sweeps a circle of about 0.23 m). Otherwise it backs up to the first point where that
# holds, but never through a point closer than CARRY_BODY_M to a listed box: three development runs
# that always backed up 0.28 m pushed the neighbouring box that stood 0.39 m behind the robot.
CARRY_HELD_M, CARRY_SETDOWN_M = .20, .31
CARRY_BACK_MAX_M, CARRY_SWEEP_M, CARRY_BODY_M, CARRY_PATH_M = .45, .30, .22, .20
# carry_to door: the robot centre stops this far in front of the remembered door centre, on the door's normal,
# with the arm raised so that it can look at the door again over the held box (rows below CARRY_BOX_ROW show it).
CARRY_DOOR_STANDOFF_M, CARRY_BOX_ROW, CARRY_LOOK_S = 1.0, 360, 1.5
# Is the box in the gripper? After HELD_CHECK_ROWS[0] carry rows (the arm is up by then) the robot holds still for
# HELD_CHECK_ROWS[1] frames; the median share of box colour along the bottom edge of the picture must reach HELD_FILL_MIN.
# Recorded runs (2026-11-15): held boxes 0.05-0.81 (21 runs; 3 blue boxes sat low at 0.05), empty grippers 0.01-0.02
# (3 runs). The margin is small and rests on few failures.
HELD_CHECK_ROWS, HELD_FILL_MIN, HELD_LOST_ROWS = (10, 6), 0.035, 10
# with robot tags: another robot within this box ahead (body frame, metres) holds a carrying robot still, up to 20 s at a time
ROBOT_AHEAD_M, ROBOT_AHEAD_HALF_M, ROBOT_WAIT_ROWS = 0.75, 0.30, 200
APPROACH_YIELD_M, APPROACH_YIELD_HALF_M = 1.0, 0.45   # while approaching a box: a lower-numbered robot this close ahead
SIGN_SET_DOWN_M = 0.32   # a box for a wall sign goes this far in front of it
# multi_carry: a look-around entry this close to the door line or beyond it (the other room) is not offered; so is one this close to a robot
# whose number tag the own camera read during the look-around (the box that robot holds sits about 0.2 m in front of its centre)
OTHER_ROOM_MARGIN_M, SEEN_ROBOT_BOX_M = 0.25, 0.45
# llm_moves: while the approach yield holds the robot still, the planner is asked after YIELD_ASK_ROWS rows (6 s) and again YIELD_REASK_ROWS later, at most YIELD_ASKS_MAX times in one approach
YIELD_ASK_ROWS, YIELD_REASK_ROWS, YIELD_ASKS_MAX = 60, 70, 2
OVERHEAD_STALE_S = 1.5   # a ceiling reading older than this is not used
OTHERS_STALE_S = 5.0     # --door-lane-fix: another robot the ceiling cameras missed in the last readings stays where it was last read for this long
LOOK_TURN_SPECS = ('right:40', 'left:80', 'right:120')   # --look-turn: the turn before the 1st, 2nd, 3rd repeated look-around of one trip (degrees from the position before the first)
RETURN_RETRIES, RETURN_RETRY_ROWS = 2, 100   # --door-lane-fix: a way back that failed at the door is tried again up to twice, after 10 s standing
OVERHEAD_EVERY = 5      # ceiling cameras read every 5 ticks (0.5 s); one reading costs about 1 s of rendering on the work VM
# look around again (run_steps look_around, DEFAULT off): the planner may ask for a fresh look-around at a pick decision. After a dropped box the
# robot first backs off this far (the dropped box lies in the blind zone 0.15 m ahead of the body: the survey cannot see it from where it stands;
# a work record M3-C3M08-T2-r2 r3: box 0.16 m ahead, 43 waits), less when a wall stands behind it (as carry_nav_v1 HELD_*).
LOOK_BACK_M, LOOK_BACK_SKIP_M = .30, .05
LOOK_REAR_M, LOOK_WALL_HALF_M, LOOK_WALL_MARGIN_M, LOOK_BACK_HALF_M = .092, .025, .03, .15


def look_back_m(pose, wall_points):
    """How far the robot may back off before it looks around again: LOOK_BACK_M, or less when a known wall stands behind it (within the
    body width along the reverse heading); 0 when that leaves under LOOK_BACK_SKIP_M. pose (x, y, yaw) and wall_points [(x, y)] in one frame."""
    c, s = math.cos(pose[2]), math.sin(pose[2])
    free = None
    for wx, wy in wall_points:
        dx, dy = wx - pose[0], wy - pose[1]
        behind, side = -(dx * c + dy * s), -dx * s + dy * c
        if behind > 0. and abs(side) < LOOK_BACK_HALF_M and (free is None or behind < free):
            free = behind
    back = LOOK_BACK_M if free is None else max(0., min(LOOK_BACK_M, free - LOOK_WALL_HALF_M - LOOK_REAR_M - LOOK_WALL_MARGIN_M))
    return back if back >= LOOK_BACK_SKIP_M else 0.


# 0.90 m: the 0.5 m opening then spans about 31 degrees of the 50 degree view, so both jambs stay in the
# picture; at 0.60 m (45 degrees) one jamb left the picture and the door was not seen (development run 90725).
CARRY_PASS_STANDOFF_M, CARRY_PASS_BEYOND_M = .90, .60
# Routes keep this far from everything remembered as standing on the floor (robot half width about 0.12 m, plus
# the error of the remembered positions). The look-around list only has the red and blue boxes; two development
# runs that drove 3.3 m straight to the door ran over a tile that was not in the list.
CARRY_ROUTE_CLEAR_M = .26


def carry_route(start, target, obstacles, clearance=None):
    """Waypoints (possibly none) from start to target that keep CARRY_ROUTE_CLEAR_M from the obstacle points.

    Returns (waypoints, clear). One waypoint at most: the shortest two-leg path whose legs are both clear, with
    the waypoint beside a blocking point. clear is False when no such path exists; the caller must then not
    drive (a development batch that kept the straight line in that case ran into a bar and a tile).
    Obstacle points right at the start (the robot stands among the boxes it picked from) do not block, and
    neither do points whose nearest place on a leg is the target itself: whether the target is a fit place to
    stop is the caller's check.
    """
    import math
    clearance = CARRY_ROUTE_CLEAR_M if clearance is None else clearance

    def gap(a, b, q):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return math.hypot(q[0] - a[0], q[1] - a[1]), 0.
        along = max(0., min(length, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / length))
        return math.hypot(q[0] - a[0] - along * dx / length, q[1] - a[1] - along * dy / length), along

    def blockers(a, b, end_is_target=True):
        out = []
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        for q in obstacles:
            g, along = gap(a, b, q)
            if g < clearance and along > .15 and not (end_is_target and along > length - .02):
                out.append(q)
        return out
    blocking = blockers(start, target)
    if not blocking:
        return [], True
    dx, dy = target[0] - start[0], target[1] - start[1]
    length = math.hypot(dx, dy)
    px, py = -dy / length, dx / length
    best = None
    for q in blocking:
        for side in (1, -1):
            for extra in (.12, .27, .42, .57, .72):
                w = (q[0] + side * (clearance + extra) * px, q[1] + side * (clearance + extra) * py)
                if blockers(start, w, end_is_target=False) or blockers(w, target):
                    continue
                cost = math.hypot(w[0] - start[0], w[1] - start[1]) + math.hypot(target[0] - w[0], target[1] - w[1])
                if best is None or cost < best[0]:
                    best = (cost, w)
    if best is None:
        return [], False
    return [list(best[1])], True


def carry_point_clearance(point, obstacles):
    import math
    return min([math.hypot(point[0] - q[0], point[1] - q[1]) for q in obstacles] or [9.])


def carry_legs_spec(pose, points, face=None):
    """Turn-and-drive segments through the points in order, then turn toward `face`."""
    import math
    x, y, yaw = pose['x'], pose['y'], pose['yaw']
    parts = []
    for px, py in points:
        bearing = math.atan2(py - y, px - x)
        turn = math.atan2(math.sin(bearing - yaw), math.cos(bearing - yaw))
        parts += ['%s:%.2f' % ('left' if turn >= 0 else 'right', math.degrees(abs(turn))), 'fwd:%.3f' % math.hypot(px - x, py - y)]
        x, y, yaw = px, py, bearing
    if face is not None:
        turn = math.atan2(face[1] - y, face[0] - x) - yaw
        turn = math.atan2(math.sin(turn), math.cos(turn))
        parts.append('%s:%.2f' % ('left' if turn >= 0 else 'right', math.degrees(abs(turn))))
    return ','.join(parts)
# crossing tolerance 0.10 m (was 0.06): the opening leaves 0.13 m each side of the 0.24 m body, and one turn pulse is
# about 5 deg, i.e. 0.08 m at the 0.9 m standoff, so 0.06 m could miss on every try (team-v17 L02 r2: 0.079 m, 3 tries)
CARRY_PASS_CROSS_M, CARRY_PASS_HEADING_DEG, CARRY_PASS_TRIES = .10, 12., 3


def carry_door_step(door, pose):
    """Next move in front of the door, from the door just seen. door: list-frame jambs; pose: own list-frame pose.

    Returns (kind, spec, facts). kind 'pass': driving straight ahead crosses the door line within
    CARRY_PASS_CROSS_M of the door centre (the opening is 0.25 m to each side), so the robot drives on to
    CARRY_PASS_BEYOND_M past the door line. kind 'align': it moves to CARRY_PASS_STANDOFF_M in front of the
    door centre on the door axis, faces the door and looks again.
    """
    import math
    c, s = math.cos(pose['yaw']), math.sin(pose['yaw'])

    def body(pt):
        dx, dy = pt[0] - pose['x'], pt[1] - pose['y']
        return dx * c + dy * s, -dx * s + dy * c
    left, right = body(door['left']), body(door['right'])
    cx, cy = .5 * (left[0] + right[0]), .5 * (left[1] + right[1])
    tx, ty = right[0] - left[0], right[1] - left[1]
    width = math.hypot(tx, ty)
    tx, ty = tx / width, ty / width
    nx, ny = -ty, tx
    if nx * -cx + ny * -cy < 0:
        nx, ny = -nx, -ny
    along = -cx * nx - cy * ny          # distance in front of the door line
    lateral = -cx * tx - cy * ty        # offset from the door axis
    heading = math.degrees(math.atan2(-ny, -nx))   # turn needed to face straight through
    # where the straight line ahead meets the door line: offset from the door centre, and how far ahead
    cross = -cy / ty if abs(ty) > .3 else float('inf')
    reach = cx + cross * tx if abs(ty) > .3 else float('inf')
    facts = {'door_in_body': [cx, cy], 'width_m': width, 'in_front_m': along, 'off_axis_m': lateral,
             'turn_to_face_deg': heading, 'straight_crossing_offset_m': cross, 'straight_distance_m': reach}
    if abs(cross) <= CARRY_PASS_CROSS_M and abs(heading) <= CARRY_PASS_HEADING_DEG and 0 < reach <= 1.3:
        return 'pass', 'fwd:%.3f' % (reach + CARRY_PASS_BEYOND_M), facts
    tx_, ty_ = cx + CARRY_PASS_STANDOFF_M * nx, cy + CARRY_PASS_STANDOFF_M * ny
    bearing, dist = math.atan2(ty_, tx_), math.hypot(tx_, ty_)
    # a point behind the robot is reached backwards, so that the turns stay small
    back = abs(bearing) > math.pi / 2
    first = bearing - math.copysign(math.pi, bearing) if back else bearing
    face = math.atan2(cy - ty_, cx - tx_) - first
    face = math.atan2(math.sin(face), math.cos(face))
    turn = lambda a: '%s:%.2f' % ('left' if a >= 0 else 'right', math.degrees(abs(a)))
    spec = '%s,%s:%.3f,%s,pause:%.1f' % (turn(first), 'back' if back else 'fwd', dist, turn(face), CARRY_LOOK_S)
    return 'align', spec, facts


def carry_nominal_pose(own, segments):
    """Own pose after the planned segments (nominal pulse lengths), in the list frame."""
    import math
    x, y, yaw = own['x'], own['y'], own['yaw']
    for s in segments:
        if s['kind'] in ('fwd', 'back'):
            d = s['nominal'] * (1 if s['kind'] == 'fwd' else -1)
            x, y = x + d * math.cos(yaw), y + d * math.sin(yaw)
        elif s['kind'] in ('left', 'right'):
            yaw += s['nominal'] * (1 if s['kind'] == 'left' else -1)
    return {'x': x, 'y': y, 'yaw': math.atan2(math.sin(yaw), math.cos(yaw))}


def carry_destination(rule, entries, index):
    """Task instruction -> destination point for the box in the look-around frame, from the robot's own list.

    'x,y'    : that point (metres; +x ahead of the start pose, +y left)
    'start'  : where the robot stood when it looked around
    'mid'    : halfway between that point and where the picked box stood
    'beside' : 0.30 m from the nearest other listed box, on its side facing the start point
    'door'   : handled by the caller (the remembered door; the robot stops in front of it and faces it)
    'through_door' : handled by the caller (as 'door', then it lines up, drives through and looks around)
    """
    import math
    if ',' in rule:
        x, y = (float(v) for v in rule.split(','))
        return [x, y]
    if rule in ('start', 'door', 'through_door') or rule.startswith('zone_'):
        return [0., 0.]
    picked = entries[index]
    if rule == 'mid':
        return [.5 * picked['x'], .5 * picked['y']]
    if rule == 'beside':
        others = [e for i, e in enumerate(entries) if i != index]
        if not others:
            return None
        o = min(others, key=lambda e: math.hypot(e['x'] - picked['x'], e['y'] - picked['y']))
        d = math.hypot(o['x'], o['y'])
        return [o['x'] - .30 * o['x'] / d, o['y'] - .30 * o['y'] / d]
    raise ValueError('carry_to must be x,y or start, mid, beside')


PLANNER_ZONES = ('orange', 'blue', 'purple', 'sign11', 'sign12', 'sign13')


def planner_zone_ok(name, extra=()):
    """A destination the planner may name: the ones of the old arena (PLANNER_ZONES), or, in a generated map scene (DEFAULT none), one of the
    numbered wall signs of that scene (`extra`, carry_to_state['map_zones'])."""
    return name in PLANNER_ZONES or name in extra


PUT_DOWN = 'put_down'    # a planner's answer to the destination question: set the held box down where the robot stands and finish


def accept_planner_destination(state, rule, at_s, events=None):
    """The first destination a planner names for the held box (state = carry_to_state). 'zone_<name>' is carried to as before.
    PUT_DOWN means there is nothing to carry: the note keeps the carry planning and the navigation from starting (the same path as
    'no destination follows from the list') and the release replay, which is also what ends every early carry outcome, sets the
    box down where the robot stands. The carry counts as finished with outcome 'put_down'."""
    if rule == PUT_DOWN:
        state.update(rule=rule, decided_at_s=at_s, put_down=True,
                     note='the planner chose to put the box down here and finish; nothing to carry')
        if events is not None:
            events.setdefault('carry_finished', {'at_s': at_s, 'outcome': PUT_DOWN})
        return
    if not (rule.startswith('zone_') and planner_zone_ok(rule[5:], state.get('map_zones', ()))):
        raise ValueError('a planner destination must be zone_<orange|blue|purple|sign11|sign12|sign13> or put_down')
    state.update(rule=rule, decided_at_s=at_s)


def change_planner_destination(state, nav, again, at_s, zones=True):
    """A planner's new answer `again` to the destination question while the robot carries (before the door is passed;
    state = carry_to_state, nav = CarryNav). Another zone replaces the goal of the carry (not with zones=False: the run was made
    without re-decision, only PUT_DOWN, which can also be the answer to the door question, is taken). PUT_DOWN drops the rest of
    the carry (nav.put_down()), after which the release replay sets the box down. True when something changed."""
    if state.get('put_down') or again is None or again == state['rule']:
        return False
    phase = nav.phase
    if again == PUT_DOWN:
        if not nav.put_down():
            return False
        state['put_down'] = True
    elif zones and again.startswith('zone_') and planner_zone_ok(again[5:], state.get('map_zones', ())):
        nav.goal, nav.colour = again, again[5:]
    else:
        return False
    state.setdefault('redecided', []).append({'at_s': at_s, 'from': state['rule'], 'to': again, 'phase': phase})
    state['rule'] = again
    return True


def carry_to_plan(own, destination, others, stop_m=None, face=None):
    """Own pose and listed boxes (look-around frame) and a destination point for the box -> plan dict.

    own: x, y, yaw. others: (x, y) of the listed boxes that are not being carried. Everything here is the
    robot's own estimate; nothing is corrected against the simulator.
    """
    import math
    unit = CARRY_UNIT['back']
    chosen = None
    for n_back in range(0, int(round(CARRY_BACK_MAX_M / unit)) + 1):
        px, py = own['x'] - n_back * unit * math.cos(own['yaw']), own['y'] - n_back * unit * math.sin(own['yaw'])
        clear = min([math.hypot(px - ox, py - oy) for ox, oy in others] or [9.])
        if n_back and clear < CARRY_BODY_M:
            break  # backing further would push a listed box
        if chosen is None or clear > chosen[1]:
            chosen = (n_back, clear, px, py)
        if clear >= CARRY_SWEEP_M:
            break
    n_back, clear, px, py = chosen
    dx, dy = destination[0] - px, destination[1] - py
    bearing = math.atan2(dy, dx)
    turn = math.atan2(math.sin(bearing - own['yaw']), math.cos(bearing - own['yaw']))
    length = math.hypot(dx, dy)
    drive = length - (CARRY_SETDOWN_M if stop_m is None else stop_m)
    # listed boxes close to the straight line from the turning point to the destination
    near = []
    for i, (ox, oy) in enumerate(others):
        along = max(0., min(length, (ox - px) * math.cos(bearing) + (oy - py) * math.sin(bearing)))
        gap = math.hypot(ox - px - along * math.cos(bearing), oy - py - along * math.sin(bearing))
        if gap < CARRY_PATH_M:
            near.append({'other': i, 'gap_m': gap})
    spec = 'back:%dp,%s:%.2f,%s:%.3f' % (n_back, 'left' if turn >= 0 else 'right', math.degrees(abs(turn)),
                                        'fwd' if drive >= 0 else 'back', abs(drive))
    if face is not None:
        # after the drive, turn toward this point (from where the robot centre stops)
        ex, ey = px + drive * math.cos(bearing), py + drive * math.sin(bearing)
        final = math.atan2(face[1] - ey, face[0] - ex)
        last = math.atan2(math.sin(final - bearing), math.cos(final - bearing))
        spec += ',%s:%.2f' % ('left' if last >= 0 else 'right', math.degrees(abs(last)))
    return {'spec': spec, 'turn_point': [px, py], 'turn_clearance_m': clear, 'turn_clear': clear >= CARRY_SWEEP_M,
            'path_near_listed': near, 'path_clear': not near}


def reached_cap(sim_s, cap_s, *, sequence_finished):
    # Preserve the existing half-control-tick timestamp comparison. A done
    # request alone does not complete SoloSequence's existing settle window.
    return not sequence_finished and sim_s >= cap_s-c.PERIOD_S/2


def run(*args, **kwargs):
    """One robot in its own world: drives run_steps() and advances the physics between its ticks."""
    steps = run_steps(*args, **kwargs)
    try:
        request = next(steps)
        while True:
            advance_physics(request['world'], [request], request['until'])
            request = next(steps)
    except StopIteration as stop:
        return stop.value


def advance_physics(world, requests, until):
    """Step the physics up to `until`, serving every robot's own command leases (one request per robot that acts).

    Per physics step and per robot: tick the port, then set the wheels to this tick's command until its pulse ends,
    as the single-robot loop always did; then one world step.
    """
    if getattr(world, '_exec_wheel_deadlines', False):
        return execution_options.advance_wheel_deadlines(world, requests, until)
    while float(world.data.time) < until - 1e-8:
        t = float(world.data.time)
        for r in requests:
            r['port'].tick(t)
            if r['wheels'] is not None:
                r['port']._set_motors(tuple(w if t < d else 0. for w, d in zip(r['wheels'], r['deadlines'])))
        world._physics_step_for(requests[0]['robot'])


def rollout_wall_cap_s(wall_cap_s, approach_survey_v1):
    """Wall-clock safety cap of one robot's rollout in seconds: the given --wall-cap-s, or (DEFAULT, unchanged) 14400 with the look-around, else 1800."""
    return wall_cap_s if wall_cap_s is not None else (14400 if approach_survey_v1 else 1800)


def run_steps(plan, protocol, model, output, *, actor_python, cap_s=60., n_action_steps=c.CHUNK,
        temporal_ensemble_coeff=None, actor_threads=1, teacher_start_v1=False,
        diagnostic_observer_factory=None, actor_server_url=None,
        grasp_transition_rule=False, gaze_code_v1=False, approach_code_v1=False, release_code_v1=False,
        approach_survey_v1=False, carry_test_v1=False, carry_v1=None, release_at_s=None,
        release_signal=None, carry_to=None, place_told=None, scene_without=(),
        shared=None, carry_gate=None, events=None, choose_box=None, truth_every=0, robot_tags=False, regrasp_max=0, overhead=False, layout=None, redecide=False,
        multi_carry=False, trip_next=None, llm_moves=False, aside_mode='strafe', move_source=None, move_ask=None, move_done=None,
        map_scene=None,
        held_edge_fix=False, look_around=False, stand_hold=None, wall_cap_s=None, render_on_demand=False, exec_options=None,
        audit_grasp_start=False, zone_confirm_close=False):
    # A generator: it yields each time the physics must advance (to the end of the settle second, then to the next
    # 0.1 s tick) and returns the report. `shared` (DEFAULT None) lets several robots act in ONE world: the first
    # call builds the world and leaves it in the dict, later calls with the same dict use it and build nothing; the
    # caller steps the physics for all of them and closes the world. `carry_gate` (DEFAULT None) is a callable the
    # robot asks before it starts to carry: while it answers False the robot stands still with the box held. It is an
    # instruction to the robot (another robot's message), like the release signal; it carries no measurement.
    # `events` (DEFAULT None) is a dict the robot writes its own milestones into ('door_passed', 'carry_finished').
    # `robot_tags` (DEFAULT False): task-definition option. Every robot carries a number tag on four sides
    # (harness/robot_tags_v1.py) and each robot reads the tags it sees in its own picture; what it read is written to
    # tags-seen.jsonl and handed to `events['robots_seen']` for its planner.
    # `overhead` (DEFAULT False): ceiling cameras measure every robot (harness/overhead_v1.py, user decision 2026-11-15).
    # The motion code uses the measured own pose (instead of the drive record) and the measured other robots; the
    # planner is told only its own rough place (events['overhead_pose']). Boxes are still found with the own camera.
    # `layout` (DEFAULT None): task definition for designed scenes. {'boxes': [{'colour': 'red'|'blue', 'x', 'y'}]}: the
    # scene's red and blue boxes are moved there before the first tick (unused ones far outside), and the start-distance
    # check of the staged single-robot plan is not applied (robot starts come from the plan's spawns).
    # `redecide` (DEFAULT False): with a callable carry_to, the callable is asked again on every tick until the robot has
    # passed the door; a changed answer replaces the goal of the memory-based carry (the planner chose another wall sign
    # after a message reached it). Nothing but the sign colour is used after the door, so nothing else is rebuilt.
    # `regrasp_max` (DEFAULT 0): with carry_to, check from the own picture right after the arm is raised for carrying
    # whether the box is in the gripper (it shows along the bottom edge). An empty gripper is reported in
    # events['not_holding']; with regrasp_max > 0 the robot then looks around again and picks again (at most that
    # many times), otherwise it ends there.
    # `held_edge_fix` (DEFAULT False): the held check does not count blobs that lie along the lens border as a box left on the floor
    # (harness/place_memory_v1.py HELD_EDGE_PX; the sliver of the held box's rim read as a box on the floor and the robot let go of it).
    # `look_around` (DEFAULT False): choose_box may answer 'look_around' (the planner chose to look around again). The robot then runs the
    # look-around routine again: after a dropped box it backs off first (look_back_m), the survey object, the drive record and the ceiling-camera
    # anchor are restarted as for a regrasp (the new list frame is where the robot stands), and choose_box is asked again with the new list.
    # Not counted as a regrasp. events['look_around'] lists them.
    # `stand_hold` (DEFAULT None): free talk. A callable that answers True while the robot speaks (the planner answered with a say at a report, a message
    # chance or a destination re-decision: scripts/run_team_carry.py talk_stand). Multi-carry and move choices hold every body command,
    # including the return through the door and a pending move. In the original single-carry path the robot stands still in the two
    # stages the code owns: the approach to the box (before the grasp) and the memory-based carry (door, sign, zone). The ACT grasp and the release
    # replay are not paused (their learned clocks would run on): a say that falls there lapses (the rows held are counted in report['talk_stand_rows']).
    # Without it, or while it answers False, nothing changes.
    # `multi_carry` (DEFAULT False = nothing below changes): a robot may carry more than one box (phase 2). When the release of a carry is over
    # the callable `trip_next` (the robot's planner side) answers 'back', 'wait' (the decision is still pending), or 'finish'. On 'back':
    # in the destination room (events has 'door_passed') the robot first drives back through the door with a CarryNav in returning mode (the
    # ceiling cameras give its pose; no held box; door right of way), in the box room it starts at once. Then everything that belonged to the
    # finished carry is started afresh (a new look-around, the way the empty-gripper restart does it, and a new list frame: frame0 is derived
    # again from the next ceiling reading) and `events` gets the next trip: the milestones of the finished carry move to events['trips'],
    # events['trip'] counts the carries. Needs overhead, approach_survey_v1, carry_to/choose_box callables and events.
    # `llm_moves` (DEFAULT False = nothing below changes): the planner may choose small moves (harness/llm_moves_v1.py): back off a little, step aside
    # (`aside_mode` 'strafe' or 'detour'), look around here. `move_source()` hands the runner the move the planner chose (None or {'kind', 'where'}),
    # `move_ask(waited_s)` is the question put while the robot stands still on the way to its box because another robot is close ahead (it answers
    # a move or None = keep waiting), `move_done(result)` tells the planner side how the move went. A move owns the ticks until its rows are used up
    # (or another robot is in the way of the next row: it stops there); before the pick every move ends with a new look-around from the new place
    # (a new list frame, as after an empty gripper). Needs overhead (the room check and the way back to a known frame use the measured pose).
    # `truth_every` (DEFAULT 0 = off): evaluation side only. Every that many ticks the true depth and the object id of
    # every pixel of the robot's own view are written to truth/ beside the run, for scoring perception offline.
    # Nothing of it is passed to the robot.
    # `choose_box` (DEFAULT None) is a callable that gets the robot's own look-around list and answers an index, None
    # (nothing to pick) or 'wait' (ask again next tick); with it the robot, not the task, decides which box to pick.
    # `carry_to` may be a callable answering a destination rule or None (not decided yet; the robot waits, box held).
    # Both stand for the robot's planner. They see only what the robot has; the evaluation side then looks up which
    # object the chosen entry is, for scoring only.
    if actor_threads not in (1, 2, 4, 8, 16):
        raise ValueError('bounded actor thread setting required')
    ChunkExecutor(None, n_action_steps=n_action_steps, temporal_ensemble_coeff=temporal_ensemble_coeff)
    if approach_survey_v1 and approach_code_v1:
        raise ValueError('approach_survey_v1 and approach_code_v1 are mutually exclusive')
    # approach_survey_v1 spends about 12 s looking around and up to 70 s squaring up, before ACT starts.
    # multi_carry (several carries per robot, 5 boxes for 3 robots): the planner runs may last up to 1500 sim s (the phase-2 recommendation is 1200)
    if not 0 < cap_s <= ((((1500. if multi_carry else 900.)) if callable(carry_to) or choose_box else 420. if carry_to else 320.) if approach_survey_v1 else 90.):
        raise ValueError('finite <=90 SIM seconds required (<=320 with approach_survey_v1, <=420 with carry_to, <=900 with a planner, <=1500 with --multi-carry)')
    if multi_carry and not (overhead and approach_survey_v1 and callable(carry_to) and choose_box is not None and callable(trip_next)
                            and events is not None):
        raise ValueError('multi_carry needs overhead, approach_survey_v1, the planner callables, trip_next and events')
    if llm_moves and not (overhead and approach_survey_v1 and callable(carry_to) and choose_box is not None and callable(move_source)
                          and callable(move_ask) and callable(move_done) and events is not None):
        raise ValueError('llm_moves needs overhead, approach_survey_v1, the planner callables, move_source, move_ask, move_done and events')
    host, source = require_gcp(training=False), source_sha()
    if layout is None:
        validate_plan(plan, protocol, teacher_start_v1=teacher_start_v1)
    with_release = plan['skill'] == 'grasp_release'
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'complete': False, 'host': host, 'source_sha': source,
        'seed': plan['seed'], 'model_sha256': sha256(model / 'model.safetensors'),
        'student_execution': True, 'teacher_assisted': False, 'weld': 'off',
        'teacher_start_v1': teacher_start_v1,
        'scope': 'staged solo grasp/lift/setdown at pickup_site; no navigation/E2E claim' if with_release
                 else 'staged near-field solo grasp; no navigation/release/E2E claim',
        'object_kind': plan['object_kind'], 'requested_sequence': plan['skill'],
        'input_audit': {'forbidden_input_fields': 0, 'teacher_input_fields': 0, 'requests': 0},
        'execution': {'actor_threads': actor_threads, 'chunk_size': c.CHUNK, 'n_action_steps': n_action_steps,
                      'temporal_ensemble_coeff': temporal_ensemble_coeff,
                      'ensemble_mode': 'off' if temporal_ensemble_coeff is None else
                          'dense_v1' if n_action_steps == 1 else 'strided_v1'},
        'completion_confirmation': 'unknown', 'gate_promotion_authorized_if_all_conditions_pass': False}
    overhead_every = OVERHEAD_EVERY
    robot_every = None
    tile_cull = False
    if exec_options is not None:
        report['exec_options'] = exec_options.settings()
        overhead_every = exec_options.overhead_every or OVERHEAD_EVERY
        robot_every = exec_options.robot_render_every
        tile_cull = exec_options.overhead_empty_tiles or exec_options.verify_overhead_tiles
        if robot_every:
            report['own_rgb'] = {'captured': 0, 'reused': 0}
    # idle-tick trims (DEFAULT off: every dict below is empty and no call changes)
    survey_kw = ({k: True for k in ('survey_fast', 'align_fast') if getattr(exec_options, k)} if exec_options is not None else {})
    sequence_kw = ({'grasp_settle_s': SoloSequence.GRASP_SETTLE_SHORT_S, 'hold_rows': GraspTransitionRule.HOLD_ROWS_SHORT}
                   if exec_options is not None and exec_options.act_hold_short else {})
    sign_scan_early_stop = exec_options is not None and exec_options.sign_scan_early_stop
    zone_close_fix = exec_options is not None and exec_options.zone_close_fix
    zone_close_far = exec_options is not None and exec_options.zone_close_far
    return_pose_fallback = exec_options is not None and exec_options.return_pose_fallback
    door_lane_fix = exec_options is not None and exec_options.door_lane_fix
    look_turn = exec_options is not None and exec_options.look_turn
    oracle_return_face = exec_options is not None and exec_options.oracle_return_face
    act_done_exit = exec_options is not None and exec_options.act_done_exit
    write_summary(output / 'summary.json', report)
    # Opt-in code-side gaze correction. The import is inside the opt-in branch
    # so the default (off) path keeps exactly its previous dependencies, and
    # the rule is a post-processing step on the ACT action: the wheels and the
    # gripper servos stay with ACT.
    gaze = None
    if gaze_code_v1:
        gaze = _gaze_class()
    # Opt-in code-side approach servo (approach_code_v1), DEFAULT OFF. Switched on by the CLI flag
    # or by the plan key 'approach_code_v1': true. The module is imported only when on (cv2 lazily).
    approach = None
    survey_select = {}
    if approach_survey_v1:
        # approach_survey_v1 (DEFAULT OFF): look around, approach from the observed list, square up. It takes
        # precedence over the plan key approach_code_v1, so the real-position start hint is never built.
        import importlib.util as _ilu
        _sspec = _ilu.spec_from_file_location('approach_survey_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'approach_survey_v1.py'))
        approach_servo_v1 = _ilu.module_from_spec(_sspec)
        _sspec.loader.exec_module(approach_servo_v1)
        approach = approach_servo_v1.SurveyApproach(c, lambda entries: survey_select['fn'](entries), places=bool(carry_to), **survey_kw)
        approach_servo_v1.D_STOP_M = approach.D_STOP_M
    elif approach_code_v1 or plan.get('approach_code_v1') is True:
        # Loaded by file path: run() executes inside the frozen-dependency import scope, where the
        # package name 'harness' resolves to the pinned teacher package (no approach module there).
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location('approach_servo_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'approach_servo_v1.py'))
        approach_servo_v1 = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(approach_servo_v1)
        approach = approach_servo_v1.ApproachServo(plan['object_kind'], c, approach_servo_v1.plan_handoff_hint(plan))
    report['gaze_correction'] = {
        'enabled': bool(gaze_code_v1),
        'applied': False,
        'inputs': 'own RGB cyan blob centroid and own issued command only; '
                  'no simulator evaluation value, no ground truth, no teacher',
        'servos': ['3', '4', '6'],
        'skill_scope': 'grasp (approach) only; the arm is handed back to ACT after '
                       'three consecutive ticks with all four ACT wheels at zero',
        'rule': 'target on the right -> servo 6 down; target below -> servo 3 down '
                'and servo 4 up; inside the central window -> unchanged',
    }
    write_json(output / 'plan.json', plan)
    write_json(output / 'RUN_META.json', {'class': 'dev', 'sha': source})
    world = worker = port = prediction_log = None
    begin = time.monotonic()
    try:
        import numpy as np
        import mujoco
        from sim.zone_scenario_scene import ScenarioFinalV3Scene
        from sim.render_profile import install
        from sim.final_pair_highpose_nearclip import wrap
        from sim import masterpi_camera_review_v3 as camera
        from sim.s2_servo_stiffness import transform_xml as stiffness
        from sim.s2_realism_camera_binding import bind_camera
        from sim.masterpi_drive_friction_v7 import build_world, PROFILE
        from sim.camera_robot_port import CameraRobotPort
        # Compose existing main Scene hooks, with the same solo recording
        # hardware/camera/render/stiffness settings. No teacher branch imports.
        borrowed = shared is not None and 'world' in shared
        tags_mod, tag_reader, robots_near = None, None, []
        approach_wait = {'rows': 0}
        look_request = {'pending': False, 'back_left': None, 'gap_left': 0, 'done': []}
        oh_mod, oh = None, {}
        if overhead:
            import importlib.util as _ilu_o
            _ospec = _ilu_o.spec_from_file_location('overhead_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'overhead_v1.py'))
            oh_mod = _ilu_o.module_from_spec(_ospec)
            _ospec.loader.exec_module(oh_mod)
            report['overhead'] = {'enabled': True, 'every_ticks': overhead_every, 'reads': 0, 'own_read': 0, 'err_m': [], 'err_deg': []}
        if robot_tags or overhead:
            import importlib.util as _ilu_t
            _tspec = _ilu_t.spec_from_file_location('robot_tags_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'robot_tags_v1.py'))
            tags_mod = _ilu_t.module_from_spec(_tspec)
            _tspec.loader.exec_module(tags_mod)
            report['robot_tags'] = {'enabled': True, 'cards': {k: 2 * v[2] for k, v in tags_mod.SIDES.items()}, 'sign_m': tags_mod.SIGN_M, 'frames_with_a_tag': 0, 'seen': {}, 'signs_seen': {}}
        rod_mod, rod_stats, rod_frame = None, None, None      # --render-on-demand (DEFAULT off): harness/render_on_demand_v1.py
        if render_on_demand:
            if not (overhead and robot_tags) or multi_carry or llm_moves:
                raise ValueError('render_on_demand needs overhead and robot_tags and is not supported with multi_carry / llm_moves')
            import importlib.util as _ilu_r
            _rspec = _ilu_r.spec_from_file_location('render_on_demand_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'render_on_demand_v1.py'))
            rod_mod = _ilu_r.module_from_spec(_rspec)
            _rspec.loader.exec_module(rod_mod)
            rod_stats = rod_mod.Stats()
            report['render_on_demand'] = rod_stats.record()
        if tile_cull:
            from importlib import util as tile_loader
            _spec = tile_loader.spec_from_file_location('render_cull_v1', Path(__file__).resolve().parents[1] / 'harness/render_cull_v1.py')
            tile_geometry = tile_loader.module_from_spec(_spec)
            _spec.loader.exec_module(tile_geometry)
        map_mod, map_cfg = None, map_scene
        world_ids, map_zones = ('r1', 'r2', 'r3'), ()
        if map_cfg is not None:
            # generated map scene (DEFAULT off): harness/map_scene_v1.py, loaded by file path like the other harness modules
            import importlib.util as _ilu_g
            _gspec = _ilu_g.spec_from_file_location('map_scene_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'map_scene_v1.py'))
            map_mod = _ilu_g.module_from_spec(_gspec)
            _gspec.loader.exec_module(map_mod)
            world_ids = tuple(map_cfg['world_robots'])
            map_zones = tuple('sign%d' % n for n in sorted(int(k) for k in map_cfg['signs']))       # the destinations the planner may name
            report['map_scene'] = {'scene_id': map_cfg['scene_id'], 'family': map_cfg['family'], 'world_robots': list(world_ids),
                                   'doors': [d['id'] for d in map_cfg['doors']], 'signs': sorted(int(k) for k in map_cfg['signs']),
                                   'cameras': [list(c_) for _, c_ in oh_mod.CAMERAS] if oh_mod is not None else None}
        door_state = {'id': None}     # map scene: the door this robot carries its box through (chosen once per carry, also the way back)
        llm_mod, llm_kit = None, None
        if llm_moves:
            import importlib.util as _ilu_m
            import types as _types_m
            _mspec = _ilu_m.spec_from_file_location('llm_moves_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'llm_moves_v1.py'))
            llm_mod = _ilu_m.module_from_spec(_mspec)
            _mspec.loader.exec_module(llm_mod)
            llm_kit = _types_m.SimpleNamespace(CARRY_PULSE=CARRY_PULSE, CARRY_UNIT=CARRY_UNIT, CARRY_GAP_ROWS=CARRY_GAP_ROWS,
                                               CARRY_SWEEP_M=CARRY_SWEEP_M, carry_rows=carry_rows)
            report['llm_moves_config'] = {'aside_mode': aside_mode, 'back_m': llm_mod.BACK_M, 'aside_m': llm_mod.ASIDE_M,
                                          'side_unit_m_estimate': llm_mod.SIDE_UNIT_M, 'clear_m': llm_mod.CLEAR_M}
        if borrowed:
            scene = shared['scene']
        else:
            scene = wrap(install(ScenarioFinalV3Scene.from_scenario(plan['scenario_id'], plan['seed']), 'floor_light_v1'))
            scene.config['setup_only']['spawns'] = plan['spawns']
            scene = solo_appearance_v1.apply_plan(scene, plan)  # solo_green_v1; no key = no change
            if map_cfg is not None:
                # the boxes beyond the four of the old pool are cloned in the XML (transform below); list them like the others
                pool_objects = dict(scene.config['setup_only']['objects'])       # the pool of the scene package, before the clones are listed
                scene.config['setup_only']['objects'].update(map_mod.cargo_items(map_cfg, pool_objects))
        obj = scene.config['setup_only']['objects'][plan['item_id']]
        if obj['kind'] != plan['object_kind'] or obj['position_m'][:2] != plan['target_setup_xy']:
            raise ValueError('static task object mismatch')
        if borrowed:
            world = shared['world']
            report['shared_world'] = {'borrowed': True, 'robots': list(shared.get('robots', ()))}
        else:
            original = scene.robot_transform
            def transform(xml, **kwargs):
                xml = camera.transform_xml(original(xml, **kwargs), profile_id=camera.PROFILE_ID)
                if map_cfg is not None:
                    xml = map_mod.transform_xml(xml, map_cfg, light_centres=[c_ for _, c_ in oh_mod.CAMERAS] if oh_mod is not None else ())
                for rid in world_ids:
                    xml = stiffness(xml, servo_stiffness='real_v1', robot_id=rid)
                if robot_tags:
                    _textures = tags_mod.write_textures(output / 'tags', tags_mod.robot_tag_numbers(range(1, len(world_ids) + 1)) + list(tags_mod.SIGNS))
                    xml = tags_mod.add_signs(tags_mod.add_to_scene(xml, world_ids, _textures), _textures)
                if overhead:
                    xml = oh_mod.add_to_scene(xml, world_ids, tags_mod.write_textures(output / 'tags_top', oh_mod.card_numbers(world_ids)))
                if exec_options is not None:
                    xml = exec_options.transform(xml)
                return xml
            scene.robot_transform = transform
            world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=640, height=480,
                render=True, warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None,
                roller_collision='mesh', idle_robot_contacts='off')
            if exec_options is not None:
                report['compiled_exec_options'] = exec_options.compiled_settings(world.model)
                if exec_options.wheel_deadlines:
                    world._exec_wheel_deadlines = True
            for controller in world.controllers.values():
                bind_camera(controller)
            scene.setup(world)
            # scene_without (DEFAULT empty; a task-definition choice, not a robot input): kinds of object left out of the
            # arena. Pair carrying is no longer part of the study (user decision 2026-11-14), so the long bar it was for can
            # be taken out. The object is moved far outside the walls before the first tick; the task object cannot be removed.
            removed = []
            _tokens = {'long_beam': 'beam'}
            _wanted = {_tokens.get(k, k) for k in scene_without}
            for _b in range(world.model.nbody):
                _name = world.model.body(_b).name
                if not _name.startswith('cargo_') or _name.split('_')[1] not in _wanted:
                    continue
                if _name == obj['body_name']:
                    raise ValueError('scene_without cannot remove the task object')
                _j = world.model.body_jntadr[_b]
                if _j < 0 or world.model.jnt_type[_j] != mujoco.mjtJoint.mjJNT_FREE:
                    raise ValueError('scene_without: %s has no free joint' % _name)
                _adr = world.model.jnt_qposadr[_j]
                world.data.qpos[_adr:_adr + 2] = [-30. - len(removed), -30.]
                removed.append({'body': _name})
            # 'robots': the other robots only stand still in a Solo run (nothing drives them), so they are left out until
            # several robots are run together (user decision 2026-11-14). The acting robot cannot be removed.
            if 'robots' in _wanted:
                for _rid in world_ids:
                    if _rid == plan['robot_id'] or (shared is not None and _rid in shared.get('robots', ())):
                        continue
                    _b = mujoco.mj_name2id(world.model, mujoco.mjtObj.mjOBJ_BODY, _rid + '__robot')
                    if _b < 0:
                        continue
                    _j = world.model.body_jntadr[_b]
                    if _j < 0 or world.model.jnt_type[_j] != mujoco.mjtJoint.mjJNT_FREE:
                        raise ValueError('scene_without: %s__robot has no free joint' % _rid)
                    _adr = world.model.jnt_qposadr[_j]
                    world.data.qpos[_adr:_adr + 2] = [-40. - 2. * len(removed), -40.]
                    removed.append({'body': _rid + '__robot'})
            if scene_without:
                # recorded even when this scene had none of them, so that a run shows whether the option took effect
                report['scene_without'] = {'asked': list(scene_without), 'removed': removed}
            if removed:
                mujoco.mj_forward(world.model, world.data)
            if robot_tags:
                # destinations are wall number signs (user decision 2026-11-15): the old floor colour patches are not
                # drawn (the blue patch looked like a blue box). Scoring uses the sign areas, not these patches
                _hidden = []
                for _g in range(world.model.ngeom):
                    if (world.model.geom(_g).name or '').startswith('zone_zone_'):
                        world.model.geom_rgba[_g, 3] = 0.
                        _hidden.append(world.model.geom(_g).name)
                report['floor_zones_hidden'] = _hidden
            if layout is not None:
                pools = {'blue': [], 'red': []}
                for _b in range(world.model.nbody):
                    _name = world.model.body(_b).name
                    if _name.startswith('cargo_') and _name.split('_')[1] in ('cyan', 'red', 'green'):
                        pools['blue' if _name.split('_')[1] == 'cyan' else 'red'].append(_name)
                placed = []
                for _box in layout['boxes']:
                    if not pools[_box['colour']]:
                        raise ValueError('layout asks for more %s boxes than the scene has' % _box['colour'])
                    _name = sorted(pools[_box['colour']])[0]
                    pools[_box['colour']].remove(_name)
                    _adr = world.model.jnt_qposadr[world.model.body_jntadr[world.model.body(_name).id]]
                    world.data.qpos[_adr:_adr + 2] = [_box['x'], _box['y']]
                    placed.append(dict(_box, body=_name))
                for _k, _name in enumerate(pools['blue'] + pools['red']):
                    _adr = world.model.jnt_qposadr[world.model.body_jntadr[world.model.body(_name).id]]
                    world.data.qpos[_adr:_adr + 2] = [-50. - _k, -50.]
                mujoco.mj_forward(world.model, world.data)
                report['layout'] = placed
                if shared is not None:
                    shared['layout'] = placed
            if shared is not None:
                shared['world'], shared['scene'] = world, scene
                report['shared_world'] = {'borrowed': False, 'robots': list(shared.get('robots', ()))}
        if exec_options is not None and exec_options.physics_until_act:
            report['physics_before_act'] = world._exec_before_act if borrowed else exec_options.start_before_act(world)
        (output / 'scene.xml').write_text(world.scene_xml)
        write_json(output / 'scene.json', scene.manifest)
        rid = plan['robot_id']
        port = CameraRobotPort(world, rid)
        # Own issued initial PWM, never measured qpos. Same fixed camera/arm fold
        # commands as the observed recording's initialization.
        previous = {'t': float(world.data.time), 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
                    'pwm': ({str(s): int(port._servo_pulses[s]) for s in c.SERVOS} if teacher_start_v1 and not approach_survey_v1 else
                            {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500})}
        if not teacher_start_v1 or approach_survey_v1:
            for s in c.SERVOS:
                port.apply({'kind': 'look', 'pan_pulse': previous['pwm'][str(s)]} if s == 6 else
                           {'kind': 'arm', 'servo_id': s, 'pulse': previous['pwm'][str(s)]}, previous['t'])
            settle = float(world.data.time) + 1.
            yield {'world': world, 'robot': world.robot(rid), 'port': port, 'wheels': None, 'deadlines': None, 'until': settle}
        previous['t'] = float(world.data.time)
        write_json(output / 'initial-issued.json', previous)
        cid = world.controllers[rid].robot_cam_cid
        write_json(output / 'camera-runtime.json', {k: getattr(world.model, 'cam_'+k)[cid].tolist()
                   for k in ('pos', 'quat', 'intrinsic', 'resolution')})
        def _pick_door(doors, commit=False):
            """The door of the arena this robot carries through. The old arena has one door; the choice is the one nearest the middle of its
            wall (as before). A generated map scene has several: of the doors that leave the room the robot stands in (its own measured place, or
            where it looked around from), the nearest. Chosen once per carry (commit): the way back uses the same door, and the planner side
            learns the door through events['door'] (the reference plan keeps one queue per door). Only walls and doors are used."""
            if map_cfg is None:
                return min(doors, key=lambda d_: abs(d_['y'] - 0.05))
            if commit or door_state['id'] is None:
                _at = oh['own'][:2] if oh.get('own') is not None and float(world.data.time) - oh.get('own_t', -1e9) <= OVERHEAD_STALE_S else oh['frame0'][:2]
                _c = map_mod.choose_door(map_cfg, _at)
                if commit:
                    door_state['id'] = _c['id']            # a new carry decides again; the way back (no commit) keeps this one
            else:
                _c = next(d_ for d_ in map_cfg['doors'] if d_['id'] == door_state['id'])
            _d = min(doors, key=lambda d_: math.hypot(d_['x'] - _c['centre'][0], d_['y'] - _c['centre'][1]))
            if math.hypot(_d['x'] - _c['centre'][0], _d['y'] - _c['centre'][1]) > 0.06:
                raise ValueError('the walls of the model have no door at %s of the scene' % (_c['centre'],))
            if commit and events is not None:
                events['door'] = _c['id']
            return dict(_d, id=_c['id'])

        def _arena_door():
            """multi_carry: (arena, door, to_list_frame) of the present list frame (frame0), or None when it is not derived yet. The shape of
            the arena (walls, the door) goes to the motion code only (user decision 2026-11-15)."""
            if oh.get('frame0') is None:
                return None
            _arena = oh_mod.arena_from_model(world.model)
            if not _arena['doors']:
                return None
            _door = _pick_door(_arena['doors'])
            return _arena, _door, (lambda xy: list(oh_mod.to_frame((xy[0], xy[1], 0.), oh['frame0'])[:2]))

        seen_robots = {}     # multi_carry: robots whose number tag the OWN camera read since this look-around began: {id: (x, y) body frame}
        chosen_log = {}

        def _own_view(entries):
            """multi_carry: indices of the look-around entries the robot still treats as boxes it may pick. Left out, from what the robot has itself:
            an entry on the far side of the door wall (a box in the other room, seen through the doorway: it was carried there; the walls and the door
            are known to the motion code), and an entry within SEEN_ROBOT_BOX_M of a robot whose number tag the own camera read during this
            look-around (a box another robot holds). Nothing from the ceiling cameras or the simulator."""
            keep = list(range(len(entries)))
            _ad = _arena_door()
            if _ad is not None:
                _f = _ad[2]
                _l, _r = _f(_ad[1]['left']), _f(_ad[1]['right'])
                _cx, _cy = .5 * (_l[0] + _r[0]), .5 * (_l[1] + _r[1])
                _tx, _ty = _r[0] - _l[0], _r[1] - _l[1]
                _n = math.hypot(_tx, _ty)
                _nx, _ny = -_ty / _n, _tx / _n
                if _nx * (0. - _cx) + _ny * (0. - _cy) < 0:     # the look-around starts at the origin of the list frame: that is this room's side
                    _nx, _ny = -_nx, -_ny
                keep = [i for i in keep if (entries[i]['x'] - _cx) * _nx + (entries[i]['y'] - _cy) * _ny > OTHER_ROOM_MARGIN_M]
            return [i for i in keep if all(math.hypot(entries[i]['x'] - xy[0], entries[i]['y'] - xy[1]) > SEEN_ROBOT_BOX_M
                                           for xy in seen_robots.values())]

        def _build_return_nav(allow_fallback=True):
            """multi_carry: the navigation for the way back from the destination room to the box room (None when the ceiling pose or the arena
            is not there). The door and the walls are the arena's (list frame of the last look-around, which is still frame0), the own pose and the
            other robots are measured by the ceiling cameras; nothing is held, so no held check and no zone is looked for. After the pass it
            drives on toward the middle of the boxes the last look-around listed besides the one picked (own memory), where the next look-around
            starts."""
            _ad = _arena_door()
            _stale = oh.get('own') is None or float(world.data.time) - oh.get('own_t', -1e9) > OVERHEAD_STALE_S
            _start = return_start_pose(None if _stale or _ad is None else oh_mod.to_frame(oh['own'], oh['frame0']),
                                       None if carry_nav is None or not allow_fallback else carry_nav.pose, return_pose_fallback)
            if _ad is None or _start is None:
                return None
            _arena, _d, _f = _ad
            _own, _fallback = _start
            if _fallback:
                # --return-pose-fallback: the ceiling cameras lost the robot near the far wall (5 s of misses at the end of SPD-P2_N03_S01 r2's carry, then the
                # way back ended on the spot). The carry's own estimate (last measured pose plus the pulses planned since, list frame) starts the way back.
                report.setdefault('return_pose_fallback', []).append({'at_s': round(float(world.data.time) - origin, 1), 'pose': dict(_own),
                                                                       'own_age_s': None if oh.get('own_t') is None else round(float(world.data.time) - oh['own_t'], 1)})
            # the box just set down lies about CARRY_SETDOWN_M in front of the robot: an obstacle of the first turn
            _box = (_own['x'] + CARRY_SETDOWN_M * math.cos(_own['yaw']), _own['y'] + CARRY_SETDOWN_M * math.sin(_own['yaw']))
            _rest = [(e['x'], e['y']) for i_, e in enumerate(approach.entries or ()) if i_ != approach.index]
            # the box just set down and the boxes the last look-around listed (own memory) are the things on the floor of the box room
            nav = carry_nav_mod.CarryNav(carry_kit, approach.places, _own, [_box] + _rest, 'through_door')
            nav.returning = True
            nav.door_lane_fix = bool(door_lane_fix)

            def _pose_back():
                if oh.get('own') is None or float(world.data.time) - oh.get('own_t', -1e9) > OVERHEAD_STALE_S:
                    return None
                _mm = oh_mod.to_frame(oh['own'], oh['frame0'])
                return {'x': _mm[0], 'y': _mm[1], 'yaw': _mm[2]}
            nav.pose_source = _pose_back
            nav.others_source = lambda: [oh_mod.to_frame(v_, oh['frame0'])[:2] for v_ in oh.get('others', {}).values()]
            nav.right_of_way_source = lambda: (rid, {r_: tuple(oh_mod.to_frame(v_, oh['frame0'])[:2]) for r_, v_ in oh.get('others', {}).items()})
            _door = {'x': _f((_d['x'], _d['y']))[0], 'y': _f((_d['x'], _d['y']))[1], 'left': _f(_d['left']), 'right': _f(_d['right']),
                     'width_m': _d['width_m']}
            nav.set_arena(_door, [_f(p_) for p_ in oh_mod.wall_points(_arena['walls'])])
            nav.return_face = [sum(x_ for x_, _ in _rest) / len(_rest), sum(y_ for _, y_ in _rest) / len(_rest)] if _rest else None
            if oracle_return_face and events is not None and events.get('return_face_world') is not None:
                # --oracle-return-face (reference plan only): the place the plan names for the next box, in the list frame
                nav.return_face = [float(v_) for v_ in _f(events['return_face_world'])]
            return nav

        def _llm_start_move(req):
            """llm_moves: the move the planner chose -> a MoveRun (one that cannot be done finishes at once with status 'refused'). Possible before the
            pick (empty hand, approach not arrived: back, aside, look) and while the robot holds its box and waits for the door question (back, aside:
            never a look-around, it opens the gripper). The room check reads the walls and the door the motion code knows, the boxes the robot remembers
            (its own list) and its measured pose; other robots only decide the side of a tie, nothing about them goes to the planner."""
            _kind, _t = req['kind'], float(world.data.time) - origin
            _pre_pick = sequence.skill == 'grasp' and carry_nav is None and approach is not None and not approach.arrived
            _at_gate = (sequence.skill == 'release' and carry_nav is not None and carry_state['started_at_s'] is None and not carry_nav.finished
                        and 'note' not in carry_to_state)
            if not ((_pre_pick and _kind in ('back', 'aside', 'look')) or (_at_gate and _kind in ('back', 'aside'))):
                return llm_mod.MoveRun.refuse(req, 'not_possible_here', _t)
            if _kind == 'look':
                return llm_mod.MoveRun.look(req, _t)
            _ad = _arena_door()
            _own = oh.get('own')
            if _own is None or oh.get('frame0') is None or float(world.data.time) - oh.get('own_t', -1e9) > OVERHEAD_STALE_S:
                return llm_mod.MoveRun.refuse(req, 'no_measured_pose', _t)
            if _ad is None:
                return llm_mod.MoveRun.refuse(req, 'no_arena', _t)
            _m = oh_mod.to_frame(_own, oh['frame0'])
            _arena, _d, _f = _ad
            _obstacles = [tuple(_f(p_)) for p_ in oh_mod.wall_points(_arena['walls'])]
            _obstacles += [(e_['x'], e_['y']) for i_, e_ in enumerate(approach.entries or ()) if not (_at_gate and i_ == approach.index)]
            _others = [tuple(oh_mod.to_frame(v_, oh['frame0'])[:2]) for v_ in oh.get('others', {}).values()]
            _plan = llm_mod.plan_move(_kind, {'x': _m[0], 'y': _m[1], 'yaw': _m[2]}, _obstacles, tuple(_f((_d['x'], _d['y']))), llm_kit,
                                      holding=_at_gate, mode=aside_mode, robots=_others)
            if not _plan['ok']:
                return llm_mod.MoveRun.refuse(req, _plan['why'], _t)
            _rows, _tags = llm_mod.build_rows(_plan, llm_kit)
            return llm_mod.MoveRun(req, _plan, _rows, _tags, _t)

        if approach_survey_v1:
            # Evaluation side only: which observed entry is the designated box. Same rule as the approach probe
            # (same kind, global greedy by distance, within 0.15 m). Only the integer index goes to the student.
            _objects = scene.config['setup_only']['objects']
            _bodies = {k: world.model.body(v['body_name']).id for k, v in _objects.items() if 'body_name' in v}
            def _select(entries):
                xyz = world.robot(rid).base_xyz()
                yaw = float(world.robot(rid).base_rpy()[2])
                co, si = math.cos(yaw), math.sin(yaw)
                pairs = []
                for index, entry in enumerate(entries):
                    for key, bid in _bodies.items():
                        # a 'green' object is drawn red and is seen as 'red' (before this, red boxes never matched)
                        if {'green': 'red'}.get(_objects[key]['kind'], _objects[key]['kind']) != entry['kind']:
                            continue
                        dx = float(world.data.xpos[bid][0] - xyz[0])
                        dy = float(world.data.xpos[bid][1] - xyz[1])
                        gap = math.hypot(entry['x'] - (co * dx + si * dy), entry['y'] - (-si * dx + co * dy))
                        if gap <= 0.15:
                            pairs.append((gap, index, key))
                used_i, used_k, chosen, matched = set(), set(), None, {}
                for gap, index, key in sorted(pairs):
                    if index not in used_i and key not in used_k:
                        used_i.add(index)
                        used_k.add(key)
                        matched[index] = key
                        if key == plan['item_id']:
                            chosen = index
                if choose_box is not None:
                    # the robot's planner picks from its own list; the task's designated box is not passed to it
                    nonlocal obj, body, gids
                    _kept = _own_view(entries) if multi_carry else None     # multi_carry: the list the planner sees, without what the robot knows is not for it
                    if _kept is not None and chosen_log.get('trip') != (trip_n, len(entries), tuple(_kept)):
                        chosen_log['trip'] = (trip_n, len(entries), tuple(_kept))
                        report.setdefault('own_view', []).append({'trip': trip_n, 'entries': len(entries), 'listed': list(_kept),
                                                                  'robots_read_by_tag': {r_: list(xy_) for r_, xy_ in seen_robots.items()}})
                    chosen = choose_box([dict(e) for e in entries] if _kept is None else [dict(entries[i_]) for i_ in _kept])
                    if chosen == 'wait':
                        return 'wait'
                    if chosen == 'look_around' and look_around:
                        look_request['pending'] = True        # handled at the top of the next tick; the survey stays on hold meanwhile
                        return 'wait'
                    if _kept is not None and type(chosen) is int:
                        chosen = _kept[chosen] if 0 <= chosen < len(_kept) else -1       # back to the index of the robot's own list
                    if type(chosen) is int and 0 <= chosen < len(entries):
                        # the robot's own idea of the colour comes from its own list entry, never from the evaluator's
                        # matching (team-v15 D01: the match failed, the task colour stayed 'cyan' and the grasp model,
                        # the held check and the carry check all looked for a blue box while the robot took a red one)
                        task['kind'] = entries[chosen]['kind']
                    if type(chosen) is int and chosen in matched:
                        task['item'] = matched[chosen]
                        obj = _objects[task['item']]
                        body =world.model.body(obj['body_name']).id
                        gids = [g for g in range(world.model.ngeom) if world.model.geom_bodyid[g] == body and world.model.geom_contype[g]]
                write_json(output / ('survey-select.json' if trip_n == 1 else 'survey-select-trip%d.json' % trip_n), {'entries': entries, 'selected_index': chosen,
                           'matched_pairs': len(used_i), 'threshold_m': 0.15, 'chosen_by': 'planner' if choose_box else 'task',
                           'scored_object': task['item'],
                           'note': 'evaluation-side matching; only the index is passed to the student'})
                return chosen
            survey_select['fn'] = _select
        task = {'item': plan['item_id'], 'kind': plan['object_kind']}
        # the student's observation names its robot, and its contract (pinned by the checkpoint's hash, so not editable) knows r1..r3 only. The name is
        # an identity key, not a model input (the context vector has no robot field): a robot beyond the third is presented to the policy as r1
        policy_rid = rid if rid in ('r1', 'r2', 'r3') else 'r1'
        history = OwnHistory(policy_rid, f'student-{plan["seed"]}', previous)
        (output / 'rgb' / policy_rid).mkdir(parents=True)
        if actor_server_url:
            report['execution']['actor_server_url']=private_url(actor_server_url)
            report['execution']['inference_device']='cuda_l4_batch1_v1'
            write_summary(output / 'summary.json', report)
        worker = subprocess.Popen([actor_python, '-m', 'scripts.grasp_act_student_worker', '--model', str(model), '--threads', str(actor_threads)]+
            (['--server-url',actor_server_url] if actor_server_url else []),
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        if response(worker) != {'ready': True}:
            raise RuntimeError('student worker did not load')
        latencies = []
        prediction_log = (output / 'chunk-predictions.jsonl').open('x')
        audit = InputAudit()
        report['input_audit'] = audit.record
        def predict(observation, jpegs):
            audit.accept(observation)
            request = {'observation': observation, 'jpegs': [base64.b64encode(x).decode() for x in jpegs]}
            start = time.monotonic()
            worker.stdin.write(json.dumps(request, allow_nan=False) + '\n')
            worker.stdin.flush()
            result = response(worker)
            latencies.append(time.monotonic() - start)
            if set(result) != {'chunk'}:
                raise ValueError('student response whitelist mismatch')
            prediction_log.write(json.dumps({'sample_id': observation['sample_id'], 't': observation['t'],
                'chunk': result['chunk']}, allow_nan=False) + '\n')
            prediction_log.flush()
            return result['chunk']
        executor = ChunkExecutor(predict, n_action_steps=n_action_steps, temporal_ensemble_coeff=temporal_ensemble_coeff)
        score = SoloScore()
        # Offline replay diagnostics only. The observer receives the selected
        # command and has no return path into the executor or sequence.
        diagnostic_observer = (diagnostic_observer_factory(world, port, obj, previous, scene)
                               if diagnostic_observer_factory else None)
        # Evaluation-only funnel. Existing frozen teacher boundaries: approach
        # .08m, box alignment .008m/.04rad (6f057f7e SoloTeacher._seek/Cargo).
        # Finger load/lift use the unchanged LiftScore criteria. None feed policy.
        funnel = {'frames': 0, 'valid_inputs': 0, 'actions': 0, 'approach': 0,
                  'alignment': 0, 'grasp': 0, 'lift_confirmation': 0}
        first_pass = {}
        minimum_external_contact = None
        # Approach variant: the grasp-end rule is armed only when the approach ARRIVED (handover). On a timeout or
        # an exhausted search it stays off, because the rule would fire on an empty grasp. Recorded in the summary.
        rule_state = {'wanted': bool(grasp_transition_rule) and approach is not None, 'armed_at_handover': False,
                      'note': 'on from start' if (grasp_transition_rule and approach is None) else
                              ('off' if approach is None else 'pending handover')}
        sequence = SoloSequence(with_release, grasp_rule=bool(grasp_transition_rule) and approach is None, **sequence_kw)
        # Experimental release replay (release_code_v1), DEFAULT OFF: on by the CLI flag or the plan key.
        release_on = bool(release_code_v1 or plan.get('release_code_v1') is True)
        release_mod, release_code = None, None
        if release_on:
            import importlib.util as _ilu
            _rspec = _ilu.spec_from_file_location('release_code_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'release_code_v1.py'))
            release_mod = _ilu.module_from_spec(_rspec)
            _rspec.loader.exec_module(release_mod)
        # release_code_v1 hold (coordinator, 90711): the last 45 issued servo PWM rows; the hold is their median.
        issued_hist, hold_pwm = [], None
        # carry_test_v1 (DEFAULT OFF, development check): between the lift and the release replay the base
        # backs up, turns and drives forward with the grasp posture held, to see whether the box stays in
        # the gripper while the robot moves. Fixed own commands only; nothing is observed or corrected.
        carry_plan, carry_i, carry_segments, carry_arm = [], 0, [], []
        if carry_test_v1:
            if not release_on:
                raise ValueError('carry_test_v1 needs release_code_v1')
            carry_plan, carry_segments, carry_arm = carry_rows('back:20p,left:30p,fwd:40p')
            assert carry_plan == ([([-.35] * 4, .10)] * 20 + [([0.] * 4, 0.)] * 5 +
                                  [([-.35, .35, -.35, .35], .10)] * 30 + [([0.] * 4, 0.)] * 5 +
                                  [([.35] * 4, .10)] * 40 + [([0.] * 4, 0.)] * 10)
        # carry_v1 (DEFAULT OFF): the same slot, with the destination given as segments in the robot's own
        # frame at the lift ("back:0.28,left:90,fwd:0.55"). After the last row the robot stands still with
        # the box held until the release trigger: an episode time (release_at_s), a signal file that some
        # other process creates (release_signal), or immediately when neither is given. The trigger is an
        # instruction to the robot, like the task itself; it carries no measurement.
        if carry_v1:
            if carry_test_v1 or carry_to or not release_on:
                raise ValueError('carry_v1 needs release_code_v1 and excludes carry_test_v1 and carry_to')
            carry_plan, carry_segments, carry_arm = carry_rows(carry_v1)
        # carry_to (DEFAULT OFF): the destination of the box is a point in the frame of the look-around list
        # (the robot's body frame at the first tick). The robot places itself in that frame from what it has:
        # the listed position of the box it picked (it stands square to that box at arm's length when the
        # gripper closes) and its heading from its own drive record. From that it builds the same segments.
        carry_to_state, drive, carry_nav, carry_nav_mod, carry_kit = None, None, None, None, None
        if carry_to:
            if carry_test_v1 or not release_on or not approach_survey_v1:
                raise ValueError('carry_to needs approach_survey_v1 and release_code_v1')
            import importlib.util as _ilu2
            _dspec = _ilu2.spec_from_file_location('drive_record_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'drive_record_v1.py'))
            _dmod = _ilu2.module_from_spec(_dspec)
            _dspec.loader.exec_module(_dmod)
            drive = _dmod.DriveRecord()
            _nspec = _ilu2.spec_from_file_location('carry_nav_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'carry_nav_v1.py'))
            carry_nav_mod = _ilu2.module_from_spec(_nspec)
            _nspec.loader.exec_module(carry_nav_mod)
            if map_cfg is not None:
                carry_nav_mod.EXTRA_GOALS = frozenset('zone_' + z_ for z_ in map_zones)      # a map scene's own signs are goals too
            # the same rows, planning arithmetic and constants as the segment carry (this module is not reachable
            # through sys.modules while the scene package is loaded)
            import types as _types
            carry_kit = _types.SimpleNamespace(
                carry_rows=carry_rows, carry_to_plan=carry_to_plan, carry_nominal_pose=carry_nominal_pose,
                carry_route=carry_route, carry_legs_spec=carry_legs_spec, carry_point_clearance=carry_point_clearance,
                carry_door_step=carry_door_step, CARRY_DOOR_STANDOFF_M=CARRY_DOOR_STANDOFF_M, CARRY_LOOK_S=CARRY_LOOK_S,
                CARRY_PASS_TRIES=CARRY_PASS_TRIES, CARRY_BOX_ROW=CARRY_BOX_ROW, CARRY_PASS_BEYOND_M=CARRY_PASS_BEYOND_M,
                CARRY_UNIT=CARRY_UNIT, CARRY_SWEEP_M=CARRY_SWEEP_M, CARRY_BODY_M=CARRY_BODY_M, CARRY_BACK_MAX_M=CARRY_BACK_MAX_M)
            if not callable(carry_to):
                carry_destination(carry_to, [{'x': 1., 'y': 0.}, {'x': 1., 'y': .5}], 0)  # reject a bad rule before the run
                if carry_to.startswith('zone_') and carry_to[5:] not in ('orange', 'blue', 'purple', 'sign11', 'sign12', 'sign13') + map_zones:
                    raise ValueError('zone colour must be orange, blue or purple')
            carry_to_state = {'rule': None if callable(carry_to) else carry_to, 'planned': False,
                              'decided_by': 'planner' if callable(carry_to) else 'task'}
            if map_cfg is not None:
                carry_to_state['map_zones'] = map_zones
        carry_on = bool(carry_v1 or carry_to)
        carry_state = {'started_at_s': None, 'arrived_at_s': None, 'wait_rows': 0, 'release_started_at_s': None,
                       'trigger': None}
        hold_state = {'rows': 0, 'pwm': None}
        # Evaluation-only private handles; these never leave the simulation owner.
        body = world.model.body(obj['body_name']).id
        gids = [g for g in range(world.model.ngeom) if world.model.geom_bodyid[g] == body and world.model.geom_contype[g]]
        fingers = {world.model.geom(rid + '__' + side + '_finger').id: i for i, side in enumerate(('left', 'right'))}
        origin, tick = float(world.data.time), 0
        sequence_finished = False
        regrasps = []
        # multi_carry: carry number, the navigation on the way back (None = not on the way back), the flag that starts the next look-around
        # at the top of the next tick, the records of the finished carries, the posture held on the way back, regrasps of earlier carries
        trip_n, return_nav, begin_trip_now, trip_reports, return_hold, regrasp_base = 1, None, False, [], None, 0
        look_turn_n = 0                              # --look-turn: repeated look-arounds of this trip so far
        return_attempts, return_retry_rows, return_pose_waits = 0, 0, 0    # --door-lane-fix: failed ways back so far, rows left of the stand before the next attempt, ticks waited for a fresh pose
        awaiting_next = False
        # llm_moves: the move being driven (None = none) and the flag that starts a new look-around at the top of the next tick
        move_run, look_now = None, False

        def _box_fill(jpeg):
            import cv2 as _cv2
            hsv = _cv2.cvtColor(_cv2.imdecode(np.frombuffer(jpeg, np.uint8), _cv2.IMREAD_COLOR), _cv2.COLOR_BGR2HSV)
            rule = {'red': lambda h, s_: ((h <= 4) | (h >= 175)) & (s_ >= 150), 'green': lambda h, s_: ((h <= 4) | (h >= 175)) & (s_ >= 150),
                    'cyan': lambda h, s_: (h >= 95) & (h <= 125) & (s_ >= 180)}[task['kind']]
            return round(float(rule(hsv[..., 0], hsv[..., 1])[440:470, 160:480].mean()), 3)

        def _still_held(jpeg):
            """While carrying: the box seen at the start must stay in view. A run of HELD_LOST_ROWS frames without it means
            it fell (one fixed-plan run dropped it against the divider wall and drove on to the zone)."""
            held = carry_state.get('held')
            if not held or not held.get('holding') or held['median_fill'] < 2 * HELD_FILL_MIN:
                return True                 # the box was never clearly in view: nothing to watch
            recent = carry_state.setdefault('carry_fills', [])
            recent.append(_box_fill(jpeg))
            del recent[:-HELD_LOST_ROWS]
            if len(recent) == HELD_LOST_ROWS and max(recent) < HELD_FILL_MIN:
                carry_state['held'] = {'holding': False, 'median_fill': max(recent), 'at_s': now - origin, 'dropped': True}
                report.setdefault('not_holding', []).append(dict(carry_state['held']))
                if events is not None:
                    events.setdefault('not_holding', []).append(now - origin)
                return False
            return True

        def _held_check(jpeg):
            """True while the check still wants frames (the robot holds still); sets carry_state['held'] when done."""
            if not regrasp_max and not carry_to:
                carry_state['held'] = None
                return False
            import cv2 as _cv2
            hsv = _cv2.cvtColor(_cv2.imdecode(np.frombuffer(jpeg, np.uint8), _cv2.IMREAD_COLOR), _cv2.COLOR_BGR2HSV)
            rule = {'red': lambda h, s_: ((h <= 4) | (h >= 175)) & (s_ >= 150), 'green': lambda h, s_: ((h <= 4) | (h >= 175)) & (s_ >= 150),
                    'cyan': lambda h, s_: (h >= 95) & (h <= 125) & (s_ >= 180)}[task['kind']]
            fills = carry_state.setdefault('held_fills', [])
            fills.append(round(float(rule(hsv[..., 0], hsv[..., 1])[440:470, 160:480].mean()), 3))
            if len(fills) < HELD_CHECK_ROWS[1]:
                return True
            fill = float(np.median(fills))
            carry_state['held'] = {'holding': fill >= HELD_FILL_MIN, 'median_fill': fill, 'at_s': now - origin}
            if not carry_state['held']['holding']:
                report.setdefault('not_holding', []).append(dict(carry_state['held']))
                if events is not None:
                    events.setdefault('not_holding', []).append(now - origin)
            return False

        with (output / 'student-inputs.jsonl').open('x') as inputs, (output / 'commands.jsonl').open('x') as commands, (output / 'eval-only.jsonl').open('x') as evaluations:
            while float(world.data.time) - origin < cap_s - 1e-8:
                if (output / 'SUPERVISOR_STOP.json').exists():
                    raise KeyboardInterrupt('supervisor stop')
                # wall-clock safety cap: 4 h with the look-around. Measured on the work VM (team-llm26/31, 65 two-robot runs):
                # wall = 215 s + 10.1 s per sim second (9.3-13.3 s per sim second; 11.9 at most for runs over 250 sim s), so
                # a 900 sim s run (--cap-s 900) needs about 9300-10700 s, which a 3 h cap (10800 s) barely clears; a
                # 600 s sim run with regrasps on a shared, fully loaded work VM took more than 90 min (team-v19 crossed-X01
                # r2 stopped while setting its box down). 14400 s covers 16 s per sim second at 900 sim s. --wall-cap-s (run_team_carry) raises it
                # for a nine-robot run (about 35-50 s per sim second).
                if time.monotonic() - begin > rollout_wall_cap_s(wall_cap_s, approach_survey_v1):
                    raise TimeoutError('rollout wall cap')
                now = float(world.data.time)
                speaking = (multi_carry or llm_moves) and stand_hold is not None and stand_hold()
                choice = trip_next() if awaiting_next and not speaking else None
                if awaiting_next and not speaking:
                    awaiting_next = choice == 'wait'
                    if choice not in ('back', 'wait'):
                        sequence_finished = True
                        break
                if rod_mod is not None or robot_every:
                    # --render-on-demand: a tick that reads no picture (harness/render_on_demand_v1.pixels_idle) hands the robot's last picture on
                    pixels_kind = None
                    if rod_mod is not None:
                        pixels_kind = rod_mod.pixels_idle(approach=approach, skill=sequence.skill, carry_nav=carry_nav, carry_state=carry_state,
                                                          carry_to_state=carry_to_state, gate_idle=getattr(carry_gate, 'idle', None), release_on=release_on)
                    pixels_kind = execution_options.reused_frame_reason(pixels_kind, robot_every, tick, rod_frame)
                    if (pixels_kind and zone_confirm_close and carry_nav is not None and
                            any(look['what'] == 'zone' and look['near'] and look['rows'][0] <= carry_nav.i < look['rows'][1]
                                for look in carry_nav.looks)):
                        pixels_kind = None  # a confirming frame belongs to this observation pose
                    if rod_stats is not None:
                        rod_stats.tick(pixels_kind)
                    if robot_every:
                        report['own_rgb']['captured' if pixels_kind is None else 'reused'] += 1
                    if pixels_kind is None:
                        rod_frame = base64.b64decode(port.capture()['image'])
                    else:
                        # the frozen world's render forwards the whole world (robot._sync_real_camera_mount: set the camera mount, mj_forward) before it
                        # draws; a skipped render does the same, so the physics stays bit-identical to a run that rendered (measured: without it the
                        # evaluation rows differ at 1e-7 m from the first skipped tick)
                        with world.physics_lock:
                            world.robot(rid)._sync_real_camera_mount()
                    jpeg = rod_frame
                else:
                    pixels_kind = None
                    jpeg = base64.b64decode(port.capture()['image'])
                obs, jpegs, rel = history.observe(now, jpeg, skill=sequence.skill,
                    object_kind=task['kind'], role=plan['role'],
                    destination_zone='pickup_site' if sequence.skill == 'release' else 'none')
                (output / rel).write_bytes(jpeg)
                if overhead:
                    # one reading of the ceiling cameras per OVERHEAD_EVERY ticks, shared by the robots of one world
                    _shared_oh = shared.setdefault('overhead', {}) if shared is not None else oh
                    if 'frame0' not in oh or tick % overhead_every == 0:
                        if _shared_oh.get('t') != round(now, 3):
                            if 'renderer' not in _shared_oh:
                                _shared_oh['renderer'] = mujoco.Renderer(world.model, oh_mod.HEIGHT, oh_mod.WIDTH)
                                _shared_oh['reader'] = oh_mod.OverheadReader()
                            _pics = {}
                            with world.physics_lock:
                                _need = None
                                if tile_cull:
                                    if 'tile_selector' not in _shared_oh:
                                        _shared_oh['tile_selector'] = tile_geometry.TopCardTiles(
                                            world.model, oh_mod.CAMERAS, world.controllers, oh_mod.WIDTH, oh_mod.HEIGHT)
                                    _need = _shared_oh['tile_selector'].needed(world.data)
                                elif rod_mod is not None:
                                    # --render-on-demand: a ceiling camera whose picture cannot hold a robot's top card is not rendered (same poses read)
                                    _hy = (oh_mod.HEIGHT_M - (oh_mod.BASE_Z + oh_mod.CARD_AT[2])) * oh_mod.ARENA_SHORT_HALF_M / oh_mod.HEIGHT_M
                                    _need = rod_mod.overhead_cameras_needed(oh_mod.CAMERAS, [tuple(world.robot(_r2).base_xyz()[:2]) for _r2 in world.controllers],
                                                                            _hy * oh_mod.WIDTH / oh_mod.HEIGHT, _hy)
                                if _need is not None:
                                    _shared_oh['cams_rendered'] = _shared_oh.get('cams_rendered', 0) + len(_need)
                                    _shared_oh['cams_skipped'] = _shared_oh.get('cams_skipped', 0) + len(oh_mod.CAMERAS) - len(_need)
                                if tile_cull:
                                    def _capture_tile(_cam):
                                        _shared_oh['renderer'].update_scene(world.data, camera=_cam)
                                        return _shared_oh['renderer'].render().copy()
                                    stats = _shared_oh.setdefault('tile_stats', dict(selected=0, omitted=0, checks=0, mismatches=0,
                                                                                    fallback=_shared_oh['tile_selector'].fallback))
                                    report['ceiling_tiles'] = stats
                                    _shared_oh['poses'] = execution_options.read_tiles(
                                        oh_mod.CAMERAS, _need, _capture_tile, _shared_oh['reader'], exec_options.verify_overhead_tiles, stats)
                                else:
                                    for _cam, _ in oh_mod.CAMERAS:
                                        if _need is None or _cam in _need:
                                            _shared_oh['renderer'].update_scene(world.data, camera=_cam)
                                            _pics[_cam] = _shared_oh['renderer'].render().copy()
                            if not tile_cull:
                                _shared_oh['poses'] = _shared_oh['reader'].read(_pics)
                            _shared_oh['t'] = round(now, 3)
                        _poses = _shared_oh.get('poses', {})
                        report['overhead']['reads'] += 1
                        _by = report['overhead'].setdefault('by_stage', {})
                        _st = _by.setdefault(oh.get('last_source', 'start'), [0, 0])
                        _st[0] += 1
                        _st[1] += int(rid in _poses)
                        if rid in _poses:
                            report['overhead']['own_read'] += 1
                            oh['own'], oh['own_t'] = _poses[rid], now
                            if 'frame0' not in oh:
                                # the list frame is where the robot stood at the first tick. Read later than that, step
                                # back along the own drive record (one robot was first read after it had moved, and its
                                # whole frame was off by that move)
                                _w = _poses[rid]
                                _dr = drive.pose() if drive is not None and tick > 0 else {'x': 0., 'y': 0., 'yaw': 0.}
                                _y0 = _w[2] - _dr['yaw']
                                oh['frame0'] = (_w[0] - (_dr['x'] * math.cos(_y0) - _dr['y'] * math.sin(_y0)),
                                                _w[1] - (_dr['x'] * math.sin(_y0) + _dr['y'] * math.cos(_y0)), _y0)
                                report['overhead']['frame0_from_tick'] = tick
                            # evaluation only: how far the measurement is from the simulator's pose
                            _b, _yy = world.robot(rid).base_xyz(), float(world.robot(rid).base_rpy()[2])
                            report['overhead']['err_m'].append(round(math.hypot(_poses[rid][0] - _b[0], _poses[rid][1] - _b[1]), 4))
                            report['overhead']['err_deg'].append(round(math.degrees(math.atan2(math.sin(_poses[rid][2] - _yy), math.cos(_poses[rid][2] - _yy))), 2))
                            if events is not None:
                                events['overhead_pose'] = list(_poses[rid])
                        if door_lane_fix:
                            # a robot whose top card the ceiling cameras miss (8 of 9 readings while it stood still, NZC-R r1) must not vanish from the door's right of way
                            _seen_at = oh.setdefault('others_seen', {})
                            _seen_at.update({r_: (v_, now) for r_, v_ in _poses.items() if r_ != rid})
                            oh['others'] = {r_: v_ for r_, (v_, t_) in _seen_at.items() if now - t_ <= OTHERS_STALE_S}
                        else:
                            oh['others'] = {r_: v_ for r_, v_ in _poses.items() if r_ != rid}
                    if oh.get('own') is not None and now - oh.get('own_t', -1e9) <= OVERHEAD_STALE_S:
                        robots_near = [(r_, oh_mod.to_frame(v_, oh['own'])[:2]) for r_, v_ in oh.get('others', {}).items()]
                if robot_tags and pixels_kind is None:         # (a reused picture is not read again: the reading would repeat the last one)
                    if tag_reader is None:
                        from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D
                        tag_reader = tags_mod.TagReader(scaled_camera_matrix(640, 480), CAMERA_FISHEYE_D)
                    _read = tag_reader.read(jpeg)
                    _signs = [t_ for t_ in _read if 'sign' in t_]
                    if _signs:
                        _gp = sys.modules.get('ground_projection')
                        _posture = {int(k_): int(v_) for k_, v_ in previous['pwm'].items()}
                        with (output / 'signs-seen.jsonl').open('a') as _sf:
                            _sf.write(json.dumps({'t': now - origin, 'frame': Path(rel).stem, 'signs': [
                                dict(sign=t_['sign'], side_px=t_['side_px'],
                                     body=None if _gp is None else tags_mod.sign_on_floor(t_, _posture, _gp.camera_extrinsics, _gp.K))
                                for t_ in _signs]}) + '\n')
                        for t_ in _signs:
                            report['robot_tags']['signs_seen'][str(t_['sign'])] = report['robot_tags']['signs_seen'].get(str(t_['sign']), 0) + 1
                    _tags = [t_ for t_ in _read if t_.get('robot') not in (None, rid)]
                    _gp2 = sys.modules.get('ground_projection')
                    _posture2 = {int(k_): int(v_) for k_, v_ in previous['pwm'].items()}
                    if not overhead:
                        robots_near = []
                    for t_ in _tags:
                        _at = None if _gp2 is None else tags_mod.robot_on_floor(t_, _posture2, _gp2.camera_extrinsics, _gp2.K)
                        if _at is not None:
                            t_['body_xy'] = [round(_at[0], 3), round(_at[1], 3)]
                            if multi_carry:
                                seen_robots[t_['robot']] = (_at[0], _at[1])
                            if not overhead:
                                robots_near.append((t_['robot'], _at))
                    if _tags:
                        report['robot_tags']['frames_with_a_tag'] += 1
                        with (output / 'tags-seen.jsonl').open('a') as _tf:
                            _tf.write(json.dumps({'t': now - origin, 'frame': Path(rel).stem, 'tags': _tags}) + '\n')
                        for t_ in _tags:
                            _s = report['robot_tags']['seen'].setdefault(t_['robot'], {'frames': 0, 'nearest_m': None, 'farthest_m': None})
                            _s['frames'] += 1
                            _s['nearest_m'] = t_['distance_m'] if _s['nearest_m'] is None else min(_s['nearest_m'], t_['distance_m'])
                            _s['farthest_m'] = t_['distance_m'] if _s['farthest_m'] is None else max(_s['farthest_m'], t_['distance_m'])
                        if events is not None:
                            events['robots_seen'] = {'t': now - origin, 'tags': _tags}
                if truth_every and tick % truth_every == 0:
                    # the same pinhole view the lens remap is applied to (the perception undoes that remap)
                    _robot = world.robot(rid)
                    with world.physics_lock, world.render_lock:
                        _robot._sync_real_camera_mount()
                        _r = world.renderer
                        _r.enable_depth_rendering()
                        _r.update_scene(world.data, camera=_robot._n('robot_cam'), scene_option=_robot._robot_sensor_scene_option)
                        _depth = _r.render().copy()
                        _r.disable_depth_rendering()
                        _r.enable_segmentation_rendering()
                        _r.update_scene(world.data, camera=_robot._n('robot_cam'), scene_option=_robot._robot_sensor_scene_option)
                        _seg = _r.render()[..., 0].copy()
                        _r.disable_segmentation_rendering()
                    (output / 'truth').mkdir(exist_ok=True)
                    np.savez_compressed(output / 'truth' / (Path(rel).stem + '.npz'), depth=_depth.astype(np.float32),
                                        geom=_seg.astype(np.int32), t=now - origin, pwm=np.array([previous['pwm'][str(s_)] for s_ in c.SERVOS]))
                    if not (output / 'truth' / 'geoms.json').exists():
                        write_json(output / 'truth' / 'geoms.json', {str(g): {'name': world.model.geom(g).name,
                                   'body': world.model.body(int(world.model.geom_bodyid[g])).name} for g in range(world.model.ngeom)})
                c.validate_observation(obs)
                funnel['frames'] += 1
                funnel['valid_inputs'] += 1
                inputs.write(json.dumps(obs) + '\n')
                ret_value, ret_source = None, 'return_code'
                if choice == 'back':
                    return_attempts, return_pose_waits, look_turn_n = 0, 0, 0
                    if 'door_passed' in events:
                        return_hold = dict(previous['pwm'])
                        return_nav = _build_return_nav()
                        if return_nav is None:
                            report['return_failed'] = {'at_s': now - origin, 'why': 'no ceiling pose or arena at the start of the way back'}
                            sequence_finished = True
                            break
                    else:
                        begin_trip_now = True
                if return_retry_rows and not speaking:
                    return_retry_rows -= 1
                    if not return_retry_rows:
                        return_nav = _build_return_nav(allow_fallback=False)       # the way back is tried again from the measured pose
                        if return_nav is None:
                            return_pose_waits += 1
                            if return_pose_waits <= 100:
                                return_retry_rows = 1                              # no fresh ceiling pose yet: look again at the next tick (10 s at most)
                            else:
                                report['return_failed'] = {'at_s': now - origin, 'why': 'no ceiling pose or arena at the retry of the way back'}
                                sequence_finished = True
                                break
                if speaking or awaiting_next or return_nav is not None or return_retry_rows:
                    ret_value, ret_source = return_or_stand_command(return_nav, jpeg, previous['pwm'], return_hold, now,
                                                                    speaking=speaking, waiting=awaiting_next or bool(return_retry_rows))
                    if speaking:
                        report['talk_stand_rows'] = report.get('talk_stand_rows', 0) + 1
                    if ret_value is None:
                        report.setdefault('returns', []).append(dict(return_nav.record(), carry=trip_n, at_s=now - origin))
                        events['return_outcome'] = return_nav.outcome
                        if return_nav.outcome != 'through_door':
                            if door_lane_fix and return_attempts < RETURN_RETRIES:
                                # --door-lane-fix: stand 10 s (the robot at the door may have moved on) and try the way back again
                                return_attempts += 1
                                return_retry_rows, return_nav = RETURN_RETRY_ROWS, None
                                report.setdefault('return_retries', []).append({'at_s': round(now - origin, 1), 'after': events['return_outcome'], 'attempt': return_attempts})
                                ret_value, ret_source = return_or_stand_command(None, jpeg, previous['pwm'], return_hold, now, speaking=False, waiting=True)
                            else:
                                break                     # it could not get back through the door: its run ends where it stands
                        else:
                            return_nav, begin_trip_now = None, True
                if llm_moves and not (speaking or awaiting_next) and move_run is None and return_nav is None and not begin_trip_now and not look_now:
                    _req = move_source()
                    if _req is not None:
                        move_run = _llm_start_move(_req)
                if move_run is not None and not speaking:
                    # a move the planner chose owns the tick (the approach does not step, nobody is asked) until its rows are used up
                    _mrow = move_run.step(robots_near)
                    if _mrow is not None:
                        _mw, _md = _mrow
                        ret_value = c.command({'t': now, 'wheels': list(_mw), 'duration_s': [_md if w_ else 0. for w_ in _mw], 'pwm': dict(previous['pwm'])})
                        ret_source = 'move_code'
                    else:
                        _mres = dict(move_run.record(), t_end_s=round(now - origin, 1))
                        events.setdefault('moves', []).append(_mres)
                        report.setdefault('llm_moves', []).append(_mres)
                        move_done(_mres)
                        # before the pick the list frame is the one of the old standing place: look around again from the new one (also for 'look')
                        look_now = (_mres['kind'] == 'look' or _mres['motion_rows_done'] > 0) and _mres['where'] in ('pick', 'blocked') and _mres['status'] != 'refused'
                        move_run = None
                if multi_carry and begin_trip_now and not speaking:
                    begin_trip_now = False
                    # The next look-around of the box room starts here. What belonged to the finished carry goes to the record and the
                    # restart is the one after an empty gripper (below); the milestones of the finished carry move to events['trips'] and
                    # events['trip'] tells the planner side that a new carry has begun.
                    trip_reports.append({'carry': trip_n, 'ended_at_s': now - origin, 'approach': approach.record(), 'regrasps': list(regrasps),
                                         'carry_to': dict(carry_to_state, nav=carry_nav.record() if carry_nav is not None else None),
                                         'carry_state': dict(carry_state)})
                    write_json(output / ('approach-trace-trip%d.json' % trip_n), approach.trace)
                    write_json(output / ('alignment-trace-trip%d.json' % trip_n), approach.alignment_trace())
                    events.setdefault('trips', []).append(dict({'carry': trip_n}, **{k_: events.pop(k_) for k_ in ('door_passed', 'carry_finished', 'not_holding')
                                                                                    if k_ in events}))
                    trip_n += 1
                    events['trip'] = trip_n
                    events.pop('door', None)     # the next box can take a different door
                    door_state['id'] = None
                    regrasp_base = len(regrasps)
                    seen_robots.clear()
                    approach_wait['rows'] = 0
                    approach_wait.pop('asks', None)
                    approach_wait.pop('next_ask_rows', None)
                    approach = approach_servo_v1.SurveyApproach(c, lambda entries: survey_select['fn'](entries), places=bool(carry_to), **survey_kw)
                    executor = ChunkExecutor(predict, n_action_steps=n_action_steps, temporal_ensemble_coeff=temporal_ensemble_coeff)
                    rule_state = {'wanted': bool(grasp_transition_rule), 'armed_at_handover': False, 'note': 'pending handover (carry %d)' % trip_n}
                    sequence = SoloSequence(with_release, grasp_rule=False, **sequence_kw)
                    issued_hist, hold_pwm, release_code = [], None, None
                    carry_plan, carry_i, carry_segments, carry_arm, carry_nav = [], 0, [], [], None
                    drive = _dmod.DriveRecord()
                    oh.pop('frame0', None)         # the list frame of the new look-around: derived again from the next ceiling reading, here
                    report['overhead'].setdefault('frame0_resets', []).append({'at_s': now - origin, 'tick': tick, 'carry': trip_n})
                    carry_to_state = {'rule': None if callable(carry_to) else carry_to, 'planned': False,
                                      'decided_by': 'planner' if callable(carry_to) else 'task', 'try': 1, 'carry': trip_n}
                    if map_cfg is not None:
                        carry_to_state['map_zones'] = map_zones      # a new carry state keeps the scene's own signs
                    carry_state = {'started_at_s': None, 'arrived_at_s': None, 'wait_rows': 0, 'release_started_at_s': None,
                                   'trigger': None}
                    hold_state = {'rows': 0, 'pwm': None}
                    history.clock = c.IssuedClock()
                    for _part in vars(score).values():   # evaluation clocks restart with the new grasp
                        if hasattr(_part, 'previous_t'):
                            _part.previous_t = None
                if look_now and not speaking:
                    # llm_moves: a new look-around from where the robot stands now (after a move, or 'look around here'): everything that belonged to the
                    # last list starts afresh, as after an empty gripper (below), but nothing counts as a regrasp
                    look_now = False
                    report.setdefault('llm_looks', []).append({'at_s': now - origin, 'tick': tick, 'entries_before': len(approach.entries or ())})
                    approach_wait['rows'] = 0
                    approach_wait.pop('asks', None)
                    approach_wait.pop('next_ask_rows', None)
                    seen_robots.clear()
                    approach = approach_servo_v1.SurveyApproach(c, lambda entries: survey_select['fn'](entries), places=bool(carry_to), **survey_kw)
                    executor = ChunkExecutor(predict, n_action_steps=n_action_steps, temporal_ensemble_coeff=temporal_ensemble_coeff)
                    rule_state = {'wanted': bool(grasp_transition_rule), 'armed_at_handover': False, 'note': 'pending handover (look again %d)' % len(report['llm_looks'])}
                    sequence = SoloSequence(with_release, grasp_rule=False, **sequence_kw)
                    issued_hist, hold_pwm, release_code = [], None, None
                    carry_plan, carry_i, carry_segments, carry_arm, carry_nav = [], 0, [], [], None
                    drive = _dmod.DriveRecord()
                    oh.pop('frame0', None)         # the list frame of the new look-around: derived again from the next ceiling reading
                    report['overhead'].setdefault('frame0_resets', []).append({'at_s': now - origin, 'tick': tick, 'look_again': len(report['llm_looks'])})
                    carry_to_state = {'rule': None if callable(carry_to) else carry_to, 'planned': False,
                                      'decided_by': 'planner' if callable(carry_to) else 'task', 'try': len(regrasps) + 1}
                    if map_cfg is not None:
                        carry_to_state['map_zones'] = map_zones      # a new carry state keeps the scene's own signs
                    carry_state = {'started_at_s': None, 'arrived_at_s': None, 'wait_rows': 0, 'release_started_at_s': None,
                                   'trigger': None}
                    hold_state = {'rows': 0, 'pwm': None}
                    history.clock = c.IssuedClock()
                    for _part in vars(score).values():   # evaluation clocks restart with the new look-around
                        if hasattr(_part, 'previous_t'):
                            _part.previous_t = None
                # While the approach servo owns the tick, ACT is not called (no chunk is consumed)
                # and the learned done bit is ignored. The first ACT call is on the tick after arrival.
                look_cmd = None
                if look_around and look_request['pending'] and not speaking:
                    # The planner chose to look around again (look_around, DEFAULT off). After a dropped box (a regrasp happened) the robot first
                    # backs off, as far as the ceiling-camera pose and the known walls allow (look_back_m); then everything of the look-around is
                    # restarted exactly as a regrasp restarts it. A look-around that changes nothing (the world is the same) gives the same list.
                    if look_request['back_left'] is None:
                        back_m = 0.
                        if regrasps and oh_mod is not None and oh.get('own') is not None and now - oh.get('own_t', -1e9) <= OVERHEAD_STALE_S:
                            back_m = look_back_m(oh['own'], oh_mod.wall_points(oh_mod.arena_from_model(world.model)['walls']))
                        _n = int(round(back_m / CARRY_UNIT['back']))
                        look_request.update(back_left=_n, gap_left=CARRY_GAP_ROWS if _n else 0, back_n=_n, started_at_s=now - origin, turn_rows=[], turn_spec=None)
                        if look_turn and multi_carry and look_turn_n < len(LOOK_TURN_SPECS):
                            # the same place gives the same list: turn before looking again, alternately right and left
                            look_request['turn_spec'] = LOOK_TURN_SPECS[look_turn_n]
                            look_request['turn_rows'] = list(carry_rows(LOOK_TURN_SPECS[look_turn_n])[0])
                            look_turn_n += 1
                    if look_request['back_left'] > 0:
                        look_request['back_left'] -= 1
                        look_cmd = c.command({'t': now, 'wheels': [CARRY_PULSE[0] * w_ for w_ in CARRY_WHEELS['back']],
                                              'duration_s': [CARRY_PULSE[1]] * 4, 'pwm': dict(previous['pwm'])})
                    elif look_request['gap_left'] > 0:
                        look_request['gap_left'] -= 1
                        look_cmd = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    elif look_request.get('turn_rows'):
                        _tw, _ts = look_request['turn_rows'].pop(0)
                        look_cmd = c.command({'t': now, 'wheels': list(_tw), 'duration_s': [_ts if w_ else 0. for w_ in _tw], 'pwm': dict(previous['pwm'])})
                    else:
                        _look = {'at_s': round(look_request['started_at_s'], 1), 'restart_s': round(now - origin, 1), 'back_pulses': look_request['back_n'],
                                 'entries_before': len(approach.entries or ()), **({'turn': look_request['turn_spec']} if look_request.get('turn_spec') else {})}
                        look_request['done'].append(_look)
                        if events is not None:
                            events.setdefault('look_around', []).append(_look)
                        report['look_around'] = look_request['done']
                        look_request.update(pending=False, back_left=None, gap_left=0, turn_rows=[], turn_spec=None)
                        approach_wait['rows'] = 0
                        approach_wait.pop('asks', None)          # llm_moves: a new look-around starts its ask budget afresh (as the llm_moves look-again restart does)
                        approach_wait.pop('next_ask_rows', None)
                        seen_robots.clear()                      # multi_carry: the robots read by tag are those since this look-around began
                        approach = approach_servo_v1.SurveyApproach(c, lambda entries: survey_select['fn'](entries), places=bool(carry_to), **survey_kw)
                        executor = ChunkExecutor(predict, n_action_steps=n_action_steps, temporal_ensemble_coeff=temporal_ensemble_coeff)
                        rule_state = {'wanted': bool(grasp_transition_rule), 'armed_at_handover': False, 'note': 'pending handover (look around again)'}
                        sequence = SoloSequence(with_release, grasp_rule=False, **sequence_kw)
                        issued_hist, hold_pwm, release_code = [], None, None
                        carry_plan, carry_i, carry_segments, carry_arm, carry_nav = [], 0, [], [], None
                        if drive is not None:
                            drive = _dmod.DriveRecord()
                        if overhead:
                            # the new list frame is where the robot stands now (see the regrasp restart below)
                            oh.pop('frame0', None)
                            report['overhead'].setdefault('frame0_resets', []).append({'at_s': now - origin, 'tick': tick, 'why': 'look_around'})
                        carry_to_state = {'rule': None if callable(carry_to) else carry_to, 'planned': False,
                                          'decided_by': 'planner' if callable(carry_to) else 'task', 'try': len(regrasps) + 1}
                        if map_cfg is not None:
                            carry_to_state['map_zones'] = map_zones      # a new carry state keeps the scene's own signs
                        carry_state = {'started_at_s': None, 'arrived_at_s': None, 'wait_rows': 0, 'release_started_at_s': None,
                                       'trigger': None}
                        hold_state = {'rows': 0, 'pwm': None}
                        history.clock = c.IssuedClock()
                        for _part in vars(score).values():   # evaluation clocks restart with the new grasp
                            if hasattr(_part, 'previous_t'):
                                _part.previous_t = None
                if not speaking and carry_state.get('held') and not carry_state['held']['holding'] and not carry_state['held'].get('handled'):
                    carry_state['held']['handled'] = True
                    if len(regrasps) - regrasp_base >= regrasp_max:
                        break                         # empty gripper, no more tries: this robot ends here
                    # Empty gripper: look around again from here and pick again. Everything of the first try that
                    # belongs to that try is started afresh (the look-around list frame is where the robot stands now).
                    regrasps.append({'at_s': now - origin, 'held': dict(carry_state['held'])})
                    approach_wait['rows'] = 0
                    approach = approach_servo_v1.SurveyApproach(c, lambda entries: survey_select['fn'](entries), places=bool(carry_to), **survey_kw)
                    executor = ChunkExecutor(predict, n_action_steps=n_action_steps, temporal_ensemble_coeff=temporal_ensemble_coeff)
                    rule_state = {'wanted': bool(grasp_transition_rule), 'armed_at_handover': False, 'note': 'pending handover (regrasp)'}
                    sequence = SoloSequence(with_release, grasp_rule=False, **sequence_kw)
                    issued_hist, hold_pwm, release_code = [], None, None
                    carry_plan, carry_i, carry_segments, carry_arm, carry_nav = [], 0, [], [], None
                    if drive is not None:
                        drive = _dmod.DriveRecord()
                    if overhead:
                        # The new look-around list (and everything the carry keeps in the list frame: the picked entry, the
                        # listed boxes, the place memory) is expressed in the body frame of THIS standing place, not of the
                        # first tick. Drop the ceiling-camera anchor so that the next ceiling reading derives it again here
                        # (the drive record was just restarted, so the step-back is zero). Own pose, door and walls then
                        # reach the carry in the same frame as the list. Without this, after a regrasp the own pose was in the
                        # first-tick frame and the picked entry in the new list frame (own_pose-to-picked_entry 0.6-2.3 m
                        # instead of 0.2 m) and the held check turned 70-90 deg away from the pick point.
                        oh.pop('frame0', None)
                        report['overhead'].setdefault('frame0_resets', []).append({'at_s': now - origin, 'tick': tick})
                    carry_to_state = {'rule': None if callable(carry_to) else carry_to, 'planned': False,
                                      'decided_by': 'planner' if callable(carry_to) else 'task', 'try': len(regrasps) + 1}
                    if map_cfg is not None:
                        carry_to_state['map_zones'] = map_zones      # a new carry state keeps the scene's own signs
                    carry_state = {'started_at_s': None, 'arrived_at_s': None, 'wait_rows': 0, 'release_started_at_s': None,
                                   'trigger': None}
                    hold_state = {'rows': 0, 'pwm': None}
                    history.clock = c.IssuedClock()
                    report['regrasps'] = regrasps
                    for _part in vars(score).values():   # evaluation clocks restart with the new grasp
                        if hasattr(_part, 'previous_t'):
                            _part.previous_t = None
                # On the way to its box a robot gives way to a lower-numbered robot close ahead (overhead camera or
                # number tags), at most ROBOT_WAIT_ROWS in one approach. Two robots crossing the box room for the far
                # boxes met mid-way; each approach then ended beside the other robot and the grasp model closed on
                # nothing (team-v19 crossed-X01, LLM T1 X01: first grasps at 0.9-1.2 m and 57-70 deg from the box)
                _yield_to = [r_ for r_, xy in robots_near if r_ < rid and 0. < xy[0] < APPROACH_YIELD_M and abs(xy[1]) < APPROACH_YIELD_HALF_M]
                if ret_value is not None:
                    code, code_source = ret_value, ret_source
                elif look_cmd is not None:
                    code, code_source = look_cmd, 'look_around'
                elif (approach is not None and not approach.arrived and (robot_tags or overhead) and _yield_to
                        and getattr(approach, 'stage', '') == 'approach' and approach_wait['rows'] < ROBOT_WAIT_ROWS and move_run is None):
                    if approach_wait.get('last', -9) < tick - 1:
                        approach_wait.setdefault('waits', []).append({'at_s': now - origin, 'robots': _yield_to})
                    approach_wait['rows'] += 1
                    approach_wait['last'] = tick
                    report['approach_yield'] = approach_wait
                    code = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    code_source = 'approach_yield_wait'
                    if (llm_moves and approach_wait['rows'] >= approach_wait.get('next_ask_rows', YIELD_ASK_ROWS)
                            and approach_wait.get('asks', 0) < YIELD_ASKS_MAX):
                        # llm_moves: the code keeps the robot still; the planner is asked what to do while it stands (keep waiting, or a move)
                        approach_wait['asks'] = approach_wait.get('asks', 0) + 1
                        approach_wait['next_ask_rows'] = approach_wait['rows'] + YIELD_REASK_ROWS
                        _asked = move_ask(approach_wait['rows'] * c.PERIOD_S)
                        if _asked is not None:
                            move_run = _llm_start_move(_asked)
                        elif stand_hold is not None and stand_hold():
                            # Speaking used this turn. If still blocked after it, offer the unspent move choice again.
                            approach_wait['asks'] -= 1
                            approach_wait['next_ask_rows'] = approach_wait['rows'] + 1
                elif stand_hold is not None and approach is not None and not approach.arrived and move_run is None and stand_hold():
                    report['talk_stand_rows'] = report.get('talk_stand_rows', 0) + 1     # free talk: the robot speaks, it stands (see stand_hold)
                    code = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    code_source = 'talk_stand'
                else:
                    code = approach.step(jpeg, now) if approach is not None and not approach.arrived and move_run is None else None
                    code_source = 'code'
                if approach_survey_v1 and approach.arrived and approach.index is None:
                    # Nothing on the look-around list was selected for this robot: there is no box to pick, so the
                    # robot ends here instead of starting the grasp model on nothing.
                    report['no_selection'] = {'at_s': now - origin, 'entries': len(approach.entries or ()),
                                              'note': 'no entry of the look-around list was selected; ended without acting'}
                    break
                if (approach_survey_v1 and approach.arrived and getattr(approach, 'box_not_seen', False) and regrasp_max
                        and not carry_state.get('held')):
                    # The approach and the squaring-up ended without the box ever having been tracked: the grasp model would
                    # start 0.4-0.5 m from a box that was never in the picture (baseline diag 20261116: 15 first grasps, all
                    # empty, about 80 s each). Nothing is held, so this is the empty-gripper case without the grasp: the next
                    # tick looks around again and picks again (the regrasp rule), or the robot ends here when no try is left.
                    # Without regrasps (regrasp_max 0) nothing changes.
                    _ar = approach.record()
                    carry_state['held'] = {'holding': False, 'median_fill': 0.0, 'at_s': now - origin,
                                           'rule': 'the box was never seen in the approach; no grasp was started',
                                           'approach_reason': _ar.get('approach_reason'), 'ticks_visible': _ar.get('ticks_visible'),
                                           'alignment': (_ar.get('alignment') or {}).get('reason')}
                    report.setdefault('not_holding', []).append(dict(carry_state['held']))
                    if events is not None:
                        events.setdefault('not_holding', []).append(now - origin)
                if approach_survey_v1 and approach.arrived and 'act_clock' not in rule_state:
                    # The actor reads two own clocks: time since the skill started and time since the issued arm
                    # posture last changed. The taught skill has no look-around and no squaring-up stage, so at the
                    # handover those clocks read 50-110 s and 12-60 s, and the actor's done output goes above its
                    # threshold before any grasp (replayed: 0.71 at 51 s / 18 s, 0.03 at 25 s / 2 s). The skill clock
                    # is therefore restarted so that it counts the approach stage only, and the posture clock starts
                    # at the handover. Both are the robot's own clocks; nothing external is read.
                    _clock = c.IssuedClock()
                    _clock.skill = (sequence.skill, task['kind'], plan['role'], 'none')
                    _clock.started = now + c.PERIOD_S - approach.approach_seconds()
                    history.clock = _clock
                    rule_state['act_clock'] = {'rebased_at_s': now - origin, 'skill_clock_counts': 'approach stage only',
                                               'approach_s': approach.approach_seconds(), 'posture_clock': 'restarts at the handover'}
                if (carry_to and carry_to_state['rule'] is None and sequence.skill == 'release' and 'note' not in carry_to_state):
                    # the planner names the destination once the box is held; None means it has not decided yet
                    _rule = carry_to()
                    if _rule is not None:
                        accept_planner_destination(carry_to_state, _rule, now - origin, None if multi_carry else events)
                    else:
                        carry_to_state['decide_wait_rows'] = carry_to_state.get('decide_wait_rows', 0) + 1
                elif ((redecide or carry_state['started_at_s'] is None) and callable(carry_to) and carry_nav is not None
                      and carry_to_state['planned'] and carry_to_state['rule']
                      and sequence.skill == 'release' and 'note' not in carry_to_state and not carry_nav.finished
                      and events is not None and 'door_passed' not in events):
                    # another zone (only with redecide), or 'put_down' (also while the robot waits for the door, redecide or not)
                    change_planner_destination(carry_to_state, carry_nav, carry_to(), now - origin, zones=redecide)
                carry_rule = carry_to_state['rule'] if carry_to_state is not None else None
                if carry_rule and not carry_to_state['planned'] and sequence.skill == 'release' and 'note' not in carry_to_state:
                    _dest = None if approach.index is None else carry_destination(carry_rule, approach.entries, approach.index)
                    if _dest is None:
                        carry_to_state['note'] = 'no box was selected or no destination follows from the list; nothing to carry'
                    else:
                        carry_to_state['destination'] = _dest
                        _e, _dr = approach.entries[approach.index], drive.pose()
                        _own = {'x': _e['x'] - CARRY_HELD_M * math.cos(_dr['yaw']),
                                'y': _e['y'] - CARRY_HELD_M * math.sin(_dr['yaw']), 'yaw': _dr['yaw']}
                        if overhead and oh.get('own') is not None and oh.get('frame0') is not None:
                            _m = oh_mod.to_frame(oh['own'], oh['frame0'])
                            _own = {'x': _m[0], 'y': _m[1], 'yaw': _m[2]}
                        _others = [(o['x'], o['y']) for i, o in enumerate(approach.entries) if i != approach.index]
                        _to_door = carry_rule in ('door', 'through_door') or carry_rule.startswith('zone_')
                        if _to_door:
                            # memory-based carry: the door remembered from the look-around (or searched for), then
                            # close looks to line up; see harness/carry_nav_v1.py
                            carry_nav = carry_nav_mod.CarryNav(carry_kit, approach.places, _own, _others, carry_rule,
                                                                held_kind=task['kind'], picked=[_e['x'], _e['y']],
                                                               told=place_told, zone_confirm_close=zone_confirm_close,
                                                               **({'zone_close_fix': True} if zone_close_fix else {}),
                                                               **({'zone_close_far': True} if zone_close_far else {}))
                            if overhead and oh.get('frame0') is not None:
                                def _pose_now():
                                    # a reading older than OVERHEAD_STALE_S is not used (the card was hidden or out of view)
                                    if oh.get('own') is None or float(world.data.time) - oh.get('own_t', -1e9) > OVERHEAD_STALE_S:
                                        return None
                                    _m = oh_mod.to_frame(oh['own'], oh['frame0'])
                                    return {'x': _m[0], 'y': _m[1], 'yaw': _m[2]}
                                carry_nav.pose_source = _pose_now
                                carry_nav.others_source = lambda: [oh_mod.to_frame(v_, oh['frame0'])[:2] for v_ in oh.get('others', {}).values()]
                            carry_nav.check_held = bool(regrasp_max) or bool(carry_to)
                            carry_nav.held_edge_fix = bool(held_edge_fix)
                            carry_nav.sign_scan_early_stop = bool(sign_scan_early_stop)
                            carry_nav.door_lane_fix = bool(door_lane_fix)
                            if multi_carry and oh.get('frame0') is not None:
                                carry_nav.right_of_way_source = (lambda: (rid, {r_: tuple(oh_mod.to_frame(v_, oh['frame0'])[:2])
                                                                                for r_, v_ in oh.get('others', {}).items()}))
                            if overhead and oh.get('frame0') is not None:
                                # the arena shape (walls, the door) goes to the motion code only (user decision 2026-11-15)
                                _arena = oh_mod.arena_from_model(world.model)
                                if _arena['doors']:
                                    _d = _pick_door(_arena['doors'], commit=True)
                                    _f = lambda xy: list(oh_mod.to_frame((xy[0], xy[1], 0.), oh['frame0'])[:2])
                                    _door = {'x': _f((_d['x'], _d['y']))[0], 'y': _f((_d['x'], _d['y']))[1],
                                             'left': _f(_d['left']), 'right': _f(_d['right']), 'width_m': _d['width_m']}
                                    carry_nav.set_arena(_door, [_f(p_) for p_ in oh_mod.wall_points(_arena['walls'])])
                                    # wall faces (the four edges of each wall box) for reading wall signs: the sign's
                                    # bearing comes from the picture, its distance from the wall the view ray meets
                                    approach.places.known_wall_segments = [
                                        (_f(a_), _f(b_)) for x0_, y0_, x1_, y1_ in _arena['walls']
                                        for a_, b_ in (((x0_, y0_), (x1_, y0_)), ((x1_, y0_), (x1_, y1_)),
                                                       ((x1_, y1_), (x0_, y1_)), ((x0_, y1_), (x0_, y0_)))]
                                    carry_to_state['arena'] = {'door_world': _d, 'wall_points': len(carry_nav.known_walls),
                                                               'wall_faces': len(approach.places.known_wall_segments)}
                                # destination sign positions are NOT given (user decision 2026-11-15 04:2x KST: "벽 / 문은
                                #줘도, 목적지는 안 주는 게 좋겠어"): the robot finds its sign with its own camera
                            _plan = {'spec': None}
                        else:
                            _plan = carry_to_plan(_own, carry_to_state['destination'], _others)
                            carry_plan, carry_segments, carry_arm = carry_rows(_plan['spec'])
                        carry_to_state.update(_plan, planned=True, own_pose=_own, drive_record=_dr,
                                              picked_entry=[_e['x'], _e['y']],
                                              own_pose_rule='position: listed box position minus the held offset along the '
                                                            'drive-record heading; heading: drive record')
                if carry_nav is not None and carry_nav.finished and carry_state['arrived_at_s'] is None:
                    carry_state['arrived_at_s'] = now - origin
                if events is not None and carry_nav is not None:
                    if carry_nav.phase in ('scan', 'zone_told', 'zone_near', 'zone_final', 'done') and carry_nav.outcome is None:
                        events.setdefault('door_passed', now - origin)
                    if carry_nav.finished and not (multi_carry and carry_nav.outcome in ('at_zone', PUT_DOWN)):
                        events.setdefault('carry_finished', {'at_s': now - origin, 'outcome': carry_nav.outcome})
                if code is not None:
                    value, done, source = code, False, code_source
                elif (carry_to_state is not None and carry_to_state['rule'] is None and sequence.skill == 'release'
                      and 'note' not in carry_to_state):
                    # holding the box, destination not decided yet: stand still
                    value = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    done, source = False, 'carry_decide_wait'
                elif (carry_gate is not None and carry_nav is not None and sequence.skill == 'release'
                      and carry_state['started_at_s'] is None and not carry_gate()):
                    # told to wait before carrying (another robot is using the door): stand still, box held
                    value = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    done, source = False, 'carry_gate_wait'
                    carry_state['gate_wait_rows'] = carry_state.get('gate_wait_rows', 0) + 1
                elif ((robot_tags or overhead) and carry_nav is not None and sequence.skill == 'release' and not carry_nav.finished
                      and carry_state['started_at_s'] is not None
                      and any(0. < xy[0] < ROBOT_AHEAD_M and abs(xy[1]) < ROBOT_AHEAD_HALF_M for _, xy in robots_near)
                      and carry_state.get('robot_wait_rows', 0) - carry_state.get('robot_wait_started', 0) < ROBOT_WAIT_ROWS):
                    # another robot read by its number tag stands in the way ahead while carrying: hold still until it
                    # has moved on (at most ROBOT_WAIT_ROWS in one go). Own picture only.
                    if carry_state.get('robot_wait_last', -9) < tick - 1:
                        carry_state['robot_wait_started'] = carry_state.get('robot_wait_rows', 0)
                        carry_state.setdefault('robot_waits', []).append({'at_s': now - origin, 'robots': [r_ for r_, _ in robots_near]})
                    carry_state['robot_wait_rows'] = carry_state.get('robot_wait_rows', 0) + 1
                    carry_state['robot_wait_last'] = tick
                    value = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    done, source = False, 'robot_ahead_wait'
                elif (carry_nav is not None and 'held' not in carry_state and carry_nav.held_result in ('held', 'not_held')):
                    # the navigation's held check has answered (it backed off and looked for the box on the floor)
                    carry_state['held'] = {'holding': carry_nav.held_result == 'held', 'median_fill': _box_fill(jpeg),
                                           'at_s': now - origin, 'rule': 'box left on the floor ahead after backing off'}
                    if not carry_state['held']['holding']:
                        report.setdefault('not_holding', []).append(dict(carry_state['held']))
                        if events is not None:
                            events.setdefault('not_holding', []).append(now - origin)
                    value = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    done, source = False, 'held_check'
                elif (carry_nav is not None and sequence.skill == 'release' and not carry_nav.finished and
                      'held' in carry_state and not _still_held(jpeg)):
                    # the box is gone from the gripper: stop here; the next tick restarts from a look-around
                    value = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    done, source = False, 'box_lost'
                elif stand_hold is not None and carry_nav is not None and sequence.skill == 'release' and not carry_nav.finished and stand_hold():
                    report['talk_stand_rows'] = report.get('talk_stand_rows', 0) + 1     # free talk: the robot speaks, it stands (see stand_hold)
                    value = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    done, source = False, 'talk_stand'
                elif (carry_nav is not None and sequence.skill == 'release' and not carry_nav.finished and
                      (_nav_command := carry_navigation_command(carry_nav, jpeg, previous['pwm'], hold_pwm, carry_state, now)) is not None):
                    value, source = _nav_command
                    done, carry_i = False, carry_nav.i
                    if carry_state['started_at_s'] is None:
                        carry_state['started_at_s'] = now - origin
                elif carry_plan and sequence.skill == 'release' and carry_i < len(carry_plan):
                    _w, _d = carry_plan[carry_i]
                    _hold = dict(hold_pwm if hold_pwm is not None else carry_state.setdefault('hold_pwm', dict(previous['pwm'])))
                    carry_state['arm_level'] = carry_arm[carry_i]
                    carry_i += 1
                    value = c.command({'t': now, 'wheels': list(_w), 'duration_s': [_d if w else 0. for w in _w],
                                       'pwm': carry_pwm(_hold, carry_state['arm_level'])})
                    done, source = False, 'carry_code'
                    if carry_state['started_at_s'] is None:
                        carry_state['started_at_s'] = now - origin
                    if carry_i == len(carry_plan):
                        carry_state['arrived_at_s'] = now - origin + c.PERIOD_S
                elif (carry_on and sequence.skill == 'release' and release_code is None and not (
                        (release_at_s is None and release_signal is None)
                        or (release_at_s is not None and now - origin >= release_at_s - 1e-8)
                        or (release_signal is not None and Path(release_signal).exists()))):
                    # Arrived; standing still with the box held until the release trigger.
                    value = c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4, 'pwm': dict(previous['pwm'])})
                    done, source = False, 'carry_wait'
                    carry_state['wait_rows'] += 1
                elif release_on and sequence.skill == 'release':
                    # Release skill: the teacher's median table owns the tick (ACT is not called).
                    if release_code is None:
                        release_code = release_mod.ReleaseCodeV1(c, previous['pwm'])
                        carry_state['release_started_at_s'] = now - origin
                        carry_state['trigger'] = (
                            'none' if not carry_on or (release_at_s is None and release_signal is None) else
                            'signal' if release_signal is not None and Path(release_signal).exists() else 'time')
                    value, done = release_code.step(now)
                    source = 'release_code'
                elif release_on and sequence.skill == 'grasp' and sequence.rule is not None and sequence.rule.fired:
                    # release_code_v1 hold (coordinator, 90711): from the tick the grasp-end rule fired until the release
                    # replay starts, ACT is not used. Servos 1,3,4,5,6 hold the median of the issued PWM of the last 45
                    # rows before the rule fired; the wheels stay at zero (the contract checks the row).
                    if hold_pwm is None:
                        hold_pwm = {}
                        for s in ('1', '3', '4', '5', '6'):
                            # the rows that satisfied the rule (its hold_rows: 45, or 25 with --act-hold-short); at 45 this is all of issued_hist
                            vals = sorted(r[s] for r in issued_hist[-sequence.rule.hold_rows:]) or [previous['pwm'][s]]
                            m = len(vals)
                            hold_pwm[s] = int(round(vals[m // 2] if m % 2 else 0.5 * (vals[m // 2 - 1] + vals[m // 2])))
                        hold_state['pwm'] = dict(hold_pwm)
                    value = c.command({'t': now, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4, 'pwm': dict(hold_pwm)})
                    done = False
                    source = 'release_hold'
                    hold_state['rows'] += 1
                else:
                    if exec_options is not None and exec_options.physics_until_act:
                        execution_options.restore_at_first_act(world)
                    value, done = executor.step(obs, jpegs)
                    source = 'act'
                if (multi_carry or llm_moves) and not speaking and stand_hold is not None and stand_hold():
                    # A pick, destination, gate or blocked callback just spoke within this tick.
                    speaking = True
                    if source != 'talk_stand':
                        report['talk_stand_rows'] = report.get('talk_stand_rows', 0) + 1
                    value, source = return_or_stand_command(None, jpeg, previous['pwm'], None, now, speaking=True, waiting=False)
                    done = False
                if audit_grasp_start and source == 'act' and 'act_start' not in report:
                    # Evaluation only, after action selection and before its first physics step.
                    base = world.model.body(rid + '__robot').id
                    poses = {'base': (world.data.xpos[base], world.data.xmat[base]),
                             'box': (world.data.xpos[body], world.data.xmat[body])}
                    for finger, side in fingers.items():
                        poses['finger%d' % side] = (world.data.geom_xpos[finger], world.data.geom_xmat[finger])
                    report['act_start'] = {'item': task['item'], 'poses': {
                        k: [xyz.tolist(), rotation.tolist()] for k, (xyz, rotation) in poses.items()}}
                if release_on:
                    issued_hist.append({s: int(value['pwm'][s]) for s in ('1', '3', '4', '5', '6')})
                    issued_hist = issued_hist[-45:]
                if gaze is not None and sequence.skill == 'grasp' and source == 'act':
                    # Code-side gaze correction (opt-in). It replaces the PWM of
                    # the gaze servos 3, 4 and 6 of this tick and leaves the
                    # wheels and servos 1 and 5 untouched. The corrected row is
                    # what the port applies and what is recorded as the robot's
                    # own issued command, so the ACT input history matches what
                    # the robot really commanded.
                    value = gaze.apply(value, jpeg)
                if diagnostic_observer is not None:
                    diagnostic_observer(obs, jpeg, value, done)
                funnel['actions'] += 1
                row = {'command': value, 'skill': obs['skill'], 'done_requested': done}
                if approach is not None or release_on:
                    row['source'] = source
                commands.write(json.dumps(row) + '\n')
                oh['last_source'] = row.get('source', 'act')
                # Match recording's independent normalized wheel pulses exactly.
                port._command_expires_at = port._drive_expires_at = None
                port._set_motors(tuple(value['wheels']))
                deadlines = [now + d for d in value['duration_s']]
                for s in c.SERVOS:
                    pwm = value['pwm'][str(s)]
                    if pwm != previous['pwm'][str(s)]:
                        port.apply({'kind': 'look', 'pan_pulse': pwm} if s == 6 else
                                   {'kind': 'arm', 'servo_id': s, 'pulse': pwm}, now)
                history.issue(value)
                if drive is not None:
                    drive.issue(value)
                previous = value
                clearance = min(float(world.data.geom_xpos[g, 2] - np.abs(world.data.geom_xmat[g].reshape(3, 3)[2]) @ world.model.geom_size[g]) for g in gids)
                rotation = world.data.xmat[body].reshape(3, 3)
                tilt = math.degrees(math.acos(float(np.clip(rotation[2, 2], -1, 1))))
                forces, force = [0., 0.], np.zeros(6)
                for i in range(world.data.ncon):
                    contact = world.data.contact[i]
                    a, b = int(contact.geom1), int(contact.geom2)
                    finger = a if b in gids else b if a in gids else None
                    if finger in fingers:
                        mujoco.mj_contactForce(world.model, world.data, i, force)
                        forces[fingers[finger]] += abs(float(force[0]))
                evaluation = {'clearance': clearance, 'tilt': tilt, 'forces': forces,
                              'weld': bool(world.data.eq_active.any())}
                if teacher_start_v1:
                    from harness.visual_arm_v3 import MOUNT_X_M
                    target = world.data.xpos[body]
                    base = world.robot(rid).base_xyz()
                    yaw = float(world.robot(rid).base_rpy()[2])
                    object_yaw = math.atan2(rotation[1, 0], rotation[0, 0])
                    station = target[:2] - (MOUNT_X_M + .152) * np.array([math.cos(object_yaw), math.sin(object_yaw)])
                    station_error = float(np.linalg.norm(station - np.asarray(base[:2])))
                    yaw_error = abs(math.atan2(math.sin(object_yaw-yaw), math.cos(object_yaw-yaw)))
                    gaps = [float(mujoco.mj_geomDistance(world.model, world.data, finger, g,
                                float(world.model.stat.extent), None)) for finger in fingers for g in gids]
                    evaluation.update(station_error_m=station_error, yaw_error_rad=yaw_error,
                                      target_finger_min_gap_m=min(gaps), target_object=task['item'])
                    if approach is not None:
                        # Evaluation-only diagnostic (approach on): base pose for the post-hoc check of which
                        # box was acquired. The approach servo never reads these values.
                        evaluation.update(base_x=float(base[0]), base_y=float(base[1]), base_yaw=yaw,
                                          object_x=float(target[0]), object_y=float(target[1]), object_yaw=object_yaw)
                    contacts=[]
                    for contact in world.data.contact[:world.data.ncon]:
                        a,b=int(contact.geom1),int(contact.geom2)
                        names=[world.model.geom(g).name or str(g) for g in (a,b)]
                        if sum(n.startswith(rid+'__') for n in names)!=1:continue
                        external=names[1] if names[0].startswith(rid+'__') else names[0]
                        if 'floor' in external or 'ground' in external:continue
                        contacts.append({'object':external,'gap_m':float(contact.dist)})
                    evaluation['external_contacts']=contacts
                    if carry_on:
                        # Evaluation only: what the carried box itself touches besides the robot and the floor.
                        touched = []
                        for contact in world.data.contact[:world.data.ncon]:
                            a, b = int(contact.geom1), int(contact.geom2)
                            if (a in gids) == (b in gids):
                                continue
                            name = world.model.geom(b if a in gids else a).name or str(b if a in gids else a)
                            if name.startswith(rid + '__') or 'floor' in name or 'ground' in name:
                                continue
                            touched.append({'object': name, 'gap_m': float(contact.dist)})
                        evaluation['object_contacts'] = touched
                    if contacts:
                        contact=min(contacts,key=lambda x:x['gap_m'])
                        if minimum_external_contact is None or contact['gap_m']<minimum_external_contact['gap_m']:
                            minimum_external_contact=contact
                velocity = np.zeros(6)
                mujoco.mj_objectVelocity(world.model, world.data, mujoco.mjtObj.mjOBJ_BODY, body, velocity, 0)
                linear_speed = float(np.linalg.norm(velocity[3:]))
                score.add(now, skill=obs['skill'], linear_speed=linear_speed,
                          **{k: evaluation[k] for k in ('clearance', 'tilt', 'forces', 'weld')})
                if teacher_start_v1:
                    passed=evaluation_gates(evaluation,stable_lift=score.lift.record()['lift_success'])
                    predecessor=True
                    for stage,ok in passed.items():
                        ok=predecessor and ok
                        funnel[stage] += int(ok)
                        if ok:first_pass.setdefault(stage,now)
                        predecessor=stage in first_pass
                evaluations.write(json.dumps({'t': now, 'skill': obs['skill'],
                    'linear_speed': linear_speed, **evaluation}, allow_nan=False) + '\n')
                if tick % 10 == 0:
                    if rod_stats is not None:
                        report['render_on_demand'] = dict(rod_stats.record(), ceiling_cameras_rendered=(shared or {}).get('overhead', oh).get('cams_rendered', 0),
                                                          ceiling_cameras_skipped=(shared or {}).get('overhead', oh).get('cams_skipped', 0))
                    for stream in (inputs, commands, evaluations):
                        stream.flush()
                    write_json(output / 'progress.json', {'sim_s': now-origin, 'done_requested': done,
                               'inference_calls': len(latencies)})
                # Student done + fixed clock window are the ONLY phase/stop inputs.
                # Evaluation truth never enters the sequence or the worker.
                # With the rule enabled the sequence additionally reads the
                # robot's OWN issued command row (wheels and commanded PWM) and
                # the clock. It never reads contact force, tilt, clearance,
                # ground truth or weld.
                if rule_state['wanted'] and sequence.rule is None and approach is not None and approach.arrived:
                    # Drive-record distance to the stop point at the handover (the approach's own odometry; never ground
                    # truth). A near-range handover arms the rule only within 0.10 m of the stop point (|d - D_STOP| <= 0.10).
                    d_drive = approach.trace[-1]['d_est_m'] if approach.trace else None
                    near_stop = d_drive is not None and abs(d_drive - approach_servo_v1.D_STOP_M) <= 0.10
                    if approach.reason in ('arrived', 'settled') or (approach.reason == 'handover_near_no_blob' and near_stop):
                        sequence.rule = GraspTransitionRule(hold_rows=sequence_kw.get('hold_rows'))
                        rule_state['armed_at_handover'] = True
                        rule_state['note'] = ('armed: approach %s' % approach.reason if approach.reason in ('arrived', 'settled') else
                                              'armed: approach %s, drive-record d_est %.3f m within 0.10 m of the stop point'
                                              % (approach.reason, d_drive))
                    else:
                        rule_state['note'] = 'off: approach %s%s' % (approach.reason, '' if d_drive is None else
                                                                   ' (drive-record d_est %.3f m)' % d_drive)
                    rule_state['wanted'] = False
                if (act_done_exit and approach_survey_v1
                        and act_done_exit_row(rule_state, done, skill=sequence.skill, rule=sequence.rule)
                        and regrasp_max and not carry_state.get('held')):
                    # --act-done-exit (DEFAULT off; a work record). The grasp model has asked to be done for ACT_DONE_EXIT_ROWS rows in a
                    # row while the grasp end rule has not fired (the box is gone: another robot lifted it, or it was pushed away; the arm stands in
                    # the rest posture and the learned done bit, ignored just below, stays up until the cap). That is a failed grasp. Same
                    # empty-gripper case as the box_not_seen one: the next tick looks around again and picks again (the regrasp rule), or the
                    # robot ends here when no try is left. Without regrasps (regrasp_max 0) nothing changes. The row reads the raw learned
                    # done bit, which is read before it is ignored below.
                    carry_state['held'] = {'holding': False, 'median_fill': 0.0, 'at_s': now - origin,
                                           'rule': 'the grasp model reported done for %d rows without the grasp end rule firing' % ACT_DONE_EXIT_ROWS,
                                           'done_rows': rule_state['done_run']}
                    report.setdefault('not_holding', []).append(dict(carry_state['held']))
                    report.setdefault('act_done_exit', []).append({'at_s': now - origin, 'rows': rule_state['done_run'],
                                                                   'try': len(regrasps) + 1})
                    if events is not None:
                        events.setdefault('not_holding', []).append(now - origin)
                # approach_survey_v1: once the own-command rule is armed, the rule alone ends the grasp skill.
                # The learned done bit fired 0.6 s after the handover in one development run (90802) and the
                # release started before any grasp; such rows are counted and ignored during the grasp skill.
                if approach_survey_v1 and done and sequence.skill == 'grasp' and sequence.rule is not None:
                    rule_state['learned_done_ignored_rows'] = rule_state.get('learned_done_ignored_rows', 0) + 1
                    done = False
                    # Issue #695 (R73): ChunkExecutor latches done_requested and then returns zero wheels on every
                    # later tick without predicting, so an ignored done froze the robot until the cap (CF4-D01-T1-r1
                    # r2: 7587 rows, 758.7 SIM s). The rule owns the grasp end here, so release the latch as well.
                    if getattr(executor, 'done_requested', False):
                        executor.done_requested = False
                        executor.pending = []
                        rule_state['learned_done_latch_released'] = rule_state.get('learned_done_latch_released', 0) + 1
                if source == 'zone_unconfirmed':
                    if events is not None:
                        events.setdefault('carry_finished', {'at_s': now - origin, 'outcome': source})
                    report['termination'] = source
                    sequence_finished = True
                    break
                if not (speaking or awaiting_next or return_nav is not None or return_retry_rows) and sequence.update(now, done, issued=value):
                    outcome = PUT_DOWN if carry_to_state and carry_to_state.get('put_down') else getattr(carry_nav, 'outcome', None)
                    if multi_carry and outcome in ('at_zone', PUT_DOWN):
                        # A precedence wait and a new trip both start from the completed release, including its settle rows.
                        events['carry_finished'] = {'at_s': now - origin, 'outcome': outcome}
                        awaiting_next = True
                    else:
                        sequence_finished = True
                        break
                tick += 1
                until = origin + tick * c.PERIOD_S
                _signal = yield {'world': world, 'robot': world.robot(rid), 'port': port, 'wheels': value['wheels'],
                                 'deadlines': deadlines, 'until': until}
                if _signal == 'body_stopped':
                    # the runner stopped this robot's body (a failed robot, run_team fail_robot) and now ends the generator so that its report is
                    # written like that of any robot (without this it would end with GeneratorExit and read 'HOST_ERROR'). Never sent by default.
                    report['body_stopped'] = True
                    break
        if multi_carry:
            events.setdefault('trips', []).append(dict({'carry': trip_n}, **{k_: events[k_] for k_ in ('door_passed', 'carry_finished', 'not_holding') if k_ in events}))
            report['trips'] = trip_reports          # the carries before the last one; the last one is in the usual keys of this report
            report['multi_carry'] = {'carries': trip_n, 'returns': len(report.get('returns', []))}
        report['release_code_v1'] = dict(
            release_code.record() if release_code is not None else
            {'enabled': release_on, 'started': False, 'source': 'teacher median table, 140 demos'},
            hold_between=dict(hold_state),
            status='EXPERIMENT: 놓기 재생 (사용자 결정 전 실험)')
        if approach is not None:
            report['approach_survey_v1' if approach_survey_v1 else 'approach_code_v1'] = approach.record()
            write_json(output / 'approach-trace.json', approach.trace)
            if approach_survey_v1:
                write_json(output / 'alignment-trace.json', approach.alignment_trace())
        report.update(status='complete', complete=True, sim_s=float(world.data.time)-origin,
            done_requested=bool(sequence.done_times), done_times=sequence.done_times,
            **score.record(sequence.done_times, with_release=with_release),
            inference_latency_s={'n': len(latencies), 'median': float(np.median(latencies)) if latencies else None,
                                 'p95': float(np.percentile(latencies, 95)) if latencies else None},
            skill_completion_success=None)
        if carry_test_v1:
            report['carry_test_v1'] = {'enabled': True, 'rows_issued': carry_i, 'rows_planned': len(carry_plan),
                                       'plan': 'back 20 pulses, turn 30 pulses, forward 40 pulses (0.10 s at 0.35), posture held'}
        if carry_to:
            if zone_confirm_close:
                carry_to_state['zone_confirm_close'] = True
            if carry_nav is not None:
                carry_to_state['nav'] = carry_nav.record()
                carry_segments = carry_nav.segments
            report['carry_to'] = dict(carry_to_state, frame='look-around list frame (body frame at the first tick)',
                                      constants={'held_m': CARRY_HELD_M, 'setdown_m': CARRY_SETDOWN_M, 'sweep_m': CARRY_SWEEP_M,
                                                 'back_max_m': CARRY_BACK_MAX_M, 'body_m': CARRY_BODY_M, 'path_m': CARRY_PATH_M},
                                      drive_record_end=drive.pose())
        if carry_on:
            report['carry_v1'] = {'enabled': True, 'spec': carry_v1 or carry_to_state.get('spec'), 'segments': carry_segments,
                                  'frame': "robot's own frame when the carry starts; drive record only",
                                  'pulse': {'wheel': CARRY_PULSE[0], 'seconds': CARRY_PULSE[1]}, 'unit_per_pulse': CARRY_UNIT,
                                  'rows_issued': carry_i, 'rows_planned': len(carry_nav.rows) if carry_nav is not None else len(carry_plan),
                                  'release_at_s': release_at_s, 'release_signal': bool(release_signal), **carry_state}
        if approach is not None:
            report['grasp_rule_at_handover'] = dict(rule_state)
        if sequence.rule is not None:
            # Distinguish a rule completion from a learned done bit. With the
            # rule OFF this block does not run at all, so the report keeps the
            # exact shape it had before the rule existed.
            report['grasp_transition_rule'] = {
                'enabled': True,
                'inputs': 'own issued commands (wheels, commanded PWM) and the clock only',
                'completion_cause': dict(sequence.done_causes),
                'fired': bool(sequence.rule.fired),
                'fired_at_sim_s': sequence.rule.fire_t,
                'constants': {'end_pwm': sequence.rule.end_pwm,
                              'tolerance_pwm': sequence.rule.tolerance_pwm,
                              'hold_rows': sequence.rule.hold_rows},
                'evidence_episodes': 1,
                'note': 'a rule completion is NOT a learned done bit; the release '
                        'skill still completes only through the learned done bit'}
        if rod_stats is not None:
            report['render_on_demand'] = dict(rod_stats.record(), ceiling_cameras_rendered=(shared or {}).get('overhead', oh).get('cams_rendered', 0),
                                              ceiling_cameras_skipped=(shared or {}).get('overhead', oh).get('cams_skipped', 0))
        report['cap_end'] = reached_cap(report['sim_s'], cap_s, sequence_finished=sequence_finished)
        report.setdefault('termination', 'cap_end' if report['cap_end'] else 'student_done')
        if report.get('body_stopped'):
            report['termination'] = 'body_stopped'
        if teacher_start_v1:
            missing = next((s for s in ('approach', 'alignment', 'grasp', 'lift_confirmation') if s not in first_pass), None)
            report.update(failure_stage=missing, funnel=funnel, first_pass_sim_t=first_pass)
            write_json(output / 'funnel.json', {'schema': 'ugrp.act14.funnel.v1', 'counts': funnel,
                'cumulative_run_pass': {s: int(s in first_pass) for s in ('approach','alignment','grasp','lift_confirmation')},
                'first_pass_sim_t': first_pass, 'failure_stage': missing,
                'rejection': None if missing is None else {'category': missing+'_not_passed',
                    'blocking_object': minimum_external_contact['object'] if minimum_external_contact else 'none_observed',
                    'target_object': plan['item_id'],
                    'minimum_gap_m': minimum_external_contact['gap_m'] if minimum_external_contact else None,
                    'target_finger_min_gap_m': evaluation.get('target_finger_min_gap_m'),
                    'scope': 'observed non-floor external contacts; no collision cause inferred'},
                'source': str(output / 'eval-only.jsonl'), 'reproduce': 'python -m scripts.analyze_grasp_act_act14 --root '+str(output)})
    except BaseException as exc:
        report.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'HOST_ERROR',
                      complete=False, error_type=type(exc).__name__)
        raise
    finally:
        if prediction_log is not None:
            prediction_log.close()
        if port is not None:
            port.stop()
        if worker is not None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill(); worker.wait(timeout=5)
        if world is not None and shared is None:
            world.close()
        if gaze is not None:
            report['gaze_correction'].update(gaze.record())
            report['gaze_correction']['applied'] = bool(gaze.corrected)
        report['wall_s'] = time.monotonic() - begin
        report['artifacts'] = {str(p.relative_to(output)): sha256(p) for p in output.rglob('*')
                               if p.is_file() and p.name != 'summary.json'}
        write_summary(output / 'summary.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--actor-python', required=True)
    p.add_argument('--cap-s', type=float, default=60.)
    p.add_argument('--n-action-steps', type=int, default=c.CHUNK)
    p.add_argument('--temporal-ensemble-coeff', type=float)
    p.add_argument('--actor-threads', type=int, choices=(1, 2, 4, 8, 16), default=1)
    p.add_argument('--actor-server-url', help='opt-in private L4, own-input-only inference')
    p.add_argument('--teacher-start-v1', action='store_true')
    # 2026-11-13 variant copy (main): rule ON by default for the g-seg + rule evaluation; the
    # multi-round guest entry point cannot pass the flag. summary.json records grasp_transition_rule.
    p.add_argument('--grasp-transition-rule', action='store_true', default=True,
                   help='opt-in: complete the grasp skill from the robot\'s own issued '
                        'commands (wheels still + grasp end posture held 45 rows) '
                        'instead of the learned done bit. Default off.')
    p.add_argument('--carry-test-v1', action='store_true',
                   help='development check (default off): drive with the box held between the lift and the release')
    p.add_argument('--carry-v1', help="opt-in (default off): carry the held box along own-frame segments before the "
                                      "release, e.g. 'back:0.28,left:90,fwd:0.55' (metres, degrees; hold:<s> waits)")
    p.add_argument('--carry-to', help="opt-in (default off): put the picked box at a point of the look-around list "
                                      "frame: 'x,y' in metres (+x ahead of the start pose, +y left), or start, mid, beside, door, through_door, zone_orange, zone_blue, zone_purple")
    p.add_argument('--zone-confirm-close', action='store_true', help='require a close camera fix before the final zone approach and release')
    p.add_argument('--scene-without', default='', help="task-definition option (default none): object kinds left out of the "
                                                          "arena, comma separated, e.g. 'long_beam'")
    p.add_argument('--place-told', help="with --carry-to zone_<colour>: where another robot said that zone is, measured "
                                        "from the door: 'forward,left' in metres past the door and to its left")
    p.add_argument('--release-at-s', type=float, help='with --carry-v1: hold the box until this episode time, then release')
    p.add_argument('--release-signal', type=Path, help='with --carry-v1: hold the box until this file exists, then release')
    p.add_argument('--approach-survey-v1', action='store_true',
                   help='opt-in (default off): look around, approach the indexed observed box, square up, then ACT')
    p.add_argument('--approach-code-v1', action='store_true',
                   help='opt-in (default off): code-side approach servo to the stop reference, then ACT')
    p.add_argument('--gaze-code-v1', action='store_true',
                   help='opt-in: the code owns the gaze during the approach and steers '
                        'the cyan target of the own RGB frame back to the optical '
                        'centre (servo 6 pan, servo 3/4 tilt). The wheels and the '
                        'gripper stay with ACT and the arm is handed back to ACT '
                        'after three consecutive ticks with all four ACT wheels at '
                        'zero. Default off.')
    p.add_argument('--release-code-v1', action='store_true',
                   help='EXPERIMENTAL opt-in (default off): replay the teacher median release table (87 rows, 140 demos) '
                        'as the release skill commands instead of ACT. Also on by plan key release_code_v1.')
    p.add_argument('--robot-tags', action='store_true', help='task definition: number tags on the robots, read from the own picture')
    p.add_argument('--overhead', action='store_true', help='ceiling cameras measure the robots for the motion code')
    p.add_argument('--truth-every', type=int, default=0, help='evaluation side: write true depth and object ids of the own view every N ticks')
    p.add_argument('--scene-source', type=Path, help='frozen 6f057f7e scene/physics package; no teacher policy')
    p.add_argument('--render-cull', action='store_true', help='use the same frustum culling as the team runner')
    p.add_argument('--render-on-demand', action='store_true', help='use the team idle-frame and empty-tile rules')
    p.add_argument('--audit-grasp-start', action='store_true', help='record base, box and finger poses at the first ACT command')
    execution_options.add_arguments(p)
    a = p.parse_args()
    opts = execution_options.from_args(p, a)
    from contextlib import ExitStack
    from scripts.run_grasp_act_recovery import dependency_modules
    if a.teacher_start_v1 != bool(a.scene_source):
        p.error('--teacher-start-v1 requires the exact frozen --scene-source')
    if a.gaze_code_v1:
        global _gaze_class
        _gaze_class = _load_gaze_class()
    with ExitStack() as stack:
        if a.render_cull:
            from harness import render_cull_v1
            cull = render_cull_v1.install()
            stack.callback(cull.uninstall)
        if a.scene_source:
            stack.enter_context(dependency_modules(a.scene_source))
        run(json.loads(a.plan.read_text()), json.loads(a.protocol.read_text()), a.model, a.output,
            actor_python=a.actor_python, cap_s=a.cap_s, n_action_steps=a.n_action_steps,
            temporal_ensemble_coeff=a.temporal_ensemble_coeff, actor_threads=a.actor_threads,
            teacher_start_v1=a.teacher_start_v1, actor_server_url=a.actor_server_url,
            grasp_transition_rule=a.grasp_transition_rule, gaze_code_v1=a.gaze_code_v1,
            approach_code_v1=a.approach_code_v1, release_code_v1=a.release_code_v1,
            approach_survey_v1=a.approach_survey_v1, carry_test_v1=a.carry_test_v1,
            carry_v1=a.carry_v1, release_at_s=a.release_at_s, release_signal=a.release_signal,
            truth_every=a.truth_every, robot_tags=a.robot_tags, overhead=a.overhead, carry_to=a.carry_to, scene_without=tuple(k for k in a.scene_without.split(',') if k),
            place_told=dict(zip(('forward_m', 'left_m'), (float(v) for v in a.place_told.split(',')))) if a.place_told else None,
            **({'zone_confirm_close': True} if a.zone_confirm_close else {}),
            **({'render_on_demand': True} if a.render_on_demand else {}),
            **({'audit_grasp_start': True} if a.audit_grasp_start else {}),
            **({'exec_options': opts} if opts is not None else {}))


if __name__ == '__main__':
    main()
