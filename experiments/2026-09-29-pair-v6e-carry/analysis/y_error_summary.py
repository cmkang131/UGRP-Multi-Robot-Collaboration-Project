#!/usr/bin/env python3
"""Cell/batch table of the PF y error at the leg end and its parts (offline; GT only to score). Usage: y_error_summary.py <raw>..."""
import sys
from collections import defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
import y_error_decomposition as yd  # noqa: E402
import y_error_phases as yph  # noqa: E402

raws = sys.argv[1:]
dec = yd.main(raws)
ph = yph.collect(raws)
key = lambda r: (r['raw'].split('-')[-1] if '-' in r['raw'] else r['raw'], r['cell'])
by = defaultdict(list)
for r in dec:
    by[(r['raw'], r['cell'])].append(r)
phk = defaultdict(list)
for r in ph:
    phk[(r['batch'], r['cell'])].append(r)
mm = lambda v: f'{np.mean(v)*1e3:+6.1f}'
print('leg-end y error [mm] (PF - GT): start -> end, |end|, sigma_y, and how the change splits (heading / body-forward / body-lateral)')
print('batch     cell       n | y_err0 -> y_err1 (|end| mean) sigma_y | d_err = heading + fwd + lat | steer-phase body-lat GT / PF / PF-GT (along cmd) | axial-leg body-lat GT / PF')
for k in sorted(by):
    v = by[k]
    p = phk.get((k[0].split('-')[-1] if k not in phk else k[0], k[1]), [])
    p = [x for x in ph if x['cell'] == k[1] and x['batch'] in k[0]]
    ax = [x for x in p if not x['lateral_leg']]
    s = lambda f: np.mean([np.sign(x['u_left'] or 1.)*f(x) for x in ax]) if ax else float('nan')
    print(f"{k[0]:10s} {k[1]:9s} {len(v):3d} | {mm([r['y_err0'] for r in v])} -> {mm([r['y_err1'] for r in v])} ({np.mean([abs(r['y_err1']) for r in v])*1e3:5.1f}) {np.mean([r['sigma_y'] for r in v])*1e3:5.1f} | "
          f"{mm([r['d_err'] for r in v])} = {mm([r['heading'] for r in v])} {mm([r['fwd'] for r in v])} {mm([r['lat'] for r in v])} | "
          f"{s(lambda x: x['steer']['gt'][1])*1e3:+6.1f} {s(lambda x: x['steer']['pf'][1])*1e3:+6.1f} {(s(lambda x: x['steer']['pf'][1]-x['steer']['gt'][1]))*1e3:+6.1f} | "
          f"{np.mean([x['leg_ph']['gt'][1] for x in ax])*1e3:+5.1f} {np.mean([x['leg_ph']['pf'][1] for x in ax])*1e3:+5.1f}" if ax else '')
