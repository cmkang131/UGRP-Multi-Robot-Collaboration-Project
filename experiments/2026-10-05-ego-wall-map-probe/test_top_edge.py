"""``top_edge_px`` option: a run top on the first frame rows is not a wall top. Synthetic, standalone. Refs #216.

The first rows of the undistorted frame are darker (remap border), which splits the uniform run of a wall that really
continues out of the top of the frame. The run top then reads row 1-4 instead of 0 and ``h`` is solved from that row: a
lower bound mistaken for the wall height (0.13 m for a 0.40 m wall in the recorded search pose, 214 of 444 faces). The
option (default 0 = off, the behaviour before #405) reads a run top within ``top_edge_px`` rows of the frame top as
"leaves the frame": ``h`` stays NaN and ``h_lb`` carries the bound.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_floor_patch_extent import POSE_740  # noqa: E402
import height_free_wall as hfw  # noqa: E402

EXTENT = {'floor_patch_max_m': hfw.FLOOR_PATCH_DIAGONAL_M}


class TopEdgeTests(unittest.TestCase):
    def setUp(self):
        img, _ = POSE_740.render(plane_x=1.9)
        self.img = img.copy()
        self.img[:3] = 40                       # darkened border rows: a step of 20 levels to the wall (60)
        self.top = np.full(len(POSE_740.cols), img.shape[0], int)

    def scan(self, **params):
        return hfw.detect(self.img, POSE_740.cm, params={**EXTENT, **params}, self_top=self.top, loaded=False)

    def test_off_reads_the_border_step_as_the_wall_top(self):
        s = self.scan()
        ok = np.isfinite(s['vb'][:, 0])
        self.assertGreater(int(ok.sum()), 80)
        self.assertTrue(np.all(s['vt'][ok, 0] == 3))
        self.assertTrue(np.all(np.isfinite(s['h'][ok, 0])))
        self.assertLess(float(np.nanmedian(s['h'][:, 0])), 0.25)           # a lower bound posing as the height (true 0.40)

    def test_on_reports_a_lower_bound_instead(self):
        s = self.scan(top_edge_px=4)
        ok = np.isfinite(s['vb'][:, 0])
        self.assertGreater(int(ok.sum()), 80)
        self.assertTrue(np.all(np.isnan(s['h'][ok, 0])))
        self.assertTrue(np.all(np.isfinite(s['h_lb'][ok, 0])))
        self.assertTrue(np.all(s['h_lb'][ok, 0] >= self.scan()['h'][ok, 0] - 1e-9))

    def test_contacts_ranges_and_faces_do_not_change(self):
        a, b = self.scan(), self.scan(top_edge_px=4)
        for k in ('vb', 'r', 'b', 'c'):
            self.assertTrue(np.array_equal(a[k], b[k], equal_nan=True), k)
        self.assertEqual(len(hfw.link_segments(a)), len(hfw.link_segments(b)))
        self.assertTrue(all(s['height_m'] is None for s in hfw.link_segments(b)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
