"""Default-off observable READY witness for the beam-pair student.

READY is a PDDL/STRIPS-style precondition over the student's own inputs, not a
learned action.  The witness consumes exactly the two input channels already in
the ACT observation: the 0 s own RGB frame (one of the four image-history
entries) and the sixteen issued commands.  It reads no partner image/pose,
teacher phase, contact, world state or evaluation truth.

Two independent own-camera checks must both hold for two consecutive fresh
frames:

* metric alignment: the existing calibrated owncam v2 beam observer returns the
  grip point in the robot base frame; the T08b relative tolerances and fit
  uncertainty bounds are applied to that point and the beam axis;
* end identity: the assigned teal/blue band colour is projected onto the beam
  top plane with the same own-camera rays, associated with the observer's grip,
  and must span at least the cargo-v6 band half-length.  The opposite colour
  must not be closer to that grip.

The hue/S/V ranges are the beamdiag colour-assay bands.  Its 9-pixel reporting
area threshold is deliberately NOT used: the identity condition uses the
physical band footprint and the measured colour bands instead of a pixel-count
acceptance constant.  The student camera FOV/resolution/profile must match the
admitted record; otherwise the witness fails closed.  Physical admission for a
new camera is not claimed here.

All decisions are recorded with a reason, frame SHA, observer values and band
counts.  This module never emits a command and never changes the pinned
READY->GO->ACK message format, deadlines or start delays.
"""
from __future__ import annotations

from copy import deepcopy
import base64
import hashlib
import math

import cv2
import numpy as np

from harness import grasp_act_contract as c
from harness import owncam_pair_beam as beam_v1
from harness import owncam_pair_beam_v2 as beam_v2
from harness.beam_approach import CONFIG as APPROACH_CONFIG, issued_servo
from harness.owncam_view import base_rays
from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD

PROFILE = 'beamact5_ready_witness_v1'
READY_GATE = PROFILE
# The only camera for which the owncam rays and the beamdiag colour assay were
# checked.  A different render profile/size must fail closed until admitted.
CAMERA_PROFILE = 'masterpi-camera-user-observation-target-review-v3'
IMAGE_HW = (480, 640)  # (height, width) of the robot_cam JPEG
# Beamdiag thresholds.color_assay: raw hue modes 40/83/120; reported bands.
END_BANDS = {'teal': ((62, 101),), 'blue': ((102, 140),)}
SAT_MIN, VAL_MIN = 128, 128
# sim.zone_cargo long_beam: _band(half_len=.018, half_w=.0205) at both ends.
BAND_HALF_LEN_M, BAND_HALF_W_M = .018, .0205
# The observer's own band-centre bias is <= 20 mm; the teacher XY tolerance is
# 30 mm.  Association uses that existing teacher tolerance, not a new pixel
# acceptance constant.
ASSOCIATION_TOL_M = .03
# Pixel quantisation / JPEG edge allowance for the projected band extent.  This
# is below the 36 mm physical band; a single stray pixel cannot satisfy it.
BAND_EXTENT_MIN_M = BAND_HALF_LEN_M
MAX_FRAME_GAP_S = .15  # same bound as c.validate_observation image staleness


def _sha256(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _wrap(value):
    return (value + math.pi) % (2 * math.pi) - math.pi


def _station_radius_m():
    from sim.masterpi_robot_models import station_grasp_convention
    return float(station_grasp_convention('masterpi_v3')['station_radius_m'])


def default_observer(image, servo):
    """Existing calibrated owncam v2 observer; no new fit or threshold."""
    return beam_v2.observe_beam(image, servo)


def default_band_evidence(image, servo, role, grip, axis):
    """Project assigned/opposite end bands onto the beam top plane.

    Returns only counts/distances/extents.  The projected points use the same
    own-camera rays as the beam observer; no world coordinate or truth is read.
    """
    frame = beam_v1.decode(image)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    masks = {}
    for name, bands in END_BANDS.items():
        mask = np.zeros(frame.shape[:2], bool)
        for lo, hi in bands:
            mask |= cv2.inRange(hsv, (lo, SAT_MIN, VAL_MIN), (hi, 255, 255)) > 0
        masks[name] = mask
    origin, rays, xs, ys, valid = base_rays(servo, beam_v1.RAY_STEP)
    down = rays[:, 2] < -1e-6
    scale = np.full(len(rays), np.nan)
    scale[down] = (beam_v1.BEAM_TOP_Z_M - origin[2]) / rays[down, 2]
    points = origin[:2] + scale[:, None] * rays[:, :2]
    keep = valid & np.isfinite(scale) & (scale > 0) & (np.linalg.norm(points, axis=1) < 2.5)
    gx, gy = float(grip[0]), float(grip[1])
    u = np.array([math.cos(float(axis)), math.sin(float(axis))])
    n = np.array([-u[1], u[0]])
    relative = points - np.array([gx, gy])
    along, across = relative @ u, relative @ n
    out = {'assigned': role, 'opposite': 'blue' if role == 'teal' else 'teal'}
    for name, mask in masks.items():
        hit = keep & mask[ys.astype(int), xs.astype(int)]
        near = hit & (np.abs(along) <= ASSOCIATION_TOL_M) & (np.abs(across) <= ASSOCIATION_TOL_M)
        idx = np.flatnonzero(near)
        out[name + '_points'] = int(len(idx))
        if len(idx) == 0:
            out[name + '_distance_m'] = None
            out[name + '_extent_along_m'] = None
            out[name + '_centroid_m'] = None
            continue
        centroid = points[idx].mean(axis=0)
        out[name + '_distance_m'] = float(np.linalg.norm(centroid - np.array([gx, gy])))
        out[name + '_extent_along_m'] = float(along[idx].max() - along[idx].min())
        out[name + '_centroid_m'] = [float(centroid[0]), float(centroid[1])]
    return out


class ReadyWitness:
    """Stateful two-frame own-observation READY monitor; fail closed."""
    def __init__(self, *, observer=None, band_evidence=None,
                 camera_profile=CAMERA_PROFILE, image_hw=IMAGE_HW,
                 station_radius_m=None, config=None):
        self.observer = observer or default_observer
        self.band_evidence = band_evidence or default_band_evidence
        self.camera_profile = camera_profile
        self.image_hw = tuple(image_hw)
        self.station_radius_m = (_station_radius_m() if station_radius_m is None
                                 else float(station_radius_m))
        self.config = dict(APPROACH_CONFIG if config is None else config)
        self.streak = 0
        self.last_frame_id = None
        self.last_sha = None
        self.last_t = None
        self.last_decision = None

    def reset(self):
        self.streak, self.last_frame_id, self.last_sha, self.last_t = 0, None, None, None
        self.last_decision = None

    def _frame(self, observation, jpegs):
        if self.camera_profile != CAMERA_PROFILE:
            raise ValueError('UNSUPPORTED_CAMERA_PROFILE')
        if not len(jpegs) or len(jpegs) != len(observation['rgb']):
            raise ValueError('OWN_RGB_HISTORY_MISMATCH')
        ref = observation['rgb'][-1]
        if ref['robot_id'] != observation['robot_id']:
            raise ValueError('OWN_RGB_ROBOT_MISMATCH')
        if abs(float(ref['t']) - float(observation['t'])) > 1e-6:
            raise ValueError('OWN_RGB_NOT_CURRENT')
        data = bytes(jpegs[-1])
        if _sha256(data) != ref['sha256']:
            raise ValueError('OWN_RGB_SHA_MISMATCH')
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None or tuple(frame.shape[:2]) != self.image_hw:
            raise ValueError('UNSUPPORTED_IMAGE_SIZE')
        return frame, ref

    def _evaluate(self, frame, observation, role):
        servo = issued_servo(observation['issued'][-1]['pwm'])
        try:
            obs = self.observer(frame, servo)
        except Exception as exc:
            return dict(aligned=False, reason='OBSERVER_ERROR:' + type(exc).__name__,
                        observer=None, band=None, errors=None)
        try:
            valid = (obs.get('visible') is True and obs.get('end_visible') is True
                     and isinstance(obs.get('grip_base_m'), (list, tuple))
                     and len(obs['grip_base_m']) == 2
                     and all(_finite(v) for v in (*obs['grip_base_m'],
                                                  obs.get('axis_heading_rad'),
                                                  obs.get('lateral_spread_m'),
                                                  obs.get('visible_length_m')))
                     and obs['lateral_spread_m'] >= 0 and obs['visible_length_m'] > 0)
        except (KeyError, TypeError):
            valid = False
        if not valid:
            return dict(aligned=False, reason='BEAM_NOT_VISIBLE_OR_UNBOUNDED',
                        observer=obs, band=None, errors=None)
        spread, length = float(obs['lateral_spread_m']), float(obs['visible_length_m'])
        std_xy, std_yaw = spread, math.atan2(spread, length)
        grip = [float(obs['grip_base_m'][0]), float(obs['grip_base_m'][1])]
        axis = float(obs['axis_heading_rad'])
        errors = [grip[0] - self.station_radius_m, grip[1], _wrap(axis)]
        summary = dict(visible=True, end_visible=True, grip_base_m=grip,
                       axis_heading_rad=axis, std_xy_m=std_xy,
                       std_yaw_rad=std_yaw, grip_source=obs.get('grip_source'),
                       points=obs.get('points'))
        if std_xy > FIX_STD_XY_M or std_yaw > FIX_STD_YAW_RAD:
            return dict(aligned=False, reason='FIT_UNCERTAIN', observer=summary,
                        band=None, errors=errors)
        band = self.band_evidence(frame, servo, role, grip, axis)
        checks = {
            'ASSIGNED_END_BAND_NOT_VISIBLE': band.get(role + '_points', 0) > 0,
            'ASSIGNED_END_BAND_NOT_AT_GRIP':
                band.get(role + '_distance_m') is not None
                and band[role + '_distance_m'] <= ASSOCIATION_TOL_M,
            'ASSIGNED_END_BAND_TOO_PARTIAL':
                band.get(role + '_extent_along_m') is not None
                and band[role + '_extent_along_m'] >= BAND_EXTENT_MIN_M,
            'OPPOSITE_END_BAND_AT_GRIP':
                band.get('opposite_distance_m') is None
                or (band.get(role + '_distance_m') is not None
                    and band[role + '_distance_m'] <= band['opposite_distance_m']),
        }
        for reason, ok in checks.items():
            if not ok:
                return dict(aligned=False, reason=reason, observer=summary,
                            band=band, errors=errors)
        tolerances = (self.config['relative_x_tol_m'],
                      self.config['relative_y_tol_m'],
                      self.config['relative_yaw_tol_rad'])
        if any(abs(e) > tol for e, tol in zip(errors, tolerances)):
            return dict(aligned=False, reason='RELATIVE_ALIGNMENT_OUTSIDE_T08B',
                        observer=summary, band=band, errors=errors)
        return dict(aligned=True, reason='ALIGNED_AND_ASSIGNED_END_BAND_VISIBLE',
                    observer=summary, band=band, errors=errors)

    def observe(self, observation, jpegs):
        """Update and return this tick's READY witness decision.

        The caller passes the ACT observation and its four own JPEGs.  The
        current (0 s lag) JPEG is the only image used.  Duplicate frames do not
        count twice; a gap longer than the ACT staleness bound resets the
        two-frame streak.
        """
        c.validate_observation(observation)
        now = float(observation['t'])
        role = observation['role']
        if role not in END_BANDS:
            raise ValueError('assigned teal/blue end required for READY witness')
        try:
            frame, ref = self._frame(observation, jpegs)
        except ValueError as exc:
            self.reset()
            decision = dict(aligned=False, reason=str(exc), observer=None,
                            band=None, errors=None, frame_sha256=None,
                            frame_t=now, streak=0)
            self.last_decision = decision
            return deepcopy(decision)
        duplicate = ref['sha256'] == self.last_sha
        gap = 0. if self.last_t is None else now - self.last_t
        if duplicate or gap > MAX_FRAME_GAP_S + 1e-9:
            self.streak = 0
        decision = self._evaluate(frame, observation, role)
        self.streak = self.streak + 1 if decision['aligned'] else 0
        decision.update(frame_sha256=ref['sha256'], frame_t=now,
                        streak=self.streak, t=now, robot_id=observation['robot_id'],
                        role=role, station_radius_m=self.station_radius_m,
                        tolerances=dict(relative_x_tol_m=self.config['relative_x_tol_m'],
                                        relative_y_tol_m=self.config['relative_y_tol_m'],
                                        relative_yaw_tol_rad=self.config['relative_yaw_tol_rad']),
                        alignment_frames=self.config['alignment_frames'],
                        source=PROFILE)
        self.last_frame_id, self.last_sha, self.last_t = ref['path'], ref['sha256'], now
        self.last_decision = decision
        return deepcopy(decision)

    def ready(self, observation, jpegs):
        decision = self.observe(observation, jpegs)
        return decision['aligned'] and decision['streak'] >= self.config['alignment_frames'], decision
