"""Own-input guards of the package F executor (issue #221; Codex review 2 of PR #206).

Every guard reads only the robot's own inputs: its own ``PoseReport`` / localizer estimate (own
wrist RGB + own issued commands), its own issued servo PWM, the static map and a fixed body
calibration. Nothing here imports the simulator, reads a peer or a ground-truth value.

1. :class:`UncertaintyGate` - two thresholds + dwell (Schmitt trigger) on the own pose sigma. Motion
   and ``own_camera_confirmed`` require BOTH an ok gate and current sigma at or below HIGH;
   ``pose_uncertain`` fires once per entry and re-arms only after a dwelled exit below the LOW
   threshold (Codex P1-1, P1-3: sigma oscillating 0.079/0.081 m fired an event per frame).
2. :class:`SweepGuard` - 3-D look-sweep collision check of the own arm, fingers and held box
   (spheres on ``harness.visual_arm`` forward kinematics of the issued PWM, calibrated once against
   the robot's own MuJoCo body: ``experiments/2026-09-26-zone-own-executor/body_model_calibration.json``)
   against the static map's walls and door posts (with their heights), inflated by the own pose
   sigma. A look keeps only the pans of the contiguous collision-free interval around the current
   pan, or backs off first (Codex P1-2: +-48 deg pans in a 0.40 m-wall door hit the jamb).
3. :class:`ProgressMonitor` - no-progress check adapted from Nav2 ``SimpleProgressChecker``: the
   own trusted estimate must move ``REQUIRED_MOVEMENT_M`` within ``STALL_COMMANDED_M`` of own
   commanded travel, confirmed by a fresh own look; on a stall the guarded driver backs off (Nav2
   ``BackUp``), marks a keep-out ahead (never at the goal or a door) and replans, at most
   ``MAX_RECOVERIES`` times (Nav2 ``RecoveryNode`` retries), then finishes ``blocked``. Inconclusive
   progress looks have a separate cumulative bound ending in ``progress_unconfirmed`` (Codex P1-3:
   660 SIM s pushing an unseen box until the 720 s job limit).
4. :class:`BlockageStreak` - route-blockage commits counted per location (passage, map cell,
   heading sector) with a maximum gap (Codex P2-7: two looks at different places made one streak).

:class:`harness.zone_own_driver.GuardedDriver` applies 1-3 to ``OwnCamDriverV2``; the executor uses it for
``goto`` and for every M1 delivery leg.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np

from harness import visual_arm as va
from harness.m1_owncam_delivery import LIMITS as M1_LIMITS
from harness.owncam_drive import CONTROL_S
from harness.owncam_drive_v2 import LOADED_FIX_STD_XY_M
from harness.owncam_localizer import GRIP_OPEN_MIN

SCHEMA = 'ugrp.zone_own_guards.v2'   # v1 = smoke v2 (a5b3687e): drive-time stall rule

# ---------------------------------------------------------------- 1. uncertainty gate


@dataclass(frozen=True, slots=True)
class GateProfile:
    """ENTER ``uncertain`` above HIGH for ``enter_dwell_s``; EXIT to ``ok`` at or below LOW for ``exit_dwell_s``."""
    name: str
    high_xy_m: float
    high_yaw_rad: float
    low_xy_m: float
    low_yaw_rad: float
    enter_dwell_s: float = .6          # 3 own frames at 5 Hz
    exit_dwell_s: float = .4           # 2 own frames


# HIGH = the pre-registered M1 navigation limits (m1_owncam_delivery.LIMITS); LOW = the loop-driver fix
# thresholds (owncam_drive LOOK_IF_STD_XY_M 0.05 unloaded, owncam_drive_v2 LOADED_FIX_STD_XY_M 0.06 loaded).
GATE_UNLOADED = GateProfile('unloaded', M1_LIMITS['nav_unloaded'].max_std_xy_m, M1_LIMITS['nav_unloaded'].max_std_yaw_rad,
                            .05, .06)
GATE_LOADED = GateProfile('loaded', M1_LIMITS['nav_loaded'].max_std_xy_m, M1_LIMITS['nav_loaded'].max_std_yaw_rad,
                          LOADED_FIX_STD_XY_M, math.radians(2.5))
for _p in (GATE_UNLOADED, GATE_LOADED):
    assert _p.low_xy_m < _p.high_xy_m and _p.low_yaw_rad < _p.high_yaw_rad, _p


def loaded_gate_profile(yaw_deg=None):
    """Instance-scoped loaded gate; the registered singleton stays unchanged."""
    if yaw_deg is None:
        return GATE_LOADED
    high, low = yaw_deg
    if not (math.isfinite(high) and math.isfinite(low) and 0 < low < high):
        raise ValueError('loaded yaw gate needs finite 0 < LOW < HIGH')
    return replace(GATE_LOADED, high_yaw_rad=math.radians(high), low_yaw_rad=math.radians(low))


def _finite(*values) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


class UncertaintyGate:
    """Schmitt trigger with dwell on (std_xy, std_yaw). Starts ``uncertain`` (nothing confirmed yet)."""

    def __init__(self, profile: GateProfile = GATE_UNLOADED):
        self.profile = profile
        self.state = 'uncertain'
        self.since: float | None = None
        self._candidate_since: float | None = None
        self._last_t: float | None = None
        self.transitions: list[dict] = []

    @property
    def ok(self) -> bool:
        return self.state == 'ok'

    def allows(self, initialized, std_xy, std_yaw) -> bool:
        """Immediate motion/confirmation interlock; event-entry dwell is NOT a grace period."""
        return self.ok and self.classify(initialized, std_xy, std_yaw) != 'high'

    def allows_estimate(self, est: Mapping) -> bool:
        return self.allows(est.get('initialized'), est.get('std_xy_m'), est.get('std_yaw_rad'))

    def set_profile(self, profile: GateProfile) -> None:
        if profile is not self.profile:
            self.profile, self._candidate_since = profile, None

    def classify(self, initialized, std_xy, std_yaw) -> str:
        """'high' (above HIGH, unknown or non-finite), 'low' (at or below LOW) or 'band'."""
        p = self.profile
        if not initialized or not _finite(std_xy, std_yaw):
            return 'high'
        if std_xy > p.high_xy_m or std_yaw > p.high_yaw_rad:
            return 'high'
        if std_xy <= p.low_xy_m and std_yaw <= p.low_yaw_rad:
            return 'low'
        return 'band'

    def update(self, t: float, initialized: bool, std_xy: float, std_yaw: float) -> str | None:
        """Feed one own estimate; returns 'entered' / 'exited' on a transition, else None."""
        if not _finite(t) or (self._last_t is not None and t < self._last_t):
            return None                                   # out-of-order or corrupt time: ignored
        self._last_t = float(t)
        cls = self.classify(initialized, std_xy, std_yaw)
        want = 'high' if self.state == 'ok' else 'low'
        dwell = self.profile.enter_dwell_s if self.state == 'ok' else self.profile.exit_dwell_s
        if cls != want:
            self._candidate_since = None
            return None
        if self._candidate_since is None:
            self._candidate_since = float(t)
        if t - self._candidate_since + 1e-9 < dwell:
            return None
        self.state = 'uncertain' if self.state == 'ok' else 'ok'
        self.since, self._candidate_since = float(t), None
        change = 'entered' if self.state == 'uncertain' else 'exited'
        self.transitions.append({'t': round(float(t), 3), 'change': change, 'profile': self.profile.name,
                                 'std_xy_m': None if not _finite(std_xy) else round(float(std_xy), 4)})
        return change

    def as_dict(self) -> dict:
        return {'state': self.state, 'profile': self.profile.name, 'since_sim_s': self.since,
                'transitions': len(self.transitions)}


# ---------------------------------------------------------------- 2. body model + sweep guard
# Body calibration (calibrate_body_model.py, own robot MuJoCo body, sync SIM, no scene object read).
# The arm yaw axis in the base frame and the sphere-model coverage residual are pinned here; the test
# ``test_body_model_matches_the_calibration_record`` re-reads the record.
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
SIGMA_CAP_XY_M = .15                # = owncam_drive.LOST_STD_XY_M: beyond it the estimate is lost anyway
SIGMA_CAP_YAW_RAD = .20
PAN_STEP_PWM = 20
BACKOFF_SPEED_MPS = .05             # = CameraRobotPort reverse limit
BACKOFF_DISTANCES_M = (.08, .15)
BACKOFF_GAIN_MAX = 1.6              # commanded -> actual displacement (calibration motion gain up to ~1.47)
MAX_LOOK_BACKOFFS = 1


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
    """Static-map collision check for own arm/finger/box sweeps and whole-body back-offs."""

    def __init__(self, static_map: Mapping, *, mount_xyz_m=BODY_MOUNT_XYZ_M, residual_m=BODY_COVERAGE_RESIDUAL_M,
                 loaded_k_xy=K_SIGMA, loaded_k_yaw=K_SIGMA):
        self.boxes = static_boxes(static_map)
        self.mount = tuple(float(v) for v in mount_xyz_m)
        self.residual = float(residual_m)
        self.loaded_k_xy, self.loaded_k_yaw = float(loaded_k_xy), float(loaded_k_yaw)

    def margin(self, pose: OwnPose, lever_m: float, *, loaded=False) -> float:
        sxy, syaw = min(pose.std_xy, SIGMA_CAP_XY_M), min(pose.std_yaw, SIGMA_CAP_YAW_RAD)
        kxy, kyaw = (self.loaded_k_xy, self.loaded_k_yaw) if loaded else (K_SIGMA, K_SIGMA)
        return BASE_MARGIN_M + self.residual + kxy * sxy + kyaw * syaw * lever_m

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

    def _clear(self, servo, pose, loaded):
        return self.arm_clearance(servo, pose, loaded=loaded)[0] >= 0.

    def transition_samples(self, current, target):
        """Issued path, including its start; shared by the check and diagnostic only."""
        cur, target = _servo(current), _servo(target)
        yield cur
        while any(cur.get(k, v) != v for k, v in target.items()):
            nxt = {**cur, **{k: cur.get(k, v) + max(-60, min(60, v - cur.get(k, v)))
                             for k, v in target.items()}}
            for u in (1 / 3, 2 / 3, 1.):
                yield {k: round(cur.get(k, v) + u * (v - cur.get(k, v))) for k, v in nxt.items()}
            cur = nxt

    def transition_clear(self, current, target, pose: OwnPose | None, *, loaded: bool) -> bool:
        """Check the issued 60-PWM-per-tick path, including simultaneous pan/arm restoration.

        Check intermediate PWM every <=20 units, with the same per-joint clipping as the callers.
        An uninitialized pose retains the existing stationary bootstrap look policy.
        """
        if pose is None:
            return True
        return all(self._clear(sample, pose, loaded) for sample in self.transition_samples(current, target))

    def transition_diagnostic(self, current, target, pose: OwnPose | None, *, loaded: bool) -> dict:
        """Own-input evidence only. Never consumed by the motion/clearance decision."""
        out = {'source': 'own_estimate_and_issued_pwm_static_map', 'loaded': bool(loaded),
               'current_pwm': _servo(current), 'target_pwm': {**_servo(current), **_servo(target)},
               'own_estimate': None if pose is None else dict(x_m=pose.x, y_m=pose.y, yaw_rad=pose.yaw,
                                                            std_xy_m=pose.std_xy, std_yaw_rad=pose.std_yaw),
               'limiting': None}
        if pose is None:
            return out
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        best = math.inf
        for sample in self.transition_samples(current, target):
            for i, (bx, by, bz, radius) in enumerate(body_spheres(sample, loaded=loaded, mount_xyz_m=self.mount)):
                mx, my = pose.x + c * bx - s * by, pose.y + s * bx + c * by
                margin = self.margin(pose, math.hypot(bx, by))
                for box in self.boxes:
                    if bz - radius >= box['height'] + margin:
                        continue
                    raw = _rect_distance(box, mx, my) - radius
                    clearance = raw - margin
                    if clearance < best:
                        best = clearance
                        part = ('yaw_bearing' if i == 0 else 'upper_arm' if i < 4 else 'forearm' if i < 6
                                else 'gripper_camera_fingers' if i < 6 + len(TOOL_SAMPLES_CM) else 'held_box')
                        out['limiting'] = {'sample_pwm': sample, 'sphere_index': i, 'sphere_part': part,
                                           'sphere_center_base_m': [bx, by, bz], 'sphere_radius_m': radius,
                                           'wall_id': box['id'], 'raw_clearance_mm': raw * 1000,
                                           'margin_mm': margin * 1000, 'clearance_mm': clearance * 1000,
                                           'overlap_mm': max(0., -clearance) * 1000}
        return out

    def translation_clear(self, current, pose: OwnPose | None, dx: float, dy: float, *, loaded: bool) -> bool:
        """Check the unchanged issued arm/fingers/cargo AND chassis over gain [0, 1.6].

        At <=5 mm spacing, reserve half a sample interval as extra clearance. Distance to a
        static rectangle is 1-Lipschitz under translation, so the gaps between samples are covered.
        No measured joints, contact feedback or live object positions enter this check.
        """
        if pose is None or not _finite(dx, dy):
            return False
        dx, dy = dx * BACKOFF_GAIN_MAX, dy * BACKOFF_GAIN_MAX
        distance = math.hypot(dx, dy)
        steps = max(1, math.ceil(distance / .005))
        reserve = distance / (2 * steps)
        for i in range(steps + 1):
            at = pose.moved(dx * i / steps, dy * i / steps)
            if min(self.chassis_clearance(at)[0], self.arm_clearance(current, at, loaded=loaded)[0]) < reserve:
                return False
        return True

    def plan(self, current: Mapping, look_pose: Mapping, pans: Sequence[int], pose: OwnPose | None, *,
             loaded: bool, allow_backoff: bool = False) -> dict:
        """Which of ``pans`` a look from ``current`` (issued PWM) may visit, or a back-off to take first.

        The arm first moves servos 1/3/4/5 to ``look_pose`` at the current pan (checked along the way),
        then pans; a pan is kept when the whole pan interval between it and the current pan is clear.
        """
        cur = _servo(current)
        pan0 = int(cur.get(6, va.BASE_CENTER))
        pans = [int(p) for p in pans]
        if pose is None:
            return {'pans': pans, 'dropped': [], 'backoff': None, 'reason': 'no_own_estimate', 'interval': None}
        look = {**cur, **_servo(look_pose), 6: pan0}
        trans_ok = self.transition_clear(cur, look, pose, loaded=loaded)
        lo, hi = min(pans + [pan0]), max(pans + [pan0])
        interval = None
        if trans_ok and self._clear({**look, 6: pan0}, pose, loaded):
            a = b = pan0
            while a - PAN_STEP_PWM >= lo and self._clear({**look, 6: a - PAN_STEP_PWM}, pose, loaded):
                a -= PAN_STEP_PWM
            b_ok = True
            while b_ok and b + PAN_STEP_PWM <= hi:
                b_ok = self._clear({**look, 6: b + PAN_STEP_PWM}, pose, loaded)
                b += PAN_STEP_PWM if b_ok else 0
            # endpoints between the grid and the requested pan itself
            a = lo if a - lo < PAN_STEP_PWM and self._clear({**look, 6: lo}, pose, loaded) else a
            b = hi if hi - b < PAN_STEP_PWM and self._clear({**look, 6: hi}, pose, loaded) else b
            interval = (a, b)
        kept = [p for p in pans if interval is not None and interval[0] <= p <= interval[1]]
        dropped = [p for p in pans if p not in kept]
        result = {'pans': kept, 'dropped': dropped, 'backoff': None, 'interval': interval,
                  'reason': 'clear' if not dropped else 'restricted' if kept else 'no_clear_pan',
                  'transition_clear': trans_ok, 'margin_m': round(self.margin(pose, .2), 4)}
        if dropped and allow_backoff:
            result['backoff'] = self.backoff(cur, look_pose, pans, pose, loaded=loaded, have=len(kept))
        return result

    def backoff(self, current, look_pose, pans, pose: OwnPose, *, loaded: bool, have: int) -> dict | None:
        """A whole-body-clear move (base frame, commanded) improving the available look pans."""
        best = None
        for deg in range(0, 360, 45):
            ux, uy = math.cos(math.radians(deg)), math.sin(math.radians(deg))
            for dist in BACKOFF_DISTANCES_M:
                dx, dy = round(ux * dist, 4), round(uy * dist, 4)
                if not self.translation_clear(current, pose, dx, dy, loaded=loaded):
                    continue
                plan = self.plan(current, look_pose, pans, pose.moved(ux * dist, uy * dist), loaded=loaded)
                end_ok = all(self._clear({**_servo(current), **_servo(look_pose), 6: p},
                                         pose.moved(ux * dist * BACKOFF_GAIN_MAX, uy * dist * BACKOFF_GAIN_MAX), loaded)
                             for p in plan['pans'])
                if not end_ok:
                    continue
                score = (len(plan['pans']), -dist)
                if len(plan['pans']) > have and (best is None or score > best[0]):
                    best = (score, {'dx_base_m': round(ux * dist, 4), 'dy_base_m': round(uy * dist, 4),
                                    'pans_after': plan['pans']})
        return None if best is None else best[1]


def backoff_commands(move: Mapping) -> tuple[dict, float]:
    """One mecanum command (per control tick) and its total duration for a commanded base move."""
    dx, dy = float(move['dx_base_m']), float(move['dy_base_m'])
    dist = math.hypot(dx, dy)
    duration = dist / BACKOFF_SPEED_MPS
    return ({'kind': 'mecanum', 'forward': round(dx / duration, 4), 'left': round(dy / duration, 4), 'turn': 0.,
             'duration_s': .15}, duration)


# ---------------------------------------------------------------- 3. progress monitor (Nav2 adaptation)
REQUIRED_MOVEMENT_M = .10           # Nav2 required_movement_radius (default 0.5 m), scaled to this robot
# Nav2 counts wall-clock time since the baseline. Smoke v2 (a5b3687e, diagnosis_v2.json) showed that
# "6 s of commanded driving" fires on slow crawls near a goal and after long looks: 3 of 5 stalls were
# false. v3 counts the robot's own COMMANDED displacement (sum |v_cmd| * tick) since the baseline.
STALL_COMMANDED_M = .40             # 4x REQUIRED_MOVEMENT_M; ~0.56 m actual (gain ~1.4) > the 0.5 m loaded travel look
TRUSTED_FIX_AGE_S = .3
MAX_RECOVERIES = 2                  # Nav2 RecoveryNode number_of_retries style bound
MAX_PROGRESS_LOOK_FAILURES = 3      # cumulative per leg; neither refix nor recovery resets this budget
RECOVERY_BACKOFF_M = .08
STALL_KEEPOUT_AHEAD_M = .20
STALL_KEEPOUT_HALF_M = .08
STALL_KEEPOUT_MIN_GOAL_M = .45      # never mark a stall keep-out on or next to the leg goal (v2: 4 goals covered)
STALL_KEEPOUT_MIN_DOOR_M = .60      # ... nor in a door lane (v2 s700 r1: the only passage covered)


class ProgressMonitor:
    """No-progress check on trusted own estimates (after a fixed look, or a fresh observation with low sigma).

    ``stalled`` needs (1) ``STALL_COMMANDED_M`` of own commanded travel since the baseline and (2) a
    trusted estimate taken AFTER that point that still did not move the baseline. When (1) holds
    without (2), ``needs_check`` asks the driver for one confirming own look first.
    """

    def __init__(self):
        self.baseline: tuple[float, float, float, float] | None = None     # x, y, goal distance, commanded m
        self.commanded_m = 0.
        self.last_trusted_cmd_m: float | None = None
        self.checks = 0
        self.look_failures = 0

    def drove(self, commanded_m: float) -> None:
        if math.isfinite(commanded_m) and commanded_m > 0:
            self.commanded_m += float(commanded_m)

    def trusted(self, xy, goal_dist) -> None:
        x, y = float(xy[0]), float(xy[1])
        self.last_trusted_cmd_m = self.commanded_m
        if self.baseline is None:
            self.baseline = (x, y, float(goal_dist), self.commanded_m)
            return
        bx, by, bd, _ = self.baseline
        need = min(REQUIRED_MOVEMENT_M, .5 * bd)
        if math.hypot(x - bx, y - by) > REQUIRED_MOVEMENT_M or bd - goal_dist > need:
            self.baseline = (x, y, float(goal_dist), self.commanded_m)

    def reset(self) -> None:
        self.baseline, self.last_trusted_cmd_m = None, None

    def _over(self) -> bool:
        return self.baseline is not None and self.commanded_m - self.baseline[3] >= STALL_COMMANDED_M

    def stalled(self) -> bool:
        return (self._over() and self.last_trusted_cmd_m is not None
                and self.last_trusted_cmd_m - self.baseline[3] >= STALL_COMMANDED_M)

    def needs_check(self) -> bool:
        return self._over() and not self.stalled()

    def inconclusive(self, xy, goal_dist) -> None:
        """Allow a fresh motion window, but charge every failed check to a finite per-leg budget."""
        self.checks += 1
        self.look_failures += 1
        if xy is not None and _finite(*xy, goal_dist):
            self.baseline = (float(xy[0]), float(xy[1]), float(goal_dist), self.commanded_m)

    def exhausted(self) -> bool:
        return self.look_failures >= MAX_PROGRESS_LOOK_FAILURES


def commanded_step_m(cmd: Mapping) -> float:
    """Own commanded planar travel of one control tick (the command itself, never a measurement)."""
    if cmd.get('kind') not in ('mecanum', 'drive'):
        return 0.
    fwd, left = cmd.get('forward', 0.), cmd.get('left', 0.)
    return math.hypot(float(fwd), float(left)) * CONTROL_S if _finite(fwd, left) else 0.


# ---------------------------------------------------------------- 4. blockage streak per location
BLOCKAGE_CELL_M = .5
BLOCKAGE_MAX_GAP_S = 2.5            # JUDGE_PERIOD_S 1 s: at most one missed judgment between commits


class BlockageStreak:
    """Consecutive ``yes`` commits at ONE location key; any other key, a ``no`` or a gap resets."""

    def __init__(self, needed: int):
        self.needed = int(needed)
        self.key = None
        self.count = 0
        self.last_t: float | None = None
        self.disarmed: set = set()

    @staticmethod
    def key_of(passage_id, pose: OwnPose | None):
        if pose is None:
            return None
        sector = int(round(math.degrees(pose.yaw) / 90.)) % 4
        return (passage_id, int(math.floor(pose.x / BLOCKAGE_CELL_M)), int(math.floor(pose.y / BLOCKAGE_CELL_M)), sector)

    def observe(self, t: float, answer: str, committed: bool, key) -> bool:
        """True exactly when a blockage at ``key`` should be reported now."""
        if key is None:
            self.key, self.count = None, 0
            return False
        if answer == 'no':
            self.disarmed.discard(key)
        if not committed:
            if self.key == key:
                self.count = 0
            return False
        if self.key != key or self.last_t is None or t - self.last_t > BLOCKAGE_MAX_GAP_S:
            self.key, self.count = key, 0
        self.count += 1
        self.last_t = float(t)
        if self.count >= self.needed and key not in self.disarmed:
            self.disarmed.add(key)
            return True
        return False
