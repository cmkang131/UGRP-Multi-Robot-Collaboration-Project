"""Map-only prediction (no image, no simulator): how much wall / door-post structure would an UNLOADED look pose see
at every chain checkpoint of the 8-leg route? Route and robot stations are the recorded probe geometry.

usage: python cand_points.py <out.json>
"""
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import geom  # noqa: E402

ROUTE = [[1.0, 0.05], [1.55, 0.05], [2.4, 0.05], [3.2, 0.05], [3.2, -0.6666666666666666], [3.2, -1.3833333333333333],
         [3.2, -2.1], [3.9, -2.1], [4.6, -2.1]]                         # recorded route_check of the carry cases
HALF_BEAM_STATION = 0.425                                               # r1 at beam x - 0.425 (yaw 0), r2 at + 0.425 (yaw pi)
SEARCH_POSE = {'1': 2000, '3': 740, '4': 2320, '5': 1320}               # harness.owncam_drive.SEARCH_POSE (unloaded look)
PANS = (1500, 1230, 1770, 970, 2030, 700, 2300)                          # centre, +-24, +-48, +-72 deg (11.1 PWM/deg)
CARRY_HOVER = {'1': 1500, '3': 611, '4': 1711, '5': 2200, '6': 1500}    # pulses recorded in the carry cases


def predict(servo, pose):
    lab4, valid4 = geom.predict_labels(servo, pose, 4)
    valid = valid4
    lab = lab4
    nv = valid.sum()
    tag = geom.tag_mask(servo, pose)
    n_tag_px = int(cv2.resize(tag.astype(np.uint8), (lab.shape[1], lab.shape[0]), interpolation=cv2.INTER_AREA).astype(bool).sum())
    wall = ((lab == geom.WALL) | (lab == geom.POST)) & valid
    post = (lab == geom.POST) & valid
    # tags in view: connected components of the full-res tag mask
    ncomp, _ = cv2.connectedComponents(tag.astype(np.uint8))
    return {'G': float(wall.sum() / nv), 'G_post': float(post.sum() / nv), 'tags_in_view': int(ncomp - 1),
            'tag_px_frac': float(tag.sum() / (480 * 640))}


def main(out):
    res = []
    for k, (bx, by) in enumerate(ROUTE):
        for rid, dx, yaw in (('r1', -HALF_BEAM_STATION, 0.), ('r2', HALF_BEAM_STATION, math.pi)):
            pose = (bx + dx, by, yaw)
            row = {'checkpoint': k, 'label': 'start' if k == 0 else f'after_L{k-1}', 'robot': rid,
                   'beam_xy': [bx, by], 'robot_xyyaw': [round(pose[0], 3), round(pose[1], 3), round(yaw, 4)], 'looks': {}}
            for pan in PANS:
                servo = {**SEARCH_POSE, '6': pan}
                row['looks'][str(pan)] = predict(servo, pose)
            row['carry_hover_G'] = predict(CARRY_HOVER, pose)['G']
            res.append(row)
    json.dump(res, open(out, 'w'), indent=1)
    print(len(res))


if __name__ == '__main__':
    main(sys.argv[1])
