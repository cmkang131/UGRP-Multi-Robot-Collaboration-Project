"""Segment-local resting beam hypothesis: own RGB + ISSUED commands only.

These are conservative development bounds, not calibrated motion accuracy.
A command prediction is never evidence that the base or arm actually moved.
The frozen M2 detector and whole-beam/wall distance calculation are unchanged.
"""
from __future__ import annotations

import math

import numpy as np

from harness import owncam_pair_beam as v1
from harness.owncam_pair_beam_v2 import observe_beam
from harness.owncam_view import base_rays
from harness.zone_own_guards import BACKOFF_GAIN_MAX

MAX_AGE_S = 30.
DRIFT_XY_M_S = .0005
DRIFT_YAW_RAD_S = .0005
ARM_XY_M_PWM = .000001
ARM_YAW_RAD_PWM = .000002


def plane_points(image, servo):
    frame = v1.decode(image)
    origin, rays, xs, ys, valid = base_rays(servo, v1.RAY_STEP)
    hit = valid & v1.lime_mask(frame)[ys.astype(int), xs.astype(int)] & (rays[:, 2] < -1e-6)
    distance = (v1.BEAM_TOP_Z_M - origin[2]) / rays[hit, 2]
    pts = (origin + distance[:, None] * rays[hit])[:, :2]
    return pts[(distance > 0) & (np.linalg.norm(pts, axis=1) < 2.5)]


def standoff_estimate(obs, servo, *, points=None, min_strip_support=0.):
    """Full band anchors position; equal-length edge pairs fit the beam axis.

    Pixel PCA weights the near end face heavily; width/sight-length is also
    not axis-fit noise. Fit midpoints of BOTH edges in >=4 separate 10 mm
    strips, spanning >=60 mm. Keep scatter, a 15 mm position / 1 degree angle
    floor, and disagreement between fits to each half. Never fit a clipped
    band's centre or extrapolate an axis from the thin grasp-height strip.
    """
    from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD

    beam = observe_beam(obs['image'], servo)
    if (not beam.get('visible') or not beam.get('end_visible')
            or beam.get('grip_source') != 'band_centre'):
        return None
    heading = beam['axis_heading_rad']
    u = np.array([math.cos(heading), math.sin(heading)])
    pts = (plane_points if points is None else points)(obs['image'], servo)
    if len(pts) < v1.MIN_POINTS:
        return None
    along, across = pts @ u, pts @ np.array([-u[1], u[0]])
    lo, hi = np.percentile(along, [1, 99])
    centres, support = [], []
    for start in np.arange(lo, hi, .01):
        mask = (along >= start) & (along < start + .01)
        if mask.sum() < 4:
            continue
        left, right = np.percentile(across[mask], [2, 98])
        if .025 <= right - left <= .055:  # catalogue 40 mm width, both edges
            centres.append((float(np.mean(along[mask])), float((left + right) / 2)))
            support.append(int(mask.sum()))
    if min_strip_support > 0 and centres:
        # v6c: a strip cut by the band/end boundary is partly covered; its
        # midpoint is not a two-edge midpoint. Keep well-supported strips.
        floor = min_strip_support * float(np.median(support))
        centres = [c for c, n in zip(centres, support) if n >= floor]
    if len(centres) < 4:
        return None
    a, n = np.array(centres).T
    span = float(np.ptp(a))
    if span < .06:
        return None
    slope, intercept = np.polyfit(a, n, 1)
    residual = float(np.max(np.abs(n - slope * a - intercept)))
    angle = math.atan(slope)
    halves = np.array_split(np.arange(len(a)), 2)
    disagreement = max(abs(math.atan(np.polyfit(a[h], n[h], 1)[0]) - angle) for h in halves)
    syaw = max(math.radians(1.), math.atan2(2 * residual + .001, span), disagreement)
    sxy = max(.015, beam['lateral_spread_m'], residual)
    if not (0 <= sxy <= FIX_STD_XY_M and 0 <= syaw <= FIX_STD_YAW_RAD):
        return None
    return {**beam, 'axis_heading_rad': heading + angle, 'std_xy_m': sxy,
            'std_yaw_rad': syaw, 'axis_fit': 'equal_length_paired_edges',
            'edge_strips': len(centres), 'edge_span_m': span, 'edge_residual_m': residual}


class RestingBeamTrack:
    # v6c GraspRangeBeamTrack overrides these two hooks; defaults are the v5h/v6 behaviour.
    def _standoff(self, obs, servo):
        return standoff_estimate(obs, servo)

    def _partial_points(self, obs, servo):
        """Visible beam patch for a consistency check, or None (no renewal)."""
        partial = observe_beam(obs['image'], servo)
        if (partial.get('reason') not in ('BAND_CLIPPED', 'END_CLIPPED')
                or partial.get('end_visible') is not False):
            return None, None  # missing/unrecognized evidence cannot renew a track
        return plane_points(obs['image'], servo), partial['reason']

    def __init__(self):
        self.beam = None
        self.segment = None
        self.t = None
        self.motion = (0., 0., 0.)
        self.until = -math.inf
        self.last_frame = None

    def advance(self, now):
        if self.t is None:
            self.t = now
        if now < self.t:
            self.beam = None
            return
        dt = now - self.t
        moving = max(0., min(now, self.until) - self.t)
        if self.beam is not None:
            b = self.beam
            f, l, w = self.motion
            # Mid-range of [stalled, bounded commanded motion]. The uncertainty
            # grows by the FULL bound, including either slip direction/turn.
            dx, dy, da = (v * moving * BACKOFF_GAIN_MAX / 2 for v in (f, l, w))
            c, s = math.cos(da), math.sin(da)
            x, y = b['grip_base_m'][0] - dx, b['grip_base_m'][1] - dy
            b['grip_base_m'] = [c * x + s * y, -s * x + c * y]
            b['axis_heading_rad'] -= da
            travel = math.hypot(dx, dy)
            b['std_xy_m'] += 2 * travel + 2 * abs(da) * math.hypot(x, y) + DRIFT_XY_M_S * dt
            b['std_yaw_rad'] += 2 * abs(da) + DRIFT_YAW_RAD_S * dt
            b['prediction_time_s'] = now
        self.t = now

    def command(self, row, servo):
        self.advance(row['t'])
        kind = row['kind']
        if kind in ('drive', 'mecanum'):
            self.motion = (row.get('forward', 0.), row.get('left', 0.), row.get('turn', 0.))
            self.until = row['t'] + row['duration_s']
        elif kind == 'hold':
            self.motion, self.until = (0., 0., 0.), row['t']
        elif kind in ('arm', 'look') and self.beam is not None:
            sid = 6 if kind == 'look' else int(row['servo_id'])
            pulse = row['pan_pulse'] if kind == 'look' else row['pulse']
            if sid == 1 and servo.get(1, 2000) < 2000 <= pulse:
                self.beam = None  # release: a new resting object needs new RGB
            elif sid != 1:
                delta = abs(pulse - servo.get(sid, pulse))
                self.beam['std_xy_m'] += ARM_XY_M_PWM * delta
                self.beam['std_yaw_rad'] += ARM_YAW_RAD_PWM * delta

    def observe_standoff(self, obs, servo, segment):
        self.advance(obs['sim_time'])
        key = (segment, obs['frame_id'], obs['sha256'])
        if self.last_frame == key:
            return False  # duplicate reads cannot refill age or uncertainty
        self.last_frame = key
        beam = self._standoff(obs, servo)
        if beam is None:
            return False
        self.segment = segment
        self.beam = {**beam, 'grip_base_m': list(beam['grip_base_m']),
                     'anchor_time_s': obs['sim_time'], 'anchor_frame_id': obs['frame_id'],
                     'anchor_sha256': obs['sha256'], 'anchor_servo': dict(servo),
                     'prediction_time_s': obs['sim_time'], 'source': 'own RGB standoff + issued commands'}
        return True

    def estimate(self, now, obs, servo, segment):
        from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD

        self.advance(now)
        b = self.beam
        if (b is None or segment != self.segment or not 0 <= now - b['anchor_time_s'] <= MAX_AGE_S
                or not 0 <= b['std_xy_m'] <= FIX_STD_XY_M
                or not 0 <= b['std_yaw_rad'] <= FIX_STD_YAW_RAD):
            return None
        pts, partial_reason = self._partial_points(obs, servo)
        if pts is None or len(pts) < v1.MIN_POINTS:
            return None
        # Only a visible patch is constrained. The short strip may be the END
        # face, so neither its PCA axis nor its v1 grip is a new beam pose.
        u = np.array([math.cos(b['axis_heading_rad']), math.sin(b['axis_heading_rad'])])
        relative = pts - np.array(b['grip_base_m'])
        a, n = relative @ u, relative @ np.array([-u[1], u[0]])
        # Catalogue bar extends 30 mm before and 570 mm after the near grip.
        pad = 2 * (b['std_xy_m'] + b['std_yaw_rad'] * .60)
        inside = (a >= -.03 - pad) & (a <= .57 + pad) & (np.abs(n) <= .02 + pad)
        if inside.mean() < .95:
            return None
        return {**b, 'partial_frame_id': obs['frame_id'], 'partial_sha256': obs['sha256'],
                'partial_support_fraction': float(inside.mean()), 'partial_reason': partial_reason,
                'partial_use': 'visible patch consistency only; no pose/age/sigma reset'}
