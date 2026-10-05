"""Cyan observations through v98's measured v3 camera, never SDK/v2 extrinsics.

Reuse the floor-cuboid fit and colour thresholds, with private dependency
binding (as the pair stack does). The last full fit is checked at the hover;
only the fixed, no-base-motion descent can then run blind.
"""
from __future__ import annotations

from types import SimpleNamespace
import math

import cv2
import numpy as np

from harness import markerless_box as box
from harness import zone_color_boxes as colors
from harness import zone_pair_highpose_blind_close as blind
from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_vision import GRASP_RADIUS_M, grasp_postures
from harness.zone_pair_highpose_contract import camera_record
from harness.visual_arm_v3 import CONTROLLER_GEOMETRY_ID


class CyanVision:
    def __init__(self, calibration):
        self.calibration = calibration
        measured = SimpleNamespace(**{**vars(box), 'camera_extrinsics': self.extrinsics,
            '_fit_floor_cuboid': lambda *a, **kw: box._fit_floor_cuboid(*a, **{**kw, 'refine_position': True})})
        self._detect = bind(colors.detect_own, _mb=measured)

    def extrinsics(self, servo):
        rec = camera_record(self.calibration, 'unloaded', servo)
        # markerless_box uses row axes; the measured record has optical axes as columns.
        return np.asarray(rec['origin_m']), np.asarray(rec['rotation']).T

    def detect(self, obs, servo):
        got = self._detect(obs['image'], servo, kinds=('cyan',), profile=colors.OWN_PROFILE_ZONE)
        return got['detections']

    def hover_support(self, obs, servo, center):
        """Partial cyan support near the last full fit; never invent a hidden centre.

        Same plane-ray idea as the pair hover patch. A complete cuboid fit can
        confirm XY directly; a clipped patch must overlap the tracked top
        footprint and straddle its lateral centre. Limits are DEV candidates.
        """
        fits = self.detect(obs, servo)
        if any(math.dist(d['estimated_box_center_base_m'][:2], center) <= .006 for d in fits):
            return True
        frame = colors._frame(obs['image'])
        mask = colors._mask(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), colors.OWN_ZONE_CYAN_HSV)
        y, x = np.nonzero(mask)
        if len(x) < 90:
            return False
        pixels = np.column_stack((x[::4], y[::4])).astype(float)
        k, d = box.scaled_camera_matrix(640, 480), np.asarray(box.CAMERA_FISHEYE_D, float)
        norm = cv2.fisheye.undistortPoints(pixels.reshape(1, -1, 2), k, d).reshape(-1, 2)
        origin, axes = self.extrinsics(servo)
        rays = np.column_stack((norm, np.ones(len(norm)))) @ axes
        down = rays[:, 2] < -1e-6
        rays = rays[down]
        scale = (colors.BOX_DIMS_M[2]-origin[2])/rays[:, 2]
        pts = origin[:2]+scale[:, None]*rays[:, :2]
        pts = pts[(scale > 0) & np.isfinite(pts).all(axis=1)]
        if len(pts) < 25:
            return False
        rel = pts-np.asarray(center)
        inside = (np.abs(rel[:, 0]) <= .030) & (np.abs(rel[:, 1]) <= .030)
        if inside.sum() < 25 or inside.mean() < .65:
            return False
        lo, hi = np.percentile(rel[inside, 1], [5, 95])
        return bool(lo < -.004 and hi > .004 and abs((lo+hi)/2) <= .006)


class BlindCyan:
    """v98 no-motion command envelope, two distinct hover frames, finite blind window."""
    def __init__(self):
        self.window = None
        self.last_frame = None
        self.streak = 0
        self.disarmed = None

    def confirm(self, now, obs, servo, center, supported):
        hover, path = grasp_postures()
        aligned = abs(center[0]-GRASP_RADIUS_M) <= .003 and abs(center[1]) <= .003
        if not (supported and aligned and blind.at_posture(servo, hover) and servo.get(1) == blind.OPEN_PWM):
            self.streak, self.window = 0, None
            return False
        if obs['frame_id'] != self.last_frame:
            self.streak += 1
        self.last_frame = obs['frame_id']
        if self.streak < blind.HOVER_CONFIRM_FRAMES:
            return False
        self.window = {'confirmed_at_s': now, 'frame_id': obs['frame_id'], 'sha256': obs['sha256'],
            'pan': hover[6], 'envelope': blind._envelope(hover, path), 'limits': blind.limits()}
        self.disarmed = None
        return True

    def command(self, row, servo):
        if self.window is not None and self.disarmed is None:
            self.disarmed = blind.off_window(row, servo, self.window)

    def ready(self, now, servo):
        return bool(self.window and not self.disarmed
            and 0 <= now-self.window['confirmed_at_s'] <= self.window['limits']['blind_max_s']
            and blind.at_posture(servo, grasp_postures()[1][-1]))
