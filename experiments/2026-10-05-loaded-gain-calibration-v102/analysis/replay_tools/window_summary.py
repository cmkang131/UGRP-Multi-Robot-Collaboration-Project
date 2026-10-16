#!/usr/bin/env python3
"""Whole-run window comparison of the full fcc5215f replays: recorded config vs v102 (PREREGISTRATION section 8, 'other segments not worse than +5 mm').
Median over 5 PF seeds of the per-seed window median |position error| (mm) and NEES2; evaluation only."""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_pf import load_truth, load_replay, score_frames
D = '/Users/changmin/projects/ugrp/outputs/pf-loadedgain-v102-20261005'
REPLAY = os.environ.get('REPLAY_DIR', f'{D}/replay7194')
RAW = '/Users/changmin/projects/ugrp/outputs/v98-dev-probe-align_to_carry-fcc5215f/zone_wide_door_geometry_v3'
WINS = [(20, 60), (60, 90), (90, 140), (140, 210), (210, 260), (260, 330), (330, 360), (360, 430)]
SEEDS = (0, 101, 102, 103, 104)
res, out = {}, {}
for rid in ('r1', 'r2'):
    tr = load_truth(RAW, rid)
    for cfg in ('rec', 'v102'):
        per = {}
        for s in SEEDS:
            fp = f'{REPLAY}/{cfg}_{rid}_s{s}_meas.jsonl'
            if not os.path.exists(fp) or not any('"kind": "final"' in l for l in open(fp)):
                continue                                   # unfinished / missing replay: not used
            S = score_frames(load_replay(fp)[0], tr)
            T = np.array([x['t'] for x in S]); E = np.array([1000*x['err'] for x in S]); N = np.array([x['nees2'] for x in S])
            for lo, hi in WINS + [(20, 430)]:
                m = (T >= lo) & (T < hi)
                per.setdefault((lo, hi), []).append((float(np.median(E[m])), float(np.median(N[m])), float(E[m].max())))
        res[(rid, cfg)] = per
print('window | rec: median |err| mm / NEES2 / max mm  | v102: ... | diff of median |err| (mm)')
for rid in ('r1', 'r2'):
    print('==', rid)
    for k in WINS + [(20, 430)]:
        a, b = np.array(res[(rid, 'rec')][k]), np.array(res[(rid, 'v102')][k])
        ra, rb = [float(np.median(a[:, i])) for i in range(3)], [float(np.median(b[:, i])) for i in range(3)]
        out[f'{rid}/{k[0]}-{k[1]}'] = {'rec': ra, 'v102': rb, 'diff_mm': rb[0] - ra[0], 'n_seeds_rec': len(a), 'n_seeds_v102': len(b)}
        print(f'{k[0]:3d}-{k[1]:3d} s | rec {ra[0]:7.1f} /{ra[1]:6.2f} /{ra[2]:7.1f} | v102 {rb[0]:7.1f} /{rb[1]:6.2f} /{rb[2]:7.1f} | {rb[0]-ra[0]:+7.1f}')
json.dump(out, open(f'{D}/window_summary_{os.path.basename(REPLAY)}.json', 'w'), indent=1)
