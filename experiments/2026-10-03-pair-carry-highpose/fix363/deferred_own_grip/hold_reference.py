"""DEFERRED (not wired into any controller): own-HIGH-view grip check.

REVIEW_363 round 2 exploratory design, set aside by the user's first-E2E
scope decision (2026-10-03, "ㅇㅇ 그렇게 하자"): the v96 grip monitor is
log-only. Kept here only so own_grip_eval.py is reproducible for the deferred
own-grip-loss detection + partner signal work. Masked ZNCC on the gray image
plus ECC translation (cv2.findTransformECCWithMask) against one own reference.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

from harness.owncam_pair_beam import decode
from harness.owncam_pair_lift_v3 import beam_colour_mask_low
from harness.owncam_view import valid_pixel_mask

MIN_ZNCC = .80
MAX_SHIFT_PX = 4.
MIN_MASK_PX = 5000
DARK_V_MAX = 50
STABLE_S = 2.
STABLE_WAIT_MAX_S = 3.


def _valid():
    return cv2.resize(valid_pixel_mask(1).astype(np.uint8), (640, 480), interpolation=cv2.INTER_NEAREST) > 0


def beam_view_mask(frame):
    """Data-derived mask from the reference frame's own beam paint."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    m = (beam_colour_mask_low(frame) | (hsv[..., 2] < DARK_V_MAX)) & _valid()
    return cv2.dilate(m.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0


@dataclass(frozen=True)
class HoldReference:
    """One own reference image of the held beam at one pose."""
    gray: np.ndarray
    mask: np.ndarray
    source: str

    @classmethod
    def from_image(cls, image, source):
        frame = decode(image)
        if frame.shape != (480, 640, 3):
            raise ValueError('RGB_SHAPE')
        mask = beam_view_mask(frame)
        if int(mask.sum()) < MIN_MASK_PX:
            raise ValueError('HOLD_REFERENCE_SHOWS_NO_BEAM')
        return cls(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32), mask, source)

    def check(self, image):
        frame = decode(image)
        if frame.shape != (480, 640, 3):
            return {'ok': False, 'reason': 'RGB_SHAPE'}
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        x, y = self.gray[self.mask], g[self.mask]
        x, y = x-x.mean(), y-y.mean()
        zncc = float((x*y).sum()/math.sqrt(float((x*x).sum()*(y*y).sum())+1e-9))
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            _, warp = cv2.findTransformECCWithMask(self.gray, g, self.mask.astype(np.uint8),
                np.ones_like(self.mask, np.uint8), warp, cv2.MOTION_TRANSLATION,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5), 5)
            shift = float(math.hypot(warp[0, 2], warp[1, 2]))
        except cv2.error:
            shift = math.inf             # no convergence: not a held view
        ok = zncc >= MIN_ZNCC and shift <= MAX_SHIFT_PX
        return {'ok': bool(ok), 'reason': 'OWN_HOLD_VIEW_OK' if ok else 'OWN_HOLD_VIEW_MISMATCH',
                'zncc': zncc, 'ecc_shift_px': shift, 'reference': self.source}


