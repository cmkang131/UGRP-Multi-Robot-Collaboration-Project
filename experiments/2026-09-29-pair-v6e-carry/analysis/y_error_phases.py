#!/usr/bin/env python3
"""Two-phase view of the carry-stage lateral error (offline, GT only to score; read-only on raw).

Every stage-probe carry case has a ~6 s 'steer' phase (own-estimate route-line correction: tiny body-lateral
commands, |left| < 0.03) followed by the planned leg (|cmd| ~ 0.04-0.05). Per phase, per robot: the issued body-lateral
command, the ground-truth body-lateral travel, and the PF body-lateral travel (PF poses are every 0.25 s).
Then a deadband fit of the loaded lateral response to the steer commands.

Usage: y_error_phases.py <raw dir> [<raw dir> ...]
"""
import json, math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from y_error_decomposition import body_incr, wrap  # noqa: E402

LEG_CMD = .03      # a command with |left| or |forward| above this starts the planned leg


def phase_split(cmds):
    mc = [c for c in cmds if c['kind'] == 'mecanum']
    big = [c['t'] for c in mc if max(abs(c['forward']), abs(c['left'])) > LEG_CMD]
    steer = [c for c in mc if max(abs(c['forward']), abs(c['left'])) <= LEG_CMD and (not big or c['t'] < big[0])]
    return (big[0] if big else None), steer


def travel(rows, rid, t0, t1):
    sel = [r for r in rows if t0 - 1e-6 <= r['t'] <= t1 + 1e-6]
    if len(sel) < 2:
        return None
    g = np.array([r['robots'][rid] for r in sel])
    p = np.array([[r['pf'][rid]['x'], r['pf'][rid]['y'], r['pf'][rid]['yaw']] for r in sel])
    out = {}
    for name, a in (('gt', g), ('pf', p)):
        bx, by, _ = body_incr(a[:, 0], a[:, 1], np.unwrap(a[:, 2]))
        out[name] = (float(bx.sum()), float(by.sum()), float(a[-1, 1] - a[0, 1]), math.degrees(np.unwrap(a[:, 2])[-1] - np.unwrap(a[:, 2])[0]))
    return out


def collect(raws):
    res = []
    for raw in raws:
        raw = Path(raw)
        for cd in sorted((raw/'cases').iterdir()):
            if not (cd/'eval_only'/'trace.jsonl').exists():
                continue
            case = json.load(open(cd/'case.json'))
            cid = case['case_id']
            leg = int(cid.split(':L')[1].split(':')[0]) if ':L' in cid else 0
            rows = [json.loads(l) for l in open(cd/'eval_only'/'trace.jsonl')]
            rows = [r for r in rows if 'pf' in r]
            cmds = json.load(open(cd/'commands.json'))
            for rid in ('r1', 'r2'):
                t_leg, steer = phase_split(cmds[rid])
                if t_leg is None or not steer:
                    continue
                ts, te = steer[0]['t'], steer[-1]['t'] + steer[-1]['duration_s']
                a = travel(rows, rid, ts, t_leg)
                b = travel(rows, rid, t_leg, rows[-1]['t'])
                if a is None or b is None:
                    continue
                res.append(dict(batch=raw.name.split('-')[-1], cell=case['cell'], leg=leg, rid=rid, beam_y=case['beam_xyyaw'][1],
                                u_left=float(np.mean([c['left'] for c in steer])), T=te - ts, steer=a, leg_ph=b, lateral_leg=leg in (3, 4, 5)))
    return res


if __name__ == '__main__':
    res = collect(sys.argv[1:])
    print('== steer phase (T ~ 5.9 s), body-lateral travel [m]: command u, GT, PF (PF/GT of the command-linear model: gain 1.016)')
    print('batch cell leg rid u_left | GT_lat PF_lat | GT dyaw | leg-phase (axial legs only): GT_lat PF_lat GT dyaw PF dyaw')
    for r in res:
        if r['lateral_leg']:
            continue
        print(f"{r['batch']:6s} {r['cell']:9s} L{r['leg']} {r['rid']} {r['u_left']:+.4f} | {r['steer']['gt'][1]:+.4f} {r['steer']['pf'][1]:+.4f} | {r['steer']['gt'][3]:+.2f} | "
              f"{r['leg_ph']['gt'][1]:+.4f} {r['leg_ph']['pf'][1]:+.4f} {r['leg_ph']['gt'][3]:+.2f} {r['leg_ph']['pf'][3]:+.2f}")
    # deadband fit v = a * sign(u) * max(|u| - c0, 0)   (effective time T_eff = T - tau(1-exp(-T/tau)), tau = .8 s loaded)
    u = np.array([r['u_left'] for r in res]); T = np.array([r['T'] for r in res])
    teff = T - .8*(1 - np.exp(-T/.8))
    gt = np.array([r['steer']['gt'][1] for r in res]); pf = np.array([r['steer']['pf'][1] for r in res])
    best = None
    for c0 in np.linspace(0, .012, 121):
        x = np.sign(u)*np.maximum(np.abs(u) - c0, 0)*teff
        a = float(x@gt/(x@x)) if x@x > 0 else 0.
        rss = float(np.sum((gt - a*x)**2))
        if best is None or rss < best[0]:
            best = (rss, c0, a)
    lin_a = float((u*teff)@gt/((u*teff)@(u*teff)))
    rss_lin = float(np.sum((gt - lin_a*u*teff)**2))
    print(f"\nsteer-phase response over {len(res)} case-robots: |u| {np.abs(u).min():.4f}..{np.abs(u).max():.4f}")
    print(f"  linear fit  GT = {lin_a:.3f} * u * Teff: rms {math.sqrt(rss_lin/len(u))*1e3:.1f} mm")
    print(f"  deadband fit GT = {best[2]:.3f} * sgn(u) * max(|u| - {best[1]:.4f}, 0) * Teff: rms {math.sqrt(best[0]/len(u))*1e3:.1f} mm")
    print(f"  PF (linear model, gain 1.016) mean body-lateral {np.mean(np.abs(pf))*1e3:.1f} mm vs GT {np.mean(np.abs(gt))*1e3:.1f} mm")
    # unexplained by deadband: per batch/cell mean signed error PF-GT of the steer phase (body lateral sign-normalised by u)
    print('\nsteer-phase PF-GT body-lateral error (signed along the command), mean over robots/legs [mm]:')
    keyed = {}
    for r in res:
        s = np.sign(r['u_left']) or 1.
        keyed.setdefault((r['batch'], r['cell']), []).append(s*(r['steer']['pf'][1] - r['steer']['gt'][1]))
    for k, v in sorted(keyed.items()):
        print(f'  {k[0]:6s} {k[1]:9s} n={len(v):2d} mean {np.mean(v)*1e3:+5.1f}  sd {np.std(v)*1e3:4.1f}')
