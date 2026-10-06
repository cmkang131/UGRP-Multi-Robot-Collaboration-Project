"""Horizon above the image: the floor-patch extent test (synthetic, no recorded episode).

Runs standalone: ``python test_floor_patch_extent.py``. Refs #216.

When the camera is pitched down by more than its half field of view the horizon row is negative, so
``above_is_vertical = run_top <= horizon`` can never hold and every wall is rejected (101 of 247
wall-visible frames of the v98 dev episode). ``height_free_wall.PARAMS['floor_patch_max_m']`` replaces
the test, on those columns only, with: a uniform run must span at least one floor-texture patch of
floor-plane distance to not be floor.

Pinned here, with a 0.571 m checker floor (the recorded scene) rendered from the settled arm poses of
the recorded episode:

  * pose 740  (horizon -29 px, floor in view out to ~5 m): a wall IS found, at its true base row, and only
    when the extent test is on;
  * bare floor, poses 740 and 508: no wall FACE (a floor run cannot stay uniform over 0.81 m of floor, and
    the few columns whose trace runs along a cell diagonal are isolated, so adjacent-column linking drops them);
  * pose 508 sees only ~0.15-0.5 m of floor, less than one cell, so the extent test cannot tell a wall from
    a floor patch there and stays silent (the recorded episode's clamp variant, which does not, reported
    faces on 335 invisible frames; that is real-texture behaviour and is not reproduced by this flat render).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'code'))
import height_free_wall as hfw  # noqa: E402
import markerless_probe as mp  # noqa: E402

WIDTH, HEIGHT = mp.WIDTH, mp.HEIGHT
CELL_M = 16.0/14/2                       # recorded scene: 16 m plane, texrepeat 14, 2 cells per repeat
L_DARK, L_BRIGHT, L_WALL = 92.8, 159.6, 60.0   # wall well away from both cells: contrast is not what is tested
BIAS_RAD = -0.0187
_KINV = np.linalg.inv(mp.K)
_UU = np.arange(WIDTH)[None, :] * np.ones((HEIGHT, 1))
_VV = np.arange(HEIGHT)[:, None] * np.ones((1, WIDTH))


class Scene:
    def __init__(self, s3, s4, s5):
        servo = {1: 2000, 2: 1500, 3: s3, 4: s4, 5: s5, 6: 1500}
        self.cm = mp.column_model(servo, BIAS_RAD, mp.column_positions(hfw.PARAMS['columns'], 2))
        self.cols = np.asarray(self.cm.columns, int)
        self.org = self.cm.origin
        self.ray = np.einsum('ij,jhw->ihw', self.cm._rot,
                             (_KINV @ np.stack([_UU, _VV, np.ones_like(_UU)]).reshape(3, -1)).reshape(3, HEIGHT, WIDTH))
        self.horizon = float(hfw.horizon_rows(self.cm).max())

    def render(self, plane_x=None, wall_h=0.40):
        s = -self.org[2] / self.ray[2]
        q = self.org[:, None, None] + s[None] * self.ray
        floor_ok = (self.ray[2] < 0) & (s > 0)
        dark = ((np.floor(q[0] / CELL_M) + np.floor(q[1] / CELL_M)) % 2) == 1
        lum = np.where(floor_ok, np.where(dark, L_DARK, L_BRIGHT), 34.0)
        wall = np.zeros((HEIGHT, WIDTH), bool)
        if plane_x is not None:
            sw = (plane_x - self.org[0]) / self.ray[0]
            qw = self.org[:, None, None] + sw[None] * self.ray
            wall = (self.ray[0] > 0) & (sw > 0) & (qw[2] >= 0) & (qw[2] <= wall_h)
            lum = np.where(wall, L_WALL, lum)
        rows = np.where(wall, np.arange(HEIGHT)[:, None] * np.ones((1, WIDTH)), np.nan)
        base = np.full(WIDTH, np.nan)
        if wall.any():
            with np.errstate(all='ignore'):
                base = np.nanmax(rows, 0)
        return np.clip(np.repeat(lum[:, :, None], 3, 2), 0, 255).astype(np.uint8), base[self.cols]

    def detect(self, img, **params):
        """(per-column contact rows, linked wall faces)."""
        scan = hfw.detect(img, self.cm, params=params, self_top=np.full(len(self.cols), HEIGHT, int), loaded=False)
        return scan['vb'][:, 0], hfw.link_segments(scan, params)


POSE_740 = Scene(740, 2320, 1320)
POSE_508 = Scene(508, 2432, 1320)


class FloorPatchExtentTest(unittest.TestCase):
    def test_poses_have_the_horizon_above_the_image(self):
        self.assertLess(POSE_740.horizon, -10)
        self.assertLess(POSE_508.horizon, -10)

    def test_default_is_one_floor_patch_diagonal(self):
        self.assertAlmostEqual(hfw.PARAMS['floor_patch_max_m'], CELL_M*2**.5, delta=0.01)

    def test_wall_found_at_its_base_only_with_the_extent_test(self):
        img, base = POSE_740.render(plane_x=1.9)
        self.assertTrue(np.isfinite(base).sum() > 60)
        off, off_faces = POSE_740.detect(img, floor_patch_max_m=0.)
        on, on_faces = POSE_740.detect(img)
        self.assertEqual(int(np.isfinite(off).sum()), 0, 'horizon test alone must reject every row')
        self.assertEqual(off_faces, [])
        hit = np.isfinite(on) & np.isfinite(base)
        self.assertGreater(int(hit.sum()), 80, 'nearly every column sees the wall base')
        err = on[hit] - base[hit]                      # vb is the first row below the last wall row
        self.assertTrue(float(np.min(err)) >= 0 and float(np.max(err)) <= 1.5, f'contact row error {np.unique(err)} px')
        self.assertEqual(len(on_faces), 1, 'one wall face')
        self.assertGreaterEqual(on_faces[0]['n_columns'], 80)

    def test_bare_floor_is_not_a_wall_face(self):
        # A few isolated columns can report a contact on a bare checker floor: a column trace that runs along
        # a cell diagonal stays one colour for more than 0.81 m. Adjacent-column linking (min_run_columns)
        # removes them, so the wall-face output must be empty.
        for name, scene in (('740', POSE_740), ('508', POSE_508)):
            img, _ = scene.render(plane_x=None)
            cols, faces = scene.detect(img)
            self.assertEqual(faces, [], f'pose {name}: wall face reported on a bare checker floor')
            self.assertLessEqual(int(np.isfinite(cols).sum()), 8, f'pose {name}: isolated contacts {np.isfinite(cols).sum()}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
