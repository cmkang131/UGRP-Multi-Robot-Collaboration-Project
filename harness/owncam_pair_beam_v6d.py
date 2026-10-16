"""v6d: beam perception with a wider hue range for the close r1 views (p45 / inspect).

Root cause (2026-09-29 stage-2 replay of the PR #263 ``b-v6c`` probe, GT yaw failures of
along+/same r1, yaw-/opp r1, corner++/opp r1 and E2E v6-s912-v5h): in r1's inspect / p45 views the
beam top renders YELLOW (hue 25-36) and lies outside the v1 lime mask (hue 36-54, S >= 60, V >= 40).
Only the end and side faces are masked, so the PCA axis is biased or even perpendicular (inspect
default error about 1.5 rad) and the align controller declared "aligned" at a true yaw of
0.07-0.115 rad. ``harness.owncam_pair_beam_v2.BEAM_HUE = (25, 54)`` (dev 613) already documents that the
beam top renders yellow at grasp range; v2 uses it only for the grip/hold views, not for the axis.

``harness.owncam_pair_beam`` (v1) and ``harness.owncam_pair_beam_v2`` are frozen, hash-checked M2 imports
without a hue parameter, and read the image only through their lime mask (v1: ``LIME_LO/LIME_HI``) and
their dark-band mask. This module therefore recolours exactly the pixels the wider hue bound adds to a
COPY of the frame and calls the unmodified v2 on it:

* the added pixels become lime (HSV 45, 255, 255), so the v1 end/axis estimate and v2's "lime beyond the
  band" test read the wider mask; nothing in v1 or v2 changes;
* pixels of the dark grip-band class (V <= 60 and S < 90) are never recoloured, so v2's band mask, which
  is the grip measurement, is bit-identical to the one on the original frame;
* ``hue_lo=None`` returns the frame itself, i.e. exactly v2.

The controller uses ``hue_lo`` only in the p45 and inspect postures; the search posture keeps the v1
range because the wide range hurts r2's search yaw (replay: rms 0.014 -> 0.030 rad).
"""
from __future__ import annotations

from typing import Any, Mapping

import cv2
import numpy as np

from harness import owncam_pair_beam as v1
from harness import owncam_pair_beam_v2 as v2

WIDE_LIME_BGR = (0, 255, 128)   # HSV (45, 255, 255): inside the v1 lime range, so v1 and v2 read it as lime


def lime_mask(frame: np.ndarray, hue_lo: int | None = None) -> np.ndarray:
    """The v1 lime mask; ``hue_lo`` lowers its hue bound, ``None`` is v1 exactly."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lo = v1.LIME_LO if hue_lo is None else (int(hue_lo),) + tuple(v1.LIME_LO[1:])
    return cv2.inRange(hsv, np.asarray(lo), np.asarray(v1.LIME_HI)) > 0


def dark_band_mask(frame: np.ndarray) -> np.ndarray:
    """The pixel class v2 reads as the black grip band (must stay untouched)."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return (hsv[..., 2] <= v2.BAND_V_MAX) & (hsv[..., 1] < v2.BAND_S_MAX)


def widen_lime(frame: np.ndarray, hue_lo: int | None) -> np.ndarray:
    """A copy of ``frame`` in which the non-band pixels that the wider hue bound adds are lime."""
    if hue_lo is None:
        return frame
    added = lime_mask(frame, hue_lo) & ~lime_mask(frame) & ~dark_band_mask(frame)
    out = frame.copy()
    out[added] = WIDE_LIME_BGR
    return out


def observe_beam(image, pose: Mapping[int | str, int | float], hue_lo: int | None = None) -> dict[str, Any]:
    """``v2.observe_beam`` on the widened frame (its result dict is returned unchanged)."""
    return v2.observe_beam(widen_lime(v1.decode(image), hue_lo), pose)
