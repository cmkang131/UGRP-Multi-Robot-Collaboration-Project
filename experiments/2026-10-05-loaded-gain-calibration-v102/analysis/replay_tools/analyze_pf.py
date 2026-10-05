#!/usr/bin/env python3
"""Score a replay_pf.py log against the recorded ground truth (evaluation only).

usage: analyze_pf.py RAWCASE ROBOT REPLAY.jsonl [--table DT]
"""
import json, math, sys, argparse
import numpy as np

def yaw_of(q):
    w, x, y, z = q
    return math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))

def load_truth(raw, rid):
    off = {'r1': 0, 'r2': 17, 'r3': 34}[rid]
    T = [json.loads(l) for l in open(f'{raw}/eval_only/trajectory.jsonl')]
    t = np.array([r['t'] for r in T])
    x = np.array([r['qpos'][off] for r in T]); y = np.array([r['qpos'][off+1] for r in T])
    yaw = np.unwrap([yaw_of(r['qpos'][off+3:off+7]) for r in T])
    return t, x, y, yaw

def truth_at(tr, tt):
    t, x, y, yaw = tr
    return np.interp(tt, t, x), np.interp(tt, t, y), np.interp(tt, t, yaw)

def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi

def load_replay(path):
    rows = [json.loads(l) for l in open(path)]
    return ([r for r in rows if r['kind'] == 'frame'], [r for r in rows if r['kind'] == 'scan'],
            [r for r in rows if r['kind'] == 'reloc'], [r for r in rows if r['kind'] == 'final'])

def score_frames(frames, tr):
    out = []
    for f in frames:
        if not f['initialized'] or f['cov'] is None:
            continue
        gx, gy, gyaw = truth_at(tr, f['t'])
        e = np.array([f['x'] - gx, f['y'] - gy]); eyaw = wrap(f['yaw'] - gyaw)
        C = np.array(f['cov'])
        Cxy = C[:2, :2]
        try:
            nees2 = float(e @ np.linalg.solve(Cxy, e))
        except np.linalg.LinAlgError:
            nees2 = float('nan')
        try:
            ee = np.array([e[0], e[1], eyaw]); nees3 = float(ee @ np.linalg.solve(C, ee))
        except np.linalg.LinAlgError:
            nees3 = float('nan')
        out.append(dict(t=f['t'], tnow=f['tnow'], gx=gx, gy=gy, gyaw=gyaw, ex=e[0], ey=e[1], eyaw=eyaw,
                        err=float(np.hypot(*e)), sx=math.sqrt(max(C[0, 0], 0)), sy=math.sqrt(max(C[1, 1], 0)),
                        syaw=math.sqrt(max(C[2, 2], 0)), sxy=f['std_xy'], nees2=nees2, nees3=nees3,
                        n_eff=f['n_eff'], since=f['since_scan'], measured=f['measured'], view_k=f['view_k']))
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('raw'); ap.add_argument('robot'); ap.add_argument('replay')
    ap.add_argument('--dt', type=float, default=5.0)
    a = ap.parse_args()
    tr = load_truth(a.raw, a.robot)
    frames, scans, relocs, final = load_replay(a.replay)
    S = score_frames(frames, tr)
    print('t gx gy | err_mm ex ey eyaw(mdeg) | sx sy syaw(mdeg) std_xy | NEES2 NEES3 | measured')
    nxt = 0
    for s in S:
        if s['t'] >= nxt:
            print(f"{s['t']:7.2f} {s['gx']:7.3f} {s['gy']:7.3f} | {1000*s['err']:6.1f} {1000*s['ex']:7.1f} {1000*s['ey']:7.1f} "
                  f"{math.degrees(s['eyaw'])*1000:7.0f} | {1000*s['sx']:6.1f} {1000*s['sy']:6.1f} {math.degrees(s['syaw'])*1000:7.0f} "
                  f"{1000*s['sxy']:6.1f} | {s['nees2']:8.1f} {s['nees3']:8.1f} | {s['measured']}")
            nxt += a.dt
