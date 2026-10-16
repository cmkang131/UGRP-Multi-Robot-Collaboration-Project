"""Own-RGB pickup-site memory and repeat-view comparison; no world-state input.

Presence/absence is visual evidence, not contact truth. The stock wrist camera
returns to the last aligned view; small residual image shifts use OpenCV ECC.
All new image thresholds are explicit UNQUALIFIED DEV algorithm choices.
"""
from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
import cv2
import numpy as np

from harness import zone_color_boxes as colors
from sim import masterpi_camera_profile as camera

PROFILE = 'cyan-pickup-site-scene-change-v1'
CONFIG = dict(frames=7, max_present_for_absent=1, min_cyan_px=90,
              min_area_ratio=.45, max_area_ratio=2.20,
              registration_correlation=.95, max_shift_px=12.,
              min_background_std=2., floor_color_tolerance=20.,
              clear_fraction=.95, max_retries=1)
# 7 frames / <=1 remaining match / .45..2.20 area ratios are inherited from
# scripts/red_block/pick.py. 90 px is v106's existing cyan support minimum.


def decode(obs):
    data = base64.b64decode(obs['image'], validate=True)
    if hashlib.sha256(data).hexdigest() != obs['sha256']:
        raise ValueError('image sha256 mismatch')
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape != (480, 640, 3):
        raise ValueError('invalid own image')
    return frame


def cyan(frame):
    return colors._mask(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), colors.OWN_ZONE_CYAN_HSV) > 0


@lru_cache(maxsize=1)
def lens_valid():
    """v3 retains the archived raw K/D remap, including its internal black rim."""
    x, y = camera.raw_fisheye_remap(640, 480)
    valid = (x >= 0) & (x <= 639) & (y >= 0) & (y <= 479)
    valid.setflags(write=False)
    return valid


class SiteMemory:
    def __init__(self, obs, bbox, center, servo):
        self.before = decode(obs)
        x, y, w, h = map(int, bbox)
        if min(w, h) <= 0 or x < 0 or y < 0 or x+w >= 640 or y+h >= 480:
            raise ValueError('pickup reference must be an unclipped cyan fit')
        self.mask = cyan(self.before)
        self.roi = np.zeros((480, 640), np.uint8)
        # A surrounding half-box margin includes small slips near the old site.
        x0, y0, x1, y1 = x-w//2, y-h//2, x+w+w//2, y+h+h//2
        if x0 < 1 or y0 < 1 or x1 >= 639 or y1 >= 479:
            raise ValueError('pickup-site comparison region is clipped')
        self.roi[y0:y1, x0:x1] = 1
        if not lens_valid()[self.roi > 0].all():
            raise ValueError('pickup-site region crosses the valid lens boundary')
        self.area = int(self.mask[y:y+h, x:x+w].sum())
        if self.area < CONFIG['min_cyan_px']:
            raise ValueError('pickup reference has insufficient cyan')
        floor = (self.roi > 0) & ~cv2.dilate(self.mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        if floor.sum() < CONFIG['min_cyan_px']:
            raise ValueError('pickup reference has no visible surrounding floor')
        pixels = self.before[floor].astype(float)
        self.floor_color = np.median(pixels, axis=0)
        self.floor_tolerance = max(CONFIG['floor_color_tolerance'],
            3*float(np.median(np.linalg.norm(pixels-self.floor_color, axis=1))))
        self.servo = {k: servo[k] for k in (3, 4, 5, 6)}
        self.record = {'profile': PROFILE, 'before_sha256': obs['sha256'],
            'before_frame_id': obs['frame_id'], 'before_t': obs['sim_time'],
            'before_cyan_area_px': self.area, 'pixel_bbox': list(bbox),
            'before_full_cyan_area_px': int(self.mask.sum()),
            'center_base_m_from_own_rgb': list(center), 'view_commands': dict(self.servo),
            'floor_bgr': self.floor_color.tolist(), 'floor_tolerance': self.floor_tolerance,
            'cyan_hsv_median': np.median(cv2.cvtColor(self.before, cv2.COLOR_BGR2HSV)[self.mask & (self.roi > 0)], axis=0).tolist()}

    def compare(self, obs):
        row = {**self.record, 'after_sha256': obs['sha256'], 'after_frame_id': obs['frame_id'],
               'after_t': obs['sim_time'], 'decision': 'unknown', 'physical_success': None}
        after = decode(obs)
        mask_after = cyan(after)
        row['after_full_cyan_area_px'] = int(mask_after.sum())
        gray0 = cv2.cvtColor(self.before, cv2.COLOR_BGR2GRAY)
        gray1 = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)
        excluded = cv2.dilate(((self.roi > 0) | self.mask | mask_after).astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
        background = ~excluded & lens_valid() & (gray0 > 30) & (gray1 > 30)
        background[:12] = background[-12:] = False
        background[:, :12] = background[:, -12:] = False
        if background.sum() < 800 or np.std(gray0[background]) < CONFIG['min_background_std']:
            return {**row, 'reason': 'background_not_registerable'}
        try:
            score, warp = cv2.findTransformECC(gray0, gray1, np.eye(2, 3, dtype=np.float32),
                cv2.MOTION_TRANSLATION, (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-5),
                background.astype(np.uint8)*255, 5)
        except cv2.error:
            return {**row, 'reason': 'registration_failed'}
        row.update(registration_correlation=float(score), translation_px=warp[:, 2].tolist())
        if score < CONFIG['registration_correlation'] or np.max(np.abs(warp[:, 2])) > CONFIG['max_shift_px']:
            return {**row, 'reason': 'view_changed'}
        aligned = cv2.warpAffine(after, warp, (640, 480), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
        valid = cv2.warpAffine(lens_valid().astype(np.uint8), warp, (640, 480),
                              flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP) > 0
        region = self.roi > 0
        if not valid[region].all():
            return {**row, 'reason': 'site_out_of_view'}
        cm = cyan(aligned)
        n = int(cm[region].sum())
        row.update(after_cyan_area_px=n, area_ratio=n/self.area,
                   roi_pixels=int(region.sum()), before_after_changed_pixels=int(
                       (np.max(np.abs(aligned.astype(float)-self.before), axis=2)[region] > self.floor_tolerance).sum()))
        # Border-connected cyan may be the wrist-held block, not the old site.
        count, labels, stats, _ = cv2.connectedComponentsWithStats(cm.astype(np.uint8))
        lens_edge = ~cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        for i in range(1, count):
            x, y, w, h, _ = stats[i]
            clipped = (x == 0 or y == 0 or x+w >= 640 or y+h >= 480 or np.any((labels == i) & lens_edge))
            if clipped and np.any((labels == i) & region):
                return {**row, 'reason': 'held_or_clipped_cyan_overlaps_site'}
        if n >= CONFIG['min_cyan_px'] and CONFIG['min_area_ratio'] <= n/self.area <= CONFIG['max_area_ratio']:
            return {**row, 'decision': 'present', 'reason': 'cyan_remains_at_pickup_site'}
        floor_like = np.linalg.norm(aligned.astype(float)-self.floor_color, axis=2) <= self.floor_tolerance
        row['clear_floor_fraction'] = float(floor_like[region].mean())
        if n == 0 and row['clear_floor_fraction'] >= CONFIG['clear_fraction']:
            return {**row, 'decision': 'absent', 'reason': 'visible_floor_at_old_cyan_site'}
        return {**row, 'reason': 'site_occluded_or_ambiguous'}
