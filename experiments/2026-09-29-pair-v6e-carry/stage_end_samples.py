"""Shared helpers for the recorded-state samples (hG: align end -> grasp_lift; hR2: grasp_lift end -> carry).

A sample is one recorded stage end state: the GT beam and robot base poses at stop (staging only) and each robot's recorded PF
posterior (weighted particle mean / spread from checkpoints/stage_stop.npz), stored as the (PF - GT) error so the staged case can
seed the controller's start prior as a stated Gaussian. Offline reading of existing raws; no physics.
"""
import json, math, re
from pathlib import Path
import numpy as np

OUT = Path('/Users/changmin/projects/ugrp/outputs')


def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def posterior(npz, rid):
    px, logw = npz[f'{rid}_px'], npz[f'{rid}_logw']
    w = np.exp(logw - logw.max()); w /= w.sum()
    m = (w[:, None]*px).sum(0)
    yaw = math.atan2((w*np.sin(px[:, 2])).sum(), (w*np.cos(px[:, 2])).sum())
    d = px[:, :2] - m[:2]
    cov = (w[:, None, None]*d[:, :, None]*d[:, None, :]).sum(0)
    syaw = math.sqrt((w*np.array([wrap(a - yaw) for a in px[:, 2]])**2).sum())
    return [float(m[0]), float(m[1]), float(yaw)], float(math.sqrt(cov[0, 0] + cov[1, 1])), float(syaw)


def case_dir(row):
    """The per-case raw dir of a cases.jsonl row (rows of a 'combined' raw carry raw_dir of their source raw)."""
    if not row.get('raw_dir'):
        return None
    d = Path(row['raw_dir'])/'cases'/re.sub(r'[^A-Za-z0-9_.+-]+', '_', row['case_id'])
    return d if d.exists() else None


def sample(sid, row, d, note):
    res = json.load(open(d/'result.json')); g = res['gt_at_stop']
    npz = np.load(d/'checkpoints/stage_stop.npz')
    post = {rid: posterior(npz, rid) for rid in ('r1', 'r2')}
    robots = {k: [float(v) for v in g['robots'][k]] for k in ('r1', 'r2')}
    return {'id': sid, 'source_case_id': row['case_id'], 'source_raw_dir': str(d), 'note': note,
            'beam_xyyaw': [float(g['beam_xyz'][0]), float(g['beam_xyz'][1]), float(g['beam_yaw'])],
            'robots': robots,
            'prior_err': {k: {'mean_err_xyyaw': [post[k][0][0] - robots[k][0], post[k][0][1] - robots[k][1], wrap(post[k][0][2] - robots[k][2])],
                              'std_xy_m': post[k][1], 'std_yaw_rad': post[k][2]} for k in post}}


def show(samples):
    for s in samples:
        e = s['prior_err']
        print(s['id'], s['source_case_id'][:48].ljust(48), ' | '.join('%s PF-GT x%+.3f y%+.3f yaw%+.2fdeg sxy %.3f' % (
            k, e[k]['mean_err_xyyaw'][0], e[k]['mean_err_xyyaw'][1], math.degrees(e[k]['mean_err_xyyaw'][2]), e[k]['std_xy_m']) for k in ('r1', 'r2')))
