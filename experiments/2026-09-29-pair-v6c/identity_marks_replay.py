"""Pre-close identity on synthetic floor marks (no physics, no models).

Adversarial review question: can beam-coloured pixels that are NOT a beam pass
the pre-close partial-view check? Starting from one recorded grasp-pose frame
(tests/fixtures/zone_pair_v6c/grasp_pose_ex+8mm_r1.jpg), every beam-colour
pixel is painted as dark floor, then a lime or yellow mark of a given half
width is painted beyond the band on the tracked axis. Both tracks start from
the same anchored beam (the v6c standoff fit of the paired standoff frame).

RestingBeamTrack = registered v5h/b-only path (v1 lime patch).
GraspRangeBeamTrack = v6c (grasp-range colour + contiguous beam cross-section).

A single view cannot separate a planar mark from a raised surface of the same
image footprint, so a beam-width mark is expected to pass both; the point is
what each path accepts below that.  Usage: python identity_marks_replay.py
"""
from __future__ import annotations

import base64
import hashlib
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import tests.test_zone_pair_v6c as fixtures  # noqa: E402  (fixture loader with hash checks)
from harness import owncam_pair_beam as v1  # noqa: E402
from harness import owncam_pair_beam_v2 as v2  # noqa: E402
from harness.owncam_view import base_rays  # noqa: E402
from harness.zone_pair_beam_track import RestingBeamTrack  # noqa: E402
from harness.zone_pair_grasp_entry_v6c import GraspRangeBeamTrack  # noqa: E402

COLOURS = {'lime': (40, 200, 120), 'yellow': (40, 190, 200)}   # BGR; HSV hue 45 / 28
HALF_WIDTHS_M = (.006, .012, .02)


def main():
    anchor = GraspRangeBeamTrack()
    assert anchor.observe_standoff(*fixtures.frame('standoff_ex+8mm_r1'), 3)
    beam = anchor.beam
    grasp, servo = fixtures.frame('grasp_pose_ex+8mm_r1')
    img0 = v1.decode(grasp['image'])
    origin, rays, xs, ys, valid = base_rays(servo, 1)
    xi, yi = xs.astype(int), ys.astype(int)
    down = valid & (rays[:, 2] < -1e-6)
    s = np.where(down, (v1.BEAM_TOP_Z_M - origin[2]) / np.where(down, rays[:, 2], -1.), np.nan)
    rel = origin[:2] + s[:, None] * rays[:, :2] - np.asarray(beam['grip_base_m'])
    u = np.array([math.cos(beam['axis_heading_rad']), math.sin(beam['axis_heading_rad'])])
    a, n = rel @ u, rel @ np.array([-u[1], u[0]])
    colour = v2.beam_colour_mask(img0)
    rows = []
    for name, bgr in COLOURS.items():
        for half in HALF_WIDTHS_M:
            img = img0.copy()
            img[colour] = (28, 28, 28)                              # no beam top: dark floor
            sel = down & (np.abs(n) <= half) & (a > .02) & (a < .30)
            img[yi[sel], xi[sel]] = bgr
            data = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()
            obs = {**grasp, 'image': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest()}
            got = {}
            for cls in (RestingBeamTrack, GraspRangeBeamTrack):
                track = cls()
                track.beam, track.segment, track.t = dict(beam), 3, beam['anchor_time_s']
                got[cls.__name__] = track.estimate(grasp['sim_time'], obs, servo, 3) is not None
            rows.append((name, round(2 * half * 1000), got['RestingBeamTrack'], got['GraspRangeBeamTrack']))
    print('mark colour | mark width (top-plane mm) | v5h/b-only RestingBeamTrack accepts | v6c accepts')
    for row in rows:
        print(' | '.join(str(x) for x in row))
    return rows


if __name__ == '__main__':
    main()
