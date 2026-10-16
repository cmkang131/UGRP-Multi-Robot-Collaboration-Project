"""Summarise outputs/stall-detection-research/flow_rows_lag1.json (too big for git, sha256 in results/raw_outputs.sha256) (flow_feasibility.py, 1.0 s frame lag): class medians, AUC with case-cluster bootstrap."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from common import auc

rows = json.load(open(Path('/Users/changmin/projects/ugrp/outputs/stall-detection-research/flow_rows_lag1.json')))
feats = ['mad_full', 'mad_dark', 'pc_dark_px', 'pc_resp', 'pc_full_px', 'fb_dark_px', 'beam_edge_dpx']
lab = {l: [r for r in rows if r['label'] == l] for l in ('STALL', 'MOVING', 'REST')}
out = {'n_pairs': {l: len(v) for l, v in lab.items()},
       'n_cases': {l: len({r['case'] for r in v}) for l, v in lab.items()},
       'gt_d_mm_median': {l: float(np.median([r['gt_d_m'] for r in v]) * 1e3) for l, v in lab.items()},
       'cmd_mm_median': {l: float(np.median([r['cmd_m'] for r in v]) * 1e3) for l, v in lab.items()}}
rng = np.random.default_rng(0)
res = {}
for f in feats:
    g = {l: np.array([r[f] for r in v if r[f] is not None], float) for l, v in lab.items()}
    d = {l: {'n': int(len(a)), 'p05': float(np.percentile(a, 5)), 'med': float(np.median(a)), 'p95': float(np.percentile(a, 95))} if len(a) else None for l, a in g.items()}
    a_pt = auc(g['MOVING'], g['STALL'])
    # case-cluster bootstrap: resample stalled cases and moving cases
    sc = sorted({r['case'] for r in lab['STALL']}); mc = sorted({r['case'] for r in lab['MOVING']})
    bys = {c: np.array([r[f] for r in lab['STALL'] if r['case'] == c and r[f] is not None], float) for c in sc}
    bym = {c: np.array([r[f] for r in lab['MOVING'] if r['case'] == c and r[f] is not None], float) for c in mc}
    bs = []
    for _ in range(300):
        s = np.concatenate([bys[c] for c in rng.choice(sc, len(sc))]); m = np.concatenate([bym[c] for c in rng.choice(mc, len(mc))])
        if len(s) and len(m):
            bs.append(auc(m, s))
    res[f] = {'classes': d, 'auc_moving_gt_stall': a_pt, 'auc_ci95_case_bootstrap': [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]}
out['features'] = res
Path(__file__).parent.joinpath('results/flow_lag1_summary.json').write_text(json.dumps(out, indent=1))
print(json.dumps(out['n_pairs']), json.dumps(out['n_cases']), out['gt_d_mm_median'], out['cmd_mm_median'])
for f, v in res.items():
    c = v['classes']
    print(f'{f:14s} AUC {v["auc_moving_gt_stall"]:.3f} CI {v["auc_ci95_case_bootstrap"][0]:.3f}-{v["auc_ci95_case_bootstrap"][1]:.3f}  ' +
          '  '.join(f'{l}:{c[l]["med"]:.4g}[{c[l]["p05"]:.3g},{c[l]["p95"]:.3g}]' if c[l] else f'{l}:-' for l in ('STALL', 'MOVING', 'REST')))
