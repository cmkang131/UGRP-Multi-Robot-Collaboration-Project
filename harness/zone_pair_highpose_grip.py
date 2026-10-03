"""HIGH raise/lower progress (gating) and own-RGB grip values (LOG-ONLY).

v96 first-E2E scope (user decision 2026-10-03, "ㅇㅇ 그렇게 하자"): the grip
monitor never gates, aborts or blocks a phase. Raise/lower progress is gated
only by the robot's own command history (gripper commanded closed, the queued
pose path) and the existing fixed-enum partner status. The own-RGB values
(relation(), view stability, frame freshness) are written to a write-only
GripMonitorLog that the evaluation output exports; no controller code reads it.
So a dropped beam is NOT detected or signalled in-run in this version.

relation() below projects COMMAND geometry (no measured loaded extrinsics).
On recorded floor_light_v1 renders it is unreliable (REVIEW_363 round 2,
experiments/2026-10-03-pair-carry-highpose/fix363), which is why it is
log-only. No simulator import, joint measurement or contact is used.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import cv2
import numpy as np

from harness import visual_arm_v3 as arm
from harness.owncam_view import _pixel_rays
from harness.owncam_pair_beam import decode
from harness.owncam_pair_lift_v3 import beam_colour_mask_low

SAMPLE_S = .1
MAX_FRAME_AGE_S = .15
MAX_COMMAND_LAG_S = .15
MIN_SUPPORT = 120                 # 4-pixel grid; positive beam colour only
MIN_COVERAGE = .65
MIN_IOU = .50
MAX_EDGE_SLOPE_DELTA = .015        # conservative desync refusal, not a measured bound
# Log-only view stability: own view vs itself (carry hold IoU) over the last
# STABLE_S of the 8 s HIGH settle. Recorded for evaluation; never gates.
STABLE_S = 2.
MONITOR_SCOPE = 'log_only_v96'


def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        value = float(value)
        return value if math.isfinite(value) else None
    return value


class GripMonitorLog:
    """Write-only eval/audit sink. Controllers append; only records() exports."""

    def __init__(self):
        self._rows = []

    def record(self, rid, kind, now, **values):
        self._rows.append({'robot_id': rid, 'kind': kind, 'sim_s': float(now),
                           'scope': MONITOR_SCOPE, **_plain(values)})

    def export(self):
        return [dict(row) for row in self._rows]


def support(servo):
    """Projected horizontal beam at the commanded pad, robot-local only.

    Both end roles face along their own +x into the beam. The pad grips 30 mm
    in from the near end of a 600 x 40 x 32 mm beam. No view/FOV alteration.
    """
    xs, ys, normal, valid = _pixel_rays(4)
    origin, axes = arm.camera_extrinsics(servo)
    rays = np.column_stack((normal, np.ones(len(normal)))) @ np.asarray(axes)
    tool = arm.tool_pose(servo)
    yaw = math.radians(tool.yaw_left_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    rot = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    grip = np.array([tool.x_m, tool.y_m, tool.z_m])
    origin = (np.asarray(origin)-grip) @ rot
    rays = rays @ rot
    # Static catalogue paint geometry matters: black grip bands are excluded
    # from positive colour evidence instead of treating every dark pixel as a
    # held beam. Both roles are symmetric under their local facing convention.
    from sim.zone_cargo import kind
    spec = kind('long_beam')
    origin = origin + np.asarray(spec.grasps[0].grip_xyz)
    entries = []
    for part in spec.parts:
        low, high = np.asarray(part.center)-part.size, np.asarray(part.center)+part.size
        with np.errstate(divide='ignore', invalid='ignore'):
            a, b = (low-origin)/rays, (high-origin)/rays
        enter, leave = np.minimum(a, b).max(axis=1), np.maximum(a, b).min(axis=1)
        entries.append(np.where(leave >= np.maximum(enter, 0.), enter, np.inf))
    entries = np.asarray(entries)
    # Fixed static near plane of the registered scene profile, from v93's
    # headless scene record. No live camera transform or geometry is sampled.
    near_m = .02222497706328516
    expected = valid & np.isfinite(entries[0]) & (entries[0] >= near_m) & (entries.argmin(axis=0) == 0)
    return xs.astype(int), ys.astype(int), valid, expected


def _slope(mask, xs, ys):
    rows = []
    for x in np.unique(xs):
        y = ys[(xs == x) & mask]
        if len(y) >= 8 and y.max() < 470:
            rows.append((x, y.max()))
    if len(rows) < 20:
        return None
    x, y = np.asarray(rows, float).T
    # Cross-section near the image centre. The metric rejects visible tilt;
    # its absence is not evidence of sync (support/IoU must still pass).
    return float(np.polyfit(x, y, 1)[0])


def relation(image, servo):
    frame = decode(image)
    if frame.shape != (480, 640, 3):
        return {'ok': False, 'reason': 'RGB_SHAPE'}
    xs, ys, valid, expected = support(servo)
    colour = beam_colour_mask_low(frame)[ys, xs] & valid
    n = int(expected.sum())
    overlap = int((expected & colour).sum())
    coverage = overlap/max(1, n)
    iou = overlap/max(1, int((expected | colour).sum()))
    es, seen = _slope(expected, xs, ys), _slope(colour, xs, ys)
    delta = None if es is None or seen is None else abs(es-seen)
    ok = (n >= MIN_SUPPORT and coverage >= MIN_COVERAGE and iou >= MIN_IOU
          and (delta is None or delta <= MAX_EDGE_SLOPE_DELTA))
    return {'ok': bool(ok), 'reason': 'HELD_RELATION' if ok else 'GRIP_RELATION_LOST_OR_UNOBSERVABLE',
            'support': n, 'coverage': coverage, 'iou': iou, 'edge_slope_delta': delta}


@dataclass(frozen=True)
class Anchor:
    """One grasp epoch, one pose. Never replaced by an arbitrary current frame."""
    epoch: int
    pose: tuple
    mask: np.ndarray
    frame_id: int
    acquired_at: float


def pose_key(servo):
    return tuple(int(servo[s]) for s in (3, 4, 5, 6))


class TransitMonitor:
    """Gates: own command history + partner status. Own RGB: log only."""

    def __init__(self, phase, started_at, initial_servo, events, until, epoch, *, sink=None, rid=None):
        self.phase, self.started_at, self.until, self.epoch = phase, started_at, until, epoch
        self.initial = dict(initial_servo)
        self.events = tuple(sorted(events))
        self.samples = 0                   # command/status checks at the control cadence
        self.last_sample = None
        self.failure = None
        self.sink, self.rid = sink if sink is not None else GripMonitorLog(), rid
        self.last_frame = None
        self.stable_ref = None
        self.stable_since = None

    def expected(self, now):
        servo = dict(self.initial)
        for t, sid, pulse in self.events:
            if t <= now+1e-8:
                servo[sid] = pulse
        return servo

    def commands(self, now, servo):
        if self.failure:
            return self.failure
        if servo.get(1) != 1500:
            self.failure = 'TRANSIT_GRIP_OPEN_COMMAND'
        else:
            # Capture precedes the current arm tick. Permit one control period
            # plus one arm tick, never a 2 s local/one-side command delay.
            allowed = [self.expected(now), self.expected(now-MAX_COMMAND_LAG_S)]
            allowed += [self.expected(t) for t, _, _ in self.events
                        if now-MAX_COMMAND_LAG_S <= t <= now]
            if not any(all(servo.get(sid) == p[sid] for sid in (3, 4, 5, 6)) for p in allowed):
                self.failure = 'TRANSIT_COMMAND_DESYNC'
        return self.failure

    def observe(self, now, obs, servo, partner_ok):
        if self.commands(now, servo):
            return False
        if not partner_ok:
            self.failure = 'TRANSIT_PARTNER_DESYNC'
            return False
        self.samples += 1
        self.last_sample = now
        self._log(now, obs, servo)
        return True

    def _log(self, now, obs, servo):
        identity = (obs['sim_time'], obs['frame_id'])
        fresh = (0 <= now-obs['sim_time'] <= MAX_FRAME_AGE_S+1e-8
                 and (self.last_frame is None or (identity[0] > self.last_frame[0]
                                                  and identity[1] > self.last_frame[1])))
        self.last_frame = identity
        image_servo = {int(k): v for k, v in obs['actuator_state']['servo_pulses'].items()}
        try:
            rel = relation(obs['image'], servo)
        except Exception as exc:          # noqa: BLE001 - logged, never gates
            rel = {'ok': None, 'reason': f'RELATION_ERROR:{type(exc).__name__}'}
        self.sink.record(self.rid, 'transit_view', now, phase=self.phase, epoch=self.epoch,
                         frame_id=obs['frame_id'], frame_sha256=obs.get('sha256'),
                         frame_fresh=fresh, image_servo_matches_command=image_servo == servo,
                         relation=rel, view_stable=self._stability(now, obs, servo))

    def _stability(self, now, obs, servo):
        from harness import owncam_pair_hold_v3 as hv3
        final = self.expected(self.until+1.)
        at_final = all(servo.get(sid) == final.get(sid) for sid in (3, 4, 5, 6))
        if not at_final or now < self.until-STABLE_S-1e-8:
            self.stable_ref = self.stable_since = None
            return None
        if self.stable_ref is None or hv3.hold_iou(self.stable_ref, obs['image']) < hv3.HOLD_MIN_IOU:
            self.stable_ref, self.stable_since = hv3.hold_view_mask(obs['image']).copy(), now
        return now-self.stable_since >= STABLE_S-1e-8

    def evidence_ok(self, now):
        # No endpoint-only jump: own command/partner-status checks ran at the
        # control cadence over the whole queued path. Images do not count.
        required = max(2, math.floor((self.until-self.started_at)/SAMPLE_S)-1)
        return (self.failure is None and now >= self.until-1e-8 and self.samples >= required
                and self.last_sample is not None and now-self.last_sample <= SAMPLE_S+1e-8)

    def complete(self, now):
        return self.evidence_ok(now)
