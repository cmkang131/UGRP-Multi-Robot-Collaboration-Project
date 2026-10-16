#!/usr/bin/env python3
"""Pre-registered selection summary (experiments/2026-10-05-unloaded-gain-calibration-v101/PREREGISTRATION.md section 7 + ADDENDUM_selection_rule.md).

Replays of the recorded v98 DEV probe inputs (r1, r2; until 60 s; seeds offset 0,101..104) through the #363 HEAD 94d083ba provider with
candidate calibrations: base (HEAD as is, reference only), B (registered r4/r5 noise overlay, old DEV gain), C (measured gain/lag + registered noise),
C2 (measured gain/lag + noise measured in the calibration; EXCLUDED from selection because its coverage gate failed, supplementary only).
Truth scores the replay offline; it never drives it.
usage: sel_summary.py [--tmax 60]
"""
import glob, os, re, sys, json, argparse
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_pf import load_truth, load_replay, score_frames
ap = argparse.ArgumentParser(); ap.add_argument('--tmax', type=float, default=60); ap.add_argument('--json', default=None); a = ap.parse_args()
D = '/Users/changmin/projects/ugrp/outputs/pf-gaincal-v101-20261005/replay'
RAW = '/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high-1f7fb800/zone_wide_door_geometry_v3'
BOUND = 13.8; MEDIAN = 1.386
WINS = [(10, 20), (20, 30), (30, 40), (40, 50), (50, 60)]
SEL_WINS = [(30, 40), (40, 50), (50, 60)]
CFGS = ('base', 'B', 'C', 'C2')
res = {}
print(f'chi2(2) 99.9% bound {BOUND}, median {MEDIAN}; cell = median over seeds of per-seed window-median NEES2 [min..max] (#seeds <= bound / #seeds)')
for rid in ('r1', 'r2'):
    tr = load_truth(RAW, rid)
    print(f'\n=== {rid}')
    print(f'{"cfg":5s}{"n":>3s} ' + ''.join(f'{lo}-{hi}s'.rjust(30) for lo, hi in WINS) + '   median |err| mm 30-60s [min..max]   mean sigma_x mm 30-60s')
    for cfg in CFGS:
        per = []
        for p in sorted(glob.glob(f'{D}/ens_{cfg}_{rid}_s*_until60.jsonl')):
            m = re.search(r'_s(\d+)_until', p)
            if not any('"kind": "final"' in l for l in open(p)):
                continue
            fr, sc, rl, fin = load_replay(p)
            S = [s for s in score_frames(fr, tr) if s['t'] <= a.tmax]
            T = np.array([s['t'] for s in S])
            if T.max() < a.tmax - 2:
                continue
            w = {win: float(np.nanmedian([s['nees2'] for s, mm in zip(S, (T >= win[0]) & (T < win[1])) if mm])) for win in WINS}
            msk = (T >= 30) & (T < 60)
            per.append((int(m.group(1)), w, float(np.median([1000*s['err'] for s, mm in zip(S, msk) if mm])),
                        float(np.mean([1000*s['sx'] for s, mm in zip(S, msk) if mm]))))
        if not per:
            print(f'{cfg:5s}{0:3d} (no runs)'); continue
        cells = ''
        med = {}
        for win in WINS:
            v = np.array([p[1][win] for p in per]); med[win] = float(np.median(v))
            cells += f'{np.median(v):9.2f} [{v.min():6.2f}..{v.max():7.2f}] ({int((v <= BOUND).sum())}/{len(v)})'.rjust(30)
        e = np.array([p[2] for p in per])
        res[(cfg, rid)] = {'n': len(per), 'seeds': [p[0] for p in per], 'median_nees': {f'{lo}-{hi}': med[(lo, hi)] for lo, hi in WINS},
                           'median_err_mm': float(np.median(e)), 'err_min_max': [float(e.min()), float(e.max())],
                           'sigma_x_mm': float(np.mean([p[3] for p in per])),
                           'per_seed': {p[0]: {'nees': {f'{lo}-{hi}': p[1][(lo, hi)] for lo, hi in WINS}, 'err_mm': p[2]} for p in per}}
        print(f'{cfg:5s}{len(per):3d} ' + cells + f'   {np.median(e):6.0f} [{e.min():.0f}..{e.max():.0f}]   {np.mean([p[3] for p in per]):5.1f}')

def score(cfg):
    if any((cfg, r) not in res for r in ('r1', 'r2')):
        return None
    return float(sum(abs(np.log10(max(res[(cfg, r)]['median_nees'][f'{lo}-{hi}'], 1e-9)/MEDIAN)) for r in ('r1', 'r2') for lo, hi in SEL_WINS))

def err(cfg):
    return float(np.median([res[(cfg, r)]['median_err_mm'] for r in ('r1', 'r2')])) if score(cfg) is not None else None

print('\n=== pre-registered score S = sum over r1,r2 and windows 30-40/40-50/50-60 of |log10(median NEES2 / 1.386)|   (lower is better)')
table = {c: {'S': score(c), 'median_err_mm_r1_r2': err(c)} for c in CFGS}
for c in CFGS:
    s = table[c]['S']
    print(f'{c:5s} S={"n/a" if s is None else f"{s:7.3f}"}   median of the two robots median |err| 30-60 s = {table[c]["median_err_mm_r1_r2"] if table[c]["median_err_mm_r1_r2"] is None else round(table[c]["median_err_mm_r1_r2"], 1)} mm')
# decision (ADDENDUM_selection_rule.md): candidates B, C only (C2 excluded by its coverage gate)
cands = [c for c in ('B', 'C') if table[c]['S'] is not None]
decision = {'candidates': cands, 'path': []}
if len(cands) == 2:
    S = {c: table[c]['S'] for c in cands}; E = {c: table[c]['median_err_mm_r1_r2'] for c in cands}
    pick = min(cands, key=lambda c: S[c]); decision['path'].append(f'lowest S: {pick}')
    best_err = min(E.values())
    if E[pick] > 1.25*best_err:
        alt = min(cands, key=lambda c: E[c])
        decision['path'].append(f'(i) error of {pick} {E[pick]:.1f} > 1.25 x min {best_err:.1f}')
        if S[alt] <= 1.3*S[pick]:
            pick = alt; decision['path'].append(f'(i) lowest-error {alt} has S within +30% of the minimum -> {alt}')
        else:
            decision['path'].append(f'(i) lowest-error {alt} S {S[alt]:.3f} > 1.3 x {S[pick]:.3f}: keep {pick}')
    other = [c for c in cands if c != pick][0]
    if abs(S[pick]-S[other]) <= 0.10*max(S[pick], S[other]) + 1e-12:
        order = ['C', 'B']
        pick2 = min((pick, other), key=order.index)
        decision['path'].append(f'(ii) S within 10% ({S[pick]:.3f} vs {S[other]:.3f}): traceability order C > B -> {pick2}')
        pick = pick2
    if pick == 'C' and S['C'] >= 1.10*S['B']:
        decision['path'].append('(iii) C is >= 10% worse than B: keep B'); pick = 'B'
    decision['selected'] = pick
    print('\nDECISION (B vs C; C2 supplementary only):', pick); [print('  -', s) for s in decision['path']]
if a.json:
    json.dump({'table': table, 'decision': decision, 'res': {f'{k[0]}/{k[1]}': v for k, v in res.items()}}, open(a.json, 'w'), indent=1)
