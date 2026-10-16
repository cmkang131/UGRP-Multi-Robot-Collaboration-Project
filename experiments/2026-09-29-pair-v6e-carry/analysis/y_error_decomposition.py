#!/usr/bin/env python3
"""Where does the PF y error of a carry leg come from? (offline, eval-only GT, read-only on raw)

For each case and carrier robot the leg-end y error change  d(err_y) = dPF_y - dGT_y  is split by integrating
the per-step displacement in each trajectory's own body frame:

  heading  = sum (sin th_pf - sin th_gt) * dxb_gt  (+ cos term)   the PF heading differs from the true one
  fwd      = sum sin th_pf * (dxb_pf - dxb_gt)                    body-forward travel mismatch seen through heading
  lat      = sum cos th_pf * (dyb_pf - dyb_gt)                    body-lateral travel mismatch (slip / lag / coupling)

GT is used ONLY to score the filter here. Usage: y_error_decomposition.py <raw dir> [<raw dir> ...]
"""
import json, math, sys
from pathlib import Path
import numpy as np


def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def leg_of(case_id):
    return int(case_id.split(':L')[1].split(':')[0]) if ':L' in case_id else 0


def rows_of(case_dir):
    rows = [json.loads(l) for l in open(case_dir/'eval_only'/'trace.jsonl')]
    return [r for r in rows if 'pf' in r]


def body_incr(x, y, th):
    """per-step body-frame increments of a trajectory (x, y, th arrays), midpoint heading."""
    dx, dy = np.diff(x), np.diff(y)
    tm = th[:-1] + .5*np.array([wrap(a) for a in np.diff(th)])
    c, s = np.cos(tm), np.sin(tm)
    return c*dx + s*dy, -s*dx + c*dy, tm


def analyse(case_dir, rid):
    rows = rows_of(case_dir)
    if len(rows) < 3:
        return None
    t = np.array([r['t'] for r in rows])
    g = np.array([r['robots'][rid] for r in rows])
    p = np.array([[r['pf'][rid]['x'], r['pf'][rid]['y'], r['pf'][rid]['yaw']] for r in rows])
    sy = math.sqrt(rows[-1]['pf'][rid]['cov'][1][1])
    gx, gy, gth = g[:, 0], g[:, 1], np.unwrap(g[:, 2])
    px, py, pth = p[:, 0], p[:, 1], np.unwrap(p[:, 2])
    bxg, byg, tmg = body_incr(gx, gy, gth)
    bxp, byp, tmp = body_incr(px, py, pth)
    heading = float(np.sum((np.sin(tmp) - np.sin(tmg))*bxg + (np.cos(tmp) - np.cos(tmg))*byg))
    fwd = float(np.sum(np.sin(tmp)*(bxp - bxg)))
    lat = float(np.sum(np.cos(tmp)*(byp - byg)))
    d_err = float((py[-1] - gy[-1]) - (py[0] - gy[0]))
    return dict(t0=float(t[0]), t1=float(t[-1]), gt_dy=float(gy[-1]-gy[0]), pf_dy=float(py[-1]-py[0]),
                gt_dyaw=math.degrees(gth[-1]-gth[0]), pf_dyaw=math.degrees(pth[-1]-pth[0]),
                gt_fwd=float(np.sum(bxg)), gt_lat=float(np.sum(byg)), pf_fwd=float(np.sum(bxp)), pf_lat=float(np.sum(byp)),
                y_err0=float(py[0]-gy[0]), y_err1=float(py[-1]-gy[-1]), d_err=d_err, heading=heading, fwd=fwd, lat=lat,
                resid=d_err-(heading+fwd+lat), sigma_y=sy, gt_y0=float(gy[0]))


def main(raws):
    out = []
    for raw in raws:
        raw = Path(raw)
        for cd in sorted((raw/'cases').iterdir()):
            if not cd.is_dir() or not (cd/'eval_only'/'trace.jsonl').exists():
                continue
            case = json.load(open(cd/'case.json'))
            leg = leg_of(case['case_id'])
            for rid in ('r1', 'r2'):
                a = analyse(cd, rid)
                if a:
                    out.append(dict(raw=raw.name.split('-', 4)[-1], cell=case['cell'], setup=case.get('setup_variant'), leg=leg, rid=rid,
                                    beam_y=case['beam_xyyaw'][1], **a))
    return out


if __name__ == '__main__':
    res = main(sys.argv[1:])
    print('batch  cell  leg rid  beam_y | GT dy  PF dy | GT dyaw PF dyaw | GT fwd  GT lat  PF lat | y_err0 -> y_err1 (sigma_y) | d_err = heading + fwd + lat (+resid)   [m, deg]')
    for r in res:
        print(f"{r['raw']:8s} {r['cell']:9s} L{r['leg']} {r['rid']} {r['beam_y']:+.3f} | {r['gt_dy']:+.3f} {r['pf_dy']:+.3f} | {r['gt_dyaw']:+6.2f} {r['pf_dyaw']:+6.2f} | "
              f"{r['gt_fwd']:+.3f} {r['gt_lat']:+.3f} {r['pf_lat']:+.3f} | {r['y_err0']:+.3f} -> {r['y_err1']:+.3f} ({r['sigma_y']:.3f}) | "
              f"{r['d_err']:+.3f} = {r['heading']:+.3f} {r['fwd']:+.3f} {r['lat']:+.3f} ({r['resid']:+.3f})")
    json.dump(res, sys.stderr) if False else None
