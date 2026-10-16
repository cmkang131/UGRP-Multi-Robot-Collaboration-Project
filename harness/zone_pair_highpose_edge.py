"""v98: robust line fit for the carried beam's lower edge in the HIGH view (own RGB only).

Problem (probe d5ca2ec3 ``align_to_carry``, PR #363): at HIGH both robots had the beam edge in 90 of 90 sampled
columns, but ``harness.own_beam_edge.edge_line`` returned None on every HIGH frame, so ``wait_carry`` timed out
(``HIGH_CARRY_EDGE_REFERENCE_TIMEOUT``). The shared function fits an ordinary least-squares line to ALL columns before
it drops columns more than 4 px away. In the HIGH view the upper beam band's lower edge sits near the 40 px minimum
run length, so a few right-end columns (5 for r1, 10 for r2) read that edge (rows 79-80) instead of the lower band's
edge (rows 169-176). These few high-leverage points tilt the least-squares line to a slope of -0.078 (r1) / -0.157 (r2),
only 25 / 13 columns stay inside the band, and the 0.6 x n rule rejects the frame. Without the 5 / 10 columns the
remaining 85 / 80 columns fit a line with RMS 0.5 px.

Rule (the shared acceptance is not changed, only the line that the band is centred on):

1. ``harness.own_beam_edge.edge_line`` runs first. If it accepts, its answer is returned unchanged (bit for bit).
2. Only when it returns None, the same column samples (same HSV mask, same rows/columns, same 40 px first run) are
   re-fit with a deterministic maximum-consensus line:
   * hypotheses: every line through two sampled columns (n (n - 1) / 2, at most 4005 for the 90 columns);
   * score: number of columns within ``INLIER_TOL_PX`` (the shared 4 px band); ties go to the smaller sum of squared
     residuals of its inliers, then to the first pair in (i, j) order; no random numbers;
   * local optimisation: the returned line is the least-squares line through that consensus set.
3. The shared acceptance then runs on that line exactly as the shared function runs it on the OLS line: columns within
   ``INLIER_TOL_PX`` of it, at least ``MIN_COLUMNS``, ``MIN_INLIER_FRAC`` x 90 x 0.5 and ``MIN_INLIER_FRAC`` x n inliers,
   one refit on the inliers, RMS <= ``MAX_RMS_PX``. The constants are read from the shared module. There is no slope
   limit in the shared acceptance and none is added.

A frame the shared function accepts therefore never changes. A frame it rejects becomes accepted only when at least
60 % of the columns lie within the band of the consensus line, which is the shared rule's own requirement.

Only the own RGB frame is read: no ground truth, no partner data, no map. The ``EdgeLine`` result is a plain
``(slope, y at column 320, inlier columns)`` tuple with a ``fit`` label ('shared_ols' or 'consensus') for the logs.

Survey (full note in the PR): RANSAC (Fischler and Bolles 1981) with exhaustive, deterministic hypotheses and a
local-optimisation step (Chum, Matas and Kittler 2003); OpenCV ``cv2.fitLine`` with DIST_HUBER / DIST_FAIR /
DIST_WELSCH (M-estimators). The M-estimators also fit the 303 recorded frames per robot, but break down when 26 or more of
90 columns are one-sided outliers (offline ladder in the PR), below the 36 columns the acceptance rule tolerates, so the
consensus line, which optimises the acceptance rule's own criterion, is used.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from harness import own_beam_edge as be
from harness.own_beam_edge import BeamEdgeTracker
from harness.zone_final_pair_binding import bind

# v98 finding (outputs/v98-znear-live-check-20261004): in the HIGH carry view the camera sits ~13 mm above the beam's top
# face, 23 mm behind its near end, so the 'lower band edge' is the renderer's near-clip-plane trace on the top face
# (znear 0.0020 x extent 11.11 m = 22.2 mm), not a physical edge. It tracks the near-plane distance, not the beam yaw
# (d slope / d relative yaw ~0.013, the tracker assumes 1.1). False: the tracker is never fed in the HIGH view, so it
# never applies a yaw increment and never reports itself available; carry yaw then relies on own command sync + DR.
HIGH_EDGE_INFORMATIVE = False

FIT_SHARED = 'shared_ols'
FIT_CONSENSUS = 'consensus'
FIT_ROWS_MAX = 15000                # per tracker, log only; covers a 900 SIM s case cap at 10 frames/s with margin


class EdgeLine(tuple):
    """``(slope, y at column 320, inlier columns)`` plus the fit that produced it."""

    def __new__(cls, values, fit):
        self = super().__new__(cls, values)
        self.fit = fit
        return self


def edge_columns(rgb):
    """``(xs, ys)`` as the shared ``edge_line`` reads them, or None when fewer than ``MIN_COLUMNS`` columns are seen."""
    img = rgb if isinstance(rgb, Image.Image) else Image.fromarray(np.asarray(rgb, dtype=np.uint8))
    hsv = np.asarray(img.convert('HSV')).astype(int)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = (h > be.HUE_LO) & (h < be.HUE_HI) & (s > be.SAT_MIN) & (v > be.VAL_MIN)
    xs, ys = [], []
    for c in be.COLUMNS:
        end = be._first_run_end(mask[be.ROW_LO:be.ROW_HI, c])
        if end is not None:
            xs.append(c)
            ys.append(end + be.ROW_LO)
    if len(xs) < be.MIN_COLUMNS:
        return None
    return np.array(xs, float), np.array(ys, float)


def accept(xs, ys, line):
    """The shared acceptance applied to an initial ``line`` (polyfit coefficients): ``(slope, y320, n)`` or None."""
    keep = np.abs(ys - np.polyval(line, xs)) <= be.INLIER_TOL_PX
    count = int(keep.sum())
    if count < be.MIN_COLUMNS or count < be.MIN_INLIER_FRAC*len(be.COLUMNS)*.5 or count < be.MIN_INLIER_FRAC*len(xs):
        return None
    a = np.polyfit(xs[keep], ys[keep], 1)
    if float(np.sqrt(np.mean((ys[keep] - np.polyval(a, xs[keep]))**2))) > be.MAX_RMS_PX:
        return None
    return float(a[0]), float(a[1] + a[0]*320), count


def consensus_line(xs, ys):
    """Deterministic maximum-consensus line (polyfit coefficients) over all two-column hypotheses."""
    first, second = np.triu_indices(len(xs), 1)
    run = xs[second] - xs[first]
    usable = run != 0.
    first, second, run = first[usable], second[usable], run[usable]
    slope = (ys[second] - ys[first])/run
    offset = ys[first] - slope*xs[first]
    residual = np.abs(ys[None, :] - (slope[:, None]*xs[None, :] + offset[:, None]))
    inside = residual <= be.INLIER_TOL_PX
    count = inside.sum(axis=1)
    tied = np.flatnonzero(count == count.max())
    squared = (np.where(inside[tied], residual[tied], 0.)**2).sum(axis=1)
    best = tied[int(np.argmin(squared))]            # np.argmin returns the first minimum: ties end in (i, j) order
    return np.polyfit(xs[inside[best]], ys[inside[best]], 1)


def fit_consensus(xs, ys):
    """Consensus fit of already read columns under the shared acceptance: ``(slope, y320, n)`` or None."""
    return accept(xs, ys, consensus_line(xs, ys))


def robust_edge_line(rgb):
    """Drop-in for ``harness.own_beam_edge.edge_line``: same result when that accepts, consensus fit when it does not."""
    shared = be.edge_line(rgb)
    if shared is not None:
        return EdgeLine(shared, FIT_SHARED)
    columns = edge_columns(rgb)
    if columns is None:
        return None
    line = fit_consensus(*columns)
    return None if line is None else EdgeLine(line, FIT_CONSENSUS)


class HighBeamEdgeTracker(BeamEdgeTracker):
    """The shared tracker (settle, reference, smoothing, step limit, availability) with ``robust_edge_line``.

    ``frozen_observe`` is the frozen shared code object re-run with only ``edge_line`` replaced; nothing in
    ``harness.own_beam_edge`` is patched or edited. ``observe`` runs the same code object per instance with a
    recording ``edge_line`` (same answers, plus fit rows in ``stats``)."""

    frozen_observe = bind(BeamEdgeTracker.observe, edge_line=robust_edge_line)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats.update({'fit_shared_ols': 0, 'fit_consensus': 0, 'fit_rows': []})
        # Logging only (coordinator ruling 3, 2026-10-04): the same frozen code with an edge_line that records each
        # fitted frame's [t, fit, y at column 320 px, slope, inlier columns]. A switch of the winning edge between the
        # upper and the lower beam band during a hold shows as a jump of y320 (~90 px). Answers are unchanged.
        self._frame_t = None
        self._logged_observe = bind(BeamEdgeTracker.observe, edge_line=self._logged_edge_line).__get__(self)

    def observe(self, now, rgb, servo, loaded):
        self._frame_t = float(now)
        return self._logged_observe(now, rgb, servo, loaded)

    def _logged_edge_line(self, rgb):
        line = robust_edge_line(rgb)
        if line is not None:
            self.stats['fit_'+line.fit] += 1
            if len(self.stats['fit_rows']) < FIT_ROWS_MAX:
                self.stats['fit_rows'].append([self._frame_t, line.fit, round(line[1], 3), round(line[0], 6), line[2]])
        return line
