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
   still lag the issued PWM is not a grasp-pose view;
4. identity (adversarial review, 2026-09-29): v1 only used a partial patch that
   its lime shape classifier called a clipped BEAM. Colour alone is not that
   identity: a narrow yellow floor mark on dark floor inside the tracked
   footprint passed the footprint and grip-view checks and closed the jaws
   with no beam. The grasp-range patch must therefore also show the catalogue
   CROSS-SECTION on the tracked axis: beyond the band centre, the 2-98 %
   across-axis span of the beam-colour points is at least
   ``MIN_WIDTH_FRACTION`` of ``BEAM_WIDTH_M`` (the footprint test above
   already bounds it from above). Recorded grasp-pose views: 0.032-0.051 m on
   all 155 boundary frames. A beam-width yellow object lying exactly on the
   tracked axis is not excluded; that residual is stated, not hidden.

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
BEAM_WIDTH_M = .04               # catalogue cross-section (RestingBeamTrack footprint |n| <= .02)
MIN_WIDTH_FRACTION = .7          # 0.028 m; recorded grasp-pose spans 0.032-0.051 m (155 frames)


def grasp_range_points(image, servo):
    """Beam-colour pixels (grasp-range model) projected onto the beam top plane."""
    frame = v1.decode(image)
    origin, rays, xs, ys, valid = base_rays(servo, v1.RAY_STEP)
    colour = v2.beam_colour_mask(frame)[ys.astype(int), xs.astype(int)]
    hit = valid & colour & (rays[:, 2] < -1e-6)
    distance = (v1.BEAM_TOP_Z_M - origin[2]) / rays[hit, 2]
    pts = (origin + distance[:, None] * rays[hit])[:, :2]
    return pts[(distance > 0) & (np.linalg.norm(pts, axis=1) < 2.5)]


def cross_section(points, beam):
    """2-98 % across-axis span of the patch beyond the tracked grip (None: too few points)."""
    u = np.array([np.cos(beam['axis_heading_rad']), np.sin(beam['axis_heading_rad'])])
    rel = np.asarray(points) - np.asarray(beam['grip_base_m'])
    far = rel @ u > 0.
    if far.sum() < v1.MIN_POINTS:
        return None
    lo, hi = np.percentile(rel[far] @ np.array([-u[1], u[0]]), [2, 98])
    return float(hi - lo)


def standoff_estimate_v6c(obs, servo):
    return standoff_estimate(obs, servo, points=grasp_range_points, min_strip_support=MIN_STRIP_SUPPORT)


class GraspRangeBeamTrack(RestingBeamTrack):
    """Same segment-local resting track; grasp-range colour evidence only."""

    def _standoff(self, obs, servo):
        return standoff_estimate_v6c(obs, servo)

    _patch = None

    def _partial_points(self, obs, servo):
        # No v1 lime 'visible' precondition: at the grasp pose the lime model
        # sees nothing although the band and beam top fill the view. The
        # footprint support test in ``estimate`` is unchanged; the patch never
        # renews pose, age or sigma. Identity is checked in ``estimate``.
        self._patch = grasp_range_points(obs['image'], servo)
        return self._patch, 'GRASP_RANGE_BEAM_COLOUR'

    def estimate(self, now, obs, servo, segment):
        self._patch = None
        got = super().estimate(now, obs, servo, segment)
        patch, self._patch = self._patch, None
        if got is None:
            return None
        span = cross_section(patch, self.beam)
        if span is None or span < MIN_WIDTH_FRACTION * BEAM_WIDTH_M:
            return None                  # colour without the beam cross-section is not beam evidence
        return {**got, 'partial_cross_section_m': span,
                'partial_identity': 'catalogue cross-section on the tracked axis'}
