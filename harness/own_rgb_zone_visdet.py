"""Own-RGB zone / arrival detection for MJWarp-GPU rendered frames.

Purpose
-------
The e2ewarp ``navigation_factory`` adapter must answer two questions from the
robot's own inputs on every frame: *is the destination zone paint visible?* and
*has the robot reached the zone edge?*  The existing visgoal detectors were
written against the MuJoCo fisheye ``robot_cam`` and import
``sim.grasp_act_solo_lookback`` (MuJoCo FK).  This module keeps the same
appearance/threshold evidence but works on **plain uint8 RGB arrays** and a
caller-supplied camera model, so it can run on GPU-rendered frames without any
sim/engine import.

Allowed inputs (never anything else)
------------------------------------
* one own RGB frame (HxWx3 uint8, RGB channel order),
* a camera model derived from the robot's own servo FK: pinhole intrinsics plus
  the camera-to-robot transform, or a precomputed ray table in the robot frame
  (both are pure data; no engine import),
* the robot's own issued commands (optional; this detector itself does not use
  them for geometry),
* the versioned static map zone rectangle (optional expected-size sanity only).

Never read: TOP camera frames or anything derived from them, simulator/GT pose,
contacts, measured joints, teacher phases/outcomes, other robots' frames,
truth labels. ``import mujoco`` / ``sim.*`` never appear in this module
(``tests/test_own_rgb_zone_visdet.py`` asserts it).

Default OFF: every public entry returns ``status='off'`` unless
``enabled=True`` (toggle ``own_rgb_zone_visdet_v1``) is passed.  Enabling it
does not grant arrival authority by itself: the navigation adapter must still
decide with its owner-approved debounce/consistency rules.

Threshold provenance
--------------------
* destination hue band and S/V floors are the visgoal C build appearance-only
  constants (blue-indigo ``PAINT_HUE['B']`` = 104..120 deg, S>=30, V>=30), not
  geometry; the same values were used by the CPU crossroom raw.
* floor-fit range limit 1.8 m and the >=600 pixel component floor are the
  vendored ``destination_visual_acquire`` limits (inherited, documented there).
* the arrival bottom-band threshold 0.98 of frame height comes from the CPU
  crossroom raw: the only recorded declaration outside zone B
  (crossroom-stageA-fix2 e02, GT margin -0.0162 m) had the zone paint bbox
  bottom at 461/480 = 0.960, so >=0.98 (bottom 2% band) is the measured
  condition used there; this module records it as evidence, it is not a
  mission success claim.
* ``gpu_calib_v1`` is fitted on the approved GPU zone-B appearance calibration
  capture (MJWarp native render, e2ewarp R4 scene, 36 frames; evidence under
  ``experiments/2026-10-17-e2ewarp/r4-selfmap-recount/zonecal-gpu/`` and
  ``zone-appearance-calib.json``).  On that capture the zone-B paint renders
  darker (component median V 77-86) than the bright pickup-room blue floor
  (V~135), so the GPU profile narrows the hue band to 110-114, raises the
  saturation floor to 100 and adds a V<=110 ceiling.  Fit result: 33/33
  zone-B capture frames accepted, 0/3 pickup negatives, 0/180 recorded R4
  floor frames (CPU profile produced 36/180).  The capture is labelled
  "GPU appearance calibration, not research result" and is not pooled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import cv2
import numpy as np

SCHEMA = 'ugrp.own_rgb_zone_visdet.v1'
TOGGLE = 'own_rgb_zone_visdet_v1'

# visgoal C build appearance-only blue paint band (see module docstring).
PAINT_HUE = (104, 120)
PAINT_SATURATION_MIN = 30
PAINT_VALUE_MIN = 30
PAINT_MIN_PIXELS = 600
FLOOR_MAX_RANGE_M = 1.8
ARRIVAL_BOTTOM_NORM = 0.98
# Authored zone-B rectangle is 0.60 x 1.40 m; a visible zone patch cannot have a
# floor-projected extent larger than its diagonal (1.52 m). 2.0 m leaves room for
# truncated/oblique patches while rejecting a floor/wall component whose extent
# spans metres. Measured CPU raw zone patches were 0.205-1.236 m.
MAX_EXTENT_M = 2.0
# Appearance profiles.  cpu_v1 is the CPU crossroom visgoal appearance band
# (floor there was pale blue-gray and did not enter the band).  gpu_calib_v1 is
# fitted on the GPU zone-B appearance calibration capture
# (experiments/2026-10-17-e2ewarp/r4-selfmap-recount/zone-appearance-calib.json):
# the MJWarp-rendered pickup-room floor is a bright saturated blue (component
# V~135) while the zone-B paint renders darker (V~77-86), so the GPU profile
# narrows hue and adds a value ceiling.  Thresholds are calibration evidence,
# not a mission claim; the capture is labelled "not research result".
APPEARANCE_PROFILES = {
    'cpu_v1': dict(hue=(104, 120), s_min=30, v_min=30, v_max=255,
                   max_extent_m=MAX_EXTENT_M),
    'gpu_calib_v1': dict(hue=(110, 114), s_min=100, v_min=30, v_max=110,
                         max_extent_m=1.75),
}
DEFAULT_APPEARANCE = 'cpu_v1'
# Bottom 25% rows and centre 40% columns, matching the own-RGB "under the
# robot" evidence used by the carry monitor and the CPU zone-edge check.
LOWER_CENTRE_ROWS = 0.25
LOWER_CENTRE_COLS = (0.30, 0.70)


@dataclass(frozen=True)
class CameraModel:
    """Pure camera model supplied by the caller (e.g. servo-FK).

    kind='pinhole': rays are generated from intrinsics and ``cam_to_robot``.
    kind='rays': ``rays`` (H,W,3) are already directions in the robot frame.

    Robot frame follows the existing UGRP convention: x forward, y left,
    z up; the robot floor plane is z=0.  ``cam_to_robot`` maps camera-frame
    directions to the robot frame; ``translation_m`` is the camera origin in
    the robot frame.
    """
    kind: str
    width: int
    height: int
    fx: float | None = None
    fy: float | None = None
    cx: float | None = None
    cy: float | None = None
    rotation: np.ndarray | None = None
    translation_m: tuple = (0.0, 0.0, 0.0)
    rays: np.ndarray | None = None

    def __post_init__(self):
        if self.kind not in ('pinhole', 'rays'):
            raise ValueError('CAMERA_MODEL_KIND')
        if self.kind == 'pinhole' and None in (self.fx, self.fy, self.cx, self.cy):
            raise ValueError('CAMERA_MODEL_INTRINSICS')
        if self.kind == 'rays' and self.rays is None:
            raise ValueError('CAMERA_MODEL_RAYS')

    def ray_grid(self):
        if self.kind == 'rays':
            rays = np.asarray(self.rays, float)
            if rays.shape != (self.height, self.width, 3):
                raise ValueError('CAMERA_MODEL_RAYS_SHAPE')
            return rays
        us = np.arange(self.width, dtype=float)
        vs = np.arange(self.height, dtype=float)
        uu, vv = np.meshgrid(us, vs)
        cam = np.stack([(uu - self.cx) / self.fx,
                        (vv - self.cy) / self.fy,
                        np.ones_like(uu)], axis=-1)
        if self.rotation is None:
            return cam
        rot = np.asarray(self.rotation, float)
        return cam @ rot.T

    def origin(self):
        return np.asarray(self.translation_m, float)


@dataclass
class ZoneSpec:
    """Optional static-map expectation (allowed input) - sanity, not truth."""
    rect: tuple = (4.30, 4.90, -2.80, -1.40)   # x0,x1,y0,y1 in the map gauge
    min_side_m: float = 0.30
    extent_slack: float = 0.60


@dataclass
class Detection:
    status: str
    enabled: bool
    pixels: int = 0
    bbox: list | None = None
    centroid: list | None = None
    nearest_range_m: float | None = None
    median_range_m: float | None = None
    ground_pixels: int = 0
    extent_m: float | None = None
    bearing_rad: float | None = None
    bottom_norm: float | None = None
    lower_centre_share: float | None = None
    paint_reaches_bottom_band: bool = False
    arrival_ready: bool = False
    reason: str = 'off'
    notes: dict = field(default_factory=dict)

    def as_dict(self):
        return dict(schema=SCHEMA, **{k: v for k, v in self.__dict__.items()})


def _off(reason='off'):
    return Detection(status='off', enabled=False, reason=reason)


def detect(rgb, camera: CameraModel, *, enabled=False, zone='B',
           spec: ZoneSpec | None = None, exclude_mask=None,
           arrival_bottom_norm=ARRIVAL_BOTTOM_NORM,
           min_pixels=PAINT_MIN_PIXELS,
           floor_max_range_m=FLOOR_MAX_RANGE_M,
           max_extent_m=MAX_EXTENT_M,
           appearance=DEFAULT_APPEARANCE,
           override=None) -> Detection:
    """Detect the destination zone paint and its metric evidence in one frame.

    ``rgb`` must be an HxWx3 uint8 RGB array of ``camera.width`` x
    ``camera.height``.  ``exclude_mask`` (HxW bool) may hide held-cargo or other
    own-RGB pixels from the colour component; the caller owns that mask.
    """
    if not enabled:
        return _off()
    prof = dict(APPEARANCE_PROFILES.get(str(appearance), {}))
    if not prof:
        raise ValueError('UNKNOWN_APPEARANCE_PROFILE:' + str(appearance))
    if override:
        prof.update(override)
    if zone != 'B':
        return _off('zone_unsupported')
    if rgb is None:
        return Detection(status='unknown', enabled=True, reason='own_rgb_missing')
    rgb = np.asarray(rgb)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('own RGB uint8 HxWx3 required')
    h, w = rgb.shape[:2]
    if (w, h) != (camera.width, camera.height):
        raise ValueError('camera/frame size mismatch')
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lo, hi = prof['hue']
    mask = ((hsv[..., 0] >= lo) & (hsv[..., 0] <= hi)
            & (hsv[..., 1] >= prof['s_min'])
            & (hsv[..., 2] >= prof['v_min'])
            & (hsv[..., 2] <= prof['v_max']))
    if exclude_mask is not None:
        mask &= ~np.asarray(exclude_mask, bool)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), 8)
    if n <= 1:
        return Detection(status='unknown', enabled=True,
                         reason='destination_colour_absent')
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    count = int(stats[i, cv2.CC_STAT_AREA])
    bbox = [int(v) for v in stats[i, :4]]  # x, y, w, h
    if count < min_pixels:
        return Detection(status='unknown', enabled=True, pixels=count,
                         bbox=bbox, reason='destination_component_small')
    # Floor-plane fit in the robot frame (pure geometry from the camera model).
    rays = camera.ray_grid().reshape(-1, 3)
    origin = camera.origin()
    valid_pix = (labels == i).reshape(-1)
    rr = rays[valid_pix]
    ok = rr[:, 2] < -1e-6
    rr = rr[ok]
    if not len(rr):
        return Detection(status='unknown', enabled=True, pixels=count,
                         bbox=bbox, reason='destination_not_ground_ray')
    scale = -origin[2] / rr[:, 2]
    xy = origin[:2] + scale[:, None] * rr[:, :2]
    rng = np.linalg.norm(xy, axis=1)
    inside = scale > 0
    xy, rng = xy[inside], rng[inside]
    if len(xy) < min_pixels // 2:
        return Detection(status='unknown', enabled=True, pixels=count,
                         bbox=bbox, reason='destination_outside_floor_fit',
                         notes=dict(ground_pixels=int(len(xy))))
    near = float(np.min(rng)); med = float(np.median(rng))
    if med > floor_max_range_m:
        return Detection(status='unknown', enabled=True, pixels=count,
                         bbox=bbox, nearest_range_m=near,
                         reason='destination_too_far')
    extent = float(np.linalg.norm(np.ptp(xy, axis=0)))
    if max_extent_m is None:
        max_extent_m = prof.get('max_extent_m')
    if max_extent_m is not None and extent > float(max_extent_m):
        return Detection(status='unknown', enabled=True, pixels=count,
                         bbox=bbox, nearest_range_m=near, extent_m=extent,
                         reason='destination_extent_not_zone',
                         notes=dict(max_extent_m=float(max_extent_m)))
    if spec is not None:
        limit = 2 * math.hypot(spec.rect[1] - spec.rect[0],
                               spec.rect[3] - spec.rect[2]) + spec.extent_slack
        if extent > limit:
            return Detection(status='unknown', enabled=True, pixels=count,
                             bbox=bbox, nearest_range_m=near,
                             extent_m=extent, reason='destination_extent_not_zone')
    cx, cy = float(centroids[i][0]), float(centroids[i][1])
    bearing = float(math.atan2(float(np.median(xy[:, 1])),
                               float(np.median(xy[:, 0]))))
    bottom_norm = (bbox[1] + bbox[3]) / float(h)
    lower_centre = (np.asarray(centroids[i]))
    ly0 = int((1.0 - LOWER_CENTRE_ROWS) * h)
    lx0 = int(LOWER_CENTRE_COLS[0] * w); lx1 = int(LOWER_CENTRE_COLS[1] * w)
    lower_pixels = int(mask[ly0:, lx0:lx1].sum())
    lower_share = lower_pixels / float(max(1, count))
    reaches = bool(bottom_norm >= float(arrival_bottom_norm))
    return Detection(status='observed', enabled=True, pixels=count, bbox=bbox,
                     centroid=[round(cx, 2), round(cy, 2)],
                     nearest_range_m=round(near, 4),
                     median_range_m=round(med, 4),
                     ground_pixels=int(len(xy)),
                     extent_m=round(extent, 4),
                     bearing_rad=round(bearing, 4),
                     bottom_norm=round(bottom_norm, 4),
                     lower_centre_share=round(lower_share, 4),
                     paint_reaches_bottom_band=reaches,
                     arrival_ready=reaches,
                     reason='painted_ground_hypothesis',
                     notes=dict(zone=zone, appearance=appearance,
                                origin=list(map(float, origin)),
                                extent_ptp=[float(v) for v in np.ptp(xy, axis=0)]))


class ZoneArrivalReporter:
    """Small stateful wrapper for navigation_factory observation reports.

    It is deliberately not an arrival authority: it exposes the own-RGB
    evidence and a debounced ``destination_arrived`` flag that the owner
    navigation adapter may combine with its own map/pose rules.  All fields
    derive from the allowed inputs of :func:`detect`.
    """

    def __init__(self, camera: CameraModel, *, enabled=False, spec=None,
                 confirm_frames=3, lost_frames=5):
        self.camera = camera
        self.enabled = bool(enabled)
        self.spec = spec
        self.confirm_frames = max(1, int(confirm_frames))
        self.lost_frames = max(1, int(lost_frames))
        self._reaches = 0
        self._missing = 0
        self._arrived = False
        self.revision = 0

    def observe(self, rgb, *, exclude_mask=None):
        det = detect(rgb, self.camera, enabled=self.enabled, spec=self.spec,
                     exclude_mask=exclude_mask)
        if not self.enabled:
            return dict(schema=SCHEMA, status='off', destination_zone='B',
                        zone_visible=False, destination_arrived=False,
                        handoff_ready=False, evidence_revision=self.revision,
                        detail=det.as_dict())
        if det.status == 'observed' and det.paint_reaches_bottom_band:
            self._reaches += 1
            self._missing = 0
        else:
            # No zone-under-robot evidence (absent, filtered or not yet at the
            # edge) counts as missing evidence for the debounced state.
            self._reaches = 0
            self._missing += 1
        if self._reaches >= self.confirm_frames:
            self._arrived = True
        if self._missing >= self.lost_frames:
            self._arrived = False
        self.revision += 1
        return dict(schema=SCHEMA, status=det.status, destination_zone='B',
                    zone_visible=det.status == 'observed',
                    destination_arrived=self._arrived,
                    handoff_ready=False,   # owner adapter decides handoff
                    evidence_revision=self.revision,
                    confirm_frames=self.confirm_frames,
                    detail=det.as_dict())
