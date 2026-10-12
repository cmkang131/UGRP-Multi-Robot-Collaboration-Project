"""Fit and validate the command-only sag model (``sag_comp.py``). Offline: ``mj_forward`` on recorded ``qpos`` only.

Refs #216. **Physical simulation runs: 0.**

Target: camera elevation error = true render camera minus FK of the commanded pulses, degrees (``true_camera``),
on SETTLED frames only (age since the last commanded change >= ``settle_s`` of the load class: 0.25 s unloaded,
2.25 s loaded, ``settle_curve.py``). The own gripper command defines the load class.

  fit        ``--fit-episode``  (the exploration recording)  -> least squares -> ``sag_coeffs.json``
  validate   ``--episode`` ...   (separate confirmation recordings; coefficients frozen)
  leave-one-pose-out on the fit recording: the confirmation recordings repeat the exploration recording's pose set, so
             they test reproducibility, not generalisation to a new pose; this is the generalisation test.

Reports the elevation error left after the constant seed bias (option off) and after the sag model (option on),
overall and per commanded pose, as median and p90 of ``|error|``, and as the row and range it moves.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import sag_comp  # noqa: E402
import true_camera as tc  # noqa: E402
import wall_probe as wp  # noqa: E402

SETTLE_S = {'unloaded': 0.25, 'loaded': 2.25}
PX_PER_DEG = mp.FY*math.pi/180.


def settled_samples(ep: Path, robot: str):
    """[(pose_key, loaded, servo, error_deg)] of the settled frames of one recording."""
    cam = tc.TrueCamera(ep, robot)
    frames, _ = wp.resolve_frames(ep, robot)
    t = np.array([float(r['sim_time']) for r in frames])
    servos = [{int(k): int(v) for k, v in r['commanded_servo'].items()} for r in frames]
    key = [tuple(sorted(s.items())) for s in servos]
    start = 0
    out = []
    for i, s in enumerate(servos):
        if key[i] != key[start]:
            start = i
        loaded = wp.is_loaded(s)
        if t[i] - t[start] < SETTLE_S['loaded' if loaded else 'unloaded']:
            continue
        _, r_true, _ = cam.at(i)
        _, r_fk = mp.camera_in_base(s)
        out.append((tuple(s[k] for k in (3, 4, 5)), loaded, s,
                    tc.elevation_deg(r_true) - tc.elevation_deg(np.asarray(r_fk, float))))
    return out


def stats(err):
    e = np.abs(np.asarray(err, float))
    return {'n': int(e.size), 'median_abs_deg': round(float(np.median(e)), 3) if e.size else None,
            'p90_abs_deg': round(float(np.percentile(e, 90)), 3) if e.size else None,
            'median_signed_deg': round(float(np.median(err)), 3) if e.size else None}


def evaluate(samples, coeffs):
    off = [e - math.degrees(wp.SEED_BIAS['loaded' if ld else 'unloaded']) for _, ld, _, e in samples]
    on = [e - sag_comp.elevation_error_deg(s, ld, coeffs) for _, ld, s, e in samples]
    res = {'seed_bias_off': stats(off), 'sag_on': stats(on), 'per_pose': {}}
    for pose in sorted({p for p, *_ in samples}):
        idx = [i for i, (p, *_ ) in enumerate(samples) if p == pose]
        res['per_pose']['-'.join(map(str, pose)) + ('/loaded' if samples[idx[0]][1] else '')] = {
            'seed_bias_off_median_deg': round(float(np.median([off[i] for i in idx])), 3),
            'sag_on_median_deg': round(float(np.median([on[i] for i in idx])), 3), 'n': len(idx)}
    return res


def fit(samples, ridge=0.):
    x = np.array([sag_comp.design_row(s, ld) for _, ld, s, _ in samples])
    y = np.array([e for *_, e in samples])
    # one fit parameter per column; the load column only exists when loaded samples are present
    use = [j for j in range(x.shape[1]) if np.any(x[:, j] != 0)]
    # pose-level weights: every distinct (pose, load) counts once, so a long hold does not outvote a short one
    poses = [(p, ld) for p, ld, *_ in samples]
    w = np.array([1./poses.count(k) for k in poses])
    a = x[:, use]*np.sqrt(w)[:, None]
    b = y*np.sqrt(w)
    sol = np.linalg.lstsq(a.T@a + ridge*np.eye(len(use)), a.T@b, rcond=None)[0]
    c = np.zeros(x.shape[1])
    c[use] = sol
    return c


def run(args):
    fit_samples = settled_samples(Path(args.fit_episode), args.robot)
    coeffs = fit(fit_samples, args.ridge)
    named = dict(zip(('c0_deg', 'A_deg', 'B_deg', 'C_deg', 'm_load_N'), map(float, coeffs)))
    report = {'fit_episode': args.fit_episode, 'coefficients': named, 'ridge': args.ridge,
              'fit_samples': len(fit_samples), 'distinct_poses': len({(p, ld) for p, ld, *_ in fit_samples}),
              'fit_recording': evaluate(fit_samples, coeffs), 'confirmation': {}}
    # leave-one-pose-out on the fit recording
    keys = sorted({(p, ld) for p, ld, *_ in fit_samples})
    held_off, held_on, per = [], [], {}
    for k in keys:
        train = [s for s in fit_samples if (s[0], s[1]) != k]
        test = [s for s in fit_samples if (s[0], s[1]) == k]
        c = fit(train, args.ridge)
        for _, ld, s, e in test:
            held_off.append(e - math.degrees(wp.SEED_BIAS['loaded' if ld else 'unloaded']))
            held_on.append(e - sag_comp.elevation_error_deg(s, ld, c))
        per['-'.join(map(str, k[0])) + ('/loaded' if k[1] else '')] = {
            'seed_bias_off_median_deg': round(float(np.median([e - math.degrees(wp.SEED_BIAS['loaded' if ld else 'unloaded'])
                                                               for _, ld, s, e in test])), 3),
            'held_out_sag_on_median_deg': round(float(np.median([e - sag_comp.elevation_error_deg(s, ld, c)
                                                                  for _, ld, s, e in test])), 3)}
    report['leave_one_pose_out'] = {'seed_bias_off': stats(held_off), 'sag_on_held_out': stats(held_on), 'per_pose': per}
    for ep in args.episode:
        report['confirmation'][ep] = evaluate(settled_samples(Path(ep), args.robot), coeffs)
    report['px_per_deg'] = round(PX_PER_DEG, 3)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    if args.write_coeffs:
        Path(args.write_coeffs).write_text(json.dumps(
            {**named, 'fit_episode': args.fit_episode, 'note': 'written by fit_sag.py; pose-weighted least squares on the settled frames of the fit '
             'recording, unloaded and loaded poses together; see README'}, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--fit-episode', required=True)
    ap.add_argument('--episode', action='append', default=[], help='confirmation recording (repeatable)')
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--output', required=True)
    ap.add_argument('--write-coeffs', default='')
    ap.add_argument('--ridge', type=float, default=0.)
    run(ap.parse_args())
