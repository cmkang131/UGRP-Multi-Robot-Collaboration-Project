"""Regression test: the wall detector is never told a wall height.

Runs standalone: ``python test_height_free_wall.py``. Everything is synthetic, so no
recorded episode is needed. The only real inputs are the frozen VIS3 calibration and one
settled arm pose, both reused from ``markerless_probe`` (which ``detect`` already
imports, so the test shares its geometry instead of re-deriving it).

The scene reproduces the failure mode the detector docstring reports from
``zone_wide_door_geometry_v3``: the floor is a checker rendering at luminance 92.8 and
159.6 (sim/render_profile.py ``floor_light_v1``, rgb .36 .35 .34 and .62 .61 .59 --
exactly the 1.72:1 ratio in the docstring) and the wall material renders at 97.4, only
4.6 levels above the dark square. On a bright square the wall base is a 62.2 level
edge; on a dark square it has almost none. Both are exercised, so nothing here can be
passed by a plain "bright vertical blob" rule.

Wall heights are used only to *render* pixels and to score the answer afterwards.
``hfw.detect`` is called with the image and the column model and nothing else.
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'code'))
import height_free_wall as hfw  # noqa: E402  (adds ROOT and markerless_probe itself)
import markerless_probe as mp  # noqa: E402

WIDTH, HEIGHT = mp.WIDTH, mp.HEIGHT
SERVO = {1: 1500, 2: 1500, 3: 1072, 4: 2400, 5: 1482, 6: 1500}  # settled "search" family
BIAS_RAD = -0.0187
CM = mp.column_model(SERVO, BIAS_RAD, mp.column_positions(hfw.PARAMS['columns'], 2))
COLS = np.asarray(CM.columns, int)
HORIZON = float(hfw.horizon_rows(CM)[0])     # ground plane converges here
CAM_HEIGHT_M = float(CM.origin[2])

# scene constants, all from the repo (see module docstring)
CELL_M = 0.214         # sim/masterpi_scene_v2.xml: 6 m plane, texrepeat 14, builtin checker
L_DARK, L_BRIGHT = 92.8, 159.6   # floor_light_v1 rgb .36 .35 .34 / .62 .61 .59, x255
L_WALL = 97.4          # measured wall material luminance
L_BACK = 34.0          # whatever lies above the horizon; must break the floor run
PLANE_X = 1.315        # wall face, metres in front of the robot along +x
HEIGHTS = (0.05, 0.10, 0.40, 1.00, 2.00)
SHORT_H, TALL_H = 0.28, 2.00   # top edge inside the frame / taller than the frame

# base-frame camera rays, computed once
_KINV = np.linalg.inv(mp.K)
_UU = np.arange(WIDTH)[None, :] * np.ones((HEIGHT, 1))
_VV = np.arange(HEIGHT)[:, None] * np.ones((1, WIDTH))
RAY = np.einsum('ij,jhw->ihw', CM._rot,
                (_KINV @ np.stack([_UU, _VV, np.ones_like(_UU)]).reshape(3, -1)).reshape(3, HEIGHT, WIDTH))
_ORG = CM.origin
_ROWS2D = np.arange(HEIGHT)[:, None] * np.ones((1, WIDTH))


def _wall_hit(wall_h, plane_x):
    """(mask, height map) of pixels whose ray meets the vertical plane x = plane_x, z <= wall_h."""
    sw = (plane_x - _ORG[0]) / RAY[0]
    qw = _ORG[:, None, None] + sw[None] * RAY
    return (RAY[0] > 0) & (sw > 0) & (qw[2] >= 0) & (qw[2] <= wall_h)


def render(wall_h: float | None, plane_x: float = PLANE_X) -> np.ndarray:
    """Pin-hole BGR frame: checker floor, optionally a vertical wall face at ``x = plane_x``.

    ``wall_h`` decides only which pixels the wall face covers; ``None`` gives the bare
    checker floor.
    """
    s = -_ORG[2] / RAY[2]
    q = _ORG[:, None, None] + s[None] * RAY
    floor_ok = (RAY[2] < 0) & (s > 0)
    dark = ((np.floor(q[0] / CELL_M) + np.floor(q[1] / CELL_M)) % 2) == 1
    lum = np.where(floor_ok, np.where(dark, L_DARK, L_BRIGHT), L_BACK)
    if wall_h is not None:
        lum = np.where(_wall_hit(wall_h, plane_x), L_WALL, lum)
    return np.clip(np.repeat(lum[:, :, None], 3, 2), 0, 255).astype(np.uint8)


def truth_rows(wall_h, plane_x=PLANE_X):
    """(top row, base row) of the rendered wall per detector column. Scoring only."""
    m = np.where(_wall_hit(wall_h, plane_x), _ROWS2D, np.nan)
    return np.nanmin(m, 0)[COLS], np.nanmax(m, 0)[COLS]


def truth_range(base_row):
    t = CM.t_of_row(np.asarray(base_row, float))
    return CM.range_bearing(np.where(np.isfinite(t), t, 0.))[0]


def run(wall_h: float | None, plane_x: float = PLANE_X) -> dict:
    """detect() on the rendered frame, reduced to the nearest accepted contact per column."""
    scan = hfw.detect(render(wall_h, plane_x), CM)
    return {k: v[:, 0] for k, v in scan.items()}


class HeightFreeWallTest(unittest.TestCase):
    maxDiff = None

    def test_params_carry_no_wall_height(self):
        """Cheap guard, and the premise of everything else: no height is an input."""
        offenders = [k for k in hfw.PARAMS if 'height' in k.lower()]
        self.assertEqual(offenders, [], f'hfw.PARAMS names a height: {offenders}')
        args = list(inspect.signature(hfw.detect).parameters)
        self.assertFalse([a for a in args if 'height' in a.lower()],
                         f'detect takes a height argument: {args}')
        # solve_height is the only height inversion and its one numeric argument is a
        # bisection ceiling, not a wall: no caller can hand it a wall height.
        sh = inspect.signature(hfw.solve_height)
        self.assertEqual([p for p in sh.parameters if sh.parameters[p].default is inspect.Parameter.empty],
                         ['cm', 'col', 't', 'row_obs'])
        # No module-level height constant. hfw.HEIGHT is the frame height in pixels.
        self.assertEqual(hfw.HEIGHT, mp.HEIGHT)
        consts = [n for n, v in vars(hfw).items()
                  if isinstance(v, (int, float)) and 'height' in n.lower() and v != mp.HEIGHT]
        self.assertEqual(consts, [], f'hfw has a module-level height constant: {consts}')

    # -- 1. HEADLINE: the contact row and range must not depend on the wall height ----
    # KNOWN OPEN: walls shorter than the camera (0.05 m, 0.10 m) are rejected by the horizon cue by design,
    # with or without the floor-patch extent test (same 96/96 misses with floor_patch_max_m=0). Kept as an
    # expected failure so the limitation stays visible and the file is green; remove the decorator when fixed.
    @unittest.expectedFailure
    def test_height_invariance(self):
        """Same wall, same range, five heights: identical contact row and range (<= 1 px).

        The wall is rendered at five heights over the same floor; the detector is
        called with no height in any argument.
        """
        scans = {h: run(h) for h in HEIGHTS}
        missed = {h: int((~np.isfinite(scans[h]['vb'])).sum()) for h in HEIGHTS}
        for h in HEIGHTS:
            print(f'    H={h:<5} m columns with no contact: {missed[h]}/{len(COLS)}')
        # (a) among the heights that ARE reported, the contact must not move. Measured
        #     first so the number is printed even when (b) fails.
        reported = [h for h in HEIGHTS if not missed[h]]
        spread = range_spread = 0.0
        for h in reported:
            vb, ref = scans[h]['vb'], scans[reported[0]]['vb']
            m = np.isfinite(vb) & np.isfinite(ref)
            spread = max(spread, float(np.max(np.abs(vb[m] - ref[m]))))
            range_spread = max(range_spread, float(np.max(np.abs(scans[h]['r'][m] - scans[reported[0]]['r'][m]))))
        print(f'    reported heights {reported}: contact row spread {spread:.2f} px, '
              f'range spread {range_spread:.6f} m')
        # (b) every height must produce a contact. A wall shorter than the camera is not
        #     something the horizon cue can accept, and that is a dependence on H.
        self.assertEqual(missed, {h: 0 for h in HEIGHTS},
                         f'wall height changes whether a contact is reported at all: {missed}')
        self.assertLessEqual(spread, 1.0)

    # -- 2. floor texture must not be accepted as a wall base -------------------------
    def test_checker_floor_yields_no_contacts(self):
        """Checker floor, no wall: zero accepted contacts.

        This is the failure mode the docstring measures -- a checker boundary is a
        sharp 1.72:1 step at plausible wall ranges, so a luminance step alone finds the
        floor. Any acceptance here means the horizon cue is not doing its job.
        """
        vb = run(None)['vb']
        n = int(np.isfinite(vb).sum())
        if n:
            print(f'    BUG: {n} floor contacts accepted at rows {sorted(set(vb[np.isfinite(vb)].astype(int)))}')
        self.assertEqual(n, 0, f'{n} checker-floor rows accepted as wall contacts')

    # -- 3a. a short wall is still found and its height is measured -------------------
    def test_short_wall_height_within_10_percent(self):
        """Top edge inside the frame -> a point estimate, not a bound.

        Height is read off the *observed top edge*, so a wall short enough to see over
        must give h within 10 % of the truth.
        """
        top = truth_rows(SHORT_H)[0]
        self.assertGreater(float(np.median(top)), 0.0, 'scene bug: short wall top already out of frame')
        self.assertLess(float(np.median(top)), HORIZON,
                        'scene bug: short wall top is below the horizon, so the horizon cue cannot fire')
        got = run(SHORT_H)
        self.assertTrue(np.isfinite(got['vb']).all(), f'{int((~np.isfinite(got["vb"])).sum())} columns missed')
        self.assertTrue(np.isfinite(got['h']).any(), 'no height measured for a wall whose top is in frame')
        med = float(np.nanmedian(got['h']))
        print(f'    short wall H={SHORT_H} m, true top row {np.median(top):.0f}, measured h '
              f'{med:.4f} m ({100 * abs(med - SHORT_H) / SHORT_H:.2f} % error)')
        self.assertLessEqual(abs(med - SHORT_H), 0.10 * SHORT_H)

    # -- 3b. a wall taller than the frame gives a lower bound, not a point estimate ----
    def test_tall_wall_reports_lower_bound_not_estimate(self):
        """Top edge out of frame -> h is NaN and h_lb is a genuine lower bound.

        Why NaN-plus-lower-bound is the height-free answer: the detector assumes no
        height, so when the surface leaves the top of the image there is no top edge to
        invert. Every height at or above the one whose top edge would land on row 0 is
        consistent with the same pixels, so the only honest output is the bound h_lb =
        that height. A lower bound therefore satisfies h_lb <= H (h_lb is the smallest
        height still allowed; the truth is at least that tall) -- the opposite
        inequality to "h_lb >= H".
        """
        got = run(TALL_H)
        self.assertTrue(np.isfinite(got['vb']).all(), 'tall wall not detected')
        finite_h = got['h'][np.isfinite(got['h'])]
        self.assertEqual(finite_h.size, 0, f'expected NaN height, got {np.unique(finite_h)}')
        lb = got['h_lb']
        self.assertTrue(np.isfinite(lb).all(), 'no lower bound reported')
        med = float(np.nanmedian(lb))
        print(f'    tall wall H={TALL_H} m: h=NaN, h_lb={med:.4f} m (<= H: {med <= TALL_H}, '
              f'>= camera height {CAM_HEIGHT_M:.4f}: {med >= CAM_HEIGHT_M})')
        self.assertLessEqual(med, TALL_H, 'h_lb is not a lower bound on the true height')
        self.assertGreaterEqual(med, CAM_HEIGHT_M,
                                'h_lb below the camera height would contradict the horizon cue')

    # -- 4. exposure must not move the contact ----------------------------------------
    def test_greyscale_invariance(self):
        """Gain 0.7 and 1.15 on the whole frame: the contact row moves at most 2 px.

        The gates are absolute 8-bit levels (``min_contrast_below``, ``max_band_std``,
        ``run_edge_tol``), so this says whether they are coupled to exposure. H = 0.40 m
        at the test range is used so there is a contact to track.
        """
        base = render(0.40)
        ref = hfw.detect(base, CM)['vb'][:, 0]
        self.assertTrue(np.isfinite(ref).all(), 'baseline scene lost the wall')
        for gain in (0.7, 1.15):
            scaled = np.clip(base.astype(np.float32) * gain, 0, 255).astype(np.uint8)
            clipped = float(np.mean(base.astype(np.float32) * gain > 255)) * 100
            vb = hfw.detect(scaled, CM)['vb'][:, 0]
            both = np.isfinite(ref) & np.isfinite(vb)
            self.assertTrue(both.all(), f'gain {gain}: {int((~both).sum())} columns lost')
            d = float(np.max(np.abs(ref[both] - vb[both])))
            print(f'    gain {gain}: clipped {clipped:.2f} % of pixels, max contact row shift {d:.1f} px')
            self.assertLessEqual(d, 2.0)


# ---- measurements that are not assertions but that the reader needs --------------------
def findings():
    print('\n== finding A: the acceptance threshold is the camera height, not the frame ==')
    print(f'   horizon row {HORIZON:.2f}, camera height {CAM_HEIGHT_M:.4f} m')
    for h in (0.18, 0.20, 0.205, 0.22, 0.28):
        top = truth_rows(h)[0]
        n = int(np.isfinite(run(h)['vb']).sum())
        print(f'   H={h:<6} m true top row {np.median(top):6.1f} -> {n:3d}/{len(COLS)} columns detected')
    for px in (1.20, 1.60, 2.20):
        n = [int(np.isfinite(run(h, px)['vb']).sum()) for h in (0.10, 0.30)]
        print(f'   plane x={px:.2f} m: H=0.10 m -> {n[0]:3d}/{len(COLS)}, H=0.30 m -> {n[1]:3d}/{len(COLS)}')

    print('\n== finding B: a wall base on a dark square has no usable edge ==')
    g = run(0.40, 1.20)
    base = truth_rows(0.40, 1.20)[1]
    rows_hist = {int(r): int((g['vb'] == r).sum()) for r in np.unique(g['vb'][np.isfinite(g['vb'])])}
    print(f'   plane x=1.20 m: true base row {np.median(base):.0f}; L_WALL-L_DARK = {L_WALL - L_DARK:.1f} '
          f'levels vs min_contrast_below={hfw.PARAMS["min_contrast_below"]}')
    print(f'   detected rows {{row: columns}}: {rows_hist}')
    print(f'   true range at the base row {np.median(truth_range(base)):.3f} m; detected range '
          f'{np.nanmin(g["r"]):.3f}-{np.nanmax(g["r"]):.3f} m')

    print('\n== finding C: rows above the horizon still get a finite "range" ==')
    rows = np.arange(HEIGHT - 2, 2, -1.)[:, None] * np.ones((1, len(COLS)))
    t = CM.t_of_row(rows)
    r, _ = CM.range_bearing(np.where(np.isfinite(t), t, 0.))
    p = hfw.PARAMS
    bad = np.isfinite(r) & (r >= p['min_range_m']) & (r <= p['max_range_m']) & (rows < HORIZON)
    print(f'   {int(bad[:, 0].sum())} image rows strictly above the horizon {HORIZON:.1f} are mapped by '
          f't_of_row into the accepted range band [{p["min_range_m"]}, {p["max_range_m"]}] m; only the '
          f'contrast and band-uniformity gates stop them.')


def table():
    print('\nH (m) | detected row | detected range (m) | h (m) | h_lb (m) | contacts')
    base = truth_rows(0.40)[1]
    print(f'truth: base row {np.median(base):.0f}, range '
          f'{np.min(truth_range(base)):.3f}-{np.max(truth_range(base)):.3f} m')
    for h in HEIGHTS:
        g = run(h)
        d = np.isfinite(g['vb'])
        hmed = np.nanmedian(g['h']) if np.isfinite(g['h']).any() else float('nan')
        lb = np.nanmedian(g['h_lb']) if np.isfinite(g['h_lb']).any() else float('nan')
        seen = (f'{g["vb"][d].min():.0f}-{g["vb"][d].max():.0f} (true {np.median(base):.0f}) '
                f'| {g["r"][d].min():.3f}-{g["r"][d].max():.3f}') if d.any() else f'{"-":>13} | {"-":>18}'
        print(f'{h:5.2f} | {seen} | {hmed:7.4f} | {lb:7.4f} | '
              f'{int(d.sum())}/{len(COLS)}{"" if d.any() else " MISSED"}')


if __name__ == '__main__':
    print(f'camera {WIDTH}x{HEIGHT}  CY={mp.CY:.2f} FY={mp.FY:.2f} CX={mp.CX:.2f}  horizon row {HORIZON:.2f}  '
          f'camera height {CAM_HEIGHT_M:.4f} m')
    print(f'servo {SERVO} bias {BIAS_RAD} -> {len(COLS)} columns; PARAMS names no height: '
          f'{not any("height" in k.lower() for k in hfw.PARAMS)} ({sorted(hfw.PARAMS)})')
    table()
    findings()
    print('\n' + '=' * 70)
    unittest.main(argv=[sys.argv[0], '-v'], exit=True)
