#!/usr/bin/env python3
"""PF posterior vs GT at the END of recorded align / grasp_lift stage probes (offline; GT = evaluation only).

The stage_stop checkpoint stores each robot's particles (r*_px, r*_logw). Weighted mean/std vs the GT base pose at stop.
Also the stated prior at stage start (case.prior mean, std) vs the GT placement, i.e. the initial PF error each source used.
Usage: pf_at_stage_end.py [raw ...]   (default: every align / grasp_lift raw with a stage_stop checkpoint)
"""
import json, math, sys, glob
from pathlib import Path
import numpy as np
OUT = Path('/Users/changmin/projects/ugrp/outputs')
def wrap(a): return (a + math.pi) % (2*math.pi) - math.pi
def stats(px, logw):
    w = np.exp(logw - logw.max()); w /= w.sum()
    m = (w[:, None]*px).sum(0)
    yaw_m = math.atan2((w*np.sin(px[:, 2])).sum(), (w*np.cos(px[:, 2])).sum())
    d = px[:, :2] - m[:2]
    cov = (w[:, None, None]*d[:, :, None]*d[:, None, :]).sum(0)
    return m[0], m[1], yaw_m, math.sqrt(cov[0, 0] + cov[1, 1]), math.sqrt((w*np.array([wrap(a - yaw_m) for a in px[:, 2]])**2).sum())
rows = []
raws = sys.argv[1:] or [p.name.removeprefix('pair-stage-probes-') for p in sorted(OUT.glob('pair-stage-probes-*'))]
for raw in raws:
    root = OUT/f'pair-stage-probes-{raw}'
    if not (root/'cases.jsonl').exists():
        continue
    for line in open(root/'cases.jsonl'):
        r = json.loads(line)
        if r['stage'] not in ('align', 'grasp_lift'):
            continue
        d = root/'cases'/r['case_id'].replace('@', '_').replace(':', '_').replace('/', '_')
        try:
            npz = np.load(d/'checkpoints/stage_stop.npz'); res = json.load(open(d/'result.json')); case = json.load(open(d/'case.json'))
        except Exception:
            continue
        g = res.get('gt_at_stop') or res.get('gt_at_end')
        if not g:
            continue
        for rid in ('r1', 'r2'):
            mx, my, myaw, sxy, syaw = stats(npz[f'{rid}_px'], npz[f'{rid}_logw'])
            gt = g['robots'][rid]
            pr = case['prior'][rid] if 'prior' in case and rid in case['prior'] else None
            pg = case['placement_xyyaw'][rid]
            rows.append(dict(raw=raw, stage=r['stage'], source=r['source'], policy=r.get('pair_policy'), cell=r['cell'], rid=rid, passed=r['passed'],
                             ex=gt[0] - mx, ey=gt[1] - my, eyaw=wrap(gt[2] - myaw), sxy=sxy, syaw=syaw,
                             prior_ey=(pg[1] - pr['mean_xyyaw'][1]) if pr else None, prior_ex=(pg[0] - pr['mean_xyyaw'][0]) if pr else None,
                             prior_sxy=pr['std_xy_m'] if pr else None, last_tag_t=res.get('localizer_stats', {}).get(rid)))
json.dump(rows, open(Path(__file__).with_name('pf_at_stage_end.json'), 'w'), indent=0)
def q(v):
    a = np.abs(np.array(v, float)); return 'med %.3f p90 %.3f p95 %.3f max %.3f' % (np.median(a), np.percentile(a, 90), np.percentile(a, 95), a.max())
groups = {}
for r in rows:
    groups.setdefault((r['stage'], r['source'], r['policy']), []).append(r)
for k, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
    pri = [x['prior_ey'] for x in rs if x['prior_ey'] is not None]
    print(f'{k} n={len(rs)}  |y err at stop| {q([x["ey"] for x in rs])} | |x err| {q([x["ex"] for x in rs])} | yaw err deg {q([math.degrees(x["eyaw"]) for x in rs])} | sxy med {np.median([x["sxy"] for x in rs]):.3f}'
          + (f' | START |prior y err| {q(pri)}' if pri else ''))
