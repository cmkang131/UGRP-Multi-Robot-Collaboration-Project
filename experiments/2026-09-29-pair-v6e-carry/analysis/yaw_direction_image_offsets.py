"""Yaw-direction analysis, step 4: how well does the FIRST loaded frame of the leg (own wrist RGB) reveal the grip offsets?

Offline. Input beam_edge_all_cases.json (first-frame beam-band edge slope and centre height + staged own-frame offsets).
Fit (least squares, leave-one-cell-out): own offsets (along x, lateral y, yaw) ~ a + b*slope0 + c*yc0, pooled over r1 and r2
(own frame: both robots see the same camera geometry). The staged offsets are eval-only; the fit is a static camera-geometry
calibration of the kind calibration_loop_v2.json is, and here it is evaluated only on held-out cells.
Then E3 is repeated with the image-derived offsets replacing 'truth + assumed noise'.
"""
import json, math
from collections import defaultdict
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaw_direction_obs_models as om

HERE = Path(__file__).resolve().parent


def main():
    D = json.load(open(HERE/'beam_edge_all_cases.json'))
    # one record per (variant, cell, leg, robot); first-frame features are leg independent (same staging), use all legs
    rows = [q for q in D if 'yc_first' in q]
    cells = sorted({q['cell'] for q in rows})
    Z = lambda q: np.array([1., q['sl_first'], q['yc_first']])
    T = lambda q: np.array(q['offsets'][q['robot']], float)
    pred = {}
    for c in cells:
        tr = [q for q in rows if q['cell'] != c]
        A = np.array([Z(q) for q in tr]); Y = np.array([T(q) for q in tr])
        s = np.abs(A).max(0)
        beta = np.linalg.lstsq(A/s, Y, rcond=None)[0]
        for i, q in enumerate(rows):
            if q['cell'] == c:
                pred[i] = (Z(q)/s)@beta
    err = np.array([pred[i] - T(q) for i, q in enumerate(rows)])
    print('image-derived own offsets, leave-one-cell-out, %d case-robots: error std x %.2f mm, y %.2f mm, yaw %.2f mrad' %
          (len(rows), err[:, 0].std()*1e3, err[:, 1].std()*1e3, err[:, 2].std()*1e3))
    for k, name in enumerate(('x', 'y', 'yaw')):
        per = defaultdict(list)
        for q, e in zip(rows, err[:, k]):
            per[q['cell']].append(e)
        print('  %-3s per-cell RMS error %s' % (name, ', '.join('%s %.2f' % (c, np.sqrt(np.mean(np.square(v)))*(1e3)) for c, v in sorted(per.items()))))
    # E3 with image-measured offsets: replace offsets of r1/r2 in each analysis record by the image estimate of that robot/leg
    est = {}
    for i, q in enumerate(rows):
        est[(q['variant'], q['cell'], q['leg'], q['robot'])] = pred[i]
    prow = om.prep()
    for r in prow:
        r['offsets_true'] = r['offsets']
        e1, e2 = est.get((r['variant'], r['cell'], r['leg'], 'r1')), est.get((r['variant'], r['cell'], r['leg'], 'r2'))
        r['offsets_img'] = {'r1': list(e1) if e1 is not None else None, 'r2': list(e2) if e2 is not None else None}
    prow = [r for r in prow if r['offsets_img']['r1'] is not None and r['offsets_img']['r2'] is not None]
    cellset = sorted({r['cell'] for r in prow})
    rho = np.zeros(len(prow))
    for c in cellset:
        tr = [r for r in prow if r['cell'] != c]
        # train on TRUE offsets (calibration), test on image-derived ones
        for cls in ('ax', 'lat'):
            t = [r for r in tr if r['cls'] == cls]
            X = np.array([np.r_[1., om.feats(r['offsets_true']['r1'], r['offsets_true']['r2'])] for r in t]); y = np.array([r['e2'] for r in t])
            s = np.maximum(np.abs(X).max(0), 1e-12)
            beta = np.linalg.lstsq(X/s, y, rcond=None)[0]/s
            for i, r in enumerate(prow):
                if r['cell'] == c and r['cls'] == cls:
                    rho[i] = r['e2'] - np.r_[1., om.feats(r['offsets_img']['r1'], r['offsets_img']['r2'])]@beta
    b2, _ = om.bal(prow, 'e2')
    b3, per = om.bal(prow, rho)
    print('E2 (pair-mean + image relative yaw) balanced RMS %.2f mrad/s ; E3 with IMAGE-derived offsets (LOPO, calibrated on other cells) %.2f mrad/s' % (b2*1e3, b3*1e3))
    print('  per cell E3-image [mrad/s]: ' + ', '.join('%s %.2f' % (c, v*1e3) for c, v in sorted(per.items())))
    for name, s0 in (('sigma0 0.0104', .0104), ('sigma0 0.0129', .0129)):
        print('  gate time (%s) at b=%.5f: %.1f s' % (name, b3, om.gate_t(b3, s0)))
    json.dump({'offset_error_std': {'x_mm': err[:, 0].std()*1e3, 'y_mm': err[:, 1].std()*1e3, 'yaw_mrad': err[:, 2].std()*1e3},
               'E2_balanced_mrad_s': b2*1e3, 'E3_image_balanced_mrad_s': b3*1e3, 'E3_image_per_cell': {c: v*1e3 for c, v in per.items()}},
              open(HERE/'yaw_direction_image_offsets.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
