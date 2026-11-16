#!/usr/bin/env python3
"""Recovery check of the stacked diffs on top of calibration C (evaluation only; truth scores the replay, never drives it).
Replays of the recorded v98 probe inputs, candidate C calibration in every tree, until 66 s.
cfg: ctrlC = diff C only, CR1 = C + R1 (local augmented MCL), I = C + R1 + R2 (expansion armed by the rejected arrival through the production helper).
mode one: r2 = its recorded rejected arrival (49.10 s frame time), r1 = a counterfactual one at the first frame >= 49.1 s.
mode two: additionally a second rejected arrival at 52.1 s.
Per run: median |err| mm / median NEES2 per window, sigma_x before (40-49) and after (60-66), injections (events/particles) in total and BEFORE 49 s (normal drive),
expansion rows (relocalization rows carrying expansion_radius)."""
import glob, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_pf import load_truth, load_replay, score_frames
D = '/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005/replay'
RAW = '/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high-1f7fb800/zone_wide_door_geometry_v3'
wins = [(40, 49), (50, 56), (56, 60), (60, 66)]
names = {'ctrlC': 'C only', 'CR1': 'C+R1', 'I': 'C+R1+R2'}
print('cells: median |err| mm / median NEES2 per window; sigma_x mm 40-49 s -> 60-66 s; injections events/particles (total | before 49 s); expansion rows')
for mode in ('one', 'two'):
    for rid in ('r2', 'r1'):
        tr = load_truth(RAW, rid)
        print(f'\n=== {rid}  mode {mode}')
        print(f'{"cfg":9s}{"seed":>5s} ' + ''.join(f'{lo}-{hi}s'.rjust(16) for lo, hi in wins) + '   sx 40-49 -> 60-66   inj total | <49s   expansions')
        for cfg in ('ctrlC', 'CR1', 'I'):
            for p in sorted(glob.glob(f'{D}/rec_{cfg}_{rid}_s*_{mode}_until66.jsonl')):
                off = int(re.search(r'_s(\d+)_', p).group(1))
                if not any('"kind": "final"' in l for l in open(p)):
                    continue
                fr, sc, rl, fin = load_replay(p)
                S = [s for s in score_frames(fr, tr) if s['t'] <= 66.0]
                T = np.array([s['t'] for s in S])
                cells = ''
                for lo, hi in wins:
                    m = (T >= lo) & (T < hi)
                    e = np.median([1000*s['err'] for s, mm in zip(S, m) if mm]); ne = np.nanmedian([s['nees2'] for s, mm in zip(S, m) if mm])
                    cells += f'{e:7.0f} /{ne:7.1f}'.rjust(16)
                sx0 = np.mean([1000*s['sx'] for s, mm in zip(S, (T >= 40) & (T < 49)) if mm]); sx1 = np.mean([1000*s['sx'] for s, mm in zip(S, (T >= 60) & (T < 66)) if mm])
                st = fin[-1]['stats']
                pre = [f['stats'].get('injections', 0) for f in fr if f['tnow'] < 49.0]
                nexp = sum(1 for r in rl if r.get('expansion_radius'))
                print(f'{names[cfg]:9s}{off:5d} ' + cells + f'   {sx0:5.1f} -> {sx1:5.1f}   {st.get("injections")}/{st.get("injected_particles")} | {max(pre) if pre else 0}   {nexp}/{len(rl)}')
