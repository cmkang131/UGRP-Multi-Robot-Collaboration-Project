"""v6c pre-grasp entry: one beam colour model for the grasp-range views.

Root cause (2026-09-28/29 stage probes, PR #260, align-tolerance boundary
set). The align stop accepts |ex| <= 12 mm, but the unchanged pre-grasp entry
passed only for ex = -8 ... -4 mm, and the robot that failed was always r1.
Replaying the recorded own frames (``experiments/2026-09-29-pair-v6c``):

* the standoff axis fit and the pre-close partial-view check projected ONLY
  v1 lime pixels (hue 36-54). At grasp range the beam top renders yellow
  (hue ~30), which ``owncam_pair_beam_v2`` already documents (dev 613) and
  handles for ``grip_view``/co-motion with ``beam_colour_mask`` (hue 25-54,
  S >= 100, V >= 120), but not here;
* at the lowered open-jaw pose the camera looks at the band with beam top on
  both sides: 14k-28k beam-colour points, yet < 60 lime points unless the
  darker near-end FACE happens to be in view (ex <= -4 mm). ex >= 0: no
  partial evidence -> ``BEAM_UNCERTAIN`` -> ``PREGRASP_NOT_READY``;
* at the standoff view with ex = -12 mm the lime pixels beyond the band were
  a few per strip while the end-face strip had ~1.4k; the two half-fits then
  disagreed by 0.068 rad (> 3 degrees) -> ``PREGRASP_BEAM_UNCERTAIN``.

v6c keeps every gate and threshold (3 degrees, 50 mm, >= 4 strips over
>= 60 mm, 95 % footprint support, MIN_POINTS) and changes only the evidence:

1. standoff edge pairs and the pre-close patch use the grasp-range beam
   colour; the vertical, darker end face (projected wrongly onto the top
   plane) drops out by its V < 120;
2. a 10 mm strip cut by the band/end boundary is only partly covered, so its
   midpoint is not a two-edge midpoint: strips below a quarter of the median
   strip support are dropped before the line fit;
3. the last descent pose settles (``FINAL_DESCENT_SETTLE_S``) before the first
   READY frame, as every other own look does; a frame taken while the joints
   still lag the issued PWM is not a grasp-pose view.

These are development bounds from the recorded boundary frames, not
calibrated accuracy.
"""
from __future__ import annotations

import numpy as np

from harness import owncam_pair_beam as v1
from harness import owncam_pair_beam_v2 as v2
from harness.owncam_view import base_rays
from harness.zone_pair_beam_track import RestingBeamTrack, standoff_estimate

MIN_STRIP_SUPPORT = .25          # of the median supported strip (partial strips at band/end cuts)
FINAL_DESCENT_SETTLE_S = .3      # = RecoveryLocalizer 'settled' after an own arm command


def grasp_range_points(image, servo):
    """Beam-colour pixels (grasp-range model) projected onto the beam top plane."""
    frame = v1.decode(image)
    origin, rays, xs, ys, valid = base_rays(servo, v1.RAY_STEP)
    colour = v2.beam_colour_mask(frame)[ys.astype(int), xs.astype(int)]
    hit = valid & colour & (rays[:, 2] < -1e-6)
    distance = (v1.BEAM_TOP_Z_M - origin[2]) / rays[hit, 2]
    pts = (origin + distance[:, None] * rays[hit])[:, :2]
    return pts[(distance > 0) & (np.linalg.norm(pts, axis=1) < 2.5)]


def standoff_estimate_v6c(obs, servo):
    return standoff_estimate(obs, servo, points=grasp_range_points, min_strip_support=MIN_STRIP_SUPPORT)


class GraspRangeBeamTrack(RestingBeamTrack):
    """Same segment-local resting track; grasp-range colour evidence only."""

    def _standoff(self, obs, servo):
        return standoff_estimate_v6c(obs, servo)

    def _partial_points(self, obs, servo):
        # No v1 lime 'visible' precondition: at the grasp pose the lime model
        # sees nothing although the band and beam top fill the view. The
        # footprint support test in ``estimate`` is unchanged; the patch never
        # renews pose, age or sigma.
        return grasp_range_points(obs['image'], servo), 'GRASP_RANGE_BEAM_COLOUR'
