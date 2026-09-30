"""Shared loaders for the stall-detection feasibility scripts (offline, read-only).

Reads recorded stage-probe raw dirs under outputs/. GT poses (eval_only/trace.jsonl)
are used ONLY to label stalled/moving windows for scoring; detectors never see them.
"""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np

OUT = Path('/Users/changmin/projects/ugrp/outputs')


def load_case(case_dir: Path):
    case_dir = Path(case_dir)
    rows = [json.loads(l) for l in open(case_dir / 'eval_only' / 'trace.jsonl')]
    host = json.load(open(case_dir / 'eval_only' / 'host.json'))
    cmds = json.load(open(case_dir / 'commands.json'))
    t = np.array([r['t'] for r in rows])
    gt = {rid: np.array([r['robots'][rid] for r in rows]) for rid in ('r1', 'r2')}
    lift = np.array([r['lift_m'] for r in rows])
    jaws = {rid: np.array([all(r['jaws'][rid]) for r in rows]) for rid in ('r1', 'r2')}
    states = {rid: [r['states'][rid] for r in rows] for rid in ('r1', 'r2')}
    frames = {}
    for rid in ('r1', 'r2'):
        fe = [f for f in host['frames_eval'] if f['robot_id'] == rid]
        frames[rid] = (np.array([f['frame'] for f in fe]), np.array([f['t'] for f in fe]))
    mec = {}
    for rid in ('r1', 'r2'):
        m = [c for c in cmds[rid] if c['kind'] == 'mecanum']
        mec[rid] = (np.array([c['t'] for c in m]),
                    np.array([[c['forward'], c['left'], c['turn']] for c in m]),
                    np.array([c['duration_s'] for c in m]))
    return dict(t=t, gt=gt, lift=lift, jaws=jaws, states=states, frames=frames, mec=mec, dir=case_dir)


def interp_pose(c, rid, tq):
    """GT pose at time tq (linear x,y; angle wrapped)."""
    t = c['t']; g = c['gt'][rid]
    x = np.interp(tq, t, g[:, 0]); y = np.interp(tq, t, g[:, 1])
    yaw = np.interp(tq, t, np.unwrap(g[:, 2]))
    return x, y, yaw


def cmd_forward_distance(c, rid, t0, t1, dt=0.1):
    """Integrated commanded body-frame displacement (forward,left,turn*dt) issued in [t0,t1)."""
    ts, v, dur = c['mec'][rid]
    sel = (ts >= t0) & (ts < t1)
    return v[sel].sum(0) * dt  # (m fwd, m left, rad)
