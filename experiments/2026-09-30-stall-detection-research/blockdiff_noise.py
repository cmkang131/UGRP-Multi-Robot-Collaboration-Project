"""Noise robustness of a better estimator than plain MAD: block-averaged, mean-removed frame difference in the dark ROI.

Pairs = STALL and MOVING windows (1.0 s lag) of results/flow_rows_lag1.json (MOVING thinned x4 for speed).
The recorded render is noise free; we ADD independent Gaussian read noise (sigma gray levels, re-quantised to 8 bit) and a
multiplicative per-frame exposure jitter, then score  f = mean |blockmean16(Ib - Ia) - mean(...)|  (structured change only).
AUC = P(MOVING scores higher than STALL). This is a synthetic-noise sensitivity test, NOT a real-camera measurement.
"""
import json, sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).parent))
from common import auc
from flow_feasibility import dark_roi
cv2.setNumThreads(1)
HERE = Path(__file__).parent
OUT = Path('/Users/changmin/projects/ugrp/outputs')
rows = json.load(open(Path('/Users/changmin/projects/ugrp/outputs/stall-detection-research/flow_rows_lag1.json')))
st = [r for r in rows if r['label'] == 'STALL']
mv = [r for r in rows if r['label'] == 'MOVING'][::4]
pairs = [(r, 0) for r in st] + [(r, 1) for r in mv]
cache = {}
for r, lab in pairs:
    d = OUT / r['set'] / 'cases' / r['case'] / 'frames' / r['rid']
    ga = cv2.imread(str(d / f"{r['fa']:05d}.jpg"), cv2.IMREAD_GRAYSCALE); gb = cv2.imread(str(d / f"{r['fb']:05d}.jpg"), cv2.IMREAD_GRAYSCALE)
    roi = dark_roi(ga, gb)
    if roi is None:
        continue
    r0, r1 = roi
    cache[id(r)] = (ga[r0:r1, 100:540].astype(np.float32), gb[r0:r1, 100:540].astype(np.float32), lab)
print('pairs', len(cache), 'stall', sum(1 for v in cache.values() if v[2] == 0), 'moving', sum(1 for v in cache.values() if v[2] == 1))
rng = np.random.default_rng(1)
def score(a, b, sig, g, blk):
    def noisy(x):
        y = x * (1 + rng.normal(0, g)) + rng.normal(0, sig, x.shape) if (sig or g) else x
        return np.clip(np.round(y), 0, 255)
    d = noisy(b) - noisy(a)
    h, w = (d.shape[0] // blk) * blk, (d.shape[1] // blk) * blk
    bm = d[:h, :w].reshape(h // blk, blk, w // blk, blk).mean((1, 3))
    return float(np.abs(bm - bm.mean()).mean())
res = []
for sig in (0, 0.25, 0.5, 1.0, 2.0):
    for g in (0, 0.003, 0.01):
        for blk in (16,):
            s = [score(a, b, sig, g, blk) for a, b, l in cache.values() if l == 0]
            m = [score(a, b, sig, g, blk) for a, b, l in cache.values() if l == 1]
            res.append(dict(read_noise_gray=sig, exposure_jitter=g, block=blk, auc=auc(m, s), stall_med=float(np.median(s)), move_med=float(np.median(m))))
            print(res[-1], flush=True)
(HERE / 'results/blockdiff_noise.json').write_text(json.dumps(res, indent=1))
