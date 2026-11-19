#!/usr/bin/env python3
"""PNG cards for the ceiling-camera calibration (floor cards) and the start card, 300 dpi, true size.

    python3 scripts/make_floor_cards.py out_dir/ --ids 0 1 2 3 4 5 --size-cm 15

Print at 100 % (no fit-to-page). Dictionary and start-card id come from real_robot/overhead_real.py, so they
never clash with the robot top cards (4x4 ids 40..48) or the destination signs.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from real_robot import overhead_real as orl  # noqa: E402

DPI = 300


def card(marker_id, size_cm, inner=0.75):
    px = int(round(size_cm / 2.54 * DPI))
    m = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, orl.FLOOR_DICT)), marker_id, int(px * inner))
    img = np.full((px + 120, px), 255, np.uint8)
    o = (px - m.shape[0]) // 2
    img[o:o + m.shape[0], o:o + m.shape[0]] = m
    label = f'{"START" if marker_id == orl.SYNC_CARD_ID else "floor"} {orl.FLOOR_DICT} id {marker_id}  card {size_cm} cm  (arrow = card top)'
    cv2.putText(img, label, (20, px + 70), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 2)
    cv2.arrowedLine(img, (px // 2, o - 10), (px // 2, max(5, o - 60)), 0, 6)
    return img


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('out', type=Path)
    p.add_argument('--ids', type=int, nargs='+', default=[0, 1, 2, 3, 4, 5])
    p.add_argument('--size-cm', type=float, default=15.)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for i in a.ids + [orl.SYNC_CARD_ID]:
        cv2.imwrite(str(a.out / f'card_{i:02d}.png'), card(i, a.size_cm))
    print(f'{len(a.ids) + 1} cards -> {a.out} (print at 100 %, {DPI} dpi)')
