"""Offline evaluation of b_marker_detect=partial_known_size_v1 on the saved e2e11 frames.

Detection sees own RGB + commanded servo + own pose only (harness/e2e_b_partial.py).
Labels and the true B pose (scene.xml + eval_only trajectory) are read AFTER detection and
written only to the evaluation record. No simulation, no network.
"""
import argparse, hashlib, json, math, subprocess, sys, time
from collections import Counter
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'scripts'))
from replay_b_marker_detect import jsonl, read, scene_B, label
from harness.e2e_b_partial import detect_partial, board_half_extents


def true_robot_frame(B, pose):
    c, h = B[0], B[1]
    d = c-pose[:2]; co, si = math.cos(pose[2]), math.sin(pose[2])
    return [co*d[0]+si*d[1], -si*d[0]+co*d[1]], (-pose[2]) % math.pi


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--e2e11-outputs', type=Path, required=True); ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); manifests, rows = {}, []
    root = a.e2e11_outputs/'e2e11-stall-odometry/selected-frames'; t0 = time.time()
    for run_path in sorted(root.iterdir()):
        raw = a.e2e11_outputs/'azure-runs'/run_path.name/'raw'
        B = scene_B(read(raw/'scene.xml', manifests).decode())
        for rid in ('r1', 'r2'):
            frames = jsonl(raw, f'robots/{rid}/frames.jsonl', manifests)
            poses = {r['frame_id']: r for r in jsonl(raw, f'robots/{rid}/ownmap.jsonl', manifests)}
            traj = jsonl(raw, f'eval_only/{rid}/trajectory.jsonl', manifests); times = np.array([v['t'] for v in traj])
            for f in frames:
                p = run_path/'raw'/f['path']
                if not p.exists(): continue
                data = read(p, manifests)
                if hashlib.sha256(data).hexdigest() != f['sha256']: raise ValueError('SAVED_RGB_HASH_MISMATCH')
                rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
                servo = {int(k): v for k, v in f['commanded_servo'].items()}
                diag = {}
                got = detect_partial(rgb, servo, poses[f['frame_id']]['pose_own_m'], diagnostics=diag)
                # ---- evaluation only below ----
                i = int(np.argmin(np.abs(times-f['sim_time'])))
                true_pose = np.array([*traj[i]['robot_xyz_m'][:2], traj[i]['robot_yaw_rad']])
                lab = label(rgb, B, true_pose.tolist(), servo)
                tc, ty = true_robot_frame(B, true_pose)
                row = dict(run=run_path.name, robot=rid, frame_id=f['frame_id'], cls=lab['cls'], corners_in=lab['corners_in'],
                           B_area_fraction=lab['B_area_fraction'], accepted=len(got), reasons=[p_.get('reason') for p_ in diag.get('patches', [])],
                           true_center_robot_m=tc, true_yaw_robot_rad=ty, B_half_scene=B[1].tolist())
                if got:
                    g = got[0]; e = np.array(g['center_robot_m'])-tc
                    row.update(est_center_robot_m=g['center_robot_m'], center_err_m=float(np.linalg.norm(e)),
                               yaw_err_deg=float(math.degrees(abs((g['yaw_robot_rad']-ty+math.pi/2) % math.pi-math.pi/2))),
                               fit_stats={k: g['stats'].get(k) for k in ('rms_m', 'inlier_fraction', 'pos_std_m', 'yaw_std_deg', 'iou')})
                rows.append(row)
    cls = Counter(r['cls'] for r in rows)
    def block(sel):
        acc = [r for r in sel if r['accepted']]
        err = [r['center_err_m'] for r in acc]; yerr = [r['yaw_err_deg'] for r in acc]
        q = lambda v, p: float(np.percentile(v, p)) if v else None
        return dict(frames=len(sel), accepted=len(acc), center_err_m=dict(median=q(err, 50), p90=q(err, 90), max=max(err, default=None)),
                    yaw_err_deg=dict(median=q(yerr, 50), p90=q(yerr, 90), max=max(yerr, default=None)),
                    reasons=dict(Counter(x for r in sel for x in r['reasons'])))
    summary = dict(frames=len(rows), classes=dict(cls), scene_B_half_m=sorted({tuple(r['B_half_scene']) for r in rows}),
                   map_B_half_m=list(board_half_extents()), wall_seconds=round(time.time()-t0, 1),
                   partial=block([r for r in rows if r['cls'] == 'partial']), full=block([r for r in rows if r['cls'] == 'full']),
                   B_not_in_view=block([r for r in rows if r['cls'] == 'none']),
                   partial_by_corners_in=dict(Counter(r['corners_in'] for r in rows if r['cls'] == 'partial')))
    a.out.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(rows, sort_keys=True).encode()
    (a.out/'partial-eval-rows.json').write_bytes(raw)
    subprocess.check_call(['zstd', '-q', '-19', '-f', str(a.out/'partial-eval-rows.json'), '-o', str(a.out/'partial-eval-rows.json.zst')])
    (a.out/'partial-eval-rows.json').unlink()
    summary['rows_sha256_uncompressed'] = hashlib.sha256(raw).hexdigest()
    (a.out/'partial-eval-summary.json').write_text(json.dumps(summary, indent=1, sort_keys=True, default=float))
    print(json.dumps(summary, indent=1, sort_keys=True, default=float))


if __name__ == '__main__': main()
