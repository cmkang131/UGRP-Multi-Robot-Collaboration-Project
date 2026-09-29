"""Shared loaders for the carry along-track bias analysis (offline; GT is read for evaluation/fitting only).

A "case dir" is one probe case under ``outputs/<raw>/cases/<name>/`` with ``eval_only/trace.jsonl`` (GT poses every
0.05 s and the PF posterior every 0.25 s), ``commands.json`` (issued commands per robot) and ``result.json``.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

OUT = Path('/Users/changmin/projects/ugrp/outputs')
ROBOTS = ('r1', 'r2')
STEP = 0.05
TAU = 0.8          # loaded lag (carry_dr_fit_cal1 mean_model.tau_s)
TAU_STOP = 0.05
GAIN_FWD = 1.4004  # loaded forward gain in the registered loaded profile


def wrap(a):
    return (a + np.pi) % (2*np.pi) - np.pi


def sha256(path, n=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:n] if n else h.hexdigest()


def cases_of(raw):
    """[(case_dir, case_id, meta_row)] of a raw run directory (cases.jsonl order)."""
    raw = Path(raw)
    rows = [json.loads(line) for line in open(raw/'cases.jsonl')]
    out = []
    for r in rows:
        cid = r['case_id']
        # case dir names are the case id with separators replaced; find by matching case.json
        out.append((cid, r))
    dirs = {}
    for cj in (raw/'cases').glob('*.case.json'):
        d = json.load(open(cj))
        dirs[d['case_id']] = raw/'cases'/cj.name[:-len('.case.json')]
    return [(dirs[cid], cid, r) for cid, r in out if cid in dirs]


def load_case(case_dir):
    case_dir = Path(case_dir)
    rows = [json.loads(line) for line in open(case_dir/'eval_only'/'trace.jsonl')]
    t = np.array([r['t'] for r in rows])
    gt = {k: np.array([r['robots'][k] for r in rows]) for k in ROBOTS}
    pf_idx = np.array([i for i, r in enumerate(rows) if 'pf' in r])
    pf = {}
    for k in ROBOTS:
        pf[k] = {
            't': np.array([rows[i]['pf'][k]['t'] for i in pf_idx]),
            'xyyaw': np.array([[rows[i]['pf'][k]['x'], rows[i]['pf'][k]['y'], rows[i]['pf'][k]['yaw']] for i in pf_idx]),
            'cov': np.array([rows[i]['pf'][k]['cov'] for i in pf_idx]),
            'std_xy': np.array([rows[i]['pf'][k]['std_xy_m'] for i in pf_idx]),
            'std_yaw': np.array([rows[i]['pf'][k]['std_yaw_rad'] for i in pf_idx]),
        }
    states = {k: [r['states'][k] for r in rows] for k in ROBOTS}
    cmds = json.load(open(case_dir/'commands.json'))
    res = json.load(open(case_dir/'result.json'))
    return {'t': t, 'gt': gt, 'pf': pf, 'pf_i': pf_idx, 'states': states, 'cmds': cmds, 'result': res,
            'case_json': json.load(open(str(case_dir)+'.case.json')), 'dir': str(case_dir)}


def base_cmds(cmds, k):
    """Sorted [(t, forward, left, turn, expires)] of base commands (hold = zeros, expiring at once)."""
    out = []
    for r in cmds[k]:
        if r['kind'] == 'mecanum':
            out.append((r['t'], r['forward'], r['left'], r['turn'], r['t'] + r['duration_s']))
        elif r['kind'] == 'drive':
            out.append((r['t'], r['forward'], 0., r['turn'], r['t'] + r['duration_s']))
        elif r['kind'] in ('hold', 'stop'):
            out.append((r['t'], 0., 0., 0., r['t']))
    out.sort()
    return out


def cmd_series(bcmds, t0, t1, dt=STEP):
    """Live command vector on the grid t0..t1 (the PF's rule: last command holds until it expires)."""
    ts = np.arange(t0, t1 + 1e-9, dt)
    u = np.zeros((len(ts), 3))
    j = -1
    exp = -1.
    cur = np.zeros(3)
    for i, t in enumerate(ts):
        while j + 1 < len(bcmds) and bcmds[j + 1][0] <= t + 1e-9:
            j += 1
            cur = np.array(bcmds[j][1:4])
            exp = bcmds[j][4]
        u[i] = cur if t < exp - 1e-9 else 0.
    return ts, u


def interp_gt(c, k, tq):
    """GT (x, y, yaw) at times tq (linear, yaw unwrapped locally)."""
    t = c['t']
    g = c['gt'][k]
    yaw = np.unwrap(g[:, 2])
    return np.stack([np.interp(tq, t, g[:, 0]), np.interp(tq, t, g[:, 1]), np.interp(tq, t, yaw)], -1)


def interp_pf(c, k, tq):
    p = c['pf'][k]
    yaw = np.unwrap(p['xyyaw'][:, 2])
    return np.stack([np.interp(tq, p['t'], p['xyyaw'][:, 0]), np.interp(tq, p['t'], p['xyyaw'][:, 1]),
                     np.interp(tq, p['t'], yaw)], -1)


def segments(c, k):
    """Carry legs of robot ``k``: [{leg, t_carry, t_drive, t_end}] from the controller timeline and the commands.

    ``t_carry`` = state 'carry' entry, ``t_drive`` = first base command with |forward| >= 0.02 (the axial cruise),
    ``t_end`` = state change out of 'carry' (wait_lower). Single-leg cases have one segment.
    """
    ts, st = c['t'], c['states'][k]
    segs = []
    cur = None
    for t, s in zip(ts, st):
        if s == 'carry' and cur is None:
            cur = {'t_carry': float(t)}
        elif s != 'carry' and cur is not None:
            cur['t_end'] = float(t)
            segs.append(cur)
            cur = None
    if cur is not None:
        cur['t_end'] = float(ts[-1])
        segs.append(cur)
    b = base_cmds(c['cmds'], k)
    for i, s in enumerate(segs):
        s['leg'] = i
        drive = [x[0] for x in b if s['t_carry'] <= x[0] < s['t_end'] and abs(x[1]) >= 0.02]
        s['t_drive'] = drive[0] if drive else s['t_end']
    return segs


def mean_model_body(bcmds, t0, t1, gain, tau=TAU, tau_stop=TAU_STOP, deadband=None, dt=STEP):
    """Deterministic mean of the PF's loaded motion model (harness/owncam_localizer.py::predict_to, unit slip scale).

    Returns cumulative body-frame displacement [forward, left, yaw] at every grid time and the grid, starting at rest.
    ``gain``: 3x3 body-velocity gain, ``deadband``: {'c0','u1'} per axis (or None).
    """
    gain = np.asarray(gain, float)
    ts, u = cmd_series(bcmds, t0, t1, dt)
    vel = np.zeros(3)
    pos = np.zeros((len(ts), 3))
    for i in range(1, len(ts)):
        ui = u[i-1].copy()
        if deadband is not None and np.any(ui):
            c0 = np.asarray(deadband['c0'], float)
            u1 = np.asarray(deadband['u1'], float)
            ui = ui*np.where(u1 > c0, np.clip((np.abs(ui) - c0)/np.maximum(u1 - c0, 1e-9), 0., 1.), 1.)
        target = gain @ ui
        a = 1. - math.exp(-dt/(tau_stop if not np.any(u[i-1]) else tau))
        vel = vel + a*(target - vel)
        pos[i] = pos[i-1] + vel*dt
    return ts, pos


def mean_model_u(u, gain, tau=TAU, tau_stop=TAU_STOP, deadband=None, dt=STEP):
    """Same as ``mean_model_body`` but from a live-command grid ``u`` (n, 3) (row i holds during step i -> i+1)."""
    gain = np.asarray(gain, float)
    vel = np.zeros(3)
    pos = np.zeros((len(u), 3))
    ax = 1. - math.exp(-dt/tau)
    as_ = 1. - math.exp(-dt/tau_stop)
    c0 = u1 = None
    if deadband is not None:
        c0 = np.asarray(deadband['c0'], float)
        u1 = np.asarray(deadband['u1'], float)
    for i in range(1, len(u)):
        ui = u[i-1]
        live = bool(np.any(ui))
        if live and c0 is not None:
            ui = ui*np.where(u1 > c0, np.clip((np.abs(ui) - c0)/np.maximum(u1 - c0, 1e-9), 0., 1.), 1.)
        vel = vel + (ax if live else as_)*(gain @ ui - vel)
        pos[i] = pos[i-1] + vel*dt
    return pos
