"""How long after a commanded arm change is the commanded-pose camera model valid again? (offline, no physics)

Refs #216. **Physical simulation runs: 0** (``mj_forward`` on recorded ``qpos`` only).

The detector's camera is forward kinematics of the COMMANDED pulses, but the arm follows them with a lag
(position servos). While it moves, the rendered camera is somewhere else. Gate for the ego map (stage C):
record only frames at least ``settle_s`` after the last commanded change. ``settle_s`` is derived here from data, not guessed:

  * split the recording into runs of constant commanded servo pulses;
  * per run of >= ``--min-run-s`` seconds: ``final`` = median camera elevation error (true render camera minus
    FK of the commanded pulses, degrees) over the last ``--tail`` frames of the run;
  * for every frame of the run: ``dev = |error - final|`` against ``age`` = seconds since the run began;
  * per run, for the camera elevation error and for the camera heading error (true minus FK, degrees; the yaw servo
    lags too): ``settle_age`` = smallest age from which ``dev`` stays <= ``--tol-deg`` (default 0.25 deg = 2.7 px
    of row or of column; see README for how that converts to range) for the rest of the run; the run's settle age is the
    larger of the two;
  * ``settle_s`` = the largest ``settle_age`` over the runs of a load class (``unloaded`` / ``loaded``: own gripper
    command closed, ``wall_probe.is_loaded``; the arm carries a beam and settles slower), rounded up to ``--bin-s``
    (a gate has to hold for the slowest transition). Most runs are already settled when they begin (the arm moved within one frame of the command
    log), so a percentile over runs would only ever see those; the maximum sees the transients.
  * fit it on the exploration recording, then run it on the confirmation recordings: the gate holds when their
    ``settle_s`` is not larger.

Scoring/diagnosis only: it reads the true camera. Nothing here reaches a detector.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import wall_probe as wp  # noqa: E402
import true_camera as tc  # noqa: E402


def heading_deg(r_bc) -> float:
    """Heading of the optical (forward) axis in the floor frame, degrees, counter-clockwise from +x."""
    z = np.asarray(r_bc, float)[:, 2]
    return float(np.degrees(np.arctan2(z[1], z[0])))


def constant_command_runs(servos, times):
    """[(first_idx, last_idx)] of maximal runs of identical commanded pulses."""
    runs, start = [], 0
    for i in range(1, len(servos) + 1):
        if i == len(servos) or servos[i] != servos[start]:
            runs.append((start, i - 1))
            start = i
    return runs


def run_settle_age(ages, devs, tol_deg):
    """Smallest age from which ``devs`` stays <= ``tol_deg`` to the end of the run (ages ascending)."""
    bad = np.flatnonzero(np.asarray(devs) > tol_deg)
    if not bad.size:
        return 0.
    return float(ages[min(bad[-1] + 1, len(ages) - 1)])


def run(args):
    ep = Path(args.episode)
    cam = tc.TrueCamera(ep, args.robot)
    frames, _ = wp.resolve_frames(ep, args.robot)
    t = np.array([float(r['sim_time']) for r in frames])
    servos = [tuple(sorted((int(k), int(v)) for k, v in r['commanded_servo'].items())) for r in frames]
    err = np.empty(len(frames))
    yerr = np.empty(len(frames))
    for i, r in enumerate(frames):
        s = {int(k): int(v) for k, v in r['commanded_servo'].items()}
        _, r_true, _ = cam.at(i)
        _, r_fk = mp.camera_in_base(s)
        err[i] = tc.elevation_deg(r_true) - tc.elevation_deg(np.asarray(r_fk, float))
        dy = heading_deg(r_true) - heading_deg(np.asarray(r_fk, float))
        yerr[i] = (dy + 180.) % 360. - 180.
    runs = []
    for a, b in constant_command_runs(servos, t):
        if t[b] - t[a] < args.min_run_s or b - a + 1 <= args.tail:
            continue
        final = float(np.median(err[b - args.tail + 1:b + 1]))
        yfinal = float(np.median(yerr[b - args.tail + 1:b + 1]))
        age = t[a:b + 1] - t[a]
        dev = np.abs(err[a:b + 1] - final)
        ydev = np.abs(yerr[a:b + 1] - yfinal)
        sa, sy = run_settle_age(age, dev, args.tol_deg), run_settle_age(age, ydev, args.tol_deg)
        runs.append({'t_start': round(float(t[a]), 2), 'duration_s': round(float(t[b] - t[a]), 2),
                     'servo': dict(servos[a]), 'loaded': bool(wp.is_loaded(dict(servos[a]))), 'err_first_deg': round(float(err[a]), 3),
                     'err_final_deg': round(final, 3), 'yaw_err_first_deg': round(float(yerr[a]), 3),
                     'yaw_err_final_deg': round(yfinal, 3), 'settle_age_elevation_s': round(sa, 3),
                     'settle_age_heading_s': round(sy, 3), 'settle_age_s': round(max(sa, sy), 3)})
    settle = {}
    for name, flag in (('unloaded', False), ('loaded', True)):
        worst = max((r['settle_age_s'] for r in runs if r['loaded'] == flag), default=None)
        settle[name] = None if worst is None else float(np.ceil(worst/args.bin_s - 1e-9)*args.bin_s)
    out = {'episode': str(ep), 'frames': len(frames), 'runs_used': len(runs), 'tol_deg': args.tol_deg,
           'settle_s': settle, 'runs_per_class': {n: sum(1 for r in runs if r['loaded'] == f) for n, f in
                                                  (('unloaded', False), ('loaded', True))},
           'runs_with_a_transient': sum(1 for r in runs if r['settle_age_s'] > 0.), 'runs': runs}
    print(json.dumps(out, indent=2))
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(out, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--output', default='')
    ap.add_argument('--min-run-s', type=float, default=0.5)
    ap.add_argument('--tail', type=int, default=3)
    ap.add_argument('--tol-deg', type=float, default=0.25)
    ap.add_argument('--bin-s', type=float, default=0.25)
    run(ap.parse_args())
