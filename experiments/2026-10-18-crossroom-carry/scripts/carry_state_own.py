"""Own-RGB + own-command cargo held monitor for cross-room Stage B.

The monitor uses only the robot's own raw fisheye RGB and its own issued
gripper command history.  It never receives a cargo world pose, contact flag,
simulator state or ground truth; the GT comparison lives in the evaluation
and analysis cells only.

State machine (thresholds frozen by the Stage B preflight, defaults below):

* ``held``      -- a red box component with at least ``HELD_MIN_PIXELS`` pixels
                   is visible in the near-field lower-centre ROI while the
                   issued gripper pulse is in the closed range.
* ``uncertain`` -- a smaller red component (>= ``LOST_MIN_PIXELS``) or a lost
                   component less than ``LOST_AFTER_S`` after the last held
                   tick.
* ``lost``      -- no red component for more than ``LOST_AFTER_S`` while the
                   gripper was commanded closed.

The detector is default-off: the runner only instantiates it for
``stage='B_loaded'`` with the ``crossroom_carry_scene_v1`` toggle on.

``full_frame_red_component`` is the same colour gate over the whole frame and
supplies the cargo band top for ``crossroom_loaded_wallline_v1`` (default off,
own RGB only; the near-field ROI would clip the measured rows 400-463 band).
"""
from __future__ import annotations

import cv2
import numpy as np

# Frozen Stage B preflight thresholds (fractions are image-relative).
ROI_ROWS = (0.40, 0.95)   # lower-centre near-field window
ROI_COLS = (0.18, 0.82)
RED_HUE_RANGES = ((0, 12), (168, 180))
SAT_MIN = 110
VAL_MIN = 35
HELD_MIN_PIXELS = 90
LOST_MIN_PIXELS = 25
GRIPPER_CLOSED_MAX_PWM = 1600   # closed command is <= this pulse (1500 nominal)
LOST_AFTER_S = 1.5


def red_mask(bgr):
    """Frozen own-RGB red gate (hue/sat/val), returned as a uint8 mask."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = ((hue >= RED_HUE_RANGES[0][0]) & (hue <= RED_HUE_RANGES[0][1])
            | (hue >= RED_HUE_RANGES[1][0]) & (hue <= RED_HUE_RANGES[1][1]))
    return (mask & (sat >= SAT_MIN) & (val >= VAL_MIN)).astype(np.uint8)


def _largest_component(mask, offset=(0, 0)):
    """Largest connected component of a uint8 mask -> dict (or ``None``)."""
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return None
    areas = stats[1:, cv2.CC_STAT_AREA]
    k = int(np.argmax(areas)) + 1
    x, y, w, h = (int(v) for v in stats[k, :4])
    return dict(largest=int(areas[k - 1]),
                bbox_xywh=[x + int(offset[1]), y + int(offset[0]), w, h],
                band_top_row=int(y + int(offset[0])),
                centroid_xy=[float(cents[k][0]) + offset[1],
                             float(cents[k][1]) + offset[0]])


def red_component(bgr):
    """Largest red component inside the near-field ROI (own RGB only)."""
    h, w = bgr.shape[:2]
    r0, r1 = int(ROI_ROWS[0] * h), int(ROI_ROWS[1] * h)
    c0, c1 = int(ROI_COLS[0] * w), int(ROI_COLS[1] * w)
    roi = bgr[r0:r1, c0:c1]
    mask = red_mask(roi)
    comp = _largest_component(mask, offset=(r0, c0))
    if comp is None:
        return dict(pixels=0, largest=0, centroid_xy=None, bbox_xywh=None,
                    band_top_row=None, roi=[r0, r1, c0, c1])
    return dict(pixels=int(mask.sum()), largest=comp['largest'],
                centroid_xy=comp['centroid_xy'],
                bbox_xywh=comp['bbox_xywh'],
                band_top_row=comp['band_top_row'], roi=[r0, r1, c0, c1])


def full_frame_red_component(bgr):
    """Largest red component on the whole frame -> the cargo's top row.

    ``crossroom_loaded_wallline_v1`` uses this top row as the cargo band top
    (own RGB only).  The Stage B verifier measured the box at rows 400-463 on
    16/16 start frames; the near-field ROI of :func:`red_component` would clip
    that band, so the band top is read on the full frame.
    """
    h, w = bgr.shape[:2]
    mask = red_mask(bgr)
    comp = _largest_component(mask)
    if comp is None:
        return dict(pixels=0, largest=0, bbox_xywh=None, band_top_row=None,
                    centroid_xy=None, frame=[h, w])
    return dict(pixels=int(mask.sum()), largest=comp['largest'],
                bbox_xywh=comp['bbox_xywh'],
                band_top_row=comp['band_top_row'],
                centroid_xy=comp['centroid_xy'], frame=[h, w])


class CarryStateOwn:
    """Own-evidence carry state; updated once per control tick."""

    def __init__(self, held_min_pixels=HELD_MIN_PIXELS,
                 lost_min_pixels=LOST_MIN_PIXELS,
                 gripper_closed_max_pwm=GRIPPER_CLOSED_MAX_PWM,
                 lost_after_s=LOST_AFTER_S):
        self.held_min = held_min_pixels
        self.lost_min = lost_min_pixels
        self.closed_max = gripper_closed_max_pwm
        self.lost_after = lost_after_s
        self.state = 'uncertain'
        self.last_held_t = None
        self.events = []

    def update(self, t, bgr, gripper_pwm):
        comp = red_component(bgr)
        closed = int(gripper_pwm) <= self.closed_max
        if closed and comp['largest'] >= self.held_min:
            state = 'held'
            self.last_held_t = t
        elif comp['largest'] >= self.lost_min:
            state = 'uncertain'
        elif (self.last_held_t is not None
              and t - self.last_held_t > self.lost_after) or (not closed and comp['largest'] == 0):
            state = 'lost'
        else:
            state = 'uncertain'
        if state != self.state:
            self.events.append(dict(t=t, state=state, previous=self.state,
                                    largest=comp['largest'],
                                    pixels=comp['pixels']))
            self.state = state
        return dict(state=state, largest=comp['largest'], pixels=comp['pixels'],
                    gripper_closed=closed,
                    centroid_xy=comp['centroid_xy'], roi=comp['roi'])

    def summary(self):
        return dict(final_state=self.state, last_held_t=self.last_held_t,
                    events=self.events[-20:])


def thresholds():
    return dict(held_min_pixels=HELD_MIN_PIXELS,
                lost_min_pixels=LOST_MIN_PIXELS,
                gripper_closed_max_pwm=GRIPPER_CLOSED_MAX_PWM,
                lost_after_s=LOST_AFTER_S, roi_rows=list(ROI_ROWS),
                roi_cols=list(ROI_COLS), sat_min=SAT_MIN, val_min=VAL_MIN,
                red_hue_ranges=[list(r) for r in RED_HUE_RANGES])
