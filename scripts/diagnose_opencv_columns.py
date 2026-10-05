#!/usr/bin/env python3
"""Offline per-column diagnosis of the OpenCV wall observer on recorded frames (no simulator, no model).

For each of the 96 detector columns of a frame, report why ``harness.opencv_wall_observation.observations``
kept or dropped it: no candidate / two or more candidates / edge row / edge step below gate / saturation mask /
pass. The classification repeats the observer's own order and is cross-checked against ``observations()``.
Ground truth (trajectory + static map) is used only to say whether the true wall/floor boundary row was among
the candidates; it never changes the observer.

  python3 scripts/diagnose_opencv_columns.py --run <run dir> --robot r1 --frame 2334 --frame 2719 --out <dir>
"""
import argparse
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
from harness import zone_pair_highpose_contract as contract             # noqa: E402
from harness import vision_loc_protocol as vp                           # noqa: E402

CLASSES = ('PASS', 'NO_CANDIDATE', 'MULTI_CANDIDATE', 'EDGE_ROW', 'STEP_BELOW_GATE', 'SATURATION_MASK')
COLORS = {'PASS': (0, 200, 0), 'NO_CANDIDATE': (160, 160, 160), 'MULTI_CANDIDATE': (0, 200, 255),
          'EDGE_ROW': (255, 0, 255), 'STEP_BELOW_GATE': (255, 128, 0), 'SATURATION_MASK': (0, 0, 255)}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def yaw_of(q):
    w, x, y, z = q
    return math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))


def build_camera(calibration):
    from harness.vision_pose_source_highpose import HighPoseSource
    static, _, _ = contract.resolve('zone_wide_door_geometry_v3')
    # Offline diagnosis only needs the camera models: read the recorded calibration without the DEV admission
    # (the run's sibling manifest is not copied into the run directory).
    from eval_partial_fix_gate import offline_calibration
    contract.admitted_calibration = offline_calibration
    src = HighPoseSource(static, str(calibration), sha256(calibration), seed=911)
    return src.loc._pf, static


def diagnose(vl, pf, gates, run, robot, frame_id, geom):
    run = Path(run)
    frames = {}
    for line in (run/f'robots/{robot}/frames.jsonl').read_text().splitlines():
        f = json.loads(line)
        frames[f['frame_id']] = f
    f = frames[frame_id]
    servo = {int(k): int(v) for k, v in f['commanded_servo'].items()}
    camera = pf.column_model_for(servo)
    bgr = cv2.imread(str(run/f['path']))
    und = vl.mp.undistort(bgr)
    scan = vl.mp.detect_boundaries(und, camera, ow.DETECTOR)
    final = ow.observations(vl, bgr, camera, gates)

    hsv = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)
    sat_img = hsv[..., 1]
    saturated = cv2.dilate(cv2.inRange(hsv, (0, int(gates['wall_band_saturation_max']), 30), (179, 255, 255)),
                           np.ones((5, 5), np.uint8)) > 0
    img = und.astype(np.float32)
    lum = .114*img[..., 0] + .587*img[..., 1] + .299*img[..., 2]
    chroma = img[..., 0] - img[..., 2]
    step_min = float(gates['wall_edge_step_min'])

    # Offline label only: true boundary rows from the recorded pose and the static map.
    idx = {'r1': 0, 'r2': 1, 'r3': 2}[robot]
    traj = [json.loads(line) for line in (run/'eval_only/trajectory.jsonl').read_text().splitlines()]
    ts = np.array([r['t'] for r in traj])
    q = traj[int(np.argmin(abs(ts - f['sim_time'])))]['qpos'][17*idx:17*idx + 7]
    true_rows, _ = vl.expected_rows(geom, np.array([[q[0], q[1], yaw_of(q[3:7])]]), camera)

    rows = []
    for j, u in enumerate(scan.columns):
        cand = np.flatnonzero(np.isfinite(scan.vb[j]))
        cand_rows = [float(scan.vb[j, k]) for k in cand]
        cand_steps = [float(ow.edge_step(lum, chroma, int(round(b)), u)) if 4 <= int(round(b)) <= 470 else None
                      for b in cand_rows]
        truth = float(true_rows[0][j]) if np.isfinite(true_rows[0][j]) else None
        row = {'col': int(u), 'candidates': len(cand), 'cand_rows': [round(b, 1) for b in cand_rows],
               'cand_steps': [None if s is None else round(s, 1) for s in cand_steps],
               'true_row': None if truth is None else round(truth, 1),
               'true_in_candidates': None if truth is None else any(abs(b - truth) < 4 for b in cand_rows)}
        if len(cand) == 0:
            cls = 'NO_CANDIDATE'
        elif len(cand) >= 2:
            cls = 'MULTI_CANDIDATE'
        else:
            k = cand[0]
            b, t = scan.vb[j, k], scan.vt[j, k]
            r = int(round(b))
            if r < 4 or r > 470:
                cls = 'EDGE_ROW'
            elif step_min > 0 and edge_step_ok(lum, chroma, r, u, step_min) is False:
                cls = 'STEP_BELOW_GATE'
            else:
                lo, hi = max(0, int(t)-3) if np.isfinite(t) else 0, min(480, int(b)+4)
                a = max(0, int(u)-2)
                window_s = sat_img[lo:hi, a:int(u)+3]
                row['sat_max_in_window'] = int(window_s.max()) if window_s.size else None
                cls = 'SATURATION_MASK' if saturated[lo:hi, a:int(u)+3].any() else 'PASS'
        row['class'] = cls
        rows.append(row)
    passed = {r['col'] for r in rows if r['class'] == 'PASS'}
    informative = final.informative.tolist()
    consistent = int(sum(informative)) == len(passed)
    return {'frame_id': frame_id, 'sim_time': f['sim_time'], 'path': f['path'], 'frame_sha256': f['sha256'],
            'servo': servo, 'columns': rows, 'observer_informative_columns': int(sum(informative)),
            'diagnosis_pass_columns': len(passed), 'consistent_with_observer': consistent,
            'true_pose': [round(float(q[0]), 3), round(float(q[1]), 3), round(math.degrees(yaw_of(q[3:7])), 2)]}, und


def edge_step_ok(lum, chroma, row, u, step_min):
    return ow.edge_step(lum, chroma, row, u) >= step_min


def draw(und, result, path):
    img = und.copy()
    for r in result['columns']:
        u, color = r['col'], COLORS[r['class']]
        cv2.line(img, (u, 0), (u, 14), color, 3)
        for b in r['cand_rows']:
            cv2.circle(img, (u, int(round(b))), 4, color, -1)
        if r['true_row'] is not None and 0 <= r['true_row'] < 480:
            cv2.drawMarker(img, (u, int(round(r['true_row']))), (255, 255, 255), cv2.MARKER_TILTED_CROSS, 7, 1)
    y = 30
    for name in CLASSES:
        n = sum(1 for r in result['columns'] if r['class'] == name)
        cv2.rectangle(img, (6, y-10), (18, y+2), COLORS[name], -1)
        cv2.putText(img, f'{name} {n}', (24, y), cv2.FONT_HERSHEY_SIMPLEX, .42, (255, 255, 255), 1, cv2.LINE_AA)
        y += 16
    cv2.putText(img, f"frame {result['frame_id']} t={result['sim_time']} pan={result['servo'].get(6)} (x = true boundary)",
                (6, 470), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(path), img)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--run', required=True, help='case dir containing robots/, eval_only/, inputs/')
    ap.add_argument('--calibration', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--frame', type=int, action='append', default=[])
    ap.add_argument('--survey-every', type=int, default=0, help='also tally classes over every N-th settled frame')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    gates = contract.own_image_gates()['values']
    pf, static = build_camera(args.calibration)
    vl = vp.load_vis3()[0]
    geom = vl.mp.MapGeometry(json.loads((Path(args.run)/'inputs/static_map.json').read_text()), include_posts=False)
    summary = []
    for fid in args.frame:
        try:
            result, und = diagnose(vl, pf, gates, args.run, args.robot, fid, geom)
        except Exception as exc:                  # e.g. a pan in mid-sweep has no calibrated camera posture
            print(json.dumps({'frame_id': fid, 'skipped': f'{type(exc).__name__}: {exc}'}))
            continue
        (out/f'columns_{args.robot}_{fid:05d}.json').write_text(json.dumps({**result, 'gates': gates}, indent=1))
        draw(und, result, out/f'columns_{args.robot}_{fid:05d}.png')
        counts = {c: sum(1 for r in result['columns'] if r['class'] == c) for c in CLASSES}
        summary.append({'frame_id': fid, 'sim_time': result['sim_time'], 'pan': result['servo'].get(6), 'counts': counts,
                        'consistent_with_observer': result['consistent_with_observer']})
        print(json.dumps(summary[-1]))
    survey = {}
    if args.survey_every:
        from eval_partial_fix_gate import settled_frames
        for rid in ('r1', 'r2'):
            if not (Path(args.run)/f'robots/{rid}/frames.jsonl').exists():
                continue
            for f in settled_frames(Path(args.run), rid, args.survey_every):
                try:
                    result, _ = diagnose(vl, pf, gates, args.run, rid, f['frame_id'], geom)
                except Exception:
                    continue                      # no calibrated unloaded posture
                key = str(result['servo'].get(6))
                tally = survey.setdefault(key, {c: 0 for c in CLASSES} | {'frames': 0, 'true_in_candidates': 0,
                                                                          'true_missing_candidates': 0,
                                                                          'pass_row_err_gt4px': 0})
                tally['frames'] += 1
                for r in result['columns']:
                    tally[r['class']] += 1
                    if r['true_in_candidates'] is True:
                        tally['true_in_candidates'] += 1
                    elif r['true_in_candidates'] is False and r['true_row'] is not None:
                        tally['true_missing_candidates'] += 1
                    if r['class'] == 'PASS' and r['true_row'] is not None and r['cand_rows'] \
                            and abs(r['cand_rows'][0] - r['true_row']) >= 4:
                        tally['pass_row_err_gt4px'] += 1
        print(json.dumps({'survey_by_pan': survey}))
    (out/'summary.json').write_text(json.dumps({'gates': gates, 'frames': summary, 'survey_by_pan': survey}, indent=1))


if __name__ == '__main__':
    main()
