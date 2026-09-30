#!/usr/bin/env python3
"""Does the wrist RGB during CARRY hold ego-motion signal?  Offline, recorded frames only, no simulation.

For every consecutive wrist-frame pair of a loaded (carrying) robot we compute cheap image-motion measures and compare
STALLED pairs (own command sustained, GT says the robot did not move) with MOVING pairs (GT moves at the expected speed).
GT is used only to label pairs (analysis); the measures themselves use two images only.

Measures (all on 320x240 gray, fisheye-valid mask):
  mad      mean |I1-I0| over the valid mask (gray levels)
  pc       phase-correlation shift magnitude in px (cv2.phaseCorrelate, Hann window) and its peak response
  fb       Farneback dense flow: median magnitude over 'textured' pixels (Sobel > 12 in I0), and the textured fraction
  edge     lime-beam lower-edge row (sub-pixel from the soft lime mask), frame-to-frame change in px (beam-vs-camera relative
           motion, i.e. grip slip / beam tilt; NOT ego motion)
Usage: wrist_flow_carry.py [--max-chain N] [--max-env N]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, auc, cmd_at, cmd_series, frame_times, gt_track, interp_pose, load_case  # noqa: E402

cv2.setNumThreads(1)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from harness import owncam_view  # noqa: E402

GAIN = 1.328          # measured carry forward gain (actual m/s per commanded unit), PR #284 / #285
SUSTAIN_S = 1.0       # command must have been on for this long before a pair counts as "commanded"
V_CMD_MIN = 0.03      # commanded forward/left magnitude that counts as "driving" (registered carry speed 0.038)

_valid = owncam_view.valid_pixel_mask(step=1)   # 480x640
VALID = cv2.erode(cv2.resize(_valid.astype(np.uint8), (320, 240), interpolation=cv2.INTER_NEAREST), np.ones((7, 7), np.uint8)) > 0
HANN = cv2.createHanningWindow((320, 240), cv2.CV_32F)


def load(path):
    bgr = cv2.imread(str(path), cv2.IMREAD_REDUCED_COLOR_2)      # 320x240
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return bgr, g


def lime_edge(bgr):
    """Sub-pixel row of the lime beam's lower edge (median over central columns); nan if no lime."""
    b, g, r = [bgr[..., i].astype(np.float32) for i in range(3)]
    lime = np.clip((g - 120.) / 100., 0, 1) * np.clip((140. - b) / 80., 0, 1) * VALID
    cols = slice(80, 240)
    col_sum = lime[:, cols].sum(axis=0)
    ok = col_sum > 5
    if ok.sum() < 20:
        return float('nan'), 0.
    rows = np.arange(lime.shape[0], dtype=np.float32)
    # lower edge = last row with lime; use weighted sum of the soft mask with weight row over the bottom transition
    edge = []
    for c in range(80, 240):
        colv = lime[:, c]
        idx = np.where(colv > 0.5)[0]
        if len(idx) < 3:
            continue
        r_last = idx.max()
        edge.append(r_last + float(colv[r_last + 1]) if r_last + 1 < len(colv) else float(r_last))
    return (float(np.median(edge)) if edge else float('nan')), float(lime.sum() / max(VALID.sum(), 1))


def pair_metrics(prev, cur):
    (bgr0, g0), (bgr1, g1) = prev, cur
    d = np.abs(g1.astype(np.float32) - g0.astype(np.float32))
    mad = float(d[VALID].mean())
    f0 = g0.astype(np.float32) * HANN
    f1 = g1.astype(np.float32) * HANN
    (sx, sy), resp = cv2.phaseCorrelate(f0, f1)
    gx = cv2.Sobel(g0, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g0, cv2.CV_32F, 0, 1, ksize=3)
    gm = np.hypot(gx, gy)
    tex = (gm > 12.) & VALID
    tex_frac = float(tex.sum() / VALID.sum())
    flow = cv2.calcOpticalFlowFarneback(g0, g1, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    mag = np.hypot(flow[..., 0], flow[..., 1])
    fb_tex = float(np.median(mag[tex])) if tex.sum() > 200 else float('nan')
    fb_all = float(np.median(mag[VALID]))
    return dict(mad=mad, pc=float(np.hypot(sx, sy)), pc_resp=float(resp), fb_tex=fb_tex, fb_all=fb_all, tex_frac=tex_frac)


def case_rows(case_dir, label_hint, rids=('r1', 'r2'), loaded_only=True):
    robots, cmds, trace = load_case(case_dir)
    rows = []
    for rid in rids:
        fr = robots[rid]['frames']
        t = frame_times(robots, rid)
        tg, xg, yg, _ = gt_track(trace, rid)
        ser = cmd_series(cmds, rid)
        prev = None
        prev_i = None
        for i, f in enumerate(fr):
            if loaded_only and f['report'].get('load_state') != 'loaded':
                prev = None
                continue
            cur = load(case_dir / 'frames' / rid / f'{i:05d}.jpg')
            edge, lime_frac = lime_edge(cur[0])
            if prev is not None and 0.08 <= t[i] - t[prev_i] <= 0.25:
                m = pair_metrics(prev, cur)
                t0, t1 = t[prev_i], t[i]
                x0, y0 = interp_pose(tg, xg, yg, np.array([t0]))
                x1, y1 = interp_pose(tg, xg, yg, np.array([t1]))
                v_gt = float(np.hypot(x1 - x0, y1 - y0)[0] / (t1 - t0))
                # sustained command over the SUSTAIN_S before t1
                tt = np.linspace(t1 - SUSTAIN_S, t1, 11)
                c = cmd_at(ser, tt)
                mag = np.hypot(c[:, 0], c[:, 1])
                v_exp = float(GAIN * mag.mean())
                sustained = bool((mag >= V_CMD_MIN).all())
                idle = bool((mag < 0.005).all()) and v_gt < 0.005
                m.update(case=case_dir.name, rid=rid, t=float(t1), dt=float(t1 - t0), v_gt=v_gt, v_exp=v_exp,
                         sustained=sustained, idle=idle, edge_d=abs(edge - prev_edge) if np.isfinite(edge) and np.isfinite(prev_edge) else float('nan'),
                         lime_frac=lime_frac, hint=label_hint)
                rows.append(m)
            prev, prev_i, prev_edge = cur, i, edge
    return rows


def label(r):
    if r['sustained'] and r['v_gt'] <= 0.1 * r['v_exp']:
        return 'stalled'
    if r['sustained'] and r['v_gt'] >= 0.8 * r['v_exp']:
        return 'moving'
    if r['idle']:
        return 'idle'
    return 'other'


def summarize(rows, keys=('mad', 'pc', 'pc_resp', 'fb_tex', 'fb_all', 'edge_d', 'tex_frac')):
    out = {}
    by = {'stalled': [], 'moving': [], 'idle': []}
    for r in rows:
        l = label(r)
        if l in by:
            by[l].append(r)
    out['n_pairs'] = {k: len(v) for k, v in by.items()}
    out['n_cases'] = {k: len({r['case'] for r in v}) for k, v in by.items()}
    out['metrics'] = {}
    for k in keys:
        def arr(l):
            a = np.array([r[k] for r in by[l]], float)
            return a[np.isfinite(a)]
        q = {}
        for l in by:
            a = arr(l)
            q[l] = dict(n=int(len(a)), p05=float(np.percentile(a, 5)) if len(a) else None, med=float(np.median(a)) if len(a) else None,
                        p95=float(np.percentile(a, 95)) if len(a) else None, max=float(a.max()) if len(a) else None)
        # AUC: probability that a MOVING pair scores higher than a STALLED pair (0.5 = no information)
        q['auc_moving_gt_stalled'] = auc(arr('moving'), arr('stalled'))
        out['metrics'][k] = q
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-chain', type=int, default=8)
    ap.add_argument('--max-env', type=int, default=8)
    ap.add_argument('--out', default=str(HERE / 'results/wrist_flow_carry.json'))
    a = ap.parse_args()
    t0 = time.time()
    stalled_dirs = []
    for tag in ('4194d34c-posAdv2R', '4194d34c-posAdv2L'):
        stalled_dirs += sorted((OUT / f'door-relax-envelope-{tag}/cases').glob('carry_*_VENV'))
    stalled_dirs += [OUT / 'door-relax-envelope-4194d34c-posAdvM/cases/carry_b-v6h.adv_teacher_E_y-0.100_h+0.0_b+0.250_+0.0_s911_pPOST_L1_VENV']
    moving_dirs = sorted((OUT / 'door-relax-envelope-77fde5f6-chK1gP2/cases').glob('chain_*_s911_*VhR2'))[:a.max_chain]
    env = sorted((OUT / 'door-relax-envelope-fdd35cee-envK1gL1/cases').glob('carry_*_s911_*VENV'))[:a.max_env]
    rows = []
    for d in stalled_dirs:
        rows += case_rows(d, 'posctl_stalled')
        print('done', d.name, len(rows), round(time.time() - t0), 's', flush=True)
    for d in moving_dirs + env:
        rows += case_rows(d, 'moving_pool')
        print('done', d.name, len(rows), round(time.time() - t0), 's', flush=True)
    s_all = summarize(rows)
    s_ctl = summarize([r for r in rows if r['hint'] == 'posctl_stalled'])
    s_mov = summarize([r for r in rows if r['hint'] == 'moving_pool'])
    # pooled comparison: stalled pairs from the 9 positive-control cases vs moving pairs from the moving pool
    st = [r for r in rows if r['hint'] == 'posctl_stalled' and label(r) == 'stalled']
    mv = [r for r in rows if r['hint'] == 'moving_pool' and label(r) == 'moving']
    pooled = {'stalled_cases': len({r['case'] for r in st}), 'stalled_pairs': len(st), 'moving_cases': len({r['case'] for r in mv}), 'moving_pairs': len(mv), 'auc_moving_gt_stalled': {}}
    for k in ('mad', 'pc', 'fb_tex', 'fb_all', 'edge_d'):
        pooled['auc_moving_gt_stalled'][k] = auc([r[k] for r in mv if np.isfinite(r[k])], [r[k] for r in st if np.isfinite(r[k])])
    res = dict(seconds=round(time.time() - t0, 1), cases_stalled_dirs=[d.name for d in stalled_dirs], cases_moving_dirs=[d.name for d in moving_dirs + env],
               per_hint_all=s_all, controls_only=s_ctl, moving_pool_only=s_mov, pooled=pooled)
    Path(a.out).write_text(json.dumps(res, indent=1))
    Path(OUT / 'stall-detection-research').mkdir(exist_ok=True)
    np.save(OUT / 'stall-detection-research/wrist_pairs.npy', np.array([json.dumps(r) for r in rows]))
    print(json.dumps(res['pooled'], indent=1))
    for k, v in res['per_hint_all']['metrics'].items():
        print(k, {l: (v[l]['med'], v[l]['p95']) for l in ('stalled', 'moving', 'idle')}, 'AUC', v['auc_moving_gt_stalled'])
    print('pairs', res['per_hint_all']['n_pairs'], 'cases', res['per_hint_all']['n_cases'])


if __name__ == '__main__':
    main()
