#!/usr/bin/env python3
"""How fragile is the only carry-time wrist-image difference (sub-quantization brightness change, 'mad')?

The noise-free render gives stalled pairs MAD ~0.008 and moving pairs ~0.02-0.03 gray levels (AUC ~0.98).  A real sensor adds
temporal noise and exposure jitter.  We re-score the same 9 positive-control cases after adding, per frame and independently,
(a) Gaussian read noise sigma in {0, 0.5, 1, 2} gray levels (then rounding to 8 bit) and (b) a multiplicative exposure jitter
(gain ~ N(1, g)), g in {0, 0.1, 0.3, 1} %.  The image content is unchanged; only these two numbers change.
Uses rows saved by wrist_flow_carry.py (labels) and re-reads the frames.  Offline, seconds to a couple of minutes.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrist_flow_carry as w  # noqa: E402
from common import OUT, auc, frame_times, load_case  # noqa: E402

HERE = Path(__file__).resolve().parent
rng = np.random.default_rng(20260930)
COMBOS = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 0.001), (0.0, 0.003), (0.0, 0.01), (1.0, 0.003)]   # (read noise, exposure jitter)


def mad(a, b):
    return float(np.abs(a - b)[w.VALID].mean())


def main():
    rows = [json.loads(s) for s in np.load(OUT / 'stall-detection-research/wrist_pairs.npy')]
    rows = [r for r in rows if r['hint'] == 'posctl_stalled' and w.label(r) in ('stalled', 'moving')]
    # every 3rd stalled pair (there are ~2400 vs ~570 moving) to keep the run short
    rows = [r for k, r in enumerate(rows) if w.label(r) == 'moving' or k % 3 == 0]
    by_case = {}
    for r in rows:
        by_case.setdefault((r['case'], r['rid']), []).append(r)
    dirs = {}
    for tag in ('4194d34c-posAdv2R', '4194d34c-posAdv2L', '4194d34c-posAdvM'):
        for p in (OUT / f'door-relax-envelope-{tag}/cases').glob('carry_*_VENV'):
            dirs[p.name] = p
    scores = {c: {'stalled': [], 'moving': []} for c in COMBOS}
    for (case, rid), rs in by_case.items():
        d = dirs[case]
        robots, _, _ = load_case(d)
        t = frame_times(robots, rid)
        cache = {}

        def gray(i):
            if i not in cache:
                cache[i] = w.load(d / 'frames' / rid / f'{i:05d}.jpg')[1].astype(np.float32)
            return cache[i]
        for r in rs:
            i1 = int(np.argmin(np.abs(t - r['t'])))
            i0 = int(np.argmin(np.abs(t - (r['t'] - r['dt']))))
            g0, g1 = gray(i0), gray(i1)
            for n, g in COMBOS:
                a = g0 * (1 + g * rng.standard_normal()) + n * rng.standard_normal(g0.shape).astype(np.float32)
                b = g1 * (1 + g * rng.standard_normal()) + n * rng.standard_normal(g1.shape).astype(np.float32)
                a = np.clip(np.rint(a), 0, 255)
                b = np.clip(np.rint(b), 0, 255)
                scores[(n, g)][w.label(r)].append(mad(a, b))
    out = {'n_stalled': sum(len(v['stalled']) for k, v in scores.items() if k == (0.0, 0.0)),
           'n_moving': sum(len(v['moving']) for k, v in scores.items() if k == (0.0, 0.0)), 'grid': []}
    for (n, g), v in scores.items():
        out['grid'].append(dict(read_noise_gray=n, exposure_jitter=g, auc_moving_gt_stalled=auc(v['moving'], v['stalled']),
                                mad_stalled_med=float(np.median(v['stalled'])), mad_moving_med=float(np.median(v['moving']))))
    (HERE / 'results/wrist_mad_noise_sensitivity.json').write_text(json.dumps(out, indent=1))
    print('n_stalled', out['n_stalled'], 'n_moving', out['n_moving'])
    print('read_noise  jitter   AUC   MADstalled MADmoving')
    for e in out['grid']:
        print(f"{e['read_noise_gray']:>6} {e['exposure_jitter']:>8} {e['auc_moving_gt_stalled']:.3f} {e['mad_stalled_med']:.4f} {e['mad_moving_med']:.4f}")


if __name__ == '__main__':
    main()
