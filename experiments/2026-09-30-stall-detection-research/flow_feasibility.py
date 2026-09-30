"""Offline feasibility: does the wrist RGB video during CARRY contain an ego-motion signal?

For each recorded case, robots r1/r2, frame pairs ~LAG seconds apart while the beam is lifted and
both jaws hold it. Windows are labelled (scoring only, from GT + issued commands):
  STALL  : issued displacement >= 25 mm but GT displacement <= 0.3 x issued
  MOVING : issued displacement >= 25 mm and GT displacement >= 0.6 x issued
  REST   : issued < 3 mm and GT < 3 mm
Image features (allowed inputs only: two own wrist frames):
  mad_full, mad_dark   mean abs gray difference (levels)
  pc_dark_px, pc_resp  phase-correlation shift (px) and response on the dark central ROI
  pc_full_px           phase correlation on the whole valid image
  fb_dark_px           median Farneback flow magnitude (px) on the dark ROI
  beam_edge_dpx        change of beam-band edge rows (px)
Run:  nice .venv-sim-worker-mac/bin/python experiments/.../flow_feasibility.py [--lag 1.0]
"""
from __future__ import annotations
import argparse, json, math, sys, time
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).parent))
from caseio import OUT, load_case, interp_pose, cmd_forward_distance
cv2.setNumThreads(1)

STALL_SETS = ['door-relax-envelope-4194d34c-posAdv2R', 'door-relax-envelope-4194d34c-posAdv2L',
              'door-relax-envelope-c955e513-posAdv', 'door-relax-envelope-4194d34c-posAdvM']
MOVE_SETS = ['door-relax-envelope-77fde5f6-chK1gP2']
H, W = 480, 640


def gray(path):
    return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)


def beam_edges(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = (hsv[..., 0] >= 12) & (hsv[..., 0] <= 63) & (hsv[..., 1] >= 100) & (hsv[..., 2] >= 60)
    col = m[:, 280:360].mean(1) > 0.5
    idx = np.flatnonzero(col)
    if len(idx) == 0:
        return None
    top = idx[idx < H // 2]; bot = idx[idx >= H // 2]
    return (top.max() if len(top) else None, bot.min() if len(bot) else None)


def dark_roi(ga, gb):
    d = (ga < 60) & (gb < 60) & (ga > 3) & (gb > 3)
    rows = np.flatnonzero(d[:, 200:440].mean(1) > 0.9)
    if len(rows) < 40:
        return None
    r0, r1 = rows.min() + 10, rows.max() - 10
    if r1 - r0 < 32:
        return None
    return r0, r1


def features(pa, pb):
    ga, gb = gray(pa), gray(pb)
    ba, bb = cv2.imread(str(pa)), cv2.imread(str(pb))
    valid = (ga > 3) | (gb > 3)
    out = {'mad_full': float(np.abs(ga.astype(np.float32) - gb)[valid].mean())}
    roi = dark_roi(ga, gb)
    if roi is None:
        out.update(mad_dark=None, pc_dark_px=None, pc_resp=None, fb_dark_px=None)
    else:
        r0, r1 = roi
        a = ga[r0:r1, 100:540].astype(np.float32); b = gb[r0:r1, 100:540].astype(np.float32)
        out['mad_dark'] = float(np.abs(a - b).mean())
        win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
        (dx, dy), resp = cv2.phaseCorrelate(a - a.mean(), b - b.mean(), win)
        out['pc_dark_px'] = float(math.hypot(dx, dy)); out['pc_resp'] = float(resp)
        fl = cv2.calcOpticalFlowFarneback(a.astype(np.uint8), b.astype(np.uint8), None, 0.5, 3, 21, 3, 5, 1.1, 0)
        out['fb_dark_px'] = float(np.median(np.hypot(fl[..., 0], fl[..., 1])))
    a = ga.astype(np.float32); b = gb.astype(np.float32)
    win = cv2.createHanningWindow((W, H), cv2.CV_32F)
    (dx, dy), _ = cv2.phaseCorrelate(a - a.mean(), b - b.mean(), win)
    out['pc_full_px'] = float(math.hypot(dx, dy))
    ea, eb = beam_edges(ba), beam_edges(bb)
    if ea and eb and None not in ea and None not in eb:
        out['beam_edge_dpx'] = float(max(abs(ea[0] - eb[0]), abs(ea[1] - eb[1])))
    else:
        out['beam_edge_dpx'] = None
    return out


def windows(c, rid, lag, stride):
    fidx, ft = c['frames'][rid]
    res = []
    for a in range(0, len(ft), stride):
        j = np.searchsorted(ft, ft[a] + lag)
        if j >= len(ft) or abs(ft[j] - ft[a] - lag) > 0.11:
            continue
        ta, tb = ft[a], ft[j]
        ia, ib = np.searchsorted(c['t'], [ta, tb])
        ia = min(ia, len(c['t']) - 1); ib = min(ib, len(c['t']) - 1)
        if not (c['lift'][ia] > 0.04 and c['lift'][ib] > 0.04 and c['jaws'][rid][ia] and c['jaws'][rid][ib]):
            continue
        xa, ya, _ = interp_pose(c, rid, ta); xb, yb, _ = interp_pose(c, rid, tb)
        d = math.hypot(xb - xa, yb - ya)
        cf = cmd_forward_distance(c, rid, ta, tb)
        m = math.hypot(cf[0], cf[1])
        if m >= 0.025 and d <= 0.3 * m:
            lab = 'STALL'
        elif m >= 0.025 and d >= 0.6 * m:
            lab = 'MOVING'
        elif m < 0.003 and d < 0.003:
            lab = 'REST'
        else:
            continue
        res.append(dict(rid=rid, fa=int(fidx[a]), fb=int(fidx[j]), ta=float(ta), tb=float(tb), gt_d_m=d, cmd_m=m, label=lab))
    return res


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--lag', type=float, default=1.0)
    ap.add_argument('--stride', type=int, default=4); ap.add_argument('--out', default='/Users/changmin/projects/ugrp/outputs/stall-detection-research/flow_rows_lag1.json')
    a = ap.parse_args()
    rows = []
    t0 = time.time()
    for sets, kind in ((STALL_SETS, 'stallset'), (MOVE_SETS, 'moveset')):
        for s in sets:
            for cd in sorted((OUT / s / 'cases').iterdir()):
                if not cd.is_dir() or not (cd / 'eval_only' / 'trace.jsonl').exists():
                    continue
                c = load_case(cd)
                for rid in ('r1', 'r2'):
                    for w in windows(c, rid, a.lag, a.stride):
                        fa = cd / 'frames' / rid / f"{w['fa']:05d}.jpg"; fb = cd / 'frames' / rid / f"{w['fb']:05d}.jpg"
                        f = features(fa, fb)
                        rows.append(dict(kind=kind, set=s, case=cd.name, **w, **f))
                print(kind, cd.name[:60], len(rows), f'{time.time()-t0:.0f}s', flush=True)
    Path(a.out).write_text(json.dumps(rows))


if __name__ == '__main__':
    main()
