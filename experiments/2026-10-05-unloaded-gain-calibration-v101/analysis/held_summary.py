#!/usr/bin/env python3
"""False-positive / harm check of the integrated diff (C + R1 + R2) on the held-out dock probes (no relocalization happens there).
ctrlC = tree with diff C only; I = integrated tree (C + R1 + R2). Evaluation only (truth scores the replay)."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_pf import load_truth, load_replay, score_frames
D = '/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005/replay'
print('case                robot cfg     frames  mean NEES2  max NEES2  frac>13.8  mean err mm  final err mm  mean sigma_xy mm  injections/particles  reloc rows')
rows = []
for case in ('3358372e', '7623c4dc'):
    RAW = f'/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high-{case}/before_door'
    for rid in ('r1', 'r2'):
        tr = load_truth(RAW, rid)
        out = {}
        for cfg in ('ctrlC', 'I'):
            p = f'{D}/held_{cfg}_{case}_{rid}.jsonl'
            if not os.path.exists(p) or not any('"kind": "final"' in l for l in open(p)):
                continue
            fr, sc, rl, fin = load_replay(p)
            S = score_frames(fr, tr)
            ne = np.array([s['nees2'] for s in S]); st = fin[-1]['stats']
            xy = np.array([[s['t'], s.get('est_x', np.nan)] for s in S]) if 'est_x' in S[0] else None
            out[cfg] = (S, st, len(rl))
            print(f'raise_high-{case} {rid}    {cfg:6s} {len(S):7d} {np.nanmean(ne):10.2f} {np.nanmax(ne):10.2f} {np.mean(ne > 13.8):10.2f} {np.mean([1000*s["err"] for s in S]):12.1f} {1000*S[-1]["err"]:13.1f} {np.mean([1000*s["sxy"] for s in S]):18.1f}  {st.get("injections")}/{st.get("injected_particles")}  {len(rl)}')
        if len(out) == 2:
            a = np.array([s['err'] for s in out['ctrlC'][0]]); b = np.array([s['err'] for s in out['I'][0]])
            rows.append({'case': case, 'robot': rid, 'identical_error_series': bool(np.array_equal(a, b)), 'max_abs_diff_m': float(np.max(np.abs(a-b))),
                         'injections_I': out['I'][1].get('injections'), 'reloc_rows_I': out['I'][2]})
print(json.dumps(rows, indent=1))
