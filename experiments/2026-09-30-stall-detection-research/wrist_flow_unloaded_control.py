#!/usr/bin/env python3
"""Method control for wrist_flow_carry.py: the same image-motion measures on UNLOADED driving, where the wrist camera sees
floor, walls, tags and the beam.  If they separate moving from still pairs here but not under carry, the carry null result
comes from what the camera sees (a rigid load), not from the method.  Offline, recorded align-stage frames only.

Labels: MOVING = GT robot speed >= 0.03 m/s and the arm/look servo commands are identical in both frames (so the image change
is base motion, not arm motion); STILL = GT speed < 0.003 m/s and identical servo commands and no drive command in the last 0.5 s.
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wrist_flow_carry as w  # noqa: E402
from common import OUT, auc, cmd_at, cmd_series, frame_times, gt_track, interp_pose, load_case  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOTS = ['pair-stage-probes-2aa03454-grid1', 'pair-stage-probes-78332709-diagC', 'pair-stage-probes-78332709-v5hctl']


def rows_for(case_dir):
    robots, cmds, trace = load_case(case_dir)
    rows = []
    for rid in ('r1', 'r2'):
        fr = robots[rid]['frames']
        t = frame_times(robots, rid)
        tg, xg, yg, _ = gt_track(trace, rid)
        ser = cmd_series(cmds, rid)
        prev = None
        for i, f in enumerate(fr):
            if f['report'].get('load_state') != 'unloaded':
                prev = None
                continue
            cur = w.load(case_dir / 'frames' / rid / f'{i:05d}.jpg')
            if prev is not None and 0.08 <= t[i] - t[pi] <= 0.25 and fr[pi]['commanded_servo'] == f['commanded_servo']:
                m = w.pair_metrics(prev, cur)
                x0, y0 = interp_pose(tg, xg, yg, np.array([t[pi]]))
                x1, y1 = interp_pose(tg, xg, yg, np.array([t[i]]))
                v = float(np.hypot(x1 - x0, y1 - y0)[0] / (t[i] - t[pi]))
                c = cmd_at(ser, np.linspace(t[i] - 0.5, t[i], 6))
                quiet = bool((np.hypot(c[:, 0], c[:, 1]) < 0.005).all() and (np.abs(c[:, 2]) < 0.005).all())
                m.update(case=case_dir.name, rid=rid, t=float(t[i]), v_gt=v, quiet=quiet)
                rows.append(m)
            prev, pi = cur, i
    return rows


def main():
    cases = []
    for root in ROOTS:
        cases += [Path(p) for p in sorted(glob.glob(str(OUT / root / 'cases/align*/')))]
    rows = []
    used = 0
    for d in cases:
        try:
            c = json.load(open(d / 'commands.json'))
        except Exception:
            continue
        n = sum(1 for e in c.get('r1', []) if e.get('kind') == 'mecanum')
        if n < 40:
            continue
        rows += rows_for(d)
        used += 1
        if used >= 14:
            break
    mv = [r for r in rows if r['v_gt'] >= 0.03]
    st = [r for r in rows if r['v_gt'] < 0.003 and r['quiet']]
    res = {'cases_used': used, 'pairs_moving': len(mv), 'pairs_still': len(st), 'cases_with_moving': len({r['case'] for r in mv}),
           'v_gt_moving_median_mps': float(np.median([r['v_gt'] for r in mv])) if mv else None, 'metrics': {}}
    for k in ('mad', 'pc', 'fb_tex', 'tex_frac'):
        a = np.array([r[k] for r in mv], float)
        b = np.array([r[k] for r in st], float)
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        res['metrics'][k] = dict(moving_med=float(np.median(a)), moving_p05=float(np.percentile(a, 5)), still_med=float(np.median(b)),
                                 still_p95=float(np.percentile(b, 95)), auc_moving_gt_still=auc(a, b))
    if mv:
        v = np.array([r['v_gt'] for r in mv])
        pcs = np.array([r['pc'] for r in mv])
        rk = lambda x: np.argsort(np.argsort(x)).astype(float)
        res['spearman_pc_vs_speed_moving'] = float(np.corrcoef(rk(v), rk(pcs))[0, 1])
    Path(HERE / 'results/wrist_flow_unloaded_control.json').write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
