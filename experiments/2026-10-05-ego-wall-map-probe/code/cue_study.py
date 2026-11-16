"""Alternative verticality cues for the height-free wall detector (probe, 2026-10-05).

Refs #216. **Physical simulation runs: 0.** This module never calls ``mj_step``; it
either reads the recorded JPEGs of ``zone_wide_door_geometry_v3`` or re-renders the
same recorded ``qpos`` through :mod:`replay_render` (``mj_forward`` only), which is
proven byte-identical to the recording at 0.40 m.

WHAT THIS IS
------------
``height_free_wall.detect`` accepts a floor contact when

    ok & (contrast >= min_contrast_below) & (std <= max_band_std) & above_is_vertical

and the last term is ``run_top[vb-1, j] <= horizon_rows(cm)[j]``.  That term needs the
horizon row to be *inside* the image, because ``run_top`` is a row index and is
therefore >= 0.  Measured over the 299 distinct servo postures of the episode the
horizon row sits above the top of the frame for 207 of them, and only 291/1848 frames
(15.7%) have a single usable column.

This module asks whether a *different* last term can lift that coverage without making
the acceptance set a function of wall height.  Every gate below is a drop-in
replacement for ``above_is_vertical``; the first three terms are computed by exactly
the same code as :mod:`height_free_wall` (that code is imported, never re-derived), so
the comparison is apples to apples.

  none        no verticality term at all.  Reference: the coverage/precision ceiling of
              everything else, and the honest answer to "what does the verticality cue
              actually buy?".
  horizon     the shipped cue, unchanged.  ``run_top[vb-1] <= horizon[j]``.
  run_to_top  (a) the uniform run leaves the top of the image: ``run_top[vb-1] == 0``.
  top_edge    (b) the mirror cue: the uniform run has a bounded top, is at least
              ``min_run_px`` tall, and the surface above that top carries at least one
              more boundary within ``above_probe_px`` -- we are looking past the wall.
  union_ab    (a) or (b): "the run either leaves the frame or ends at a visible edge".
  extent_gt   (c)/(d) "the uniform run must be longer than the floor's own texture can
              make it": the run's floor-plane-equivalent range extent must exceed
              ``floor_extent_m``, the largest uniform-run extent measured on wall-free
              pixels of this same episode.  Pure camera geometry + one scene constant
              that is a property of the FLOOR, never of a wall height.
  horizon_or_extent  their union.  Reported to show it is not a compromise: ``horizon``
              is a strict subset of ``extent_gt`` (see below), so this row is identical
              to ``extent_gt`` and the union buys nothing.
  extent_gt_floor_rows  DIAGNOSTIC, not a cue: ``extent_gt`` restricted to candidate rows
              that can physically be a floor contact.  Isolates a bug in the shipped
              ``ok`` mask; see BUGS below.

WHY (a), (b) AND (c) COME OUT THE WAY THEY DO
--------------------------------------------
Every gate has a MINIMUM ADMITTED WALL HEIGHT even when no wall height appears in it, so
the question is never "is it height-free" but "what sets the minimum, and how far below the
heights under test is it".  ``stage_hmin`` measures that minimum at the true contact rows:
the height whose visible top edge lands on the row the gate's condition names.

The camera is 0.20..0.21 m above the floor and the wall tops in this episode are 1.8..2.2 m
away, so a floor point at that range is only ~5 degrees below horizontal while the image
spans ~42 degrees.  Hence:
  * the horizon row is ``camera height`` in disguise.  ``above_is_vertical`` asks for the
    top edge to reach the horizon, i.e. for the wall to be TALLER THAN THE CAMERA.
    Measured minimum admitted height: p10/p50/p90 = 0.204/0.204/0.209 m -- the camera
    height, to three decimals.  That is why the cue is blind in 84% of the frames: it is
    a "wall taller than my eyes" test, and a 0.10 m wall is 100% invisible to it.
  * ``run_to_top`` (a) asks for the top edge to reach row 0, i.e. for a taller wall
    still: minimum admitted height p10/p50/p90 = 0.091/0.293/0.384 m.  It admits a 0.10 m
    wall in 10.8% of contact columns, a 0.40 m wall in 91.4%, a 0.50 m wall in 99.0%.
    It is a tall-wall filter.  The letter of the invariant holds (no height constant in
    the code); the substance does not.
  * ``top_edge`` (b) is the exact complement -- it needs the top edge INSIDE the frame --
    so it admits 0.10 m walls and rejects 0.40 m ones.  (a) and (b) partition the height
    axis at the frame's top edge; their union accepts everything and discriminates
    nothing, so its height-invariance is a coin flip per frame, not a property.
  * ``extent_gt`` (c)/(d) sets its minimum from the FLOOR: the checker cell is 8 m / 14
    repeats = 0.571 m, so no floor patch can be uniform over more than one cell, at most
    sqrt(2)*0.571 = 0.807 m along a diagonal.  Measured on wall-free frames of this
    episode the floor's own uniform-run floor-equivalent extent is p50 0.072, p90 0.195,
    p99 0.394, p99.9 0.576, max 0.775 m, which sits under that geometric bound as it must.
    With ``floor_extent_m = 0.90`` the minimum admitted wall height is p10/p50/p90 =
    0.034/0.069/0.081 m, so a 0.10 m wall is admitted in 100% of contact columns, as are
    0.40 m and 0.50 m.

So ``extent_gt`` is not free of a height threshold either -- nothing can be, since "the
uniform run must be longer than the longest uniform floor patch" is only informative about
surfaces longer than that patch.  The difference is which scene property sets it and which
way it fails.  The horizon gate's minimum is the CAMERA height, above half the wall heights
under test, and it is one-sided: it can never report a low wall.  ``extent_gt``'s minimum
is the FLOOR's texture bound, roughly 4x below the shortest wall under test, and it moves
DOWN when the floor texture gets finer and UP when it gets coarser -- never up with the
wall.  Its failure mode is "too coarse a floor", which is a different detector from "too
short a wall".

The assumption (d) really makes: that the ground is textured in bounded patches and that
the vertical surface above a contact is uniform over more ground range than one patch.  The
floor bound is measured from wall-free pixels of the same episode (:func:`stage_calibrate`)
rather than assumed, so the floor half of the assumption is self-checking.  The wall half
is the band-uniformity test the detector already had.  It does NOT assume the horizon is in
frame, a wall height, a wall range, or any map.

BUGS FOUND (reported, not fixed -- no existing file was edited)
--------------------------------------------------------------
1. ``markerless_probe.ColumnModel.t_of_row`` returns FINITE NEGATIVE distances for rows
   above the horizon instead of NaN, and ``height_free_wall.detect``'s ``ok`` mask only
   range-checks their magnitude (``range_bearing`` takes a hypot, so the sign is lost).
   On frame 100 that admits 2307 of the 41171 accepted (row, column) candidates above the
   horizon row, with t = -6.2..-5.1 m, i.e. points BEHIND the camera.  72% of
   ``extent_gt``'s false positives are exactly those rows.  Gate ``extent_gt_floor_rows``
   quantifies the cost; it is a diagnostic, not a proposed patch.
2. ``ColumnModel.rows(t, h)`` broadcasts a scalar ``t`` across all columns, so
   ``cm.rows(3.0, 0.)`` silently returns COLUMN 0's row for every column.  ``solve_height``
   already guards this by hand; every other caller has to.
3. ``ColumnModel.t_of_row`` DIVERGES above the horizon rather than saturating, so any
   statistic built from it silently breaks on exactly the pitched-down postures (84% of
   frames) this work is about.  Here it was pinned to +inf explicitly.
4. ``ColumnModel``'s row<->range map disagrees with the rendered camera.  The floor trace
   line and its direction are right -- at frame 100 column 48 the trace direction
   (0.933, 0.361) matches the raycast ray to 3 decimals, and the hit point is the wall's
   own face at x = 2.174 -- but the ROW the model assigns to it is wrong by ~18 px: the
   model puts the contact at row 110.3 while a MuJoCo raycast puts the wall face at rows
   0..133 and the rendered luminance jumps at exactly rows 133/134.  Over the 488 wall
   frames the model GT row sits 11.5/17.9/36.5 px (p10/p50/p90) ABOVE the raycast one.
   Scoring against the model GT costs ~10x recall (0.129 vs 0.613 for ``extent_gt``) and
   ~5x precision; both ground truths are scored side by side in ``eval.json``.  Because
   the detector's ranges are produced by the same map, this is a detector-accuracy bug and
   not only a scoring one.
5. ``coverage.py:ray_rect`` starts its ray at ``cm.origin[:2]`` rather than ``cm.q0[j]``.
   Those differ by 0.214/0.225/0.247 m (p10/p50/p90), so it tests a parallel, offset ray
   against the wall rectangles instead of the column's own ray.

GROUND TRUTH IS SCORING ONLY.  :func:`gt_contact_t` reads ``static_map.json`` and
``wall_rects``; nothing it returns is ever passed to a gate, a threshold or the shared
evidence.  It is used by :func:`score` and by nothing else.  The detector-side functions
(:func:`evidence`, the gate registry, :func:`detect_with`) take no map argument.

A NOTE ON ``cm.rows``
---------------------
``ColumnModel.rows(t, h)`` is elementwise in ``(alpha[:, 1], beta[:, 1], ...)``, so a
``t`` of shape (C,) yields *that column's* row for *that column's* distance.  A scalar
``t`` broadcasts and the caller then silently reads column 0's geometry.  Every call in
this module that wants per-column rows passes a per-column array; the ground-truth
contact row is built that way and :func:`gt_contact_rows` asserts it.

USAGE
-----
  cue_study.py frames  --episode E --out DIR        # which frames genuinely hold a wall
  cue_study.py render  --episode E --frames F --heights 0.10 0.40 0.50 --out DIR
  cue_study.py eval    --episode E --frames F --out DIR
  cue_study.py calibrate --episode E --out DIR      # floor texture constants
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import height_free_wall as hfw          # noqa: E402  (imported, never edited)
import markerless_probe as mp           # noqa: E402
import wall_probe as wp                 # noqa: E402  (episode plumbing + seed bias)

WIDTH, HEIGHT, CY, FY = mp.WIDTH, mp.HEIGHT, mp.CY, mp.FY
DEFAULT_OUT = Path('/Users/changmin/projects/ugrp/outputs/ego-wall-map-probe/cue_study')

# Gate-local knobs.  None of them is a wall height; they are image tolerances in the
# same units as height_free_wall.PARAMS (rows, 8-bit levels) plus one floor-texture
# extent in metres, which :func:`calibrate` measures rather than assumes.
GATE_PARAMS = {
    'min_run_px': 4.,        # (b) a shorter uniform run is not a face, it is a sliver
    'above_probe_px': 60.,   # (b) how far above the run top we look for one more edge
    'floor_extent_m': .90,   # (c)/(d) measured floor bound; see calibrate()
    'step_tol': 10.,         # "a boundary" magnitude, same as run_edge_tol
}

GATES = ('none', 'horizon', 'run_to_top', 'top_edge', 'union_ab', 'extent_gt',
         'horizon_or_extent', 'extent_gt_floor_rows')


# ------------------------------------------------------------------ detector side
def evidence(und_bgr, cm, params=None, self_top=None, loaded=True):
    """Every per-(row, column) quantity the gates need, plus the shared accept mask.

    Mirrors :func:`height_free_wall.detect` line for line up to (but excluding) the
    ``above_is_vertical`` term, and adds the run's floor-extent and the step profile.
    Nothing here sees the map, the robot pose or any wall height.
    """
    p = {**hfw.PARAMS, **GATE_PARAMS, **(params or {})}
    cols = np.asarray(cm.columns, int)
    n_c = len(cols)
    strips = hfw.ColumnStrips(und_bgr, cols, int(p['strip_half_px']))
    if self_top is None:
        self_top = hfw.self_top_mask(und_bgr, cm, p, loaded)
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

    run_top = hfw.surface_run_top(strips, float(p['run_edge_tol']))
    horizon = hfw.horizon_rows(cm)
    ar = np.arange(n_c)[None, :]
    above = run_top[np.clip(vb_i - 1, 0, HEIGHT - 1), ar]

    # floor trace distance of every image pixel, (HEIGHT, C).  cm.t_of_row broadcasts v
    # against the per-column alpha/beta, so a (H, C) grid gives per-column distances.
    row_grid = np.arange(HEIGHT, dtype=float)[:, None]*np.ones((1, n_c))
    t_row = cm.t_of_row(row_grid)
    t_at_vb = t_row[vb_i, ar]
    t_at_top = t_row[np.clip(above, 0, HEIGHT - 1), ar]
    # The run climbs the image toward the horizon, i.e. toward larger range, so its
    # floor-plane-equivalent extent is t(above) - t(vb) > 0.  This is (c)/(d)'s statistic:
    # the range of ground plane the uniform surface would have to cover in order to still
    # be that plane.  A floor checker patch can never exceed one cell (~0.57 m); a wall
    # face reaches the horizon (extent -> inf).
    #
    # cm.t_of_row is only the inverse of the FLOOR row map.  Above the horizon there is
    # no floor point at all: it returns negative values that diverge (measured, frame 100
    # column 48, horizon row 50.3: t_of_row(50) = -445.7, t_of_row(0) = -3.03).  A run whose
    # top is at or above the horizon therefore has UNBOUNDED floor-equivalent extent, so
    # it is pinned to +inf here rather than left to the diverging inverse.
    run_extent_m = np.where(above <= horizon[None, :], np.inf, t_at_top - t_at_vb)

    # "one more boundary within above_probe_px above the run top", per (row, column)
    step = np.hypot(strips.L[1:] - strips.L[:-1], strips.Cr[1:] - strips.Cr[:-1])   # (H-1, C)
    edge = step > float(p['step_tol'])
    cs = np.concatenate([np.zeros((1, n_c), bool), np.cumsum(edge, 0, dtype=np.int32)], 0)
    lo = np.clip(above - int(math.ceil(p['above_probe_px'])), 0, HEIGHT - 1)
    hi = np.clip(above, 0, HEIGHT - 1)
    edges_above = (cs[hi, ar] - cs[lo, ar])

    return {
        'p': p, 'cm': cm, 'strips': strips, 'self_top': self_top,
        'rows': rows, 't_all': t_all, 'rng_all': rng_all, 'ok': ok,
        'vb_i': vb_i, 'contrast': contrast, 'std': std,
        'run_top': run_top, 'horizon': horizon, 'above': above,
        'run_extent_m': run_extent_m, 'edges_above': edges_above,
        'base': ok & (contrast >= p['min_contrast_below']) & (std <= p['max_band_std']),
        'step': step,
    }


def _gate_mask(name, ev):
    """(HEIGHT-2 x C) boolean: the verticality term that replaces ``above_is_vertical``."""
    p, ar = ev['p'], np.arange(ev['cm'].columns.size)[None, :]
    above, horizon = ev['above'], ev['horizon']
    run_len = ev['vb_i'] - above
    if name == 'none':
        m = np.ones_like(ev['ok'])
    elif name == 'horizon':
        m = above <= horizon[None, :]
    elif name == 'run_to_top':
        m = above <= 0
    elif name == 'top_edge':
        m = ((above > 0) & (run_len >= p['min_run_px']) & (ev['edges_above'] >= 1))
    elif name == 'union_ab':
        m = (above <= 0) | ((above > 0) & (run_len >= p['min_run_px']) & (ev['edges_above'] >= 1))
    elif name == 'extent_gt':
        m = ev['run_extent_m'] > p['floor_extent_m']
    elif name == 'horizon_or_extent':
        m = (above <= horizon[None, :]) | (ev['run_extent_m'] > p['floor_extent_m'])
    elif name == 'extent_gt_floor_rows':
        # DIAGNOSTIC, not a new cue: ``extent_gt`` restricted to candidate rows that can
        # physically be floor contacts at all, i.e. at or below the horizon row.  The
        # shipped ``ok`` mask does not enforce this, because ``cm.t_of_row`` returns
        # finite NEGATIVE distances above the horizon instead of NaN and
        # ``range_bearing`` keeps only their magnitude: on frame 100, 2307 of the 41171
        # admitted (row, column) candidates sit above the horizon row with t = -6.2..-5.1 m.
        # 72% of ``extent_gt``'s false positives are exactly those rows.
        m = (ev['run_extent_m'] > p['floor_extent_m']) & (ev['rows'] >= horizon[None, :])
    else:
        raise KeyError(name)
    return np.asarray(m, bool)


def detect_with(und_bgr, cm, gate, params=None, self_top=None, loaded=True, ev=None):
    """``height_free_wall.detect`` with the verticality term swapped for ``gate``.

    The candidate enumeration (bottom-to-top, one candidate per surface run, ceiling at
    ``top + 2``) is :mod:`height_free_wall`'s, so the two detectors differ in exactly
    one boolean term.
    """
    ev = ev or evidence(und_bgr, cm, params, self_top, loaded)
    p, cm_ = ev['p'], ev['cm']
    n_c, n_k = len(cm_.columns), int(p['candidates'])
    rows, t_all, vb_i, run_top = ev['rows'], ev['t_all'], ev['vb_i'], ev['run_top']
    accept = ev['base'] & _gate_mask(gate, ev)

    out = {k: np.full((n_c, n_k), np.nan) for k in ('vb', 'vt', 'h', 'h_lb', 'c', 's', 'r', 'b')}
    for j in range(n_c):
        k, ceiling = 0, np.inf
        for i in np.flatnonzero(accept[:, j]):
            if k >= n_k:
                break
            vb = float(rows[i, j])
            if vb > ceiling:
                continue
            out['vb'][j, k] = vb
            out['c'][j, k] = ev['contrast'][i, j]
            out['s'][j, k] = ev['std'][i, j]
            t_here = float(t_all[i, j])
            top = float(run_top[vb_i[i, j] - 1, j])
            out['vt'][j, k] = top
            if top > 0:
                h = hfw.solve_height(cm_, j, t_here, top)
                if h is not None:
                    out['h'][j, k] = h
            else:
                h_lb = hfw.solve_height(cm_, j, t_here, 0.)
                if h_lb is not None:
                    out['h_lb'][j, k] = h_lb
            ceiling = top + 2. if top > 0 else vb - int(p['band_px'])
            r_here, b_here = hfw.column_range_bearing(cm_, j, t_here)
            out['r'][j, k] = r_here
            out['b'][j, k] = b_here
            k += 1
    return out


# ------------------------------------------------------------------ ground truth (SCORING ONLY)
def gt_contact_t(cm, rects, max_range=6.):
    """Per-column trace distance at which the column's floor ray enters a wall footprint.

    The ray origin is ``cm.q0[j]``, the column's OWN floor-trace start point, not
    ``cm.origin[:2]``: the trace of column j is ``q0[j] + t*d[j]``, so a ray started at
    the camera nadir is a *parallel, offset* ray and does not follow the column.
    Measured on this episode the offset is 0.21..0.25 m (see README).
    """
    n_c = len(cm.columns)
    best = np.full(n_c, np.inf)
    o, d = cm.q0, cm.d
    for cx, cy, hx, hy, _h in rects:
        lo = np.full(n_c, -np.inf); hi = np.full(n_c, np.inf); ok = np.ones(n_c, bool)
        for k, (c, e) in enumerate(((cx, hx), (cy, hy))):
            dk = d[:, k]
            par = np.abs(dk) < 1e-12
            with np.errstate(divide='ignore', invalid='ignore'):
                t1 = np.where(par, -np.inf, (c - e - o[:, k])/dk)
                t2 = np.where(par, np.inf, (c + e - o[:, k])/dk)
            ok &= ~(par & (np.abs(o[:, k] - c) > e))
            lo = np.maximum(lo, np.minimum(t1, t2))
            hi = np.minimum(hi, np.maximum(t1, t2))
        ok &= (hi >= np.maximum(lo, 0.))
        best = np.where(ok & (lo > 0.) & (lo < best), lo, best)
    return np.where(np.isfinite(best) & (best <= max_range), best, np.nan)


def gt_contact_rows(cm, rects, max_range=6.):
    """Per-column image row of the wall/floor contact, or NaN.

    ``cm.rows`` is elementwise in the per-column alpha/beta, so the (C,) array of
    per-column distances from :func:`gt_contact_t` gives each column its own row.  The
    assertion is the point: passing a scalar here silently returns column 0's geometry
    for every column.
    """
    t = gt_contact_t(cm, rects, max_range)
    row = cm.rows(t, np.zeros(len(cm.columns)))       # (C,) array t -> per-column rows
    assert row.shape == t.shape == (len(cm.columns),)
    return np.where(np.isfinite(row), row, np.nan), t


def gt_top_rows(cm, rects, h, max_range=6.):
    """Per-column row of the wall's TOP EDGE at height ``h`` (ground truth, scoring only).

    The column plane cuts the horizontal plane ``z = h`` in a line with direction
    ``d``; the wall's top edge projects horizontally onto the wall's base line, so the
    visible top edge in column j is the height-h point whose horizontal position lies on
    that line.  Found with the same slab test run on ``cm.trace_at(h)``, then the row
    comes from the trace direction, which is exact inside the column plane.
    """
    n_c = len(cm.columns)
    if abs(h - float(cm.origin[2])) < 1e-6:
        return np.full(n_c, np.nan)
    q0h, a = cm.trace_at(h)
    best = np.full(n_c, np.inf)
    o, d = q0h, cm.d
    for cx, cy, hx, hy, _hh in rects:
        lo = np.full(n_c, -np.inf); hi = np.full(n_c, np.inf); ok = np.ones(n_c, bool)
        for k, (c, e) in enumerate(((cx, hx), (cy, hy))):
            dk = d[:, k]
            par = np.abs(dk) < 1e-12
            with np.errstate(divide='ignore', invalid='ignore'):
                t1 = np.where(par, -np.inf, (c - e - o[:, k])/dk)
                t2 = np.where(par, np.inf, (c + e - o[:, k])/dk)
            ok &= ~(par & (np.abs(o[:, k] - c) > e))
            lo = np.maximum(lo, np.minimum(t1, t2))
            hi = np.minimum(hi, np.maximum(t1, t2))
        ok &= (hi >= np.maximum(lo, 0.))
        best = np.where(ok & (lo > 0.) & (lo < best), lo, best)
    s = np.where(np.isfinite(best) & (best <= max_range), best, np.nan)
    cy_, cz = a[:, 1] + s*cm.beta[:, 1], a[:, 2] + s*cm.beta[:, 2]
    with np.errstate(divide='ignore', invalid='ignore'):
        row = np.where(cz > 1e-6, CY + FY*cy_/cz, np.nan)
    return row


# --------------------------------------------------------- ground truth by scene raycast
CX_, CY_, FX_, FY_ = mp.CX, mp.CY, mp.FX, mp.FY


class SceneRaycaster:
    """Wall/floor contact rows read out of the simulator itself (SCORING ONLY).

    An independent ground truth that does not go through ``ColumnModel`` at all: for each
    column the image row is turned into a camera ray with the frozen pinhole intrinsics,
    the ray is cast into the *static* scene through :mod:`mujoco`, and the contact row is
    the last row whose ray still lands on a ``zone_wall_*`` geom.

    It exists because :func:`gt_contact_rows` inherits ``ColumnModel``'s row<->range map,
    and that map disagrees with the rendered image.  Validated on frame 100: the raycast
    puts the wall base at rows 128/133/140 in columns 30/48/70, the rendered luminance
    profile jumps at exactly rows 133/134 in column 48, and ``gt_contact_rows`` returns
    105.4/110.3/116.2.  See the report; the detector was not changed.

    Assumptions, stated because they matter: an undistorted pixel maps to a camera ray by
    the frozen pinhole K (true by construction of :func:`markerless_probe.undistort`); the
    camera's own +y axis is flipped relative to the image, fixed by requiring the rendered
    horizon to match; and the lens geom's body is excluded so the ray leaves the camera,
    which also excludes anything else mounted on that body.
    """

    STEP = 8

    def __init__(self, ep_dir: Path, height_m: float = .40, robot: str = 'r1'):
        import mujoco
        import replay_render as rr
        self._mj = mujoco
        traj, _frames, _rel, ep = rr.load_episode(Path(ep_dir), robot)
        xml = rr.scene_with_wall_height(ep/'scene.xml', ep/'inputs'/'static_map.json', height_m)
        self.model = mujoco.MjModel.from_xml_string(xml)
        self.data = mujoco.MjData(self.model)
        self.trajs = traj
        self.cam = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, f'{robot}__robot_cam')
        lens = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, f'{robot}__v3_camera_lens_glass')
        self.skip_body = int(self.model.geom_bodyid[lens]) if lens >= 0 else -1
        self.walls = {i for i in range(self.model.ngeom)
                      if (mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, i) or '')
                      .startswith('zone_wall')}
        self._gid = np.zeros(1, np.int32)

    def set_frame(self, idx):
        mujoco = self._mj
        s = self.trajs[idx]
        self.data.qpos[:] = np.asarray(s['qpos'], float)
        self.data.qvel[:] = np.asarray(s['qvel'], float)
        self.data.time = float(s['t'])
        mujoco.mj_forward(self.model, self.data)
        self.R = self.data.cam_xmat[self.cam].reshape(3, 3)
        self.p0 = self.data.cam_xpos[self.cam].copy()

    def _hits_wall(self, u, row):
        d = np.array([(u - CX_)/FX_, -(row - CY_)/FY_, -1.0])
        d /= np.linalg.norm(d)
        dw = self.R @ d
        dist = self._mj.mj_ray(self.model, self.data, self.p0 + 1e-3*dw, dw,
                               None, 1, self.skip_body, self._gid, None)
        return dist > 0 and int(self._gid[0]) in self.walls

    def contact_row(self, u):
        """Last image row in column ``u`` whose ray still lands on a wall, or NaN."""
        grid = range(0, HEIGHT, self.STEP)
        hits = [self._hits_wall(u, v) for v in grid]
        if not any(hits):
            return float('nan')
        last = max(v for v, h in zip(grid, hits) if h)
        lo, hi = max(0, last - self.STEP), min(HEIGHT - 1, last + self.STEP)
        while hi - lo > 1:                      # bisect the boundary inside the step
            mid = (lo + hi)//2
            if self._hits_wall(u, mid):
                lo = mid
            else:
                hi = mid
        return float(lo)


def gt_raycast_rows(rc: SceneRaycaster, columns):
    """Per-column wall contact row from :class:`SceneRaycaster` (ground truth, scoring only)."""
    return np.asarray([rc.contact_row(int(u)) for u in np.asarray(columns, int)], float)


# ------------------------------------------------------------------ episode plumbing
def load_episode(ep_dir: Path, robot='r1'):
    frames, _ = wp.resolve_frames(ep_dir, robot)
    static_map = json.loads((ep_dir/'inputs'/'static_map.json').read_text())
    rects = np.asarray(wp.wall_rects(static_map), float)
    return frames, static_map, rects


def column_model_for(row):
    """The detector's own extrinsics: own commanded servo + own load state + fixed bias."""
    servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
    loaded = wp.loaded_for(servo)                 # option load_rule (default s3 = the earlier servo[3] >= 900)
    b0 = mp.elevation_bias(wp.SEED_BIAS['loaded' if loaded else 'unloaded'], servo)
    cols = mp.column_positions(wp.FROZEN_DETECTOR['columns'], wp.FROZEN_DETECTOR['strip_half_px'])
    return mp.column_model(servo, b0, cols), servo, loaded


def undistorted(ep_dir: Path, row):
    bgr = cv2.imread(str(ep_dir/row['path']), cv2.IMREAD_COLOR)
    if bgr is None:
        return None
    return mp.undistort(bgr)


def is_wall_frame(cm, rects, min_cols=8, max_range=6.):
    row, _ = gt_contact_rows(cm, rects, max_range)
    return int(np.sum(np.isfinite(row) & (row >= 0) & (row <= HEIGHT - 1))), row


# ------------------------------------------------------------------ stages
def stage_frames(args):
    ep = Path(args.episode).resolve()
    frames, sm, rects = load_episode(ep, args.robot)
    keep = []
    for i, f in enumerate(frames):
        if args.every > 1 and i % args.every:
            continue
        cm, _, _ = column_model_for(f)
        n, row = is_wall_frame(cm, rects, args.min_cols)
        if n >= args.min_cols:
            keep.append({'i': i, 't': round(float(f['sim_time']), 3), 'gt_cols': n,
                         'gt_row_med': round(float(np.nanmedian(row)), 2)})
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out/'wall_frames.json').write_text(json.dumps(
        {'episode': str(ep), 'robot': args.robot, 'min_cols': args.min_cols,
         'n_frames': len(frames), 'n_wall_frames': len(keep), 'frames': keep}, indent=1))
    print(f'{len(keep)} of {len(frames)} frames hold >= {args.min_cols} wall-contact columns '
          f'({len(keep)/max(1,len(frames))*100:.1f}%)  -> {out/"wall_frames.json"}')
    return keep


def stage_render(args):
    """Re-render the selected frames at several wall heights (mj_forward only)."""
    import replay_render as rr

    ep = Path(args.episode).resolve()
    out_dir = Path(args.out).resolve()
    repo = ROOT.resolve()
    if out_dir == repo or repo in out_dir.parents:
        raise SystemExit(f'refusing to write inside the repository: {out_dir}')
    out_dir.mkdir(parents=True, exist_ok=True)
    frames_sel = json.loads(Path(args.frames).read_text())['frames']
    idxs = [int(k) for k in args.frame] if args.frame else [int(f['i']) for f in frames_sel]

    traj, frames, frames_rel, ep = rr.load_episode(ep, args.robot)
    width, height = 640, 480
    fisheye_map = rr.raw_fisheye_remap(width, height)
    camera = f'{args.robot}__robot_cam'
    summary = {}
    for hm in args.heights:
        xml = rr.scene_with_wall_height(ep/'scene.xml', ep/'inputs'/'static_map.json', hm)
        model = __import__('mujoco').MjModel.from_xml_string(xml)
        data = __import__('mujoco').MjData(model)
        renderer, option = rr.make_renderer(model, width, height)
        hdir = out_dir/f'h{hm:.3f}'
        hdir.mkdir(parents=True, exist_ok=True)
        n_same = 0
        t0 = time.time()
        for k, idx in enumerate(idxs):
            step = traj[idx]
            data.qpos[:] = np.asarray(step['qpos'], float)
            data.qvel[:] = np.asarray(step['qvel'], float)
            data.time = float(step['t'])
            __import__('mujoco').mj_forward(model, data)
            rgb = rr.render_robot_cam(renderer, option, model, data, camera, fisheye_map)
            blob = rr.encode_jpeg(rgb, args.jpeg_quality)
            (hdir/f'r1_{idx:05d}_h{hm:.3f}.jpg').write_bytes(blob)
            if abs(hm - 0.40) < 1e-9:
                n_same += hashlib.sha256(blob).hexdigest() == frames[idx]['sha256']
            if (k + 1) % 100 == 0:
                print(f'  h={hm:.2f}  {k+1}/{len(idxs)}  {time.time()-t0:.0f}s', flush=True)
        renderer.close()
        summary[f'{hm:.3f}'] = {'frames': len(idxs), 'bytes_match_recorded': n_same if abs(hm-.4) < 1e-9 else None}
        print(f'height {hm:.2f} m: {len(idxs)} frames in {time.time()-t0:.0f}s'
              + (f', {n_same}/{len(idxs)} byte-identical to the recording' if abs(hm-.4) < 1e-9 else ''),
              flush=True)
    (out_dir/'render_summary.json').write_text(json.dumps(summary, indent=1))


def stage_calibrate(args):
    """Measure the floor's own texture constants on frames that hold NO wall.

    Two numbers the (c)/(d) gate needs, taken from this episode's own pixels rather
    than from the map: the largest uniform-run floor extent the floor can produce, and
    the rendered luminance ratio of the two checker tones.
    """
    ep = Path(args.episode).resolve()
    frames, sm, rects = load_episode(ep, args.robot)
    extents, n_wallfree = [], 0
    tone_hist = np.zeros(128, np.int64)
    for i, f in enumerate(frames):
        if i % args.every:
            continue
        cm, _, _ = column_model_for(f)
        row, _ = gt_contact_rows(cm, rects)
        if np.any(np.isfinite(row) & (row >= 0) & (row <= HEIGHT - 1)):
            continue                                            # wall present: skip
        und = undistorted(ep, f)
        if und is None:
            continue
        n_wallfree += 1
        ev = evidence(und, cm)
        m = ev['base'] & (ev['above'] > 0)                    # a bounded uniform run
        if m.any():
            extents.append(ev['run_extent_m'][m])
        # rendered floor tones: the strip luminance over rows that back-project inside
        # 0.15..6 m, i.e. floor only (the walls are excluded by the skip above)
        t = cm.t_of_row(ev['vb_i'])
        fy = (np.isfinite(t) & (t > .15) & (t < 6.))
        lum = np.clip(np.rint(ev['strips'].L[ev['vb_i']]), 0, 127).astype(np.int64)[fy]
        tone_hist += np.bincount(lum.ravel(), minlength=128)
    extents = np.concatenate(extents)

    # two dominant modes of the floor luminance histogram
    sm_hist = np.convolve(tone_hist.astype(float), np.ones(5)/5., mode='same')
    pk, _ = scipy_find_peaks(sm_hist)
    res = {'wall_free_frames_scanned': n_wallfree, 'n_uniform_runs': int(extents.size),
           'run_extent_m': {f'p{q}': round(float(np.percentile(extents, q)), 4)
                            for q in (50, 90, 99, 99.5, 99.9, 100)},
           'rendered_floor_tones': _tone_report(tone_hist, pk),
           'note': 'run_extent_m is the floor-equivalent range a uniform run above a row '
                   'covers; floor_extent_m must sit above its p99.9 for the (c)/(d) gate '
                   'to be sound (a floor patch can never be uniform over more than one '
                   'checker cell, so this is a property of the FLOOR, not of a wall)'}
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out/'floor_constants.json').write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return res


def min_admitted_height(cm, col, t_b, target_row, h_max=2.):
    """Smallest wall height whose visible top edge lands at ``target_row`` (metres).

    ``cm.rows(t, h)`` is the row of the point at height ``h`` on the vertical line at trace
    distance ``t``, which for ``t = t_b`` is the wall's own top edge.  The row is monotone
    decreasing in ``h`` (the point climbs toward the horizon), so a plain bisection
    inverts it.  Evaluated on column ``col`` alone for the reason given in
    :func:`height_free_wall.solve_height`: a scalar would broadcast column 0's geometry.
    """
    a1, a2 = float(cm.alpha[col, 1]), float(cm.alpha[col, 2])
    b1, b2 = float(cm.beta[col, 1]), float(cm.beta[col, 2])
    g1, g2 = float(cm.gamma[1]), float(cm.gamma[2])

    def f(h):
        cy, cz = a1 + t_b*b1 + h*g1, a2 + t_b*b2 + h*g2
        return CY + FY*cy/cz if cz > 1e-6 else float('nan')

    r0, r1 = f(0.), f(h_max)
    if not (np.isfinite(r0) and np.isfinite(r1)):
        return float('nan')
    if r0 < target_row:
        return 0.                 # already past the target at zero height: admits everything
    if r1 > target_row:
        return float('inf')       # never reaches the target inside the search range
    lo, hi = 0., h_max
    for _ in range(50):
        m = .5*(lo + hi)
        if f(m) > target_row:
            lo = m
        else:
            hi = m
    return .5*(lo + hi)


def stage_hmin(args):
    """Per-gate MINIMUM ADMITTED WALL HEIGHT, at the true contact rows.

    This is the number that says whether a gate is height-free.  A gate that can only
    accept a wall once it is taller than something is a height filter wearing a different
    hat, no matter that nothing in its code is called ``wall_height``.

      run_to_top  h at which the wall's top edge leaves the top of the image
      horizon     h at which the top edge reaches the horizon row  (== the camera height)
      extent_gt   h at which the run's floor-plane-equivalent range extent first exceeds
                  ``floor_extent_m`` -- a bound set by the FLOOR texture, not by a wall

    Ground truth (the raycast contact rows) is used here for scoring/reporting only.
    """
    ep = Path(args.episode).resolve()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    frames, sm, rects = load_episode(ep, args.robot)
    sel = json.loads(Path(args.frames).read_text())['frames'][::max(1, args.every)]
    rc = SceneRaycaster(ep, 0.40, args.robot)
    E = float(args.floor_extent_m)
    acc = []
    for entry in sel:
        idx = int(entry['i'])
        cm, _, _ = column_model_for(frames[idx])
        rc.set_frame(idx)
        rrow = gt_raycast_rows(rc, cm.columns)
        ok = np.isfinite(rrow)
        if ok.sum() < 8:
            continue
        C = len(cm.columns)
        zeros = np.zeros(C)
        for j in np.flatnonzero(ok):
            t_b = float(cm.t_of_row(np.full(C, float(rrow[j])))[j])
            if not np.isfinite(t_b) or t_b <= 0:
                continue
            r_ext = float(cm.rows(np.full(C, t_b + E), zeros)[j])
            acc.append((
                t_b,
                min_admitted_height(cm, j, t_b, 0.),                       # run_to_top
                min_admitted_height(cm, j, t_b, float(hfw.horizon_rows(cm)[j])),  # horizon
                min_admitted_height(cm, j, t_b, r_ext)))                  # extent_gt
    a = np.asarray(acc, float)
    rep = {'frames_sampled': len(sel), 'contact_columns': int(a.shape[0]),
           'floor_extent_m': E, 'heights_tested_m': [.10, .40, .50]}
    for i, key in ((1, 'run_to_top'), (2, 'horizon'), (3, 'extent_gt')):
        v, f = a[:, i], a[:, i][np.isfinite(a[:, i])]
        rep[key] = {
            'h_min_m': {f'p{q}': round(float(np.percentile(f, q)), 4) for q in (10, 50, 90)},
            'admits_0.10_m_pct': round(100*float(np.mean(v < .10)), 1),
            'admits_0.40_m_pct': round(100*float(np.mean(v < .40)), 1),
            'admits_0.50_m_pct': round(100*float(np.mean(v < .50)), 1)}
    rep['contact_range_m'] = {f'p{q}': round(float(np.percentile(a[:, 0], q)), 3)
                              for q in (10, 50, 90)}
    (out/'min_admitted_height.json').write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    return rep


def stage_coverage(args):
    """Coverage of every gate over EVERY recorded frame, not only the wall frames.

    The headline number the shipped cue is judged on is "frames with at least one usable
    column": 15.7% of the episode's 1848 frames.  The eval stage can only score the 488
    frames that hold a wall, so coverage has to be measured over the whole recording.
    Recorded frames only, so no re-render is needed and wall height cannot matter.
    """
    ep = Path(args.episode).resolve()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    frames, sm, rects = load_episode(ep, args.robot)
    rc = SceneRaycaster(ep, 0.40, args.robot)
    n = len(frames)
    acc = {g: {'any': 0, 'seg4': 0, 'cols': 0} for g in args.gates}
    hold = {'wall_frame': 0, 'wall_frame_detected': 0, 'hz_usable': 0, 'hz_and_wall': 0}
    for i, f in enumerate(frames):
        cm, _, loaded = column_model_for(f)
        und = undistorted(ep, f)
        if und is None:
            continue
        st = hfw.self_top_mask(und, cm, loaded=loaded)
        ev = evidence(und, cm, self_top=st)
        rc.set_frame(i)
        rrow = gt_raycast_rows(rc, cm.columns)
        has_wall = bool(np.sum(np.isfinite(rrow) & (rrow >= 0)) >= 8)
        hold['wall_frame'] += int(has_wall)
        hold['hz_usable'] += int(np.any(np.isfinite(ev['horizon']) & (ev['horizon'] >= 0)))
        hold['hz_and_wall'] += int(has_wall and np.any(np.isfinite(ev['horizon']) & (ev['horizon'] >= 0)))
        for g in args.gates:
            d = detect_with(None, cm, g, params={'floor_extent_m': args.floor_extent_m},
                            self_top=st, ev=ev)
            hit = np.isfinite(d['vb'][:, 0])
            acc[g]['any'] += int(hit.any())
            acc[g]['seg4'] += int(_longest_run(hit) >= 4)
            acc[g]['cols'] += int(hit.sum())
            if g == 'extent_gt_floor_rows' and has_wall:
                hold['wall_frame_detected'] += int(hit.any())
        if (i + 1) % 200 == 0:
            print(f'  {i+1}/{n}', flush=True)
    res = {'episode': str(ep), 'n_frames': n, 'floor_extent_m': args.floor_extent_m,
           'coverage_pct': {g: {'any_col': round(100*v['any']/n, 2),
                                 'run_of_4_cols': round(100*v['seg4']/n, 2),
                                 'mean_cols': round(v['cols']/n, 2)} for g, v in acc.items()},
           'frames_holding_a_wall': hold['wall_frame'],
           'frames_with_usable_horizon_column': hold['hz_usable'],
           'wall_frames_with_usable_horizon_column': hold['hz_and_wall'],
           'wall_frames_detected_by_extent_gt_floor_rows': hold['wall_frame_detected'],
           'recall_of_wall_frames_by_best_gate_pct': round(
               100*hold['wall_frame_detected']/max(1, hold['wall_frame']), 2)}
    (out/'coverage.json').write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return res


def scipy_find_peaks(y):
    """Local maxima of a smoothed 1-D signal, at least 20 counts above the neighbours."""
    out = [i for i in range(2, len(y)-1) if y[i] >= y[i-1] and y[i] > y[i+1] and y[i] > 20]
    out.sort(key=lambda i: -y[i])
    return sorted(out[:2]), None


def _tone_report(hist, peaks):
    tot = int(hist.sum())
    tones = [float(i + .5) for i in peaks]
    rep = {'n_pixels': tot, 'modes_lum': [round(t, 1) for t in tones]}
    if len(tones) == 2:
        rep['ratio'] = round(max(tones)/min(tones), 4)
        rep['share_dark'] = round(float(hist[:int(tones[0])].sum()/tot), 4)
        rep['share_bright'] = round(float(hist[int(tones[1]):].sum()/tot), 4)
    return rep


def stage_eval(args):
    ep = Path(args.episode).resolve()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    frames, sm, rects = load_episode(ep, args.robot)
    idxs = json.loads(Path(args.frames).read_text())['frames']
    idxs = [f['i'] for f in idxs]
    heights = args.heights
    tol_px = args.tol_px
    render_dir = Path(args.render_dir).resolve() if args.render_dir else Path(args.out).resolve()
    rc = SceneRaycaster(ep, 0.40, args.robot) if 'raycast' in args.gt else None

    recs = []
    for n_i, idx in enumerate(idxs):
        f = frames[idx]
        cm, servo, loaded = column_model_for(f)
        gt_row, gt_t = gt_contact_rows(cm, rects)
        gt_ok = np.isfinite(gt_row) & (gt_row >= 0) & (gt_row <= HEIGHT - 1)
        gts = {'model': (gt_ok, gt_row)}
        d_model = np.nan
        if rc is not None:
            rc.set_frame(idx)
            r_row = gt_raycast_rows(rc, cm.columns)
            r_ok = np.isfinite(r_row) & (r_row >= 0) & (r_row <= HEIGHT - 1)
            gts['raycast'] = (r_ok, r_row)
            both = gt_ok & r_ok
            d_model = float(np.median(r_row[both] - gt_row[both])) if both.any() else float('nan')
        hz = hfw.horizon_rows(cm)
        rec = {'i': idx, 't': round(float(f['sim_time']), 3), 'loaded': bool(loaded),
               'gt_cols': int(gt_ok.sum()),
               'gt_cols_ray': int(gts['raycast'][0].sum()) if 'raycast' in gts else None,
               'gt_row_offset_model_minus_raycast_px': None if np.isnan(d_model) else round(d_model, 1),
               'hz_cols': int(np.sum(np.isfinite(hz) & (hz >= 0))),
               'cam_z': round(float(cm.origin[2]), 4),
               'by_gate': {}}
        per_h = {}
        for hm in heights:
            tag = f'{hm:.3f}'
            src = (ep/f['path']) if abs(hm - 0.40) < 1e-9 else \
                  (render_dir/f'h{tag}'/f'r1_{idx:05d}_h{tag}.jpg')
            bgr = cv2.imread(str(src), cv2.IMREAD_COLOR)
            if bgr is None:
                raise SystemExit(f'missing rendered frame {src}')
            und = mp.undistort(bgr)
            st = hfw.self_top_mask(und, cm, loaded=loaded)
            ev = evidence(und, cm, self_top=st)
            per_h[tag] = (ev, st, und)
        st_ref = np.asarray([int(v) for v in per_h[f'{heights[0]:.3f}'][1]])
        for g in args.gates:
            dets = {hm: detect_with(None, cm, g, params={'floor_extent_m': args.floor_extent_m},
                                    self_top=per_h[f'{hm:.3f}'][1], ev=per_h[f'{hm:.3f}'][0])
                    for hm in heights}
            rec['by_gate'][g] = score_gate(dets, per_h, gts, heights, tol_px)
        # ceilings + the run-extent statistic at the true contact row (scoring only)
        cgt = gts.get('raycast', gts['model'])
        ext_at_gt, con_at_gt, base_ceil = [], [], []
        gate_ceil_acc = {g: [] for g in args.gates}
        for hm in heights:
            ev = per_h[f'{hm:.3f}'][0]
            c0 = ceilings(ev, 'none', *cgt, tol_px)
            base_ceil.append(c0['base_ceil'])
            ext_at_gt.append(c0['extent_at_gt']); con_at_gt.append(c0['contrast_at_gt'])
            for g in args.gates:
                gate_ceil_acc[g].append(
                    c0['base_ceil'] if g == 'none'
                    else ceilings(ev, g, *cgt, tol_px)['gate_ceil'])
        for g in args.gates:
            rec['by_gate'][g]['gate_recall_at_gt'] = round(float(np.mean(gate_ceil_acc[g])), 4)
            rec['by_gate'][g]['base_recall'] = round(float(np.mean(base_ceil)), 4)
        rec['base_ceiling_pct'] = round(100*float(np.mean(base_ceil)), 2)
        rec['contrast_at_gt_med'] = round(float(np.nanmedian(np.concatenate(con_at_gt))), 2)
        rec['contrast_at_gt_p90'] = round(float(np.nanpercentile(np.concatenate(con_at_gt), 90)), 2)
        E = np.asarray(ext_at_gt, float)                        # (n_heights, n_gt_cols)
        fin = np.isfinite(E)
        rec['extent_at_gt_frac_inf'] = round(float(np.mean(np.isinf(E[fin.any(1)]))), 4) \
            if fin.any() else 0.0
        rec['extent_at_gt_p10'] = round(float(np.nanpercentile(E[np.isfinite(E)], 10)), 3) \
            if np.isfinite(E).any() else None
        rec['extent_at_gt_p50'] = round(float(np.nanmedian(E[np.isfinite(E)])), 3) \
            if np.isfinite(E).any() else None
        # self-mask drift across heights (a pipeline confound, reported not corrected)
        rec['self_top_max_diff'] = int(max(np.max(np.abs(np.asarray(per_h[f'{hm:.3f}'][1], int) - st_ref))
                                         for hm in heights))
        recs.append(rec)
        if (n_i + 1) % 50 == 0:
            print(f'  {n_i+1}/{len(idxs)}', flush=True)

    agg = aggregate(recs, heights, tol_px)
    res = {'episode': str(ep), 'n_wall_frames': len(recs), 'heights_m': list(heights),
           'tol_px': tol_px, 'floor_extent_m': args.floor_extent_m,
           'render_dir': str(render_dir),
           'gate_params': {k: v for k, v in GATE_PARAMS.items() if k != 'floor_extent_m'},
           'aggregate': agg, 'per_frame': recs}
    (out/'eval.json').write_text(json.dumps(res, indent=1))
    print(json.dumps(agg, indent=1))
    return res


def score_gate(dets, per_h, gts, heights, tol_px):
    """Per-frame scoring of one gate.  Ground truth enters here and nowhere earlier.

    ``gts`` maps a ground-truth name to ``(gt_ok, gt_row)``.  Two are scored side by side:
    ``model`` (the floor trace intersected with the map rectangles, projected through
    ``ColumnModel``) and ``raycast`` (the simulator's own geometry).  They disagree; see
    :class:`SceneRaycaster`.
    """
    n_c = len(next(iter(gts.values()))[1])
    vb0 = dets[heights[0]]['vb']
    hit0 = np.isfinite(vb0[:, 0])

    per_gt = {}
    for name, (gt_ok, gt_row) in gts.items():
        tp = fp = 0
        matched = np.zeros(n_c, bool)
        for k in range(vb0.shape[1]):
            for j in range(n_c):
                v = vb0[j, k]
                if not np.isfinite(v):
                    continue
                g = np.flatnonzero(gt_ok & (~matched) & (np.abs(gt_row - v) <= tol_px))
                if g.size:
                    tp += 1; matched[g[0]] = True
                else:
                    fp += 1
        per_gt[name] = {
            'precision': round(tp/max(1, tp + fp), 4),
            'recall': round(float(matched[gt_ok].sum())/max(1, int(gt_ok.sum())), 4),
            'tp': tp, 'fp': fp, 'gt_cols': int(gt_ok.sum())}

    # --- height invariance on columns that really do hold a contact (raycast GT where it
    # is available: it is the one that agrees with the pixels, and the contact row does
    # not depend on wall height)
    gt_ok, gt_row = gts.get('raycast', gts['model'])
    agree = same_row = 0
    spreads, rspreads, n_seen = [], [], []
    for j in np.flatnonzero(gt_ok):
        vals, rs, seen = [], [], 0
        for hm in heights:
            v = dets[hm]['vb'][j, 0]
            vals.append(v)
            rs.append(dets[hm]['r'][j, 0])
            seen += int(np.isfinite(v))
        n_seen.append(seen)
        fin = [v for v in vals if np.isfinite(v)]
        finr = [x for x in rs if np.isfinite(x)]
        spread = (max(fin) - min(fin)) if fin else float('nan')
        rspread = (max(finr) - min(finr)) if finr else float('nan')
        if fin:
            spreads.append(spread); rspreads.append(rspread)
        same_row += int(seen == len(heights) and spread <= tol_px)
        agree += int(seen == len(heights))
    out = {
        'fires': int(hit0.sum()),
        'seg_cols': int(_longest_run(hit0)),
        'gt_cols_inv': int(np.sum([n == len(heights) for n in n_seen])) if n_seen else 0,
        'gt_cols_total': int(len(n_seen)),
        'row_spread_px': round(float(np.median(spreads)), 2) if spreads else None,
        'row_spread_p90': round(float(np.percentile(spreads, 90)), 2) if spreads else None,
        'rng_spread_m': round(float(np.median(rspreads)), 4) if rspreads else None,
        'det_at_all_heights': int(agree),
        'row_same_at_all_heights': same_row,
        'per_gt': per_gt,
    }
    for name in gts:
        out[f'precision_{name}'] = per_gt[name]['precision']
        out[f'recall_{name}'] = per_gt[name]['recall']
        out[f'tp_{name}'] = per_gt[name]['tp']
        out[f'fp_{name}'] = per_gt[name]['fp']
    return out


def ceilings(ev, gate, gt_ok, gt_row, tol_px):
    """Recall ceilings: shared evidence alone, and shared evidence AND this gate's term.

    Also returns the run-extent statistic sampled at the true contact row, which is the
    number that decides whether the (c)/(d) gate has any separation at all.
    """
    vb_i = ev['vb_i']
    near = np.abs(vb_i - gt_row[None, :]) <= tol_px          # (R, C) rows within tol of GT
    base = ev['base'] & near
    base_ceil = float(np.mean([bool(base[:, j].any()) for j in np.flatnonzero(gt_ok)] or [0.]))
    gmask = base if gate == 'none' else base & _gate_mask(gate, ev)
    gate_ceil = float(np.mean([bool(gmask[:, j].any()) for j in np.flatnonzero(gt_ok)] or [0.]))
    ext = np.full(len(gt_row), np.nan)
    for j in np.flatnonzero(gt_ok):
        ext[j] = ev['run_extent_m'][int(np.argmin(np.abs(vb_i[:, j] - gt_row[j]))), j]
    return {'base_ceil': base_ceil, 'gate_ceil': gate_ceil, 'extent_at_gt': ext,
            'contrast_at_gt': np.array([ev['contrast'][int(np.argmin(np.abs(vb_i[:, j] - gt_row[j]))), j]
                                        for j in np.flatnonzero(gt_ok)])}


def _longest_run(mask):
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def aggregate(recs, heights, tol_px):
    n = len(recs)
    gt_names = list(recs[0]['by_gate'][list(recs[0]['by_gate'])[0]]['per_gt'])
    out = {}
    for g in recs[0]['by_gate']:
        rows = [r['by_gate'][g] for r in recs]
        gt_tot = sum(r['gt_cols_total'] for r in rows)
        spread = np.asarray([r['row_spread_px'] for r in rows if r['row_spread_px'] is not None], float)
        rspread = np.asarray([r['rng_spread_m'] for r in rows if r['rng_spread_m'] is not None], float)
        det3 = sum(r['det_at_all_heights'] for r in rows)
        entry = {
            'coverage_any_col_pct': round(100*sum(r['fires'] > 0 for r in rows)/n, 2),
            'coverage_seg4_col_pct': round(100*sum(r['seg_cols'] >= 4 for r in rows)/n, 2),
            'mean_det_cols': round(float(np.mean([r['fires'] for r in rows])), 2),
            'gt_cols_total': gt_tot,
            'gt_cols_det_at_all_heights_pct': round(100*det3/max(1, gt_tot), 2),
            'row_same_at_all_heights_pct': round(
                100*sum(r['row_same_at_all_heights'] for r in rows)/max(1, gt_tot), 2),
            'gate_recall_at_gt': round(float(np.mean([r['gate_recall_at_gt'] for r in rows])), 4),
            'row_spread_px_med': round(float(np.median(spread)), 2) if spread.size else None,
            'row_spread_px_p90': round(float(np.percentile(spread, 90)), 2) if spread.size else None,
            'rng_spread_m_med': round(float(np.median(rspread)), 4) if rspread.size else None,
        }
        for name in gt_names:
            tot_tp = sum(r[f'tp_{name}'] for r in rows)
            tot_fp = sum(r[f'fp_{name}'] for r in rows)
            entry[f'precision_{name}'] = round(tot_tp/max(1, tot_tp + tot_fp), 4)
            entry[f'recall_{name}'] = round(float(np.mean([r[f'recall_{name}'] for r in rows])), 4)
            entry[f'tp_{name}'], entry[f'fp_{name}'] = tot_tp, tot_fp
        out[g] = entry
    out['_frames'] = n
    out['_gt_sources'] = gt_names
    out['_self_top_max_diff_over_heights'] = int(max(r['self_top_max_diff'] for r in recs))
    out['_shared_evidence_ceiling_pct'] = round(
        float(np.mean([r['base_ceiling_pct'] for r in recs])), 2)
    out['_contrast_at_true_contact_px'] = {
        'p50': round(float(np.median([r['contrast_at_gt_med'] for r in recs])), 2),
        'p90': round(float(np.median([r['contrast_at_gt_p90'] for r in recs])), 2)}
    out['_run_extent_at_true_contact_m'] = {
        'frac_unbounded': round(float(np.mean([r['extent_at_gt_frac_inf'] for r in recs])), 4),
        'p10': round(float(np.median([r['extent_at_gt_p10'] for r in recs
                                      if r['extent_at_gt_p10'] is not None])), 3),
        'p50': round(float(np.median([r['extent_at_gt_p50'] for r in recs
                                      if r['extent_at_gt_p50'] is not None])), 3)}
    off = [r['gt_row_offset_model_minus_raycast_px'] for r in recs
           if r['gt_row_offset_model_minus_raycast_px'] is not None]
    if off:
        out['_model_gt_minus_raycast_gt_px'] = {
            'p10': round(float(np.percentile(off, 10)), 1),
            'p50': round(float(np.median(off)), 1),
            'p90': round(float(np.percentile(off, 90)), 1)}
        out['_gt_cols_raycast_vs_model_pct'] = round(
            100*float(np.mean([(r['gt_cols_ray'] or 0)/max(1, r['gt_cols']) for r in recs])), 1)
    out['_horizon_usable_frames_pct'] = round(100*sum(r['hz_cols'] > 0 for r in recs)/n, 2)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('stage', choices=('frames', 'render', 'calibrate', 'eval', 'hmin', 'coverage'))
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--render-dir', default=None,
                    help='where the render stage wrote h0.100/ h0.400/ h0.500/ (default: --out)')
    ap.add_argument('--frames', default=None, help='wall_frames.json from the frames stage')
    ap.add_argument('--frame', nargs='*', type=int, default=None)
    ap.add_argument('--heights', nargs='*', type=float, default=[.10, .40, .50])
    ap.add_argument('--gates', nargs='*', default=list(GATES))
    ap.add_argument('--every', type=int, default=1)
    ap.add_argument('--min-cols', type=int, default=8)
    ap.add_argument('--tol-px', type=float, default=2.)
    ap.add_argument('--floor-extent-m', type=float, default=GATE_PARAMS['floor_extent_m'])
    ap.add_argument('--gt', nargs='*', default=['model', 'raycast'],
                    choices=('model', 'raycast'),
                    help='ground truths to score against (both by default); neither '
                         'ever reaches a gate or a threshold')
    ap.add_argument('--jpeg-quality', type=int, default=82)
    ap.add_argument('--load-rule', choices=('s3', 'gripper'), default='s3',
                    help='own load state: s3 = the earlier servo[3] >= 900 (default), gripper = commanded gripper closed')
    args = ap.parse_args()
    wp.set_load_rule(args.load_rule)
    return {'frames': stage_frames, 'render': stage_render,
            'calibrate': stage_calibrate, 'eval': stage_eval,
            'hmin': stage_hmin, 'coverage': stage_coverage}[args.stage](args)


if __name__ == '__main__':
    main()
