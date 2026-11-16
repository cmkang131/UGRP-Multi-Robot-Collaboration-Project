#!/usr/bin/env python3
"""Real arrival rejection (v98-dev-probe-dock_approach-1236c63d, r1: first arrival rejected by the own-view check, recorded begin_relocalization at frame time 46.40 s;
a second rejection ends the approach at ~64 s). Replays of the recorded inputs (evaluation only; truth scores the replay, never drives it).
base = #363 HEAD 94d083ba as is (recorded DEV calibration 398372ae); ctrlC = diff C; CR1 = C + R1; I = C + R1 + R2 (the recorded relocalization is armed through the
production helper = what the arrival-rejection call site does). Per run: median |err| mm / median NEES2 per window, sigma_x, injections, expansions."""
import glob, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_pf import load_truth, load_replay, score_frames
D = '/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005/replay'
RAW = '/Users/changmin/projects/ugrp/outputs/v98-dev-probe-dock_approach-1236c63d/zone_wide_door_geometry_v3'
wins = [(20, 36), (36, 46), (46.5, 52), (52, 58), (58, 66)]
names = {'base': 'HEAD as is', 'ctrlC': 'C only', 'CR1': 'C+R1', 'I': 'C+R1+R2'}
print('cells: median |err| mm / median NEES2 per window; sigma_x mm mean 36-46 s -> 58-66 s; injections events/particles (total | before 46.4 s); expansion rows / relocalization rows')
for rid in ('r1', 'r2'):
    tr = load_truth(RAW, rid)
    print(f'\n=== {rid}')
    print(f'{"cfg":11s}{"seed":>5s} ' + ''.join(f'{lo}-{hi}s'.rjust(16) for lo, hi in wins) + '   sx 36-46 -> 58-66   inj total | <46.4s   expansions')
    for cfg in ('base', 'ctrlC', 'CR1', 'I'):
        for p in sorted(glob.glob(f'{D}/real_{cfg}_{rid}_s*.jsonl')):
            off = int(re.search(r'_s(\d+)\.jsonl', p).group(1))
            if not any('"kind": "final"' in l for l in open(p)):
                continue
            fr, sc, rl, fin = load_replay(p)
            S = score_frames(fr, tr)
            T = np.array([s['t'] for s in S])
            cells = ''
            for lo, hi in wins:
                m = (T >= lo) & (T < hi)
                vals = [(1000*s['err'], s['nees2']) for s, mm in zip(S, m) if mm]
                cells += (f'{np.median([v[0] for v in vals]):7.0f} /{np.nanmedian([v[1] for v in vals]):7.1f}' if vals else '    n/a').rjust(16)
            sx0 = np.mean([1000*s['sx'] for s, mm in zip(S, (T >= 36) & (T < 46)) if mm]); sx1 = np.mean([1000*s['sx'] for s, mm in zip(S, (T >= 58) & (T < 66)) if mm])
            st = fin[-1]['stats']
            pre = [f['stats'].get('injections', 0) for f in fr if f['tnow'] < 46.4]
            nexp = sum(1 for r in rl if r.get('expansion_radius'))
            print(f'{names[cfg]:11s}{off:5d} ' + cells + f'   {sx0:5.1f} -> {sx1:5.1f}   {st.get("injections")}/{st.get("injected_particles")} | {max(pre) if pre else 0}   {nexp}/{len(rl)}')
