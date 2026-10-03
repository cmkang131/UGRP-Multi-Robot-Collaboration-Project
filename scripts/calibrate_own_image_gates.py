#!/usr/bin/env python3
"""Offline recalibration of the own-image gates (docs/own_image_gate_calibration.md).

Reads recorded runs only; no simulation is started. Ground truth (the trajectory and the static map) is used
here, offline, to LABEL which candidate boundary columns are correct; the controller never sees it. Values are
derived from the calibration split only, then scored on a different run/map (the evaluation split).

  python3 scripts/calibrate_own_image_gates.py --outputs <outputs root> --calibration <DEV calibration json> \
      --out configs/calibration/own_image_gates_floor_light_v1.json
"""
import argparse
import bisect
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
from harness import own_image_gates as gates_module                     # noqa: E402
from harness import owncam_pair_beam_v2 as beam_v2                      # noqa: E402
from harness import zone_pair_highpose_contract as contract             # noqa: E402
from harness import zone_pair_vision as zv                              # noqa: E402

V88 = 'final-pair-v88-cal-747d2b9f-20261001'
RUN = 'zone_wide_two_doors_final_v3'
# Calibration and evaluation come from different runs AND different maps (two_doors vs door_geometry).
SPLITS = {
    'column_calibration': {'runs': [f'{V88}/calibration-unloaded/{RUN}', f'{V88}/calibration-fine/{RUN}'],
                           'every': 3, 'poses': ['740,2320,1320,1500', '1072,2400,1482,1500',
                                                 '1072,2400,1482,1230', '1072,2400,1482,970',
                                                 '1072,2400,1482,1770', '1072,2400,1482,2030']},
    'column_evaluation': {'runs': ['v96-dev-probe-raise_high-323fe3f9/before_door'], 'every': 2, 'poses': None},
    'occluder_check_high_pose': {'runs': ['final-pair-v92-loaded-257953ec-20261003/' + RUN], 'every': 12,
                                 'poses': ['896,2035,1894,1500']},
    'frame_calibration': {'runs': [(f'{V88}/calibration-unloaded/{RUN}', 10), (f'{V88}/calibration-fine/{RUN}', 2),
                                   (f'{V88}-r8/calibration-loaded/{RUN}', 10),
                                   ('final-pair-v92-loaded-257953ec-20261003/' + RUN, 20)]},
    'frame_evaluation': {'runs': [('v96-dev-probe-raise_high-323fe3f9/before_door', 3)],
                         'fixtures': 'tests/fixtures/highpose_recorded_frames'},
}
RULES = {
    'wall_band_saturation_max': 'round(1.2 x P99.9 of the max-S in the boundary-band window over CORRECT candidate '
                                'columns of column_calibration, to the nearest 10)',
    'wall_edge_step_min': 'round(0.5 x P0.5 of the luminance/chroma edge step over CORRECT candidate columns of '
                          'column_calibration)',
    'frame_contrast_spread_min': 'round(0.5 x P0.1 of the 1-99 percentile V spread over frame_calibration frames, '
                                 '1 decimal)',
    'frame_value_std_min': 'round(0.5 x P0.1 of the V std over frame_calibration frames, 2 decimals)',
    'correct_column': '|observed boundary row - row expected from GT pose and map| < 4 px (label only; offline)',
    'valid_frame': 'every frame of a successful nominal run is a valid view; bad frames are made offline by covering '
                   'the lowest f of the valid circle with black, or constant frames',
}
ACCEPT = {'A1_eval_correct_columns_kept_min': .995, 'A2_eval_column_precision_min': .95,
          'A3_high_pose_occluder_pass_rate_max': 'not above the old filter', 'A4_eval_frame_false_reject_max': .005,
          'A5_false_accept_on_bad_frames': 'not above the old gate'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def yaw_of(q):
    w, x, y, z = q
    return math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))


def collect_columns(run, rid, every, poses, pf, vl):
    """Labelled single-candidate boundary columns of one robot's settled frames (offline, GT only for labels)."""
    d = Path(run)
    sm = json.loads((d/'inputs/static_map.json').read_text())
    geom = vl.mp.MapGeometry(sm, include_posts=False)
    idx = {'r1': 0, 'r2': 1}[rid]
    traj = [json.loads(line) for line in (d/'eval_only/trajectory.jsonl').read_text().splitlines()]
    ts = np.array([r['t'] for r in traj])
    cmds = [json.loads(line) for line in (d/f'robots/{rid}/commands.jsonl').read_text().splitlines()]
    starts = sorted(c['t'] for c in cmds if c['kind'] in ('arm', 'look', 'initial_servo_command'))
    frames = [json.loads(line) for line in (d/f'robots/{rid}/frames.jsonl').read_text().splitlines()]
    rows = []
    for n, f in enumerate(frames):
        if n % every:
            continue
        t = f['sim_time']
        i = bisect.bisect_right(starts, t - 1e-9)
        if i and t - starts[i-1] < .2 - 1e-9:        # not settled (same 0.2 s as the localizer's settle gate)
            continue
        servo = {int(k): int(v) for k, v in f['commanded_servo'].items()}
        key = f'{servo[3]},{servo[4]},{servo[5]},{servo[6]}'
        if poses and key not in poses:
            continue
        try:
            camera = pf.column_model_for(servo)
        except Exception:                            # pose without a calibrated camera record
            continue
        q = traj[int(np.argmin(abs(ts - t)))]['qpos'][17*idx:17*idx + 7]
        vb, _ = vl.expected_rows(geom, np.array([[q[0], q[1], yaw_of(q[3:7])]]), camera)
        und = vl.mp.undistort(cv2.imread(str(d/f['path'])))
        scan = vl.mp.detect_boundaries(und, camera, ow.DETECTOR)
        img = und.astype(np.float32)
        lum = .114*img[..., 0] + .587*img[..., 1] + .299*img[..., 2]
        chroma = img[..., 0] - img[..., 2]
        sat = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)[..., 1]
        for j, u in enumerate(scan.columns):
            cand = np.flatnonzero(np.isfinite(scan.vb[j]))
            if len(cand) != 1:
                continue
            b, t_top = scan.vb[j, cand[0]], scan.vt[j, cand[0]]
            v = int(round(b))
            if v < 4 or v > 470:
                continue
            lo = max(0, int(t_top) - 3) if np.isfinite(t_top) else 0
            window = sat[lo:min(480, int(b) + 4), max(0, int(u) - 2):int(u) + 3]
            rows.append({'key': key,
                         'err': float(abs(b - vb[0][j])) if np.isfinite(vb[0][j]) else math.inf,
                         'step': ow.edge_step(lum, chroma, v, u), 'smax': float(window.max())})
    return rows


def column_split(name, outputs, pf, vl):
    out = []
    for run in SPLITS[name]['runs']:
        for rid in ('r1', 'r2'):
            out += collect_columns(str(outputs/run), rid, SPLITS[name]['every'], SPLITS[name]['poses'], pf, vl)
    return out


def frame_stats(frame):
    valid = beam_v2._valid()
    v = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[..., 2]
    val = v[valid]
    lo, hi = np.percentile(val, [1, 99])
    return {'spread': float(hi - lo), 'std': float(val.std()),
            'dark_ob': float((val <= zv.dark_level(v)).mean())}


def frame_ok(s, spread_min, std_min):
    return bool(s['dark_ob'] < .25 and s['spread'] >= spread_min and s['std'] >= std_min)


def frame_paths(outputs, run, every):
    paths = []
    for rid in ('r1', 'r2'):
        rows = [json.loads(line) for line in (outputs/run/f'robots/{rid}/frames.jsonl').read_text().splitlines()]
        paths += [str(outputs/run/r['path']) for r in rows[::every]]
    return paths


def pct(a, q):
    return float(np.percentile(a, q))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--outputs', required=True)
    ap.add_argument('--calibration', required=True, help='admitted DEV calibration json (sibling manifest needed)')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    outputs = Path(args.outputs)

    from harness import vision_loc_protocol as vp
    from harness.vision_pose_source_highpose import HighPoseSource
    static, _, _ = contract.resolve('zone_wide_door_geometry_v3')
    # The provider is only the source of the calibrated camera model here; it must not depend on this script's
    # own output, so it is built with the legacy gate values.
    contract.own_image_gates = lambda: {'path': gates_module.PATH, 'sha256': '', 'values': dict(gates_module.LEGACY)}
    src = HighPoseSource(static, args.calibration, sha256(args.calibration), seed=911)
    pf, vl = src.loc._pf, vp.load_vis3()[0]

    cal, ev = column_split('column_calibration', outputs, pf, vl), column_split('column_evaluation', outputs, pf, vl)
    ok = lambda R: np.array([r['err'] < 4 for r in R])                                   # noqa: E731
    col = lambda R, k: np.array([r[k] for r in R])                                       # noqa: E731
    c_ok = ok(cal)
    values = {'wall_band_saturation_max': int(round(1.2*pct(col(cal, 'smax')[c_ok], 99.9), -1)),
              'wall_edge_step_min': float(round(.5*pct(col(cal, 'step')[c_ok], .5))),
              'frame_contrast_spread_min': 0., 'frame_value_std_min': 0.}

    stats = {}
    for name, split in (('cal', SPLITS['frame_calibration']), ('eval', SPLITS['frame_evaluation'])):
        paths = [p for run, every in split['runs'] for p in frame_paths(outputs, run, every)]
        if 'fixtures' in split:
            fx = ROOT/split['fixtures']
            paths += [str(fx/f['file']) for f in json.loads((fx/'manifest.json').read_text())['frames']]
        stats[name] = [frame_stats(cv2.imread(p)) for p in paths]
    values['frame_contrast_spread_min'] = round(.5*pct([s['spread'] for s in stats['cal']], .1), 1)
    values['frame_value_std_min'] = round(.5*pct([s['std'] for s in stats['cal']], .1), 2)

    legacy = gates_module.LEGACY

    def keep(R, g):
        return (col(R, 'smax') < g['wall_band_saturation_max']) & (col(R, 'step') >= g['wall_edge_step_min'])

    results = {}
    for name, R in (('column_calibration', cal), ('column_evaluation', ev)):
        good = ok(R)
        results[name] = {'columns': len(R), 'correct': int(good.sum())}
        for tag, g in (('old', legacy), ('new', values)):
            k = keep(R, g)
            results[name][tag] = {'correct_kept': int((k & good).sum()), 'wrong_kept': int((k & ~good).sum()),
                                  'precision': float((k & good).sum()/max(k.sum(), 1))}
    # HIGH pose: the view is the beam and floor, no wall; every candidate column there is an occluder column.
    pf.load.loaded = True
    occ = column_split('occluder_check_high_pose', outputs, pf, vl)
    results['occluder_check_high_pose'] = {'columns': len(occ), 'correct': int(ok(occ).sum()),
        'old_pass': int(keep(occ, legacy).sum()), 'new_pass': int(keep(occ, values).sum())}
    # Frames: false-reject on valid frames, false-accept on labelled bad frames made from held-out frames.
    ys, _ = np.nonzero(beam_v2._valid())
    base = [cv2.imread(p) for p in frame_paths(outputs, SPLITS['frame_evaluation']['runs'][0][0], 15)]
    fixtures = ROOT/SPLITS['frame_evaluation']['fixtures']
    base += [cv2.imread(str(fixtures/f['file'])) for f in json.loads((fixtures/'manifest.json').read_text())['frames']]
    fr = {}
    for tag, (sp, sd) in (('old', (15., 3.)), ('new', (values['frame_contrast_spread_min'],
                                                          values['frame_value_std_min']))):
        fr[tag] = {'false_reject_cal': float(np.mean([not frame_ok(s, sp, sd) for s in stats['cal']])),
                   'false_reject_eval': float(np.mean([not frame_ok(s, sp, sd) for s in stats['eval']]))}
        for cover in (.1, .2, .3, .5, 1.):
            thr = np.percentile(ys, 100*(1 - cover)) if cover < 1 else -1
            accepted = []
            for img in base:
                bad = img.copy()
                bad[beam_v2._valid() & (np.arange(480)[:, None] >= thr)] = 0
                accepted.append(frame_ok(frame_stats(bad), sp, sd))
            fr[tag][f'false_accept_black_cover_{int(cover*100)}pct'] = float(np.mean(accepted))
        fr[tag]['constant_frames_accepted'] = [frame_ok(frame_stats(np.full((480, 640, 3), c, np.uint8)), sp, sd)
                                               for c in (0, 64, 128, 255)]
    results['frames'] = fr
    results['frame_stats_percentiles'] = {n: {k: {str(q): pct([s[k] for s in S], q) for q in (0, .1, 1, 50)}
                                              for k in ('spread', 'std')} for n, S in stats.items()}

    e = results['column_evaluation']
    checks = {'A1': e['new']['correct_kept']/e['correct'] >= ACCEPT['A1_eval_correct_columns_kept_min'],
              'A2': e['new']['precision'] >= ACCEPT['A2_eval_column_precision_min']
                    and e['new']['precision'] >= e['old']['precision'],
              'A3': results['occluder_check_high_pose']['new_pass'] <= results['occluder_check_high_pose']['old_pass'],
              'A4': fr['new']['false_reject_eval'] <= ACCEPT['A4_eval_frame_false_reject_max'],
              'A5': all(fr['new'][k] <= fr['old'][k] for k in fr['new'] if k.startswith('false_accept'))
                    and not any(fr['new']['constant_frames_accepted'])}
    doc = {'schema': gates_module.SCHEMA, 'gates_id': 'own_image_gates_floor_light_v1',
           'render_profile': 'floor_light_v1', 'robot_model': 'masterpi_v3', 'status': 'DEV_CALIBRATED',
           'procedure': 'docs/own_image_gate_calibration.md', 'script': 'scripts/calibrate_own_image_gates.py',
           'script_sha256': sha256(__file__), 'values': values, 'legacy_values': legacy, 'rules': RULES,
           'acceptance': ACCEPT, 'acceptance_passed': checks, 'splits': SPLITS,
           'data_sha256': {run if isinstance(run, str) else run[0]: {
               rid: sha256(outputs/(run if isinstance(run, str) else run[0])/f'robots/{rid}/frames.jsonl')
               for rid in ('r1', 'r2')}
               for split in SPLITS.values() for run in split['runs']},
           'fixtures_manifest_sha256': sha256(ROOT/SPLITS['frame_evaluation']['fixtures']/'manifest.json'),
           'dev_calibration_sha256': sha256(args.calibration), 'results': results}
    Path(args.out).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    print(json.dumps({'values': values, 'acceptance_passed': checks}, indent=1))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
