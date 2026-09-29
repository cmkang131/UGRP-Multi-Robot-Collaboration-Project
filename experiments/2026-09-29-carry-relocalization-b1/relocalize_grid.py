"""Offline re-localization of the checkpoint look sweeps (numpy only; runs in either env).

For every (checkpoint, robot, look variant) of a render directory and every start-error draw of the requested cells,
a fresh VIS3 particle filter is started with a Gaussian prior centred on (true pose + start error) with the given prior
spread, receives the sweep frames in `common.SWEEP_PANS` order (one own-servo command per pan, frame 1.0 s later,
i.e. settled) and reports its estimate after every frame. The truth pose is used ONLY to (a) draw the wrong prior mean
and (b) score the outcome; the filter sees its own observations, the static map, the frozen calibration and its own
issued commands (`initial_servo_command`, `look`). Observation source `vision` = segmentation network (the student);
`oracle` = teacher labels (eval-only perception ceiling).

usage: python relocalize_grid.py <render_dir> <out.jsonl> --obs vision|oracle --prior wide|tight --cells S Y L --n S=30,Y=6,L=20
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import numpy as np  # noqa: E402

FRAME_DT_S = 1.0          # frame time after the own servo command (settle_s of the frozen config is 0.2 s)
PAN_GAP_S = 1.5
SEED_BASE = 20260929


def seed_of(*parts) -> int:
    return int(hashlib.sha256('|'.join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def run_sweep(ctx, obs_by_pan: dict, servo0: dict, mean, std, seed: int):
    """One re-localization: returns the list of per-frame estimates (dicts) of a fresh filter."""
    vl = ctx.vl
    pf = ctx.make_pf(seed)
    pf.init_gaussian(mean, std)
    servo = {int(k): int(v) for k, v in servo0.items()}
    pf.command({'t': 0.0, 'kind': 'initial_servo_command', 'pulses': dict(servo)})
    out = []
    t = 0.0
    for i, pan in enumerate(common.SWEEP_PANS):
        if i > 0:
            t += PAN_GAP_S
            pf.command({'t': t, 'kind': 'look', 'pan_pulse': int(pan)})
            servo[6] = int(pan)
        ft = t + FRAME_DT_S
        obs = vl.ColumnObs.from_dict(obs_by_pan[pan], ctx.columns)
        est = pf.update_obs(ft, obs, servo)
        out.append({'pan': int(pan), 'x': est['x'], 'y': est['y'], 'yaw': est['yaw'], 'std_xy': est['std_xy_m'],
                    'std_yaw': est['std_yaw_rad'], 'measured': bool(est.get('measured')), 'n_cols': int(obs.informative.sum())})
    return out


def truth_consistency(ctx, row, obs_dict):
    """Eval-only diagnostic: observed sharp bottom edges against the map rows expected at the TRUE pose."""
    vl = ctx.vl
    obs = vl.ColumnObs.from_dict(obs_dict, ctx.columns)
    pf = ctx.make_pf(0)
    servo = {int(k): int(v) for k, v in row['servo'].items()}
    cm = pf.column_model_for(servo)
    vb, vt = vl.expected_rows(pf.geometry, np.asarray([common.true_pose(row)]), cm)
    e = (obs.b_kind == vl.EDGE) & np.isfinite(vb[0]) & (np.abs(vb[0]) < 1e3)
    res = np.abs(obs.b_lo[e] - vb[0][e]) if e.any() else np.zeros(0)
    itv = obs.b_kind == vl.INTERVAL
    fit = None
    if (obs.b_kind != vl.NONE).any():
        # mean per-column probability of the observation given the map row expected at the TRUE pose (1 = fully explained)
        p = vl.interval_prob(vb, obs.b_kind, obs.b_lo, obs.b_hi, float(ctx.cfg['measurement'].get('sigma_px', 2.5)))[0]
        fit = float(np.nanmean(p[obs.b_kind != vl.NONE]))
    return {'informative': int(obs.informative.sum()), 'edges': int(e.sum()), 'intervals': int(itv.sum()),
            'edge_resid_px_median': None if not res.size else round(float(np.median(res)), 2),
            'edge_resid_px_p90': None if not res.size else round(float(np.percentile(res, 90)), 2),
            'edge_within_3px': None if not res.size else round(float((res <= 3).mean()), 3),
            'mean_column_prob_at_truth': None if fit is None else round(fit, 3)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('render_dir')
    ap.add_argument('out')
    ap.add_argument('--obs', default='vision', choices=('vision', 'oracle'))
    ap.add_argument('--prior', default='wide', choices=('wide', 'tight'))
    ap.add_argument('--cells', nargs='+', default=['S', 'Y', 'L'])
    ap.add_argument('--n', default='S=30,Y=6,L=20')
    ap.add_argument('--checkpoints', type=int, nargs='*')
    ap.add_argument('--looks', nargs='*')
    ap.add_argument('--robots', nargs='*')
    ap.add_argument('--tag', default='')
    ap.add_argument('--consistency', action='store_true', help='also write per-frame truth-pose consistency rows')
    a = ap.parse_args(argv)
    ns = {k: int(v) for k, v in (kv.split('=') for kv in a.n.split(','))}
    d = Path(a.render_dir)
    man = json.loads((d / 'render_manifest.json').read_text())
    obs_all = json.loads((d / f'obs_{a.obs}.json').read_text())['obs']
    ctx = common.Context()
    std = common.PRIOR_WIDE if a.prior == 'wide' else common.PRIOR_TIGHT
    rows = man['rows']
    groups: dict = {}
    for r in rows:
        groups.setdefault((r['checkpoint'], r['robot'], r['look']), {})[r['pan']] = r
    out_path = Path(a.out)
    if out_path.exists():
        raise SystemExit(f'refusing to overwrite {out_path}')
    t0 = time.time()
    n_runs = 0
    with open(out_path, 'w') as fh:
        for (k, rid, look), by_pan in sorted(groups.items()):
            if (a.checkpoints is not None and k not in a.checkpoints) or (a.looks and look not in a.looks) or (a.robots and rid not in a.robots):
                continue
            if set(by_pan) < set(common.SWEEP_PANS):
                continue
            first = by_pan[1500]
            tx, ty, tyaw = common.true_pose(first)
            obs_by_pan = {pan: obs_all[by_pan[pan]['name']] for pan in by_pan}
            if a.consistency:
                for pan, r in by_pan.items():
                    fh.write(json.dumps({'kind': 'consistency', 'render_profile': man['render_profile'], 'obs': a.obs, 'checkpoint': k, 'robot': rid,
                                         'look': look, 'pan': pan, **truth_consistency(ctx, r, obs_all[r['name']])}) + '\n')
            for cell in a.cells:
                offs = common.offsets(cell, ns[cell], seed_of(SEED_BASE, 'offsets', cell, k, rid, look))
                for j, (dx, dy, dyaw) in enumerate(offs):
                    seed = seed_of(SEED_BASE, 'pf', a.tag, cell, j, k, rid, look, a.prior)
                    mean = (tx + dx, ty + dy, float(common.wrap(tyaw + dyaw)))
                    est = run_sweep(ctx, obs_by_pan, first['servo'], mean, std, seed)
                    fin = est[-1]
                    rec = {'kind': 'run', 'render_profile': man['render_profile'], 'obs': a.obs, 'prior': a.prior, 'checkpoint': k,
                           'label': first['label'], 'robot': rid, 'look': look, 'cell': cell, 'draw': j,
                           'start_err': [float(dx), float(dy), float(dyaw)], 'seed': seed,
                           'true': [tx, ty, tyaw], 'frames': [
                               {**f, 'err_xy': float(math.hypot(f['x'] - tx, f['y'] - ty)),
                                'err_yaw': float(common.wrap(f['yaw'] - tyaw)), 'err_x': float(f['x'] - tx), 'err_y': float(f['y'] - ty)} for f in est]}
                    rec.update(final_err_xy=rec['frames'][-1]['err_xy'], final_err_yaw=rec['frames'][-1]['err_yaw'],
                               final_std_xy=fin['std_xy'], final_std_yaw=fin['std_yaw'], measured_frames=int(sum(f['measured'] for f in est)))
                    fh.write(json.dumps(rec) + '\n')
                    n_runs += 1
    print(json.dumps({'runs': n_runs, 'wall_s': round(time.time() - t0, 1), 'out': str(out_path)}))


if __name__ == '__main__':
    main()
