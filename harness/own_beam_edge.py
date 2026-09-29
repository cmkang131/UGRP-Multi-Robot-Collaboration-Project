"""v6e: the robot-to-beam relative yaw from the slope of the carried beam's lower edge in the robot's OWN wrist RGB.

Opt-in (``PairPolicy.carry_beam_edge``); with the flag off nothing here is reached.

Why. While two robots carry the beam open loop the PF yaw is pure dead reckoning. Recorded cal-cohort carry cases
(experiments/2026-09-29-pair-v6e-carry, section "yaw 방향 분석") show that the wrist camera sees the beam as a band at
the top of the image and that the slope of that band's lower edge changes with the robot-minus-beam relative yaw
(slope change = 0.96 x relative yaw change over 200 case-robots, corr 0.994, residual sd 1.9 mrad over a leg,
no-motion noise sd 0.3-0.8 mrad). The common-mode rotation of the beam itself is NOT visible in this view.

Input boundary. Only the robot's own RGB frame, its own issued servo state and its own load state (grip closed on
the beam, from its own commands) are used. No ground truth, no partner data, no ultrasonic reading.

Measurement. Per accepted frame the lower boundary of the first hue-mask run (yellow-green beam faces, hue
25-90 on the PIL 0-255 scale) is read in columns 140..500 (step 4), rows 40..300, and a line is fitted (>= 20 columns).
The tracker holds a reference slope (the mean of the first ``ref_n`` samples after the arm has been still for
``settle_s`` and the load is held) and reports, at each accepted frame, the INCREMENT of the smoothed
(median of the last ``smooth_n`` samples) cumulative relative-yaw change ``(slope - slope_ref) / ratio``. Increments
telescope, so the accumulated shift equals one smoothed measurement, never a random walk of frame noise.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np
from PIL import Image

# Beam-band mask (PIL HSV, 0-255 scale). Hue 25-90 covers the yellow-green faces under the lighting seen in the carry.
HUE_LO, HUE_HI, SAT_MIN, VAL_MIN = 25, 90, 100, 60
COLUMNS = np.arange(140, 500, 4)
ROW_LO, ROW_HI = 40, 300
MIN_RUN_PX = 20
MIN_COLUMNS = 20
# Arm/wrist servos (not the gripper, servo 1) fix the camera-to-beam geometry; any change restarts the reference.
VIEW_SERVOS = (2, 3, 4, 5, 6)


def edge_line(rgb):
    """(slope, y at image centre column 320, n columns) of the lower edge of the beam band, or None.

    ``rgb`` is the own camera frame as an ``(H, W, 3)`` uint8 array (or a PIL image).
    """
    img = rgb if isinstance(rgb, Image.Image) else Image.fromarray(np.asarray(rgb, dtype=np.uint8))
    hsv = np.asarray(img.convert('HSV')).astype(int)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = (h > HUE_LO) & (h < HUE_HI) & (s > SAT_MIN) & (v > VAL_MIN)
    xs, ys = [], []
    for c in COLUMNS:
        col = mask[ROW_LO:ROW_HI, c]
        idx = np.flatnonzero(col)
        if len(idx) > MIN_RUN_PX:
            end = idx[0]                                # lower boundary of the first (top) run
            while end + 1 < len(col) and col[end + 1]:
                end += 1
            xs.append(c)
            ys.append(end + ROW_LO)
    if len(xs) < MIN_COLUMNS:
        return None
    a = np.polyfit(xs, ys, 1)
    return float(a[0]), float(a[1] + a[0]*320), len(xs)


class BeamEdgeTracker:
    """Cumulative robot-minus-beam relative-yaw change from the beam edge slope, as increments for the PF."""

    def __init__(self, ratio, *, settle_s=3., ref_n=2, smooth_n=3, min_dt_s=.5, step_limit_rad=.03, max_rejects=5):
        if not (0. < ratio < 3.):
            raise ValueError('slope-to-yaw ratio out of range')
        self.ratio, self.settle_s, self.ref_n, self.smooth_n = float(ratio), float(settle_s), int(ref_n), int(smooth_n)
        self.min_dt_s, self.step_limit_rad, self.max_rejects = float(min_dt_s), float(step_limit_rad), int(max_rejects)
        self.total_rad = 0.          # accumulated shift handed to the PF (sum of the increments)
        self.stats = {'frames': 0, 'no_edge': 0, 'applied': 0, 'rejected': 0, 'resets': 0}
        self._reset()

    def _reset(self):
        self._sig = None
        self._still_since = None
        self._ref = []
        self._ref_slope = None
        self._recent = deque(maxlen=self.smooth_n)
        self._applied = 0.
        self._rejects = 0
        self._last_t = None

    def _restart(self):
        self.stats['resets'] += 1
        self._reset()

    def observe(self, now, rgb, servo, loaded):
        """One own frame. Returns the increment [rad] to add to every particle's yaw, or None."""
        sig = tuple(int(servo.get(k, -1)) for k in VIEW_SERVOS)
        if not loaded:
            if self._sig is not None or self._ref:
                self._restart()
            return None
        if sig != self._sig:
            if self._sig is not None:
                self.stats['resets'] += 1
            self._reset()
            self._sig, self._still_since = sig, float(now)
        if now < self._still_since + self.settle_s:
            return None
        if self._last_t is not None and now - self._last_t < self.min_dt_s - 1e-9:
            return None
        self._last_t = float(now)
        self.stats['frames'] += 1
        el = edge_line(rgb)
        if el is None:
            self.stats['no_edge'] += 1
            return None
        slope = el[0]
        if self._ref_slope is None:
            self._ref.append(slope)
            if len(self._ref) >= self.ref_n:
                self._ref_slope = float(np.mean(self._ref))
                self._recent.extend(self._ref[-self.smooth_n:])
            return None
        self._recent.append(slope)
        cum = (float(np.median(self._recent)) - self._ref_slope)/self.ratio
        step = cum - self._applied
        if abs(step) > self.step_limit_rad:
            self.stats['rejected'] += 1
            self._rejects += 1
            if self._rejects >= self.max_rejects:
                self._restart()
            return None
        self._rejects = 0
        self._applied = cum
        self.total_rad += step
        self.stats['applied'] += 1
        return step if step != 0. else None
