#!/usr/bin/env python3
"""Per-leg comparison of replayed PF estimates against recorded truth (evaluation only; truth never drives a replay).

For each own-command leg (a run of >= MIN_TICKS identical non-zero commands in robots/<rid>/commands.jsonl) of the
recorded case, over the window [first command, last command + 0.15 s lease + COAST_S]:
  D_truth   displacement of the true chassis along the commanded body axis (truth heading at the leg start)
  D_est     the same displacement of the PF estimate, in the estimate's OWN heading at the leg start (so a prior yaw error does not rotate the leg)
  ratio     D_est / D_truth       (dead reckoning, --nomeasure runs: includes the estimate's own heading drift)
  D_vel     time integral of the PF mean body velocity on the commanded axis: the pure model prediction, heading-independent
  d_err     D_est - D_truth, cross_err = cross-axis displacement difference, eyaw = yaw displacement difference (deg)
  e_end     |est - truth| position error at the window end, NEES2 there (measured runs)
usage: leg_summary.py RAW ROBOT LABEL=replay.jsonl [LABEL=replay.jsonl ...]
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_pf import load_truth, truth_at, load_replay, score_frames, wrap  # noqa: E402

MIN_TICKS = 20
COAST_S = 3.0
LEASE_S = 0.15


def legs_of(raw, rid):
    rows = [json.loads(l) for l in open(f'{raw}/robots/{rid}/commands.jsonl')]
    legs, cur = [], None
    for r in rows:
        a = r.get('action') or r
        if r.get('kind') in ('initial_servo_command',) or 'forward' not in a:
            cur = None
            continue
        key = (a.get('forward'), a.get('left'), a.get('turn'))
        if not any(key):
            cur = None
            continue
        if cur and cur['key'] == key and abs(r['t'] - cur['t1'] - .1) < .06:
            cur['t1'], cur['n'] = r['t'], cur['n'] + 1
        else:
            cur = {'key': key, 't0': r['t'], 't1': r['t'], 'n': 1}
            legs.append(cur)
    return [l for l in legs if l['n'] >= MIN_TICKS]


def est_at(frames, t):
    ts = np.array([f['t'] for f in frames])
    i = int(np.argmin(abs(ts - t)))
    f = frames[i]
    return f['x'], f['y'], f['yaw'], f


def leg_row(raw, rid, leg, frames, tr):
    t0, t1 = leg['t0'], leg['t1'] + LEASE_S + COAST_S
    gx0, gy0, gyaw0 = truth_at(tr, t0)
    gx1, gy1, gyaw1 = truth_at(tr, t1)
    ex0, ey0, eyaw0, _ = est_at(frames, t0)
    ex1, ey1, eyaw1, f1 = est_at(frames, t1)

    def body(dx, dy, yaw):
        c, s = math.cos(yaw), math.sin(yaw)
        return np.array([c*dx + s*dy, -s*dx + c*dy])        # (forward, left) at the leg-start heading
    tb = body(gx1 - gx0, gy1 - gy0, gyaw0)                  # truth displacement in the truth heading frame
    eb = body(ex1 - ex0, ey1 - ey0, eyaw0)                  # estimate displacement in the estimate's own heading frame
    axis = 0 if abs(leg['key'][0] or 0) > abs(leg['key'][1] or 0) else 1
    u = leg['key'][axis]
    cross = 1 - axis
    sign = 1. if u > 0 else -1.
    dt_, de_ = sign*tb[axis], sign*eb[axis]
    S = score_frames([f1], tr)
    ts = np.array([f['t'] for f in frames])
    m = (ts >= t0) & (ts <= t1)
    vv = np.array([f['vel'][axis] for f, k in zip(frames, m) if k])
    tt = ts[m]
    d_vel = sign*float(np.sum(.5*(vv[1:] + vv[:-1])*np.diff(tt))) if len(tt) > 1 else float('nan')   # integral of the PF mean body velocity
    return {'D_vel': d_vel, 'ratio_vel': d_vel/dt_ if abs(dt_) > 1e-6 else float('nan'), 'axis': 'forward' if axis == 0 else 'left', 'u': u, 'n': leg['n'], 't0': t0, 't1': t1,
            'D_truth': dt_, 'D_est': de_, 'ratio': de_/dt_ if abs(dt_) > 1e-6 else float('nan'), 'd_err': de_ - dt_,
            'cross_err': eb[cross] - tb[cross], 'eyaw_deg': math.degrees(wrap((eyaw1 - eyaw0) - (gyaw1 - gyaw0))),
            'e_end': S[0]['err'] if S else float('nan'), 'nees2': S[0]['nees2'] if S else float('nan'),
            'ey_end_body': float(body(ex1 - gx1, ey1 - gy1, gyaw1)[1])}


def main(argv):
    raw, rid, pairs = argv[0], argv[1], argv[2:]
    tr = load_truth(raw, rid)
    legs = legs_of(raw, rid)
    print(f'{rid}: {len(legs)} legs  ' + '  '.join(f"[{l['key'][0]:+.4f},{l['key'][1]:+.4f}] {l['t0']:.1f}-{l['t1']:.1f}s x{l['n']}" for l in legs))
    out = {}
    for pair in pairs:
        label, path = pair.split('=', 1)
        frames = load_replay(path)[0]
        frames = [f for f in frames if f['initialized']]
        rows = [leg_row(raw, rid, l, frames, tr) for l in legs]
        out[label] = rows
        print(f'\n== {label}')
        print('  axis    u        t0      D_truth  D_est   ratio  D_vel  ratio_v d_err_mm cross_mm eyaw_deg  e_end_mm  NEES2')
        for r in rows:
            print(f"  {r['axis']:7s}{r['u']:+.4f} {r['t0']:7.1f}  {r['D_truth']:7.4f} {r['D_est']:7.4f} {r['ratio']:7.4f} {r['D_vel']:7.4f} {r['ratio_vel']:7.4f} "
                  f"{1000*r['d_err']:8.1f} {1000*r['cross_err']:8.1f} {r['eyaw_deg']:8.2f}  {1000*r['e_end']:8.1f} {r['nees2']:7.1f}")
    return out


if __name__ == '__main__':
    main(sys.argv[1:])
