"""seg5_v1: fixed colour-class front end for the own RGB frame (no learning, no teacher input).

Input : one own frame as uint8 RGB (3, 240, 320), exactly the array harness.grasp_act_data.image_array
        returns for a 640x480 student JPEG (the dataset stores the same array in images.npy), and the
        observation's object_kind, which must be 'red' or 'cyan' (the target kind of the episode).
Output: uint8 RGB (3, 240, 320) painted with flat classes:
          floor  (128,128,128)  default for everything not listed below
          wall   (  0,140,  0)  dark green wall paint, HSV hue 55..85
          target (255,  0,  0)  the box whose paint matches object_kind (red paint for red, blue for cyan)
          other  (  0,  0,255)  the other box paint (blue for red targets, red for cyan targets)
          body   (255,255,255)  own robot body, orange paint, hue 9..24
          dark   (  0,  0,  0)  pixels with V < 45 (outlines and dark parts), applied last
Only numpy is needed here; OpenCV is imported lazily inside segment(), so the option-off path never imports it.
Thresholds are those of the 2026-11-12 draft (OpenCV 8-bit HSV: H 0..179, S 0..255, V 0..255).
"""
from __future__ import annotations

import numpy as np

FRONTEND = 'seg5_v1'
TARGET_KINDS = ('red', 'cyan')
FLOOR = (128, 128, 128)
WALL = (0, 140, 0)
TARGET = (255, 0, 0)
OTHER = (0, 0, 255)
BODY = (255, 255, 255)
BLACK = (0, 0, 0)


def masks(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    red = ((h <= 8) | (h >= 172)) & (s > 150) & (v > 90)
    blue = (h >= 110) & (h <= 124) & (s > 170) & (v > 70)
    wall = (h >= 55) & (h <= 85) & (s > 110) & (v < 140)
    body = (h >= 9) & (h <= 24) & (s > 140) & (v > 120)
    dark = v < 45
    return red, blue, wall, body, dark


def segment(frame_chw, object_kind):
    """Return the colour-class image (3, 240, 320) uint8 RGB for one frame."""
    if object_kind not in TARGET_KINDS:
        raise ValueError('seg5_v1 needs object_kind red or cyan, got %r' % (object_kind,))
    frame = np.asarray(frame_chw)
    if frame.shape != (3, 240, 320) or frame.dtype != np.uint8:
        raise ValueError('seg5_v1 expects uint8 (3, 240, 320) RGB')
    import cv2  # lazy: only the seg option needs OpenCV
    hwc = np.ascontiguousarray(frame.transpose(1, 2, 0))
    hsv = cv2.cvtColor(hwc, cv2.COLOR_RGB2HSV)
    red, blue, wall, body, dark = masks(hsv)
    target, other = (red, blue) if object_kind == 'red' else (blue, red)
    out = np.empty_like(hwc)
    out[:] = FLOOR
    out[wall] = WALL
    out[other] = OTHER
    out[target] = TARGET
    out[body] = BODY
    out[dark] = BLACK
    return np.ascontiguousarray(out.transpose(2, 0, 1))


def apply_frontend(frame_chw, object_kind, frontend):
    """The single entry point used by both GraspActor.predict and GraspDataset.__getitem__."""
    if frontend is None:
        return frame_chw
    if frontend != FRONTEND:
        raise ValueError('unknown image frontend %r' % (frontend,))
    return segment(frame_chw, object_kind)
