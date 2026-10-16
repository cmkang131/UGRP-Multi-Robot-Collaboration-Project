"""Rule-based structure-pixel counting for a recorded wrist frame (no network, no ground truth).

Same family of rules v6e uses on carry frames (harness/own_beam_edge.py: PIL-HSV hue mask for the yellow-green beam,
harness/owncam_view.valid_pixel_mask for the fisheye rim), extended with a wall colour model and a top-down column
scan: in every image column, the wall is the run of wall-coloured pixels that starts at the top of the valid area and
ends where the floor (saturated blue) or a beam/gripper colour begins. Objects standing on the floor (beam, robots,
shadows) sit below that boundary and are not counted. Tag pixels (white/black squares inside the run) are counted
apart and excluded from the structure fraction.
"""
from __future__ import annotations

import cv2
import numpy as np

# cv2 HSV scale: H 0-179, S/V 0-255. own_beam_edge's PIL bounds are hue 25-90 / 255 -> 12-63 here, sat >= 100, val >= 60.
BEAM = dict(h_lo=12, h_hi=63, s_min=100, v_min=60)
BLUE_H = (85, 125)
WALL_S_MAX = 105          # wall band saturation 25-70 in the recorded renders, floor >= 112 even far away
WALL_V = (22, 140)
FLOOR_S_MIN = 108
FLOOR_V_MIN = 28
TAG_WHITE = dict(v_min=150, s_max=70)
TAG_BLACK_V = 22
MIN_RUN = 6               # px; shorter runs are noise
REFL_STEP = None          # optional: end a run at a brightness step below this ratio (mirror image of the wall on the glossy floor); off by default, it also cuts real wall bands
REFL_MIN_RUN = 12
REFL_SPAN = 6
LEAD_SKIP = 60            # px of non-wall (sky / dark background) allowed above the wall run


def masks(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = (hsv[..., i].astype(np.int16) for i in range(3))
    beam = (h >= BEAM['h_lo']) & (h <= BEAM['h_hi']) & (s >= BEAM['s_min']) & (v >= BEAM['v_min'])
    blue = (h >= BLUE_H[0]) & (h <= BLUE_H[1])
    floor = blue & (s >= FLOOR_S_MIN) & (v >= FLOOR_V_MIN)
    wall = ~beam & ~floor & (v >= WALL_V[0]) & (v <= WALL_V[1]) & (s <= WALL_S_MAX)
    white = (v >= TAG_WHITE['v_min']) & (s <= TAG_WHITE['s_max']) & ~beam
    black = v < TAG_BLACK_V
    return dict(h=h, s=s, v=v, beam=beam, floor=floor, wall=wall, white=white, black=black)


def structure(bgr, valid):
    """Return (structure_mask, tag_mask, beam_mask, stats) at full resolution.

    structure_mask: wall run pixels minus tag pixels. tag_mask: tag-like pixels inside wall runs.
    """
    m = masks(bgr)
    hgt, wid = valid.shape
    wallish = m['wall'] | m['white']          # tag whites do not end a run
    stop = m['floor'] | m['beam']
    run = np.zeros((hgt, wid), bool)
    state = np.zeros(wid, np.int8)            # 0 = before run, 1 = in run, 2 = finished
    lead = np.zeros(wid, np.int16)
    length = np.zeros(wid, np.int16)
    vs = cv2.blur(m['v'].astype(np.float32), (1, 9))
    for r in range(hgt):
        ok = valid[r]
        w = wallish[r] & ok
        st = stop[r] & ok
        dark = m['black'][r] & ok
        inrun = (state == 1)
        # start a run
        start = (state == 0) & w
        state = np.where(start, 1, state)
        # a running column ends at a stop pixel; black pixels may belong to tags inside the run
        ratio = vs[min(r + REFL_SPAN, hgt - 1)] / np.maximum(vs[max(r - REFL_SPAN, 0)], 1.)
        end = inrun & (st | ((ratio < REFL_STEP) & (length >= REFL_MIN_RUN)) if REFL_STEP else st)
        state = np.where(end, 2, state)
        # a not-yet-started column that sees floor/beam first has no wall above the boundary
        state = np.where((state == 0) & st, 2, state)
        lead += ((state == 0) & ok).astype(np.int16)
        state = np.where((state == 0) & (lead > LEAD_SKIP), 2, state)
        cur = (state == 1) & ok & (w | dark | (inrun & ~st))
        length = np.where(cur, length + 1, length)
        run[r] = cur
    # keep only vertical runs long enough
    lab_run = run.copy()
    # remove short runs per column
    col_len = lab_run.sum(axis=0)
    lab_run[:, col_len < MIN_RUN] = False
    tag_seed = (m['white'] | m['black']) & lab_run
    tag = cv2.dilate(cv2.morphologyEx(tag_seed.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)),
                     np.ones((5, 5), np.uint8)) > 0
    # tag mask must be limited to compact blobs; drop it if nearly everything in the run is 'tag'
    tag &= lab_run
    struct = lab_run & ~tag
    return struct, tag, m['beam'] & valid, m
