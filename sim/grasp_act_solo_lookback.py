"""Opt-in pickup-site evidence from own RGB and issued PWM, never live truth.

An empty pickup site is evidence of removal, not proof of retention (a pushed
away object is indistinguishable). The separate physics evaluator owns that
distinction. Nominal loaded FK is a prediction, not measured arm/base motion.
"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache

import cv2
import numpy as np

from harness.servo_camera_fk import axis_rotation, commanded_joints, fixed_transform, model
from harness.visual_arm_v3 import forward_grip, tool_pose, solve_grip_site_ik
from harness.zone_own_perception import _usable_region, hue_mask
from harness.zone_own_perception_v3 import _pixel_rays, _ray_box
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

MODE = 'solo_lift_lookback_v1'
BACKOFF_M = .125


def plan_lookback(kind, grasp_pwm, lift_pwm):
    """Deterministic command-space plan, fixed before the lookback starts.

    Tile gets 25 mm extra lift to fit its wider floor footprint. A bounded
    5 mm grid selects the retreat with a +/-5 mm geometric margin. This is
    NOT measured base odometry or a correction from simulator truth.
    """
    pose = pose_for(kind, lift_pwm)
    x, y, _ = forward_grip(grasp_pwm)
    if kind == 'tile':
        pose.update(solve_grip_site_ik((x, y, .120),
                    preferred_pitch_deg=tool_pose(grasp_pwm).pitch_deg, calibrated_grasp_only=False))
    for mm in sorted(range(90, 156, 5), key=lambda n: (abs(n-125), n)):
        checks = [regions(kind, grasp_pwm, pose, site=(x+(mm+delta)/1000, y, 0.))[2]
                  for delta in (-5, 0, 5)]
        if all(c['qualified'] for c in checks):
            return {'pwm': pose, 'backoff_m': mm/1000, 'geometry': checks[1],
                    'command_distance_margin_m': .005, 'backoff_bounds_m': [.09, .155]}
    raise ValueError('no framed unoccluded pickup site in bounded command-space plan')


def pose_for(kind, lift_pwm):
    from sim.grasp_act_solo_teacher import cargo
    cargo(kind)  # validate catalogue key
    # Preserve the existing 95 mm lift and pan; move the base back 125 mm.
    # This preserves the grasp pitch instead of tilting the held cargo.
    return {1: 1500, **{s: int(lift_pwm.get(s, lift_pwm.get(str(s)))) for s in (3, 4, 5, 6)}}


def transforms(pwm):
    """Frozen structural chain; does not qualify the unloaded egomap FK API."""
    _, joints = commanded_joints(pwm)
    spec = model()
    t = np.eye(4)
    t[:3, 3] = spec['floor_to_chassis_translation_m']
    for link in spec['chain']:
        t = t @ fixed_transform(link)
        if 'servo' in link:
            q = joints[link['servo']]
            if not link['range_rad'][0] <= q <= link['range_rad'][1]:
                raise ValueError('command outside mechanical joint range')
            joint = np.eye(4)
            joint[:3, :3] = axis_rotation(link['joint_axis'], q)
            t = t @ joint
    camera = t @ fixed_transform(spec['camera'])
    camera[:3, :3] = camera[:3, :3] @ np.diag([1., -1., -1.])
    return t, camera


def object_transform(kind, grasp_pwm, view_pwm):
    from sim.grasp_act_solo_teacher import cargo
    spec = cargo(kind)
    grip, _ = transforms(grasp_pwm)
    now, _ = transforms(view_pwm)
    obj = np.eye(4)
    obj[:3, :3] = axis_rotation([0, 0, 1], np.deg2rad(tool_pose(grasp_pwm).yaw_left_deg))
    obj[:3, 3] = np.asarray(forward_grip(grasp_pwm)) + [0, 0, spec.dims_m[2]/2-spec.grip_z_m]
    return now @ np.linalg.inv(grip) @ obj


def project(points, pwm, size=(640, 480)):
    _, c = transforms(pwm)
    optical = (np.asarray(points)-c[:3, 3]) @ c[:3, :3]
    pixels = cv2.fisheye.projectPoints(optical.reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
        scaled_camera_matrix(*size), np.asarray(CAMERA_FISHEYE_D))[0].reshape(-1, 2)
    return pixels, optical[:, 2] > .001


def _key(pwm):
    return tuple(int(pwm.get(s, pwm.get(str(s)))) for s in (1, 3, 4, 5, 6))


def regions(kind, grasp_pwm, view_pwm, size=(640, 480), *, site=None, held=True):
    site = tuple(site) if site is not None else (*forward_grip(grasp_pwm)[:2], 0.)
    return _regions(kind, _key(grasp_pwm), _key(view_pwm), size, site, held)


@lru_cache(maxsize=128)
def _regions(kind, grasp_key, view_key, size, site, held):
    """Floor footprint from issued close pose and base history, with 6 mm slack.

    Conservative held-cargo box (+1 mm) ray tests include the entire can. No
    clipping near the lens is used to excuse an occlusion. Self hardware is
    screened in the static audit; actual occlusion must also pass RGB floor tests.
    """
    from sim.grasp_act_solo_teacher import cargo
    gp, vp = (dict(zip((1, 3, 4, 5, 6), k)) for k in (grasp_key, view_key))
    w, h = size
    spec = cargo(kind)
    centre = np.asarray(site)
    yaw = np.deg2rad(tool_pose(gp).yaw_left_deg)
    rot = axis_rotation([0, 0, 1], yaw)
    half = np.asarray(spec.dims_m)/2
    # Sample faces, not only corners: fisheye edges are curved.
    points = np.array([[x, y, z] for x in np.linspace(-half[0]-.006, half[0]+.006, 9)
        for y in np.linspace(-half[1]-.006, half[1]+.006, 9) for z in (0.,)])
    points = points @ rot.T + centre
    pixels, front = project(points, vp, size)
    usable = _usable_region(w, h)
    interior = cv2.erode(usable.astype(np.uint8), np.ones((25, 25), np.uint8),
                        borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    xy = np.rint(pixels).astype(int)
    inside = front & (xy[:, 0] >= 0) & (xy[:, 0] < w) & (xy[:, 1] >= 0) & (xy[:, 1] < h)
    good = np.zeros(len(xy), bool)
    good[inside] = interior[xy[inside, 1], xy[inside, 0]]
    roi = np.zeros((h, w), np.uint8)
    if front.all() and np.max(np.abs(xy)) < 10000:
        cv2.fillConvexPoly(roi, cv2.convexHull(xy.astype(np.int32)), 1)
    roi &= usable.astype(np.uint8)
    roi = roi.astype(bool)
    outer = cv2.dilate(roi.astype(np.uint8), np.ones((41, 41), np.uint8)).astype(bool)
    ring = outer & ~cv2.dilate(roi.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & interior
    # A retained cargo is rigid in the gripper, including its orientation.
    obj = object_transform(kind, gp, vp)
    _, c = transforms(vp)
    rays = _pixel_rays(w, h) @ c[:3, :3].T
    entry, exit_ = _ray_box(c[:3, 3], rays, obj[:3, 3], half+.001, obj[:3, :3])
    occ = (np.isfinite(entry) & (exit_ >= np.maximum(entry, 0.)) & (exit_ > 0.)).reshape(h, w)
    if not held:
        occ[:] = False
    # Known held pixels cannot be a floor-colour reference either.
    ring &= ~occ
    occluded = int((roi & occ).sum())
    info = {'site_from_issued_grip_m': centre.tolist(), 'site_pixels': int(roi.sum()),
            'ring_pixels': int(ring.sum()), 'surface_in_frame_n': int(good.sum()),
            'surface_N': len(good), 'held_occlusion_pixels': occluded,
            'bbox_xyxy': [*xy.min(0).tolist(), *xy.max(0).tolist()],
            'qualified': bool(good.all() and roi.sum() >= 600 and ring.sum() >= 300 and occluded == 0),
            'fk_scope': 'nominal issued PWM; loaded sag and physical calibration unverified'}
    for mask in (roi, ring, occ):
        mask.setflags(write=False)
    return roi, ring, info


def colour_evidence(frame, kind, roi, ring):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    reference = np.median(frame[ring], axis=0) if ring.any() else np.zeros(3)
    difference = np.max(np.abs(frame.astype(float)-reference), axis=2)
    # Cargo colour alone is insufficient on a similarly painted floor.
    colour = (hue_mask(hsv, kind) > 0) & (difference > 34) & roi
    n, labels, stats, _ = cv2.connectedComponentsWithStats(colour.astype(np.uint8))
    largest = int(max(stats[1:, cv2.CC_STAT_AREA], default=0))
    return {'colour_pixels': int(colour.sum()), 'largest_blob_pixels': largest,
            'colour_share': float(colour.sum()/max(1, roi.sum())),
            'floor_like_share': float(((difference <= 34) & roi).sum()/max(1, roi.sum())),
            'ring_uniform_share': float((difference[ring] <= 34).mean()) if ring.any() else 0.,
            'floor_bgr': reference.tolist(), 'floor_lit': bool(reference.max() >= 40)}


class LookbackObserver:
    def __init__(self, kind, *, propagate=None):
        self.propagate = propagate
        self.kind = kind
        self.before = self.before_command = self.grasp = None
        self.samples = {}
        self.commands = []
        self.started_at = self.completed_at = None
        self.invalid = None
        self.site = self.expected = self.previous = None
        self.advanced_t = None
        self.last = None
        self.answer_counts = {'yes': 0, 'no': 0, 'unknown': 0}

    def start(self, frame, command, save):
        self.before, self.before_command = frame.copy(), deepcopy(command)
        self.samples['before_pick'] = save('before_pick', frame, command['t'])
        self.commands = []

    def issue(self, command, phase):
        if self.before is None or phase in ('lookback_return', 'lower', 'open', 'retract', 'backoff', 'lookaround', 'complete'):
            return
        self._advance(command['t'])
        self.previous, self.advanced_t = deepcopy(command), command['t']
        self.commands.append(deepcopy(command))
        if any(command['wheels']) and phase != 'lookback':
            self.invalid = 'base_command_after_reference'
        if phase == 'close' and self.grasp is None:
            self.grasp = {int(s): int(v) for s, v in command['pwm'].items()}
            self.site = (*forward_grip(self.grasp)[:2], 0.)
        if phase == 'lookback' and self.started_at is None:
            self.started_at = command['t']
            self.expected = pose_for(self.kind, command['pwm'])

    def _advance(self, now):
        if self.previous is not None and self.site is not None and now > self.advanced_t:
            from sim.grasp_act_teacher_v3 import propagate_owned
            dt = now-self.advanced_t
            if dt > .15+1e-8:
                self.invalid = 'command_history_gap'
            self.site = tuple((self.propagate or propagate_owned)(self.site, self.previous, dt))
            self.advanced_t = now

    def observe(self, frame, command, *, complete, save):
        self._advance(command['t'])
        out = {'evidence': MODE, 'answer': 'unknown', 'reason': 'reference_or_motion_pending'}
        if self.before is not None and self.grasp is not None and complete and self.started_at is not None:
            if self.completed_at is None:
                self.completed_at = command['t']
                self.samples['lookback_complete'] = save('lookback_complete', frame, command['t'])
            pose = {int(s): int(v) for s, v in command['pwm'].items()}
            expected = self.expected
            if self.invalid or any(command['wheels']) or pose != expected or pose[1] != 1500:
                out['reason'] = self.invalid or 'lookback_command_changed'
            elif frame.shape != self.before.shape or np.array_equal(frame, self.before):
                out['reason'] = 'missing_fresh_comparable_frame'
            else:
                size = (frame.shape[1], frame.shape[0])
                # Pre-pick view is open: do not require its hypothetical HELD
                # silhouette to be clear. The cargo itself must be in view.
                pre, pring, pi = regions(self.kind, self.grasp, self.before_command['pwm'], size, held=False)
                post, ring, gi = regions(self.kind, self.grasp, pose, size, site=self.site)
                before = colour_evidence(self.before, self.kind, pre, pring)
                after = colour_evidence(frame, self.kind, post, ring)
                out.update(before=before, after=after, geometry=gi, before_geometry=pi)
                if pi['site_pixels'] < 600 or pi['ring_pixels'] < 300:
                    out['reason'] = 'pickup_reference_out_of_view'
                elif before['largest_blob_pixels'] < 150 or before['colour_share'] < .03:
                    out['reason'] = 'pickup_reference_colour_unproven'
                elif not gi['qualified']:
                    out['reason'] = 'pickup_site_unframed_or_occluded'
                elif after['largest_blob_pixels'] >= 150 and after['colour_share'] >= .03:
                    out.update(answer='no', reason='cargo_remains_at_pickup_site')
                elif (after['colour_share'] <= .01 and after['floor_like_share'] >= .90
                      and after['ring_uniform_share'] >= .90 and after['floor_lit']
                      and np.max(np.abs(np.array(after['floor_bgr'])-before['floor_bgr'])) <= 55):
                    out.update(answer='yes', reason='pickup_site_proven_empty')
                else:
                    out['reason'] = 'pickup_site_not_proven_bare_floor'
            if command['t']-self.completed_at >= 3.-1e-8 and 'settled_lookback' not in self.samples:
                self.samples['settled_lookback'] = save('settled_lookback', frame, command['t'])
        out.update(samples=dict(self.samples), evidence_scope='removal_only; retention scored separately')
        self.answer_counts[out['answer']] += 1
        self.last = out
        return out

    def record(self):
        return {'mode': MODE, 'samples': self.samples, 'answer_counts': self.answer_counts,
                'last': self.last, 'commands': self.commands}
