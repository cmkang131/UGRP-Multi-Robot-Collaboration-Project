"""Explicit-parameter v2: HSV, component area/solidity and floor-ring support.

No fitted defaults are fabricated before the registered DEV RGB exists. Callers
must pass frozen DEV options. v1 remains the original detector and memory rules.
"""
from dataclasses import dataclass, fields
import math

import cv2
import numpy as np

from harness.floor_goal import (FloorGoalMemory, FloorGoalOptions, commanded_camera,
                                floor_intersections, optical_rays)


@dataclass(frozen=True)
class FloorGoalV2Options(FloorGoalOptions):
    # Geometry is the same calibrated forward-floor projection as v1. Full
    # downward FOV avoids using the old lower-65% crop as a hidden recall denominator.
    roi_top: float = 0.
    floor_saturation_max: int = 128
    minimum_solidity: float = .3

    def __post_init__(self):
        super().__post_init__()
        if not math.isfinite(self.minimum_solidity) or not 0 < self.minimum_solidity <= 1:
            raise ValueError('INVALID_GOAL_V2_SOLIDITY')


def detect_floor_v2(rgb, *, servo, profile, options):
    """Colour and shape-only inference. Truth masks/material IDs are not inputs."""
    if not isinstance(options, FloorGoalV2Options):
        raise ValueError('GOAL_V2_NEEDS_EXPLICIT_OPTIONS')
    rgb = np.asarray(rgb)
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 3:
        raise ValueError('GOAL_REQUIRES_UINT8_RGB')
    h, s, v = cv2.split(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV))
    o = options
    hue = ((h >= o.hue_low) & (h <= o.hue_high) if o.hue_low <= o.hue_high else
           (h >= o.hue_low) | (h <= o.hue_high))
    origin, axes = commanded_camera(servo, profile)
    points, valid = floor_intersections(optical_rays(rgb.shape[1], rgb.shape[0]), origin, axes,
                                       downward_min=o.downward_min, max_range_m=o.max_range_m)
    valid[:int(math.ceil(rgb.shape[0]*o.roi_top))] = False
    mask = (hue & (s >= o.saturation_min) & (v >= o.value_min) & valid).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    accepted = np.zeros_like(labels, dtype=np.uint16)
    diagnostics = {'small': 0, 'solidity': 0, 'floor_connection': 0, 'accepted': 0}
    patches = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < o.min_pixels:
            diagnostics['small'] += 1
            continue
        region = labels == label
        yy, xx = np.where(region)
        hull_px = cv2.convexHull(np.stack([xx, yy], axis=-1).astype(np.float32))
        # Pixel count vs continuous hull area: cap tiny lattice excess at 1.
        solidity = min(1., area/max(1., cv2.contourArea(hull_px)))
        if solidity < o.minimum_solidity:
            diagnostics['solidity'] += 1
            continue
        ring = (cv2.dilate(region.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & ~region
        floor_support = (s <= o.floor_saturation_max) & (v >= o.value_min) & valid
        support = float((floor_support & ring).sum()/max(1, ring.sum()))
        if support < o.floor_ring_min:
            diagnostics['floor_connection'] += 1
            continue
        xy = points[region, :2]
        hull = cv2.convexHull(xy.astype(np.float32)).reshape(-1, 2)
        component = len(patches)+1
        accepted[region] = component
        patches.append({'component': component, 'pixels': area, 'center_body_m': xy.mean(axis=0).tolist(),
                        'hull_body_m': hull.tolist(), '_points_body_m': xy,
                        'confidence': support*solidity*min(1., area/(4*o.min_pixels)),
                        'floor_connection': support, 'solidity': solidity})
    diagnostics['accepted'] = len(patches)
    return patches, accepted, diagnostics


class FloorGoalMemoryV2(FloorGoalMemory):
    detector = staticmethod(detect_floor_v2)

    def __init__(self, robot_id, *, options=None):
        required = {'hue_low', 'hue_high', 'saturation_min', 'min_pixels', 'minimum_solidity'}
        if options is None or not required.issubset(options):
            raise ValueError('GOAL_V2_NEEDS_FROZEN_DEV_OPTIONS')
        selected = FloorGoalV2Options(**options)
        super().__init__(robot_id, options={f.name: getattr(selected, f.name) for f in fields(FloorGoalOptions)})
        self.options = selected
