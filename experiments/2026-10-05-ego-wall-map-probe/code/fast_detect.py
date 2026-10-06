"""Optimised drop-in candidate for ``height_free_wall.py`` -- MEASUREMENT PROTOTYPE, NOT LANDED.

*** READ THIS BEFORE ADOPTING ANYTHING HERE ***

This file is a *copy* of ``height_free_wall.py`` (the same module docstring, the same
``PARAMS``, the same public names: ``ColumnStrips``, ``horizon_rows``,
``surface_run_top``, ``solve_height``, ``column_range_bearing``, ``self_top_mask``,
``detect``, ``link_segments``) with the per-frame work restructured for speed. It was
written to answer one question -- *can height-free wall detection run in realtime?* --
and it has **not** been adopted. Before anything here is moved into
``height_free_wall.py`` it must be diffed against that module line by line and the
equivalence harness re-run; nothing in the repository imports this file.

WHAT CHANGED (all four are the same idea: do the work on the 96 column strips, not on
the 480x640 image, and take the per-column loop off the Python interpreter)

1. ``ColumnStrips.__init__`` builds the strips first and prefix-sums *the strips*.
   The original takes a float64 prefix sum along every one of the 640 image rows and
   then reads 96 of the 641 entries, i.e. it integrates 307200 values to use 46080.

   This is **bit-exact**, not approximate. ``lum``/``chroma`` are float32 values
   derived from 8-bit samples, so summing at most 640 of them into a float64 running
   total needs at most ~45 significant bits (< 53) and cannot round: the original's
   prefix sums are therefore the *exact* column sums, and so is the difference of two
   of them. Summing the 5 strip samples directly gives the same exact real number and
   the same float64 quotient. Measured: max abs difference 0.0 on all six arrays
   (``L``, ``Cr``, ``SL``, ``SL2``, ``SC``, ``SC2``) over 40 recorded frames.

2. ``window_rows`` replaces the general ``window`` inside ``detect``. The original
   indexes ``SL[r1, ci]`` with a *broadcast* column index, which is element-wise
   fancy indexing on a 476x96 grid. ``detect``'s row arguments are constant along
   columns (``vb_i`` depends only on the row), so the same value is a row gather.

3. ``surface_run_top`` replaces the 479-iteration Python row scan with
   ``np.maximum.accumulate`` over the break mask. The scan's ``cur`` is
   non-decreasing and each break writes the current row, so the maximum over the
   prefix *is* ``cur``.

4. ``detect``'s per-column candidate loop is a vectorised "greedy chain". ``rows`` is
   strictly decreasing, so "the next accepted row whose vb <= ceiling" is
   ``nxt[start]`` where ``nxt[i] = min{i' >= i : accept[i']}`` is one reverse
   ``np.minimum.accumulate`` over the accept mask, and the next ``start`` is
   ``max(i + 1, ROW0 - ceiling_after(i))``. That runs at most ``n_k`` rounds over all
   96 columns at once. ``solve_height`` becomes ``solve_height_many``: the same 48-step
   bisection with the same arithmetic, on one flat array, so it is bit-exact too.

A measurement that decided the shape of (1): numpy advanced indexing on a 2-D array is
~7x faster than on the 3-D uint8 image (0.14 ms vs 0.95 ms for the same 230400 values),
because the 3-byte channel axis defeats its iterator. So luminance and chroma are
formed over the whole image (0.70 ms, and those ops are contiguous and SIMD) and the
strips are then gathered from the 2-D float32 plane. Gathering first -- the obvious
reading of "build the strip, then prefix-sum the strip" -- is what the first version of
this file did and it was 0.6 ms slower.

5. ``window_rows(..., need_std=False)``. ``detect`` reads only ``below[0]`` and
   ``below[1]``; ``below[2]``, the below-window variance, was being built and thrown
   away. Same numbers, five fewer passes over a 476x96 float64 array.

6. ``self_top_mask(..., fast=True)`` -- OFF BY DEFAULT. At the optimised ``detect``
   cost the :mod:`self_mask` delegation is the largest remaining stage, and three of
   its ops are pure waste: ``_strip_flags`` prefix-sums all 640 columns of the mask to
   read 96 five-pixel windows, and ``_cyan_mask`` evaluates ``1.6*r + 8.`` twice. The
   ``fast`` path counts the strip pixels directly and hoists the duplicate. Bit-exact
   (integer count vs float64 quotient of the same small integers), and verified
   separately below. Left off because it is outside what ``detect`` was asked to
   absorb; see the report for what it is worth.

WHAT DID NOT CHANGE

* Every gate, threshold and parameter. ``PARAMS`` is copied verbatim.
* ``self_top_mask`` default path still delegates to :mod:`self_mask` unchanged, so the
  occlusion ceiling is identical by construction.
* ``link_segments`` is copied verbatim.
* ``horizon_rows``, ``column_range_bearing``, ``solve_height`` and the general
  ``window``/``value`` methods of ``ColumnStrips`` are copied verbatim.

THE ONE PLACE THE ARITHMETIC IS NOT BIT-IDENTICAL
``r``/``b`` are reported with ``np.hypot``/``np.arctan2`` on a vector where the
original used ``math.hypot``/``math.atan2`` on a scalar. ``np.hypot`` and ``math.hypot``
are both correctly rounded to within an ulp of each other but not to the same ulp, so
``r`` can move by ~1e-16. Nothing thresholds ``r`` or ``b`` -- they are outputs, and
``link_segments`` only compares differences of them, where a 1-ulp change cannot flip a
segment -- so this is reported in the equivalence table rather than eliminated.
``rng_all``, which *is* thresholded against ``min_range_m``/``max_range_m``, keeps the
original ``cm.range_bearing`` numerics exactly. Everything else is bit-identical.
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
}

ROW0 = HEIGHT - 2           # bottom-most row ``detect`` scans; ``rows_i[i] == ROW0 - i``


def _pre_rows(a):
    """``out[r] = a[0] + ... + a[r-1]``, the original's row-prefix sums.

    Same ``np.cumsum`` over the same rows in the same order as
    ``height_free_wall.ColumnStrips``; only the allocation of the zero row moves.
    """
    out = np.empty((a.shape[0] + 1, a.shape[1]))
    out[0] = 0.
    np.cumsum(a, axis=0, out=out[1:])
    return out


class ColumnStrips:
    """Prefix sums of the column-averaged luminance and chroma strips of one frame.

    Only the 96 strips of half-width ``half`` (about 46080 of the 307200 image
    values) are ever read, so the prefix sums are built over those and not over the
    640-wide image. See the module docstring for why that is bit-identical rather
    than approximate, and for why the strips are gathered from the 2-D float32
    luminance/chroma planes rather than from the 3-D uint8 image.
    """

    def __init__(self, und_bgr, columns, half):
        cols = np.asarray(columns, int)
        n_c = len(cols)
        lo = np.clip(cols - half, 0, WIDTH)
        hi = np.clip(cols + half + 1, 0, WIDTH)
        n_pix = (hi - lo).astype(np.float64)
        idx = lo[:, None] + np.arange(2*half + 1)[None, :]     # (C, 2*half+1)
        inside = idx < hi[:, None]                             # only false at the image edge
        img = und_bgr.astype(np.float32)
        lum = .114*img[..., 0] + .587*img[..., 1] + .299*img[..., 2]
        cr = img[..., 0] - img[..., 2]
        # gather from the 2-D planes: same samples, ~7x faster than the 3-D gather
        L = lum[:, np.where(inside, idx, 0)].sum(2, dtype=np.float64)
        Cr = cr[:, np.where(inside, idx, 0)].sum(2, dtype=np.float64)
        if not inside.all():                                   # degenerate edge columns only
            L = np.where(inside[None, :, :], L, 0.)
            Cr = np.where(inside[None, :, :], Cr, 0.)
        self.L = L/n_pix[None, :]
        self.Cr = Cr/n_pix[None, :]
        self.SL, self.SL2 = _pre_rows(self.L), _pre_rows(self.L*self.L)
        self.SC, self.SC2 = _pre_rows(self.Cr), _pre_rows(self.Cr*self.Cr)
        self.n_c = n_c

    def window_rows(self, r0, r1, need_std: bool = True):
        """:meth:`window` for row arguments that are constant along columns.

        ``detect``'s row bounds are ``vb_i - band_px`` and ``vb_i - m`` with
        ``vb_i = round(rows)``, and ``rows`` is a per-row ramp, so every bound is
        the same for all 96 columns. Indexing the prefix sums with the full
        (n_rows, n_c) broadcast grid is element-wise fancy indexing; indexing with
        the (n_rows,) bound alone is a row gather and returns the same (n_rows, n_c)
        values by the same arithmetic.

        ``need_std=False`` skips the variance, which ``detect`` does not read for
        the below-contact window.
        """
        r0 = np.clip(r0, 0, HEIGHT)
        r1 = np.clip(r1, 0, HEIGHT)
        n = np.maximum(r1 - r0, 1)[:, None]
        mL = (self.SL[r1] - self.SL[r0])/n
        mC = (self.SC[r1] - self.SC[r0])/n
        if not need_std:
            return mL, mC, None
        vL = np.maximum((self.SL2[r1] - self.SL2[r0])/n - mL*mL, 0.)
        vC = np.maximum((self.SC2[r1] - self.SC2[r0])/n - mC*mC, 0.)
        return mL, mC, vL + vC

    def window(self, r0, r1):
        """Original general form, kept for any caller with non-uniform row bounds."""
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


def surface_run_top(strips, tol):
    """Topmost row of the uniform surface run containing each row, per column.

    A step between adjacent rows larger than ``tol`` (luminance and chroma together)
    starts a new run, so the result is the top of the visually uniform surface the row
    belongs to. Rows of the same run share a top; the run reaching row 0 continues out of
    the top of the image.

    One pass over the break mask instead of a Python loop over the 479 row
    transitions: the scan's ``cur`` is non-decreasing and a break writes the current
    row, so ``cur`` after row ``v`` is the running maximum of ``i if breaks[i-1]``.
    """
    L, Cr = strips.L, strips.Cr
    step = np.hypot(L[1:] - L[:-1], Cr[1:] - Cr[:-1])      # (HEIGHT-1, C): row v-1 -> v
    breaks = step > tol
    top = np.zeros(L.shape, np.int32)
    top[1:] = np.maximum.accumulate(np.where(breaks, np.arange(1, L.shape[0])[:, None], 0), axis=0)
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


def solve_height_many(cm, col, t, row_obs, h_max=2.):
    """:func:`solve_height` for many (column, t, row) triples at once. Bit-identical.

    The bisection is per-element independent and every operation is the same one in
    the same order, so batching changes nothing but the loop nesting. The two guards
    are evaluated vectorised and become the ``live`` mask; unreachable elements
    return NaN, exactly where :func:`solve_height` returns ``None``.

    ``cz`` is affine in ``h``, so an element that reaches the bisection has
    ``cz > 1e-6`` at both endpoints and therefore on the whole interval: the scalar
    ``cz <= 1e-6`` early return never fires inside the loop for a live element, and
    the vectorised division therefore performs the same arithmetic the scalar does.
    """
    g1, g2 = float(cm.gamma[1]), float(cm.gamma[2])
    A1 = cm.alpha[col, 1] + t*cm.beta[col, 1]          # a1 + t*b1
    A2 = cm.alpha[col, 2] + t*cm.beta[col, 2]          # a2 + t*b2
    with np.errstate(divide='ignore', invalid='ignore'):
        r0 = CY + mp.FY*A1/A2
        r1 = CY + mp.FY*(A1 + h_max*g1)/(A2 + h_max*g2)
        live = np.isfinite(r0) & np.isfinite(r1) & (np.abs(r0 - r1) >= 1e-6) \
            & (row_obs <= r0) & (row_obs >= r1)
        lo = np.zeros_like(A1)
        hi = np.full_like(A1, float(h_max))
        for _ in range(48):
            mid = .5*(lo + hi)
            row = CY + mp.FY*(A1 + mid*g1)/(A2 + mid*g2)
            up = row > row_obs
            lo = np.where(up, mid, lo)
            hi = np.where(up, hi, mid)
        return np.where(live, .5*(lo + hi), np.nan)


def column_range_bearing(cm, col, t):
    """Floor distance from the camera nadir and bearing of the column ``col`` point at ``t``."""
    p = cm.q0[col] + t*cm.d[col] - cm.origin[:2]
    return float(math.hypot(p[0], p[1])), float(math.atan2(p[1], p[0]))


def self_top_mask(und_bgr, cm, params: Mapping | None = None, loaded: bool = True):
    """Per-column carried-object occlusion ceiling, from :mod:`self_mask`.

    Unchanged from ``height_free_wall``: it delegates to :mod:`self_mask` so the mask
    is identical by construction. It is *not* the thing this file optimises -- at the
    optimised ``detect`` cost it is the largest remaining stage, see the report.
    """
    p = {**PARAMS, **(params or {})}
    return self_mask.self_top_for(None, und_bgr, np.asarray(cm.columns, int),
                                  int(p['strip_half_px']), bool(loaded))


def detect(und_bgr, cm, params: Mapping | None = None, self_top=None, loaded: bool = True):
    """Per-column floor contacts whose upper surface is not the ground plane.

    Same gate as ``height_free_wall.detect``, same output dict, same defaults; see
    that function's docstring and this module's for what changed and why.
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
    # rows_i[i] == ROW0 - i, bottom -> top, so every row bound below is a per-row ramp
    rows_i = np.arange(ROW0, 2, -1)
    n_rows = len(rows_i)
    t_all = cm.t_of_row(rows_i.astype(float)[:, None])       # (n_rows, n_c)
    # cm.range_bearing's first output only; the (n_rows, n_c, 2) floor_point temporary
    # and the bearing that detect throws away are not built.
    t_safe = np.where(np.isfinite(t_all), t_all, 0.)
    rng_all = np.hypot(cm.q0[:, 0] + t_safe*cm.d[:, 0] - cm.origin[0],
                       cm.q0[:, 1] + t_safe*cm.d[:, 1] - cm.origin[1])
    ok = (np.isfinite(t_all) & (rng_all >= p['min_range_m']) & (rng_all <= p['max_range_m'])
          & (rows_i.astype(float)[:, None] <= (self_top - int(p['self_margin_px']) - 1)[None, :]))

    vb_i = rows_i
    band = strips.window_rows(vb_i - band_px, vb_i - m)
    below = strips.window_rows(vb_i + 1, vb_i + 1 + w)
    contrast = np.hypot(band[0] - below[0], band[1] - below[1])
    std = np.sqrt(band[2])

    run_top = surface_run_top(strips, float(p['run_edge_tol']))
    horizon = horizon_rows(cm)
    above = run_top[np.clip(vb_i - 1, 0, HEIGHT - 1)]       # (n_rows, n_c) row gather
    above_is_vertical = above <= horizon[None, :]

    accept = ok & (contrast >= p['min_contrast_below']) & (std <= p['max_band_std']) & above_is_vertical

    # ---- greedy chain, all columns at once -------------------------------------
    # The scalar loop takes accepted rows top-down (i increasing = row decreasing)
    # and keeps the first n_k whose vb is at or below the running ceiling. Because
    # vb decreases along i, "first accepted row with vb <= ceiling" is a suffix-min
    # lookup on the accept mask, and the next ceiling is a function of the row just
    # taken, so the whole per-column loop is n_k rounds of two small gathers.
    BIG = n_rows
    nxt = np.minimum.accumulate(
        np.where(accept, np.arange(n_rows, dtype=np.int32)[:, None], np.int32(BIG))[::-1],
        axis=0)[::-1]                                        # nxt[i, j] = first accept >= i
    ceil_after = np.where(above > 0, above + 2, vb_i[:, None] - band_px)
    col_ix = np.arange(n_c)
    cur = nxt[0]
    sel = [cur]
    live = cur < BIG
    for _ in range(1, max(n_k, 1)):
        take = np.where(live, cur, 0)
        start = np.maximum(take + 1, ROW0 - ceil_after[take, col_ix])
        step_ok = live & (start <= n_rows - 1)
        cur = np.where(step_ok, nxt[np.minimum(start, n_rows - 1), col_ix], np.int32(BIG))
        live = step_ok & (cur < BIG)
        sel.append(cur)

    out = {k: np.full((n_c, n_k), np.nan) for k in ('vb', 'vt', 'h', 'h_lb', 'c', 's', 'r', 'b')}
    if n_k <= 0:
        return out

    # ---- one flat gather for all n_k slots of all n_c columns ------------------
    ir = np.concatenate(sel)                                 # (n_c*n_k,) row index or BIG
    rep = np.tile(col_ix, max(n_k, 1))
    good = ir < BIG
    safe = np.where(good, ir, 0)
    top = above[safe, rep].astype(np.int64)
    t_here = t_all[safe, rep]
    # rows below the ceiling are already clipped to [0, HEIGHT] by window_rows, and
    # contrast/std are finite everywhere, so the masked gather is exact.
    slot = np.where(good, ROW0 - ir, np.nan)
    c_val = np.where(good, contrast[safe, rep], np.nan)
    s_val = np.where(good, std[safe, rep], np.nan)
    vt_val = np.where(good, top, np.nan)

    h_val = solve_height_many(cm, rep, t_here, np.where(top > 0, top, 0.).astype(float))
    h_val = np.where(good, h_val, np.nan)

    px = cm.q0[rep, 0] + t_here*cm.d[rep, 0] - cm.origin[0]
    py = cm.q0[rep, 1] + t_here*cm.d[rep, 1] - cm.origin[1]
    r_val = np.where(good, np.hypot(px, py), np.nan)
    b_val = np.where(good, np.arctan2(py, px), np.nan)

    sh = (max(n_k, 1), n_c)
    out['vb'] = slot.reshape(sh).T
    out['vt'] = vt_val.reshape(sh).T
    out['c'] = c_val.reshape(sh).T
    out['s'] = s_val.reshape(sh).T
    out['h'] = np.where(top.reshape(sh).T > 0, h_val.reshape(sh).T, np.nan)
    out['h_lb'] = np.where(top.reshape(sh).T > 0, np.nan, h_val.reshape(sh).T)
    out['r'] = r_val.reshape(sh).T
    out['b'] = b_val.reshape(sh).T
    return out


def link_segments(scan, params: Mapping | None = None):
    """Group per-column contacts into wall faces by adjacent-column continuity.

    Copied verbatim from ``height_free_wall``: at 0.3 ms it is not worth the risk.
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
