"""Loaders for stage-probe raw case directories (offline analysis only; GT is used for labels, never as a detector input).

A case dir has robots.json (per-frame time/servo/report), commands.json (own published commands), eval_only/trace.jsonl
(GT poses at 20 Hz, evaluation only) and frames/<rid>/NNNNN.jpg (wrist RGB for r1/r2, TOP camera for r3).
"""
import json
import math
from pathlib import Path

import numpy as np

OUT = Path('/Users/changmin/projects/ugrp/outputs')


def load_case(case_dir):
    case_dir = Path(case_dir)
    robots = json.loads((case_dir / 'robots.json').read_text())
    cmds = json.loads((case_dir / 'commands.json').read_text())
    trace = [json.loads(line) for line in (case_dir / 'eval_only/trace.jsonl').read_text().splitlines() if line.strip()]
    return robots, cmds, trace


def frame_times(robots, rid):
    return np.array([f['t'] for f in robots[rid]['frames']])


def gt_track(trace, rid):
    """(t, x, y, yaw) arrays of the GT robot pose from the evaluation trace."""
    rows = [(r['t'], *r['robots'][rid]) for r in trace if r.get('robots') and rid in r['robots']]
    a = np.array(rows)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def gt_beam(trace):
    rows = [(r['t'], r['beam_xyz'][0], r['beam_xyz'][1], r['beam_yaw']) for r in trace if 'beam_xyz' in r]
    a = np.array(rows)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


def cmd_series(cmds, rid):
    """Piecewise-constant commanded (forward, left, turn) at time t (own published mecanum commands)."""
    m = [e for e in cmds[rid] if e.get('kind') == 'mecanum']
    holds = sorted(e['t'] for e in cmds[rid] if e.get('kind') == 'hold')
    t = np.array([e['t'] for e in m])
    v = np.array([[e['forward'], e['left'], e['turn']] for e in m]) if m else np.zeros((0, 3))
    dur = np.array([e.get('duration_s', 0.15) for e in m])
    return t, v, dur, np.array(holds)


def cmd_at(series, tq):
    t, v, dur, holds = series
    out = np.zeros((len(tq), 3))
    if len(t) == 0:
        return out
    idx = np.searchsorted(t, tq, side='right') - 1
    for k, (i, q) in enumerate(zip(idx, tq)):
        if i >= 0 and q < t[i] + dur[i] + 1e-9:
            if len(holds) and np.any((holds > t[i]) & (holds <= q)):
                continue
            out[k] = v[i]
    return out


def interp_pose(t, x, y, tq):
    return np.interp(tq, t, x), np.interp(tq, t, y)


def wilson(k, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0., c - h), min(1., c + h))


def auc(pos, neg):
    """Mann-Whitney AUC, ties count 1/2. pos/neg are 1-D arrays; larger value = 'more positive'."""
    pos = np.asarray(pos, float)
    neg = np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float('nan')
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind='mergesort')
    ranks = np.empty(len(allv))
    sv = allv[order]
    i = 0
    r = np.empty(len(allv))
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        r[i:j + 1] = (i + j) / 2 + 1
        i = j + 1
    ranks[order] = r
    u = ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2
    return u / (len(pos) * len(neg))
