"""Real image column profile around the floor/wall boundary, with every row estimate marked (offline).

Refs #216. **Physical simulation runs: 0.** Reads the recorded JPEG and a ``diag_bias.py`` ``column_rows.csv``
(which holds, per frame and detector column, the segmentation-render boundary and the ground-truth rows of the
five scoring constructions V0..V4 and the detector rows). Prints the luminance L and chroma Cr of the detector's
own strip (5 px wide, the strip the detector averages) for the rows around the boundary.

Marks (row numbers are image rows of the undistorted 640x480 frame; a boundary 'edge' is the lowest wall row + 0.5):
  seg    lowest wall pixel + 0.5 of the segmentation render through the recorded camera (reference, needs no model)
  det    detector contact ``vb`` with the corrected load rule        det_old: with the legacy load rule
  V0     legacy ground-truth row (model camera, servo[3] >= 900)    V4: true camera, exact trace (current scorer)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import height_free_wall as hfw  # noqa: E402
import wall_probe as wp  # noqa: E402


def main(a):
    ep = Path(a.episode)
    frames, _ = wp.resolve_frames(ep, a.robot)
    row = frames[a.frame - 1]
    und = mp.undistort(cv2.imread(str(ep/row['path']), cv2.IMREAD_COLOR))
    cols = mp.column_positions(wp.FROZEN_DETECTOR['columns'], wp.FROZEN_DETECTOR['strip_half_px'])
    j = int(np.flatnonzero(cols == a.col)[0])
    strips = hfw.ColumnStrips(und, cols, int(wp.FROZEN_DETECTOR['strip_half_px']))
    rec = next(r for r in csv.DictReader(open(a.column_rows))
               if int(r['frame_index']) == a.frame and int(r['col']) == a.col)
    marks = {'seg': float(rec['seg_row']), 'det': float(rec['det_row_new']), 'det_old': float(rec['det_row_old']),
             'V0': float(rec['gt_row_V0']), 'V1': float(rec['gt_row_V1']), 'V4': float(rec['gt_row_V4'])}
    print(f"frame {a.frame} ({row['path']}), detector column {a.col}, s1={rec['s1']} s3={rec['s3']}")
    print('marks: ' + ', '.join(f'{k}={v:.2f}' for k, v in marks.items()))
    lo = int(min(marks.values())) - a.pad
    hi = int(max(marks.values())) + a.pad
    print('row      L      Cr   marks')
    for v in range(lo, hi + 1):
        tags = [k for k, m in marks.items() if abs(m - v) < 0.5 or (k in ('seg',) and abs(m - (v + 0.5)) < 0.01)]
        print(f'{v:4d} {strips.L[v, j]:6.1f} {strips.Cr[v, j]:6.1f}   {" ".join(tags)}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--column-rows', required=True)
    ap.add_argument('--frame', type=int, required=True, help='1-based frame_index as in per_frame.csv')
    ap.add_argument('--col', type=int, required=True, help='detector column (image x) as in column_rows.csv')
    ap.add_argument('--pad', type=int, default=4)
    main(ap.parse_args())
