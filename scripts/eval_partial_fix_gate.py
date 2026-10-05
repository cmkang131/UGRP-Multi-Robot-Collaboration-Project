#!/usr/bin/env python3
"""Offline comparison of the old fix gate and the second-eigenvalue (partial fix) gate on recorded frames.

No simulator, renderer or model. For each sampled settled, calibrated, unloaded frame of a recorded run:
  1. the OpenCV observer (same gates) gives the column observation;
  2. a particle cloud is drawn around the TRUE pose displaced by a random offset (prior sigma given below) -
     the truth is used only to build this evaluation prior and to score, never inside the observer or the gate;
  3. both gates judge the scan; the scan is applied; the posterior mean error is scored per direction.

  python3 scripts/eval_partial_fix_gate.py --outputs <outputs root> --run <name> [--run ...] --out <json> \
      [--every 10] [--max-frames 120]
"""
import argparse
import bisect
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import opencv_wall_observation as ow                       # noqa: E402
from harness import vision_loc_protocol as vp                           # noqa: E402
from harness import zone_pair_highpose_contract as contract             # noqa: E402
from harness import zone_pair_highpose_partial_fix as pfix              # noqa: E402
from harness import zone_final_pair_scan as old_scan                    # noqa: E402

# name: (cloud sigma, true-offset sigma), each (x m, y m, yaw rad). 'wrong' = a confidently wrong prior: the
# gate must not accept scans that pull toward a wrong pose.
PRIORS = {'tight': ((.02, .02, .01), (.02, .02, .01)), 'dock': ((.05, .05, .03), (.05, .05, .03)),
          'wrong': ((.05, .05, .03), (.20, .20, .15))}


def yaw_of(q):
    w, x, y, z = q
    return math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))


def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def offline_calibration(path, sha, map_id):
    """The recorded DEV calibration without the DEV admission checks (the run's sibling manifest is not copied
    into run directories): only the registered unloaded motion fill is applied, as ``dev_pilot_calibration`` does."""
    cal = json.loads(Path(path).read_text())
    fill = contract.dev_pilot_admission()['unloaded_motion_fill']
    if cal.get('missing'):
        cal['params']['motion'] = copy.deepcopy(fill['values'])
        cal['missing'] = []
    return cal


def make_source(calibration):
    from harness.vision_pose_source_highpose import HighPoseSource
    static, _, _ = contract.resolve('zone_wide_door_geometry_v3')
    contract.admitted_calibration = offline_calibration
    return HighPoseSource(static, str(calibration), hashlib.sha256(Path(calibration).read_bytes()).hexdigest(), seed=911)


def settled_frames(case, rid, every):
    cmds = [json.loads(line) for line in (case/f'robots/{rid}/commands.jsonl').read_text().splitlines()]
    starts = sorted(c['t'] for c in cmds if c['kind'] in ('arm', 'look', 'initial_servo_command'))
    out = []
    for n, line in enumerate((case/f'robots/{rid}/frames.jsonl').read_text().splitlines()):
        if n % every:
            continue
        f = json.loads(line)
        i = bisect.bisect_right(starts, f['sim_time'] - 1e-9)
        if i and f['sim_time'] - starts[i-1] < .25:
            continue
        out.append(f)
    return out


def evaluate(outputs, run, every, max_frames, seed=7):
    out = Path(outputs)/run
    case = next(out.glob('zone_wide_door_geometry_v3'))
    src = make_source(out/'dev_pilot_calibration.json')
    pf, vl = src.loc._pf, vp.load_vis3()[0]
    geom = vl.mp.MapGeometry(json.loads((case/'inputs/static_map.json').read_text()), include_posts=False)
    traj = [json.loads(line) for line in (case/'eval_only/trajectory.jsonl').read_text().splitlines()]
    ts = np.array([r['t'] for r in traj])
    rng = np.random.default_rng(seed)
    gates = contract.own_image_gates()['values']
    rows = []
    for idx, rid in enumerate(('r1', 'r2')):
        if not (case/f'robots/{rid}/frames.jsonl').exists():
            continue
        frames = settled_frames(case, rid, every)
        for f in frames:
            servo = {int(k): int(v) for k, v in f['commanded_servo'].items()}
            try:
                camera = pf.column_model_for(servo)
            except Exception:
                continue                                  # no calibrated unloaded posture (moving, loaded, ...)
            q = traj[int(np.argmin(abs(ts - f['sim_time'])))]['qpos'][17*idx:17*idx + 7]
            truth = np.array([q[0], q[1], yaw_of(q[3:7])])
            bgr = cv2.imread(str(case/f['path']))
            obs = ow.observations(vl, bgr, camera, gates)
            n_cols = int(obs.informative.sum())
            if n_cols < int(pf.measurement['min_columns']):
                rows.append({'run': run, 'robot': rid, 'frame_id': f['frame_id'], 't': f['sim_time'], 'pan': servo[6],
                             'columns': n_cols, 'skipped': 'below_min_columns'})
                continue
            for pname, (sig, off_sig) in PRIORS.items():
                offset = rng.normal(size=3)*np.asarray(off_sig)
                pf.init_gaussian(tuple(truth + offset), sig)
                before = pf.px.copy(), pf.logw.copy()
                qo = old_scan.quality(vl, pf, obs, servo)
                qn = pfix.scan_quality(vl, pf, obs, servo)
                logw = pf.logw + pf.scan_loglik(obs, servo)[0]
                w = np.exp(logw - logw.max())
                w /= w.sum()
                mean = (w[:, None]*pf.px).sum(0)
                mean[2] = truth[2] + wrap(float(np.angle((w*np.exp(1j*(pf.px[:, 2]-truth[2]))).sum())))
                err = mean - truth
                eig = qn.get('eigenvalues')
                weak = qn.get('weakest_direction_xy_yaw')
                rows.append({'run': run, 'robot': rid, 'frame_id': f['frame_id'], 't': f['sim_time'], 'pan': servo[6],
                             'prior': pname, 'columns': n_cols, 'truth': truth.tolist(), 'prior_err': offset.tolist(),
                             'post_err': err.tolist(), 'old_informative': bool(qo['informative']),
                             'old_matches_module': bool(qo['informative']) == bool(qn.get('old_informative')),
                             'new_informative': bool(qn['informative']), 'eigenvalues': eig, 'weakest': weak,
                             'inlier_fraction': qn.get('inlier_fraction'), 'support': qn.get('posterior_support')})
            if sum(1 for r in rows if r['run'] == run and 'prior' in r) >= 2*max_frames:
                break
    return rows


def summarize(rows):
    res = {}
    for prior in PRIORS:
        sel = [r for r in rows if r.get('prior') == prior]
        if not sel:
            continue
        old = [r for r in sel if r['old_informative']]
        new = [r for r in sel if r['new_informative']]
        part = [r for r in sel if r['new_informative'] and not r['old_informative']]
        rest = [r for r in sel if not r['new_informative']]

        def stat(rs):
            if not rs:
                return None
            pe = np.array([np.hypot(*r['prior_err'][:2]) for r in rs])
            qe = np.array([np.hypot(*r['post_err'][:2]) for r in rs])
            pa = np.array([abs(r['prior_err'][2]) for r in rs])
            qa = np.array([abs(r['post_err'][2]) for r in rs])
            return {'n': len(rs), 'xy_prior_mm_med': round(1000*float(np.median(pe)), 1),
                    'xy_post_mm_med': round(1000*float(np.median(qe)), 1),
                    'xy_post_mm_p90': round(1000*float(np.percentile(qe, 90)), 1),
                    'yaw_prior_deg_med': round(math.degrees(float(np.median(pa))), 2),
                    'yaw_post_deg_med': round(math.degrees(float(np.median(qa))), 2),
                    'yaw_post_deg_p90': round(math.degrees(float(np.percentile(qa, 90))), 2),
                    'post_xy_over_100mm_or_yaw_over_3deg_frac':
                        round(float(((qe > .10) | (qa > math.radians(3.))).mean()), 3),
                    'worse_than_prior_xy_frac': round(float((qe > 1.5*pe + 0.005).mean()), 3),
                    'worse_than_prior_yaw_frac': round(float((qa > 1.5*pa + math.radians(.5)).mean()), 3)}

        res[prior] = {'frames': len(sel), 'old_accept_frac': round(len(old)/len(sel), 3),
                      'new_accept_frac': round(len(new)/len(sel), 3), 'partial_only': stat(part),
                      'both_accepted': stat([r for r in old]), 'rejected_by_new': stat(rest),
                      'old_equals_module_frac': round(float(np.mean([r['old_matches_module'] for r in sel])), 3)}
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--outputs', required=True)
    ap.add_argument('--run', action='append', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--every', type=int, default=10)
    ap.add_argument('--max-frames', type=int, default=120)
    args = ap.parse_args()
    allrows, summary = [], {}
    for run in args.run:
        rows = evaluate(args.outputs, run, args.every, args.max_frames)
        allrows += rows
        summary[run] = summarize(rows)
        print(run, json.dumps(summary[run]), flush=True)
    summary['ALL'] = summarize(allrows)
    Path(args.out).write_text(json.dumps({'summary': summary, 'priors': PRIORS, 'rule': pfix.record(),
                                          'rows': allrows}, indent=1))
    print('ALL', json.dumps(summary['ALL']))


if __name__ == '__main__':
    main()
