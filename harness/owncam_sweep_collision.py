"""Shared static-body look collision API for memory_v3 and EXECFIX.

body_spheres/OwnPose/static boxes and sphere clearances are extracted from
499e4fd6445614a8b647eaea11f7bb9c77e5e2bd:harness/zone_own_guards.py.
Uses issued PWM, own-camera pose uncertainty and authored walls/door posts;
no live robot/body/contact state. The calibrated sphere model is unchanged.
Unlike that snapshot, uncertainty is not capped and unknown poses fail closed.
plan_safe_sweep checks transitions, the entire pan path and the restore path.
"""
from __future__ import annotations
import math
from collections.abc import Mapping
from dataclasses import dataclass
import numpy as np
from harness import visual_arm as va
from harness.owncam_localizer import GRIP_OPEN_MIN

BODY_MODEL_SOURCE = '499e4fd6445614a8b647eaea11f7bb9c77e5e2bd'

def _finite(*values):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)

BODY_MOUNT_XYZ_M = (0.0, 0.0, 0.0)
BODY_COVERAGE_RESIDUAL_M = .015            # measured 0.0144 m (camera body AABB corner, carry)
R_LINK_M = .022                     # arm links (servo brackets)
BEARING_Z_M, BEARING_R_M = .085, .045   # arm yaw bearing (r1__base_yaw_bearing_visual, z 0.07-0.10 m)
R_GRIP_CLOSED_M = .030              # gripper + camera, fingers closed / on a box
R_GRIP_OPEN_M = .045                # fingers open (servo 1 >= GRIP_OPEN_MIN)
R_BOX_M = .035                      # held 0.04 m box: half diagonal
TOOL_SAMPLES_CM = (0., 3., 6., 9., va.GRIPPER_LINK_CM + 2.)
# Chassis (base frame, env v3 record: x +0.094 m, |y| 0.081 m; rear from UNLOADED_ENVELOPE) and its height.
CHASSIS_X_M, CHASSIS_Y_M, CHASSIS_TOP_M = (-.15, .10), .09, .10
BASE_MARGIN_M = .02
K_SIGMA = 2.


def _servo(pose: Mapping) -> dict[int, int]:
    return {int(k): int(v) for k, v in pose.items()}


def body_spheres(servo: Mapping, *, loaded: bool, mount_xyz_m=BODY_MOUNT_XYZ_M) -> list[tuple[float, float, float, float]]:
    """(x, y, z_above_floor, radius) of the arm, gripper/fingers and held box in the base frame.

    Forward kinematics: ``harness.visual_arm`` (tool points via ``tool_pose``; the elbow from the same
    link constants). Pan (servo 6) rotates everything about the arm yaw axis at ``mount_xyz_m``.
    """
    pose = _servo(servo)
    yaw = math.radians((pose[6] - va.BASE_CENTER) / va.PULSE_PER_DEGREE)
    cy, sy = math.cos(yaw), math.sin(yaw)
    theta5 = math.radians(90. - (pose[5] - va.SERVO_DEVIATION[5] - 1500.) / va.PULSE_PER_DEGREE)
    z0 = (va.ROBOT_BASE_FLOOR_HEIGHT_CM + va.LINK_1_CM) / 100.
    elbow_r, elbow_z = va.LINK_2_CM * math.cos(theta5) / 100., z0 + va.LINK_2_CM * math.sin(theta5) / 100.
    wrist = va.tool_pose(pose, tool_length_cm=0.)
    wrist_r, wrist_z = math.hypot(wrist.x_m, wrist.y_m) * (1 if wrist.x_m * cy + wrist.y_m * sy >= 0 else -1), wrist.z_m
    mx, my, mz = (float(v) for v in mount_xyz_m)
    out = []

    def add(r, z, radius):
        out.append((mx + r * cy, my + r * sy, mz + z, radius))

    add(0., BEARING_Z_M, BEARING_R_M)                   # yaw bearing disc on the chassis
    for u in (0., .5, 1.):
        add(u * elbow_r, z0 + u * (elbow_z - z0), R_LINK_M)
    for u in (.5, 1.):
        add(elbow_r + u * (wrist_r - elbow_r), elbow_z + u * (wrist_z - elbow_z), R_LINK_M)
    grip = R_GRIP_OPEN_M if pose.get(1, 1500) >= GRIP_OPEN_MIN else R_GRIP_CLOSED_M
    for length in TOOL_SAMPLES_CM:
        tp = va.tool_pose(pose, tool_length_cm=length)
        out.append((mx + tp.x_m, my + tp.y_m, mz + tp.z_m, grip))
    if loaded:
        tp = va.tool_pose(pose, tool_length_cm=va.GRIPPER_LINK_CM)
        out.append((mx + tp.x_m, my + tp.y_m, mz + tp.z_m, R_BOX_M))
    return out


def static_boxes(static_map: Mapping) -> list[dict]:
    """Walls and door posts of the static map with their heights (2-D rectangle + height)."""
    out = []
    for o in static_map.get('obstacles', ()):
        out.append({'id': o['id'], 'center': tuple(map(float, o['center_m'])), 'half': tuple(map(float, o['half_extents_m'])),
                    'yaw': float(o.get('yaw_rad', 0.)), 'height': float(o.get('height_m', 1.))})
    for p in (static_map.get('landmarks') or {}).get('door_posts', ()):
        out.append({'id': p['id'], 'center': tuple(map(float, p['center_m'])), 'half': tuple(map(float, p['half_extents_m'])),
                    'yaw': 0., 'height': float(p['height_m'])})
    return out


def _rect_distance(box, x, y) -> float:
    (cx, cy), (hx, hy) = box['center'], box['half']
    dx, dy = x - cx, y - cy
    if box['yaw']:
        c, s = math.cos(box['yaw']), math.sin(box['yaw'])
        dx, dy = c * dx + s * dy, -s * dx + c * dy
    return math.hypot(max(abs(dx) - hx, 0.), max(abs(dy) - hy, 0.))


@dataclass(frozen=True, slots=True)
class OwnPose:
    """The own estimate the guard works on (x, y, yaw, sigma); never a simulator pose."""
    x: float
    y: float
    yaw: float
    std_xy: float
    std_yaw: float

    @classmethod
    def from_estimate(cls, est: Mapping) -> 'OwnPose | None':
        if not est or not est.get('initialized'):
            return None
        vals = (est.get('x'), est.get('y'), est.get('yaw'), est.get('std_xy_m'), est.get('std_yaw_rad'))
        return cls(*map(float, vals)) if _finite(*vals) else None

    @classmethod
    def from_report(cls, rep) -> 'OwnPose | None':
        if rep is None or not rep.initialized:
            return None
        vals = (rep.x_m, rep.y_m, rep.yaw_rad, rep.std_xy_m, rep.std_yaw_rad)
        return cls(*map(float, vals)) if _finite(*vals) else None

    def moved(self, dx_base: float, dy_base: float) -> 'OwnPose':
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        return OwnPose(self.x + c * dx_base - s * dy_base, self.y + s * dx_base + c * dy_base, self.yaw,
                       self.std_xy, self.std_yaw)


class SweepGuard:
    """Static-map collision check for own arm/finger/box sweeps and chassis back-offs."""

    def __init__(self, static_map: Mapping, *, mount_xyz_m=BODY_MOUNT_XYZ_M, residual_m=BODY_COVERAGE_RESIDUAL_M):
        self.boxes = static_boxes(static_map)
        self.mount = tuple(float(v) for v in mount_xyz_m)
        self.residual = float(residual_m)

    def margin(self, pose: OwnPose, lever_m: float) -> float:
        sxy, syaw = pose.std_xy, pose.std_yaw
        return BASE_MARGIN_M + self.residual + K_SIGMA * sxy + K_SIGMA * syaw * lever_m

    def arm_clearance(self, servo: Mapping, pose: OwnPose, *, loaded: bool) -> tuple[float, str | None]:
        """Smallest (distance - radius - margin) of any body sphere to any wall/post it is not above."""
        best, hit = math.inf, None
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        for bx, by, bz, r in body_spheres(servo, loaded=loaded, mount_xyz_m=self.mount):
            mx, my = pose.x + c * bx - s * by, pose.y + s * bx + c * by
            margin = self.margin(pose, math.hypot(bx, by))
            for box in self.boxes:
                if bz - r >= box['height'] + margin:
                    continue                                    # passes over this wall
                d = _rect_distance(box, mx, my) - r - margin
                if d < best:
                    best, hit = d, box['id']
        return best, hit

    def chassis_clearance(self, pose: OwnPose) -> tuple[float, str | None]:
        (x0, x1), hy = CHASSIS_X_M, CHASSIS_Y_M
        pts = [(x, y) for x in np.linspace(x0, x1, 6) for y in (-hy, hy)] + [(x, y) for x in (x0, x1)
                                                                           for y in np.linspace(-hy, hy, 5)]
        best, hit = math.inf, None
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        for bx, by in pts:
            mx, my = pose.x + c * bx - s * by, pose.y + s * bx + c * by
            margin = self.margin(pose, math.hypot(bx, by))
            for box in self.boxes:
                d = _rect_distance(box, mx, my) - margin
                if d < best:
                    best, hit = d, box['id']
        return best, hit


# At most 20 PWM between checks; enclose the intervening revolute motion by
# the whole arm's reach times the angle. 0.55 m exceeds the sum of link/tool
# lengths of this pinned model. Add it to the residual, including z clearance.
TRANSITION_SAMPLE_PWM = 20
BODY_REACH_BOUND_M = .55


def _valid(pose, servo):
    return (pose is not None and _finite(pose.x, pose.y, pose.yaw, pose.std_xy, pose.std_yaw)
            and pose.std_xy >= 0 and pose.std_yaw >= 0
            and all(k in servo and 500 <= servo[k] <= 2500 for k in (1, 3, 4, 5, 6)))


def _servo_box_clear(guard, low, high, pose, loaded):
    """Enclose every joint ordering/interpolation within a command step.

    A centre sphere moves by at most reach * sum(abs(joint angle change)).
    Subdivide ambiguous PWM boxes; never infer safety from endpoints alone.
    """
    mid = {k: (low[k]+high[k])/2 for k in low}
    moving = [k for k in low if k != 1 and low[k] != high[k]]
    # body_spheres converts PWM to integers: include <1 PWM per moving joint.
    half_span = sum(abs(high[k]-low[k])/2+1 for k in moving)
    padding = BODY_REACH_BOUND_M * math.radians(half_span/va.PULSE_PER_DEGREE) * (1+K_SIGMA*pose.std_yaw)
    if max(low[1], high[1]) >= GRIP_OPEN_MIN:
        mid[1] = GRIP_OPEN_MIN  # open sphere envelope covers the whole grip stroke
    padded = SweepGuard({}, residual_m=guard.residual+padding, mount_xyz_m=guard.mount)
    padded.boxes = guard.boxes
    if padded.arm_clearance(mid, pose, loaded=loaded)[0] >= 0:
        return True
    if not moving or guard.arm_clearance(mid, pose, loaded=loaded)[0] < 0:
        return False
    joint = max(moving, key=lambda k: abs(high[k]-low[k]))
    if abs(high[joint]-low[joint]) <= TRANSITION_SAMPLE_PWM:
        return False  # uncertainty enclosure still touches: do not authorize
    cut = (low[joint]+high[joint])/2
    return (_servo_box_clear(guard, low, {**high, joint: cut}, pose, loaded)
            and _servo_box_clear(guard, {**low, joint: cut}, high, pose, loaded))


def transition_clear(guard: SweepGuard, current, target, pose: OwnPose | None, *, loaded: bool) -> bool:
    """Check complete 60 PWM/tick issued-command envelopes, including restore.

    The joint box at each step includes serial and simultaneous interpolation.
    This is the calibrated static command model, not measured robot motion.
    """
    cur, target = _servo(current), _servo(target)
    if not _valid(pose, cur) or not _valid(pose, {**cur, **target}):
        return False
    while True:
        nxt = {**cur, **{k: cur[k]+max(-60, min(60, v-cur[k])) for k, v in target.items()}}
        if not _servo_box_clear(guard, cur, nxt, pose, loaded):
            return False
        if nxt == cur:
            return True
        cur = nxt


def commands_clear(static_map, current, commands, pose, *, loaded, guard=None):
    """Public arm/look batch check, including simultaneous servo transitions."""
    guard = guard or SweepGuard(static_map)
    target = {}
    for cmd in commands:
        if cmd['kind'] == 'look':
            target[6] = int(cmd['pan_pulse'])
        elif cmd['kind'] == 'arm':
            target[int(cmd['servo_id'])] = int(cmd['pulse'])
    return not target or transition_clear(guard, current, target, pose, loaded=loaded)


def plan_safe_sweep(static_map, current, look_pose, pans, pose, *, loaded, restore, guard=None):
    """Importable shared API: safe ordered pans plus explicit rejection reason.

    Retain a pan only if the whole path to it AND restore from it are clear.
    This also permits any short-look early exit. Never substitute an unchecked
    home pan when all choices fail. No implicit base back-off is issued.
    """
    guard = guard or SweepGuard(static_map)
    cur, look = _servo(current), _servo(look_pose)
    requested = list(map(int, pans))
    result = {'pans': [], 'dropped': requested, 'reason': 'no_own_estimate', 'transition_clear': False}
    if not _valid(pose, cur):
        return result
    # Driver/sweep moves the look arm first, then pan. Treat look pan separately.
    arm = {k: v for k, v in look.items() if k != 6}
    if not transition_clear(guard, cur, arm, pose, loaded=loaded):
        return {**result, 'reason': 'unsafe_posture_transition'}
    look = {**cur, **arm}
    kept, dropped = [], []
    for pan in requested:
        if (transition_clear(guard, look, {6: pan}, pose, loaded=loaded)
                and transition_clear(guard, {**look, 6: pan}, restore, pose, loaded=loaded)):
            kept.append(pan)
            look[6] = pan
        else:
            dropped.append(pan)
    return {'pans': kept, 'dropped': dropped, 'transition_clear': True,
            'reason': 'clear' if kept and not dropped else 'restricted' if kept else 'no_clear_pan'}
