"""``run_step_window`` option: the contact stays on the wall base. Synthetic, standalone. Refs #216.

``run_step_window = k`` splits a uniform surface run where the difference of the k-row means across a row boundary
exceeds ``run_edge_tol`` (default 1: the adjacent-row difference, the behaviour before #405). With k > 1 the rows within
k - 1 of an edge are already split off, so the run of the surface above a candidate has to be read k rows above it, not
one: reading row ``vb - 1`` rejected the true wall base and reported the contact ~2.5 px too high (recorded episodes:
row error -2.5 px, range overestimated at distance). Pinned here on a soft (blurred) wall base:

  * k = 3 puts the median contact row within 1.5 px of the base, and no further from it than k = 1 does;
  * k = 3 gives one wall face.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_floor_patch_extent import POSE_740  # noqa: E402
import height_free_wall as hfw  # noqa: E402


class RunStepWindowTest(unittest.TestCase):
    def setUp(self):
        img, self.base = POSE_740.render(plane_x=1.9)
        self.soft = cv2.GaussianBlur(img, (0, 0), sigmaX=0.01, sigmaY=1.5)

    def median_error(self, k):
        cols, faces = POSE_740.detect(self.soft, floor_patch_max_m=hfw.FLOOR_PATCH_DIAGONAL_M, run_step_window=k)
        hit = np.isfinite(cols) & np.isfinite(self.base)
        self.assertGreater(int(hit.sum()), 80)
        return float(np.median(cols[hit] - self.base[hit])), faces

    def test_k3_contact_row_within_1p5_px_of_the_base_and_not_worse_than_k1(self):
        e1, _ = self.median_error(1)
        e3, _ = self.median_error(3)
        self.assertLessEqual(abs(e3), 1.5, f'k=3: median contact row error {e3} px')
        self.assertLessEqual(abs(e3), abs(e1) + 1e-9, f'k=3 {e3} px vs k=1 {e1} px')

    def test_k3_gives_one_wall_face(self):
        _, faces = self.median_error(3)
        self.assertEqual(len(faces), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
