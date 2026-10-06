"""Height-free wall contact detection and column linking (offline probe, 2026-10-05).

Refs #216. Reuses the frozen VIS3 camera geometry (``markerless_probe.ColumnModel``,
``undistort``, ``column_positions``) but replaces the height-prior acceptance test.

The frozen detector (``markerless_probe.detect_boundaries``) predicts where the top
of a wall of a *given* height must appear and accepts a band only when the observed
band matches that predicted proportion. That makes it a filter for one wall height:
``wall_height_m`` is an input constant, and a wrong constant rejects real walls.

Nothing here uses a wall height to decide whether a contact exists. The only inputs
are the own undistorted image, the own commanded servo (for extrinsics), the own load
state and a fixed camera calibration. Wall height is an *output*: the top of the surface
is measured where it is visible and the height is inverted from it.

Cues used, all independent of wall height:
  floor contact   the candidate row back-projects onto the floor plane
  edge step       a real luminance/chroma step across the row, not a shading gradient
  band uniformity the surface just above the row is uniform
  surface extent  the contact persists across neighbouring image columns
  above horizon   the surface above the contact reaches past the horizon row
  self occlusion  rows at or below the carried beam / crate are rejected (``self_mask``)

The last cue is what separates a wall from the floor pattern, and it is the one this
module exists for. Measured on a recorded frame of ``zone_wide_door_geometry_v3``:
the floor is a checker texture whose dark square renders at luminance 92.8 against the
wall material's 97.4, so a wall standing on a dark square has essentially no luminance
edge at its base (contrast 0.4 over 8-bit levels), while checker-square boundaries put
a sharp 1.72:1 step across the whole image at plausible wall ranges. A luminance step
alone therefore finds floor texture and misses walls, and no colour threshold repairs
it either: the floor's rendered colour also shifts with view angle at grazing incidence.

The horizon cue uses only calibrated camera geometry. The ground plane converges to the
horizon row and can never appear above it, so any uniform surface that continues from a
candidate row up past the horizon is *not* floor -- it is a vertical surface, and the
candidate row is its contact with the ground. This asserts that the wall is taller than
what the camera can see at that range; it never compares against a wall height constant,
and it does not care whether that wall is 0.10 m or 1 m.

Ground truth is never read in this module. Scoring happens in ``wall_probe.py`` from
``eval_only/`` files and is kept separate from detection.
"""
from __future__ import annotations

import math
import sys
from collections.abc import Mapping

import numpy as np

HERE = __import__('pathlib').Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))          # self_mask is a sibling; no other self_mask.py exists

import markerless_probe as mp  # noqa: E402
import self_mask  # noqa: E402

WIDTH, HEIGHT, CY = mp.WIDTH, mp.HEIGHT, mp.CY

# No wall_height_m. The detector cannot be told a wall height.
PARAMS = {
    'columns': 96,
    'strip_half_px': 2,
    'min_range_m': .12,
    'max_range_m': 6.,
    'band_px': 10,            # surface window just above the contact row (fixed, not height-derived)
    'window_px': 3,            # floor window below the contact row
    'edge_margin_px': 1.5,
    'self_margin_px': 3,
    'chroma_weight': 1.,
    'min_contrast_below': 6., # 8-bit levels
    'max_band_std': 3.,
    'min_band_px': 3.,
    'min_edge_step': 0.,      # 0 disables; the contrast test is the primary gate
    'candidates': 3,
    'min_run_columns': 4,     # a surface spanning fewer adjacent columns is not a wall face
    'max_step_range_m': .45,  # adjacent-column continuity of the contact distance
    'max_step_bearing_rad': .09,
    'run_edge_tol': 10.,      # adjacent-row step (luminance+chroma) that splits one surface run
    'clamp_horizon': False,   # horizon above the image: require the run to reach row 0 instead of failing every row
    'run_step_window': 1,     # rows per side of the step that splits a surface run (1 = adjacent rows, legacy)
    # Horizon above the image (camera pitched down by more than the half field of view): no run can reach
    # it. Instead a uniform run must span at least this much floor-plane distance to not be floor: the
    # longest uniform patch a textured floor shows along one image column. The floor is a 0.571 m checker
    # (texrepeat 14 over 16 m, 2 cells per repeat; edges measured 0.54-0.59 m apart in recorded frames), so
    # a column can stay inside one cell for at most its diagonal, 0.571*sqrt(2) = 0.81 m (FLOOR_PATCH_DIAGONAL_M).
    # OPTION, OFF by default (0): the behaviour before #405. Switch on with ``floor_patch_max_m=FLOOR_PATCH_DIAGONAL_M``.
    'floor_patch_max_m': 0.,
}

# The value the floor-patch option is meant to take on the recorded 0.571 m checker floor.
FLOOR_PATCH_DIAGONAL_M = 0.81

# Options added in #405 and their OFF values (= the behaviour before #405). ``recorded_params`` leaves an option out
# of a run's recorded parameter dict while it is off, so a run with every option off records exactly what it
# recorded before.
OPTION_PARAMS_OFF = {'clamp_horizon': False, 'run_step_window': 1, 'floor_patch_max_m': 0.}


def recorded_params(params: Mapping | None = None) -> dict:
    p = {**PARAMS, **(params or {})}
    return {k: v for k, v in p.items() if not (k in OPTION_PARAMS_OFF and v == OPTION_PARAMS_OFF[k])}


class ColumnStrips:
    """Prefix sums of the column-averaged luminance and chroma strips of one frame."""

    def __init__(self, und_bgr, columns, half):
        img = und_bgr.astype(np.float32)
        lum = .114*img[..., 0] + .587*img[..., 1] + .299*img[..., 2]
        chroma = (img[..., 0] - img[..., 2])
        n_c = len(columns)
        lo = np.clip(columns - half, 0, WIDTH)
        hi = np.clip(columns + half + 1, 0, WIDTH)
        out = []
        for a in (lum, chroma):
            cs = np.concatenate([np.zeros((a.shape[0], 1), np.float64), np.cumsum(a, 1, dtype=np.float64)], 1)
            out.append((cs[:, hi] - cs[:, lo])/(hi - lo)[None, :])
        self.L, self.Cr = out
        pre = lambda a: np.vstack([np.zeros((1, n_c)), np.cumsum(a, 0)])
        self.SL, self.SL2 = pre(self.L), pre(self.L*self.L)
        self.SC, self.SC2 = pre(self.Cr), pre(self.Cr*self.Cr)
        self.n_c = n_c

    def window(self, r0, r1):
        r0 = np.clip(r0, 0, HEIGHT)
        r1 = np.clip(r1, 0, HEIGHT)
        n = np.maximum(r1 - r0, 1)
        ci = np.broadcast_to(np.arange(self.n_c), r0.shape)
        mL = (self.SL[r1, ci] - self.SL[r0, ci])/n
        mC = (self.SC[r1, ci] - self.SC[r0, ci])/n
        vL = np.maximum((self.SL2[r1, ci] - self.SL2[r0, ci])/n - mL*mL, 0.)
        vC = np.maximum((self.SC2[r1, ci] - self.SC2[r0, ci])/n - mC*mC, 0.)
        return mL, mC, vL + vC

    def value(self, j, v):
        return self.L[v, j], self.Cr[v, j]


def horizon_rows(cm):
    """Per-column image row of the horizon, the limit of the ground plane as range grows.

    ``cm.rows(t, 0)`` tends to ``CY + FY*beta_y/beta_z`` for t -> inf, which is where an
    infinitely distant floor point lands. This is pure camera geometry: no wall height.
    Columns whose trace is horizontal have no finite horizon and get ``-inf``.
    """
    bz = np.asarray(cm.beta[:, 2], float)
    with np.errstate(divide='ignore', invalid='ignore'):
        v = CY + mp.FY*np.asarray(cm.beta[:, 1], float)/bz
    return np.where(np.isfinite(v), v, -np.inf)


def surface_run_top(strips, tol, k=1):
    """Topmost row of the uniform surface run containing each row, per column.

    A step between adjacent rows larger than ``tol`` (luminance and chroma together)
    starts a new run, so the result is the top of the visually uniform surface the row
    belongs to. Rows of the same run share a top; the run reaching row 0 continues out of
    the top of the image.

    Computed by a single scan over rows with per-column numpy state, so the cost is one
    pass over the strip regardless of how many candidates are examined.
    """
    L, Cr = strips.L, strips.Cr
    if k <= 1:
        step = np.hypot(L[1:] - L[:-1], Cr[1:] - Cr[:-1])      # (HEIGHT-1, C): row v-1 -> v
    else:
        # difference of the k-row means just above and just below the boundary between rows v-1
        # and v: the same step operator the contact contrast uses, so a blurred or shaded edge
        # that changes by < tol per row still splits the run when it changes by > tol in total
        H = L.shape[0]
        cl = np.vstack([np.zeros((1, L.shape[1])), np.cumsum(L, 0)])
        cc = np.vstack([np.zeros((1, Cr.shape[1])), np.cumsum(Cr, 0)])
        v = np.arange(1, H)
        lo, hi = np.clip(v - k, 0, H), np.clip(v + k, 0, H)
        n_up, n_dn = (v - lo)[:, None], (hi - v)[:, None]
        dl = (cl[hi] - cl[v])/n_dn - (cl[v] - cl[lo])/n_up
        dc = (cc[hi] - cc[v])/n_dn - (cc[v] - cc[lo])/n_up
        step = np.hypot(dl, dc)
    breaks = step > tol
    top = np.zeros(L.shape, np.int32)
    cur = np.zeros(L.shape[1], np.int32)
    for v in range(1, L.shape[0]):
        cur = np.where(breaks[v - 1], v, cur)
        top[v] = cur
    return top


def solve_height(cm, col, t, row_obs, h_max=2.):
    """Wall height whose top edge lands on ``row_obs`` for a contact at trace distance ``t``.

    Evaluated on column ``col`` only. ``cm.rows`` is vectorised over all columns and
    broadcasts the scalar ``t`` across them, so calling it here would return column 0's
    geometry. The column's own alpha/beta/gamma are used instead.

    ``row(t, h)`` is monotonically decreasing in ``h`` (the point rises toward the
    horizon), so bisection inverts it. ``None`` when the row is not reachable in
    ``[0, h_max]``: the surface top is outside the frame, or the candidate is not a
    contact on the floor plane.
    """
    a1, a2 = float(cm.alpha[col, 1]), float(cm.alpha[col, 2])
    b1, b2 = float(cm.beta[col, 1]), float(cm.beta[col, 2])
    g1, g2 = float(cm.gamma[1]), float(cm.gamma[2])

    def f(h):
        cy, cz = a1 + t*b1 + h*g1, a2 + t*b2 + h*g2
        if cz <= 1e-6:
            return float('nan')
        return CY + mp.FY*cy/cz

    r0, r1 = f(0.), f(h_max)
    if not np.isfinite(r0) or not np.isfinite(r1) or abs(r0 - r1) < 1e-6:
        return None
    if row_obs > r0 or row_obs < r1:
        return None
    lo, hi = 0., h_max
    for _ in range(48):
        mid = .5*(lo + hi)
        if f(mid) > row_obs:
            lo = mid
        else:
            hi = mid
    return .5*(lo + hi)


def column_range_bearing(cm, col, t):
    """Floor distance from the camera nadir and bearing of the column ``col`` point at ``t``."""
    p = cm.q0[col] + t*cm.d[col] - cm.origin[:2]
    return float(math.hypot(p[0], p[1])), float(math.atan2(p[1], p[0]))


def self_top_mask(und_bgr, cm, params: Mapping | None = None, loaded: bool = True):
    """Per-column carried-object occlusion ceiling, from :mod:`self_mask`.

    Evaluated on the UNDISTORTED frame, and that is not optional: the raw fisheye is
    padded with (0, 0, 0) outside the image circle, the beam's black-band HSV test
    matches that padding, and measured on the v98 dev episode the same code lights up
    17.7% of every *raw* frame and drives ``self_top`` to 0 on 96/96 columns -- including
    frames with no beam in view at all. ``self_mask`` already walks the undistorted
    rows, so the raw frame is passed as ``None`` (its only other role, undistorting,
    is not needed) and nothing here reads it.

    Inputs: the own undistorted image, the own commanded load state and the detector's
    own column geometry. No map, no pose, no ground truth.
    """
    p = {**PARAMS, **(params or {})}
    return self_mask.self_top_for(None, und_bgr, np.asarray(cm.columns, int),
                                  int(p['strip_half_px']), bool(loaded))


def detect(und_bgr, cm, params: Mapping | None = None, self_top=None, loaded: bool = True):
    """Per-column floor contacts whose upper surface is not the ground plane.

    A row is accepted as a wall contact when the usual floor-contact evidence holds
    (a real step across the row, a uniform band above, the row back-projecting onto the
    floor plane) *and* the uniform surface above it reaches past the horizon row. The
    last condition is the one that rejects the floor's checker pattern; see the module
    docstring for the measurement that forced it.

    The carried-object self-mask is ON by default: when the caller passes no
    ``self_top``, :func:`self_top_mask` is computed here so the detector cannot report
    the robot's own beam or crate as a wall. Pass ``self_top`` explicitly (all-``HEIGHT``
    for no mask) to turn it off, and ``loaded=False`` when the own commands say nothing
    is being carried.

    Returns dict of (n_c, K) arrays: ``vb`` contact row, ``vt`` top row of the uniform
    surface (0 when it continues out of the top of the image), ``h`` height measured from
    ``vt`` or NaN when the top is not in frame, ``h_lb`` height lower bound when the top
    is not in frame, ``c`` contrast against the floor below, ``s`` band std, ``r`` range
    in metres, ``b`` bearing in radians.
    """
    p = {**PARAMS, **(params or {})}
    cols = np.asarray(cm.columns, int)
    n_c, n_k = len(cols), int(p['candidates'])
    strips = ColumnStrips(und_bgr, cols, int(p['strip_half_px']))
    if self_top is None:
        self_top = self_top_mask(und_bgr, cm, p, loaded)   # self-mask ON unless the caller overrides
    self_top = np.asarray(self_top, int)

    band_px, w = int(p['band_px']), int(p['window_px'])
    m = int(math.ceil(float(p['edge_margin_px'])))
    rows = np.arange(HEIGHT - 2, 2, -1, dtype=float)[:, None]*np.ones((1, n_c))  # bottom -> top
    t_all = cm.t_of_row(rows)
    rng_all, _ = cm.range_bearing(np.where(np.isfinite(t_all), t_all, 0.))
    ok = (np.isfinite(t_all) & (rng_all >= p['min_range_m']) & (rng_all <= p['max_range_m'])
          & (rows <= (self_top - int(p['self_margin_px']) - 1)[None, :]))

    vb_i = np.round(rows).astype(int)
    band = strips.window(vb_i - band_px, vb_i - m)
    below = strips.window(vb_i + 1, vb_i + 1 + w)
    contrast = np.hypot(band[0] - below[0], band[1] - below[1])
    std = np.sqrt(band[2])

    run_top = surface_run_top(strips, float(p['run_edge_tol']), int(p['run_step_window']))
    horizon = horizon_rows(cm)
    above = run_top[np.clip(vb_i - 1, 0, HEIGHT - 1), np.arange(n_c)[None, :]]
    if p['clamp_horizon']:
        horizon = np.maximum(horizon, 0.)     # horizon outside the frame: the frame top is the nearest it can be tested
    above_is_vertical = above <= horizon[None, :]
    if float(p['floor_patch_max_m']) > 0:
        # Horizon above the image: no run can reach it, so ask instead how much floor the run would
        # have to be if the candidate were floor. A textured floor cannot stay uniform over more than
        # one texture patch, so a uniform run spanning >= floor_patch_max_m of floor-plane distance
        # is not floor. Columns whose horizon is inside the image keep the exact horizon test.
        t_top = cm.t_of_row(above.astype(float))
        extent = np.where(np.isfinite(t_top), t_top - t_all, np.inf)
        above_is_vertical |= (horizon[None, :] < 0) & (extent >= float(p['floor_patch_max_m']))

    accept = ok & (contrast >= p['min_contrast_below']) & (std <= p['max_band_std']) & above_is_vertical

    out = {k: np.full((n_c, n_k), np.nan) for k in ('vb', 'vt', 'h', 'h_lb', 'c', 's', 'r', 'b')}
    for j in range(n_c):
        rows_ok = np.flatnonzero(accept[:, j])
        k, ceiling = 0, np.inf
        for i in rows_ok:
            if k >= n_k:
                break
            vb = float(rows[i, j])
            if vb > ceiling:
                continue
            out['vb'][j, k] = vb
            out['c'][j, k] = contrast[i, j]
            out['s'][j, k] = std[i, j]
            t_here = float(t_all[i, j])
            top = float(run_top[vb_i[i, j] - 1, j])
            out['vt'][j, k] = top
            if top > 0:
                h = solve_height(cm, j, t_here, top)
                if h is not None:
                    out['h'][j, k] = h
            else:
                # the surface leaves the frame: every height at or above the one that
                # reaches row 0 is consistent with what is visible
                h_lb = solve_height(cm, j, t_here, 0.)
                if h_lb is not None:
                    out['h_lb'][j, k] = h_lb
            ceiling = top + 2. if top > 0 else vb - band_px
            r_here, b_here = column_range_bearing(cm, j, t_here)
            out['r'][j, k] = r_here
            out['b'][j, k] = b_here
            k += 1
    return out


def link_segments(scan, params: Mapping | None = None):
    """Group per-column contacts into wall faces by adjacent-column continuity.

    A wall face is a contact that persists across at least ``min_run_columns`` adjacent
    columns with smoothly varying range and bearing. Short runs (pillars seen edge-on,
    boxes, cargo) and range steps (a floor marking edge) are not faces. This is the
    surface-extent cue and it needs no map and no wall height.
    """
    p = {**PARAMS, **(params or {})}
    vb, r, b = scan['vb'], scan['r'], scan['b']
    n_c = vb.shape[0]
    primary = np.isfinite(vb[:, 0])
    segments = []
    run = []

    def flush(run):
        if len(run) < int(p['min_run_columns']):
            return
        hs = scan['h'][run, 0]
        hs = hs[np.isfinite(hs)]
        segments.append({
            'col_first': int(run[0]), 'col_last': int(run[-1]),
            'range_first_m': float(r[run[0], 0]), 'range_last_m': float(r[run[-1], 0]),
            'bearing_first_rad': float(b[run[0], 0]), 'bearing_last_rad': float(b[run[-1], 0]),
            'range_span_m': float(np.ptp(r[run, 0])), 'bearing_span_rad': float(np.ptp(b[run, 0])),
            'n_columns': len(run),
            'height_m': float(np.median(hs)) if hs.size else None,
            'contrast_med': float(np.median(scan['c'][run, 0])),
        })

    for j in range(n_c + 1):
        ok = j < n_c and primary[j] and np.isfinite(r[j, 0])
        if ok and run:
            j0 = run[-1]
            if abs(r[j, 0] - r[j0, 0]) > p['max_step_range_m'] or \
               abs(b[j, 0] - b[j0, 0]) > p['max_step_bearing_rad']:
                ok = False
        if ok:
            run.append(j)
        else:
            flush(run)
            run = []
    return segments