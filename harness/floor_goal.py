"""Opt-in, robot-private floor-colour goal observations; no world map or GT input.

OpenCV HSV/inRange + fisheye unprojection + forward ray/plane intersection.
Parameters/provenance: experiments/2026-10-07-mapfree-goal-floor/README.md.
Confidence is a heuristic quality score, not a calibrated posterior probability.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from functools import lru_cache
import math

import cv2
import numpy as np

from harness.self_odom_grid import transform
from harness.visual_arm import camera_extrinsics
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix


@dataclass(frozen=True)
class FloorGoalOptions:
    hue_low: int = 100
    hue_high: int = 130
    saturation_min: int = 35
    value_min: int = 30
    min_pixels: int = 64
    roi_top: float = .35
    downward_min: float = .05
    max_range_m: float = 4.
    floor_saturation_max: int = 55
    floor_ring_min: float = .35
    cell_m: float = .1
    association_gap_m: float = .30

    def __post_init__(self):
        for k, v in asdict(self).items():
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValueError(f"INVALID_GOAL_OPTION: {k}")
        for k in ('hue_low', 'hue_high', 'saturation_min', 'value_min', 'floor_saturation_max', 'min_pixels'):
            if not isinstance(getattr(self, k), int):
                raise ValueError(f"INVALID_GOAL_OPTION: {k}")
        if not (0 <= self.hue_low <= 179 and 0 <= self.hue_high <= 179 and
                0 <= self.saturation_min <= 255 and 0 <= self.value_min <= 255 and
                0 <= self.floor_saturation_max <= 255 and 0 <= self.roi_top < 1 and
                0 < self.downward_min < 1 and 0 <= self.floor_ring_min <= 1 and
                self.min_pixels >= 3 and self.cell_m > 0 and self.max_range_m > 0 and self.association_gap_m >= 0):
            raise ValueError("INVALID_GOAL_OPTIONS")


def commanded_camera(servo, profile):
    """Optical origin/row axes in chassis XY, with Z relative to the floor.

    v3 fixed mount from sim/masterpi_camera_review_v3.py (PR #401), composed
    with the existing command-only FK. Neither mount is measured hand-eye GT.
    """
    origin, axes = (np.array(x, float) for x in camera_extrinsics(servo))
    if profile == 'camera_v3':
        old = math.radians(7.45917653)
        new = math.radians(10.)
        def optical_rows(a):
            return np.array([[0., -1., 0.], [math.sin(a), 0., -math.cos(a)],
                             [math.cos(a), 0., math.sin(a)]])
        gripper_rotation = axes.T @ optical_rows(old)
        origin += gripper_rotation @ (np.array([.052982009925558314, 0., .028152173913043477]) -
                                      [.067, 0., .0136])
        axes = optical_rows(new) @ gripper_rotation.T
    elif profile != 'legacy':
        raise ValueError('UNKNOWN_GOAL_CAMERA_PROFILE')
    origin[0] += .0482  # Same arm-axis/chassis offset as the frozen own-wall module.
    return origin, axes


@lru_cache(maxsize=4)
def optical_rays(width, height):
    yy, xx = np.indices((height, width))
    uv = np.stack([xx, yy], axis=-1).astype(float)
    xy = cv2.fisheye.undistortPoints(uv.reshape(-1, 1, 2),
            np.asarray(scaled_camera_matrix(width, height)), np.asarray(CAMERA_FISHEYE_D)).reshape(height, width, 2)
    rays = np.concatenate([xy, np.ones((height, width, 1))], axis=-1)
    rays.setflags(write=False)
    return rays


def floor_intersections(rays, origin, axes, *, downward_min=.05, max_range_m=4.):
    """No backward intersections. Return XYZ and validity, never clip bad ranges."""
    direction = np.asarray(rays) @ np.asarray(axes)
    origin = np.asarray(origin)
    with np.errstate(divide='ignore', invalid='ignore'):
        t = -origin[2] / direction[..., 2]
        points = origin + direction * t[..., None]
    valid = (np.isfinite(points).all(axis=-1) & (np.asarray(rays)[..., 2] > 0) & (t > 0) &
             (direction[..., 2] < -downward_min) & (np.linalg.norm(points-origin, axis=-1) <= max_range_m))
    return points, valid


def detect_floor(rgb, *, servo, profile, options=None):
    """Return accepted observed patches, a component label image and gate counts.

    Label IDs link evaluation to exact accepted pixels. Rejected mask components
    never enter memory. Missing/distorted/horizon pixels are not extrapolated.
    """
    opt = options or FloorGoalOptions()
    rgb = np.asarray(rgb)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 3:
        raise ValueError('GOAL_REQUIRES_UINT8_RGB')
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    hue = ((h >= opt.hue_low) & (h <= opt.hue_high) if opt.hue_low <= opt.hue_high else
           (h >= opt.hue_low) | (h <= opt.hue_high))
    mask = (hue & (s >= opt.saturation_min) & (v >= opt.value_min)).astype(np.uint8)
    mask[:int(math.ceil(rgb.shape[0]*opt.roi_top))] = 0
    origin, axes = commanded_camera(servo, profile)
    points, valid = floor_intersections(optical_rays(rgb.shape[1], rgb.shape[0]), origin, axes,
                                      downward_min=opt.downward_min, max_range_m=opt.max_range_m)
    mask[~valid] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    accepted = np.zeros_like(labels, dtype=np.uint16)
    diagnostics = {'small': 0, 'floor_connection': 0, 'accepted': 0}
    patches = []
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] < opt.min_pixels:
            diagnostics['small'] += 1
            continue
        region = labels == label
        ring = (cv2.dilate(region.astype(np.uint8), np.ones((3, 3), np.uint8)) != 0) & ~region
        # Neutral floor support must itself have a valid downward floor ray.
        neutral = (s <= opt.floor_saturation_max) & (v >= opt.value_min) & valid
        support = float(np.count_nonzero(neutral & ring) / max(1, np.count_nonzero(ring)))
        if support < opt.floor_ring_min:
            diagnostics['floor_connection'] += 1
            continue
        xy = points[region, :2]
        hull = cv2.convexHull(xy.astype(np.float32)).reshape(-1, 2)
        # Save observed cells only: never fill the hull or infer unseen B extent.
        patch_id = len(patches)+1
        accepted[region] = patch_id
        patches.append({'component': patch_id, 'pixels': int(len(xy)),
                        'center_body_m': xy.mean(axis=0).tolist(), 'hull_body_m': hull.tolist(),
                        '_points_body_m': xy,
                        'confidence': float(min(1., support) * min(1., len(xy)/(4*opt.min_pixels))),
                        'floor_connection': support})
    diagnostics['accepted'] = len(patches)
    return patches, accepted, diagnostics


class FloorGoalMemory:
    """Own observed colour patches. No peer merge or static-world goal fallback."""
    def __init__(self, robot_id, *, options=None):
        self.robot_id = robot_id
        self.options = FloorGoalOptions(**(options or {}))
        self.last_t = -math.inf
        self.seen = set()
        self.tracks = []

    def observe(self, rgb, *, robot_id, frame_id, t, pose, servo, profile, settled):
        if robot_id != self.robot_id:
            raise ValueError('GOAL_PEER_INPUT_FORBIDDEN')
        if not math.isfinite(t) or np.asarray(pose).shape != (3,) or not np.isfinite(pose).all():
            raise ValueError('GOAL_NONFINITE_POSE_TIME')
        if frame_id in self.seen:
            raise ValueError('GOAL_DUPLICATE_FRAME')
        if t <= self.last_t:
            raise ValueError('GOAL_NON_MONOTONIC_TIME')
        if not settled:
            self.seen.add(frame_id)
            self.last_t = t
            return [], None, {'unsettled': 1}
        patches, labels, diagnostics = detect_floor(rgb, servo=servo, profile=profile, options=self.options)
        self.seen.add(frame_id)
        self.last_t = t
        for patch in patches:
            center = transform([patch['center_body_m']], pose)[0]
            hull = transform(patch['hull_body_m'], pose)
            # Quantize after SE(2) placement; union contains only observed cells.
            cells = {tuple(x) for x in np.floor(transform(patch.pop('_points_body_m'), pose)/self.options.cell_m).astype(int)}
            box = np.array([hull.min(axis=0), hull.max(axis=0)])
            compatible = []
            for track in self.tracks:
                gap = np.maximum(0., np.maximum(track['box'][0]-box[1], box[0]-track['box'][1]))
                if np.linalg.norm(gap) <= self.options.association_gap_m:
                    compatible.append((float(np.linalg.norm(track['box'].mean(axis=0)-center)), track['id']))
            if compatible:
                track = self.tracks[min(compatible)[1]-1]
            else:
                track = {'id': len(self.tracks)+1, 'cells': set(), 'box': box, 'views': {},
                         'first_t': t, 'confirmed_t': None, 'quality_sum': 0., 'patches': 0}
                self.tracks.append(track)
            track['cells'].update(cells)
            track['box'] = np.array([np.minimum(track['box'][0], box[0]), np.maximum(track['box'][1], box[1])])
            track['views'][frame_id] = (t, tuple(pose))
            track['last_t'] = t
            track['quality_sum'] += patch['confidence']
            track['patches'] += 1
            views = list(track['views'].values())
            first = np.array(views[0][1])
            baseline = any(np.linalg.norm(np.array(p)[:2]-first[:2]) >= .05 or
                           abs(math.atan2(math.sin(p[2]-first[2]), math.cos(p[2]-first[2]))) >= math.radians(5)
                           for _, p in views)
            if track['confirmed_t'] is None and len(views) >= 3 and t-track['first_t'] >= 2 and baseline:
                track['confirmed_t'] = t
            patch.update(track_id=track['id'], center_odom_m=center.tolist(), hull_odom_m=hull.tolist(),
                         confirmed_t=track['confirmed_t'])
        return patches, labels, diagnostics

    def snapshot(self):
        candidates = []
        for track in self.tracks:
            xy = (np.array(sorted(track['cells']))+.5)*self.options.cell_m
            candidates.append({'id': track['id'], 'state': ('locally_confirmed_region' if track['confirmed_t'] is not None
                               else 'visually_seen'), 'center_m': xy.mean(axis=0).tolist(),
                               'bounds_m': [xy.min(axis=0).tolist(), xy.max(axis=0).tolist()],
                               'observed_cells': len(xy), 'observations': len(track['views']),
                               'first_t': track['first_t'], 'last_t': track['last_t'],
                               'confirmed_t': track['confirmed_t'],
                               'confidence': track['quality_sum']/track['patches']})
        return {'robot_id': self.robot_id, 'coordinate_frame': f'{self.robot_id}/own_odom',
                'goal': 'B', 'state': ('locally_confirmed_region' if any(t['confirmed_t'] is not None for t in self.tracks)
                                     else 'visually_seen' if self.tracks else 'unknown'),
                'extent': 'observed cells only; full destination boundary unknown', 'candidates': candidates}
