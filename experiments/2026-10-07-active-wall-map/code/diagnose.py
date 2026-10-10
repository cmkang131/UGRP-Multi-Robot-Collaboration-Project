"""Post-seal evaluation only; never imported by the acquisition/controller.

Separate detector/projection errors from online pose errors without fitting.
The .05 m segment sampling and .15 m wall tolerance match the existing grid.
"""
from collections import Counter
import argparse
import math
import sys
import numpy as np
from score import RAW, EXP, ROOT, load, rows, prediction, dump

sys.path.insert(0, str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
from odom_grid_replay import boundary_dist
from harness.self_odom_grid import transform


def contact_points(segments):
    chunks = [np.linspace(a, b, max(2, math.ceil(np.linalg.norm(b-a)/.05)+1))
              for a, b in np.asarray(segments).reshape(-1, 2, 2)]
    return np.concatenate(chunks) if chunks else np.empty((0, 2))


def statistics(distances):
    d = np.asarray(distances)
    return dict(n=len(d), correct=int((d <= .15).sum()),
                precision=float((d <= .15).mean()) if len(d) else None,
                median_m=float(np.median(d)) if len(d) else None,
                rmse_m=float(np.sqrt(np.mean(d*d))) if len(d) else None)


def diagnose(case, partial=False):
    ep = RAW/case
    view = prediction(case, partial)
    truth = {round(r['t'], 6): r for r in rows(ep/'eval_only/trajectory.jsonl')}
    cams = {round(r['t'], 6): r for r in rows(ep/'eval_only/camera.jsonl')}
    scene = load(ep/'inputs/static_map.json')
    rects = np.array([w['center_m']+w['half_extents_m'] for w in scene['obstacles']
                      if w.get('kind') == 'wall'])
    body_errors, camera_errors, pitch_errors = [], [], []
    for row in rows(ep/'own-contacts.jsonl'):
        points = contact_points(row['segments'])
        t = round(row['t'], 6)
        gt, camera = truth[t], cams[t]
        nominal_origin = np.array(row['camera_origin'])
        nominal_rotation = np.array(row['camera_rotation'])
        actual_rotation = np.array(camera['camera_rotation']).reshape(3, 3) @ np.diag([1, -1, -1])
        body_rotation = np.array(camera['body_rotation']).reshape(3, 3)
        actual_body_rotation = body_rotation.T @ actual_rotation
        pitch_errors.append(math.degrees(math.asin(np.clip(actual_body_rotation[2, 2], -1, 1))
                                        -math.asin(np.clip(nominal_rotation[2, 2], -1, 1))))
        if not len(points):
            continue
        world = transform(points, [*gt['robot_xyz_m'][:2], gt['robot_yaw_rad']])
        body_errors.extend(boundary_dist(world, rects))
        # Recover the SAME nominal optical rays; replace only the camera pose.
        optical = (np.c_[points, np.zeros(len(points))]-nominal_origin) @ nominal_rotation
        rays = optical @ actual_rotation.T
        origin = np.array(camera['camera_xyz'])
        with np.errstate(divide='ignore', invalid='ignore'):
            depth = -origin[2]/rays[:, 2]
            ground = origin+rays*depth[:, None]
        valid = (depth > 0) & np.isfinite(ground).all(1)
        camera_errors.extend(boundary_dist(ground[valid, :2], rects))
    start = truth[min(truth)]
    origin = [*start['robot_xyz_m'][:2], start['robot_yaw_rad']]
    traces = rows(ep/'own-controller.jsonl')
    online = transform(np.array([r['pose'][:2] for r in traces]), origin)
    actual = np.array([truth[round(r['t'], 6)]['robot_xyz_m'][:2] for r in traces])
    errors = np.linalg.norm(online-actual, axis=1)
    sigma = np.array([r['sigma_xy'] for r in traces])
    events = load(ep/'active-events.json')
    decisions = [r for r in events if r['reason'] == 'information_decision']
    doors = [d for r in traces for d in r['doors']]
    result = dict(case=case, source_sha=load(view/'result.json')['source_sha'],
        gt_body_contacts=statistics(body_errors), actual_camera_contacts=statistics(camera_errors),
        pitch=dict(n=len(pitch_errors), median_abs_deg=float(np.median(np.abs(pitch_errors))),
                   p95_abs_deg=float(np.quantile(np.abs(pitch_errors), .95))),
        online_uncertainty=dict(n=len(traces), error_over_3sigma=int((errors > 3*sigma).sum()),
                                max_sigma_xy_m=float(sigma.max()), online_rmse_m=float(np.sqrt(np.mean(errors**2)))),
        information=dict(decisions=len(decisions), uncertain=sum(r['uncertain'] for r in decisions),
                         selected=dict(Counter(r['selected'] for r in decisions)),
                         revisit_reached=sum(r['reason']=='active_revisit_reached' for r in events)),
        navigation=dict(Counter(r['reason'] for r in load(ep/'navigation.json'))),
        frame_status=dict(Counter(r['status'] for r in traces)),
        frontend=dict(Counter(r['reason'] for r in load(ep/'decisions.json'))),
        doors=dict(candidate_rows=len(doors), candidate_frames=sum(bool(r['doors']) for r in traces),
                   feasible_rows=sum(d['payload_clearance_feasible'] for d in doors),
                   reasons=dict(Counter(d['reason'] for d in doors)),
                   qualification='No eligible door means zero measured wrong-door attempts is not passage validation.'),
        qualification='Post-seal GT diagnostics only; repeated-frame samples are not independent; no fitted thresholds.')
    dump(EXP/'results'/f'{case}-diagnostics.json', result)
    print(__import__('json').dumps(result, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('case', choices=['photo', 'speckle'])
    p.add_argument('--partial', action='store_true')
    args=p.parse_args()
    diagnose(args.case,args.partial)
