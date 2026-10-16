#!/usr/bin/env python3
"""Run the wall/fix evaluation across many random seeds and check that the
error rate stays <= 3% (goal: extract walls matching the actual map from
image input only, robustly).

Uses the existing offline eval_partial_fix_gate machinery: for each sampled
settled frame, draws a perturbed prior around the true pose and checks that
accepting a scan never produces xy > 100mm or yaw > 3° from truth.

    python3 scripts/benchmark_wall_extract.py \
        --outputs <outputs root> --run <name> --calibration <cal json> \
        [--out <json>] [--seeds 50] [--runs-once 0|1]

runs-once == 1 means the eval is run once per seed but only one frame-set
(mimics the seed-draw randomness, not re-scanning images).
No simulator, renderer or model.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import opencv_wall_observation as ow                       # noqa: E402
from harness import vision_loc_protocol as vp                           # noqa: E402
from harness import zone_pair_highpose_contract as contract             # noqa: E402
from harness import zone_pair_highpose_partial_fix as pfix              # noqa: E402
from harness import zone_final_pair_scan as old_scan                    # noqa: E402
from harness.vision_pose_source_highpose import HighPoseSource          # noqa: E402

PRIORS = {'tight': ((.02, .02, .01), (.02, .02, .01)), 'dock': ((.05, .05, .03), (.05, .05, .03)),
          'wrong': ((.05, .05, .03), (.20, .20, .15))}


def yaw_of(q):
    w, x, y, z = q
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def settle_frames(run_dir, rid, every):
    cases = list(Path(run_dir).glob('zone_wide_door_geometry_v3'))
    if not cases:
        return [], None
    case = cases[0]
    cmds = [json.loads(line) for line in (case / f'robots/{rid}/commands.jsonl').read_text().splitlines()]
    starts = sorted(c['t'] for c in cmds if c['kind'] in ('arm', 'look', 'initial_servo_command'))
    out = []
    for n, line in enumerate((case / f'robots/{rid}/frames.jsonl').read_text().splitlines()):
        if n % every:
            continue
        f = json.loads(line)
        i = bisect.bisect_right(starts, f['sim_time'] - 1e-9)
        if i and f['sim_time'] - starts[i - 1] < .25:
            continue
        out.append(f)
    return out, case


def seed_run(run_dir, run, every, max_frames, seed):
    """One seed: perturbed priors for a fixed sample of frames -> error rate."""
    from bisect import bisect_right
    settled, case = settle_frames(run_dir, 'r1', every)
    if not settled:
        settled, case = settle_frames(run_dir, 'r2', every)
    if not settled:
        return {'n': 0, 'max_error': None, 'seeds': {}}
    cal = json.loads((Path(run_dir) / 'dev_pilot_calibration.json').read_text())
    static, _, _ = contract.resolve('zone_wide_door_geometry_v3')
    contract.admitted_calibration = lambda p, sha, mid: cal
    src = HighPoseSource(static, str(Path(run_dir) / 'dev_pilot_calibration.json'),
                         hashlib.sha256((Path(run_dir) / 'dev_pilot_calibration.json').read_bytes()).hexdigest(),
                         seed=seed)
    pf, vl = src.loc._pf, vp.load_vis3()[0]
    geom = vl.mp.MapGeometry(json.loads((case / 'inputs/static_map.json').read_text()), include_posts=False)
    traj = [json.loads(line) for line in (case / 'eval_only/trajectory.jsonl').read_text().splitlines()]
    ts = np.array([r['t'] for r in traj])
    gates = contract.own_image_gates()['values']
    rng = np.random.default_rng(seed)
    errors = []

    for f in settled:
        servo = {int(k): int(v) for k, v in f['commanded_servo'].items()}
        try:
            camera = pf.column_model_for(servo)
        except Exception:
            continue
        q = traj[int(np.argmin(abs(ts - f['sim_time'])))]['qpos'][0:7]
        truth = np.array([q[0], q[1], yaw_of(q[3:7])])
        bgr = cv2.imread(str(case / f['path']))
        obs = ow.observations(vl, bgr, camera, gates)
        n_cols = int(obs.informative.sum())
        if n_cols < int(pf.measurement['min_columns']):
            continue
        for pname, (sig, off_sig) in PRIORS.items():
            offset = rng.normal(size=3) * np.asarray(off_sig)
            pf.init_gaussian(tuple(truth + offset), sig)
            qn = pfix.scan_quality(vl, pf, obs, servo)
            if not qn['informative']:
                continue
            logw = pf.logw + pf.scan_loglik(obs, servo)[0]
            w = np.exp(logw - logw.max())
            w /= w.sum()
            mean = (w[:, None] * pf.px).sum(0)
            mean[2] = truth[2] + wrap(float(np.angle((w * np.exp(1j * (pf.px[:, 2] - truth[2]))).sum())))
            pe = np.hypot(*offset[:2])
            qa = abs(wrap(mean[2] - truth[2]))
            err = ((np.hypot(*(mean[:2] - truth[:2])) > 0.10) | (qa > math.radians(3.))).mean()
            if err:
                errors.append({'frame_id': f['frame_id'], 'pan': servo.get(6), 'prior': pname,
                               'old_informative': bool(old_scan.quality(vl, pf, obs, servo)['informative']),
                               'new_informative': bool(qn['informative']), 'error': err})
        if len(errors) >= max_frames:
            break
    return {'n': len(errors), 'max_error': max((e['error'] for e in errors), default=0.0),
            'per_prior': {p: [e['error'] for e in errors if e['prior'] == p] for p in PRIORS},
            'seeds': {seed: len(errors)}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--outputs', required=True)
    ap.add_argument('--run', action='append', default=[])
    ap.add_argument('--calibration', required=True)
    ap.add_argument('--out', default='wall_extract_benchmark_seeds.json')
    ap.add_argument('--every', type=int, default=10)
    ap.add_argument('--max-frames', type=int, default=120)
    ap.add_argument('--seeds', type=int, default=50)
    args = ap.parse_args()

    all_seeds = {}
    max_overall = 0.0
    counts_ok = 0
    counts_fail = 0
    for seed in range(args.seeds):
        res = seed_run(args.outputs, args.run[0] if args.run else 'dummy', args.every,
                       args.max_frames, seed)
        if seed not in res['seeds']:
            continue
        max_overall = max(max_overall, res['max_error'])
        all_seeds[seed] = {'n': res['n'], 'max_error': res['max_error'],
                           'per_prior': {k: round(np.mean(v) if v else None, 4) for k, v in res['per_prior'].items()}}
        if res['max_error'] <= 0.03:
            counts_ok += 1
        else:
            counts_fail += 1
        if seed % 10 == 0 or res['max_error'] > 0.03:
            print(f'seed {seed}: max_error={res["max_error"]:.4f} n={res["n"]} "OK"/"FAIL"')
    summary = {'num_seeds': args.seeds, 'seeds': all_seeds,
               'all_seeds_under_3pct': max_overall <= 0.03,
               'max_error_over_seeds': max_overall,
               'seeds_ok': counts_ok, 'seeds_fail': counts_fail,
               'goal_met': max_overall <= 0.03 and counts_fail == 0,
               'threshold': 0.03}
    Path(args.out).write_text(json.dumps(summary, indent=1))
    print('SUMMARY')
    print(json.dumps({'all_seeds_under_3pct': summary['all_seeds_under_3pct'],
                      'max_error_over_seeds': summary['max_error_over_seeds'],
                      'seeds_ok': counts_ok, 'seeds_fail': counts_fail, 'goal_met': summary['goal_met']}))
    print(f'wrote {args.out}')


if __name__ == '__main__':
    import hashlib, cv2
    import bisect
    main()
