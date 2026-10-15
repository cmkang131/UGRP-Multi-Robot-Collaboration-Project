"""Saved own RGB diagnostics; evaluation geometry is opened only after detection.

No simulator, renderer or controller action is executed. Visibility is analytic
static-wall visibility, not a claim about texture detectability/dynamic occlusion.
"""
import argparse
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from scripts.offline_self_map import digest, dump, read, rows, score


def detect_frames(raw):
    from harness.natural_floor_slam import extract
    from harness.active_wall_vision import observe
    from harness.e2e_rgb_vo import image_mask
    frames, source = rows(raw/'robots/r3/frames.jsonl')
    trace, trace_source = rows(raw/'trace.jsonl')
    original = {r['frame_id']: r for r in trace}
    result, pixels = [], []
    for f in frames:
        from scripts.offline_self_map import safe_rgb_path
        p = safe_rgb_path(raw, f['path'], 'r3')
        if digest(p) != f['sha256']:
            raise ValueError('RGB_HASH_MISMATCH')
        rgb = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
        servo = {int(k): v for k, v in f['commanded_servo'].items()}
        obs = extract(rgb, servo, frame_id=f['frame_id'], t=f['sim_time'])
        wall = observe(rgb, servo)
        keys, _ = cv2.ORB_create(nfeatures=800).detectAndCompute(
            cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), image_mask(rgb, servo))
        uv = np.array([k.pt for k in keys], float).reshape(-1, 2)
        pixels.append(uv)
        e = original[f['frame_id']]
        result.append(dict(frame_id=f['frame_id'], t=f['sim_time'], sha256=f['sha256'],
            elapsed_s=round(f['sim_time']-frames[0]['sim_time'], 8),
            detected_kinds=dict(floor_mask_orb=len(obs.points_body),
                wall_floor_segments=len(wall['segments']), floor_rays=len(wall['floor_xy'])),
            admitted_features=e['features'], matches=e['matches'], inliers=e['inliers'],
            reason=e['visual_reason'], stage=e['stage'], pan=servo[6]))
    return result, pixels, [source, trace_source]


def ray_wall_distance(origin, directions, walls):
    """Ray/AABB slab intersection; t uses the caller's direction scale."""
    near = np.full(len(directions), np.inf)
    for wall in walls:
        center = np.array([*wall['center_m'], wall['height_m']/2])
        half = np.array([*wall['half_extents_m'], wall['height_m']/2])
        with np.errstate(divide='ignore', invalid='ignore'):
            a, b = (center-half-origin)/directions, (center+half-origin)/directions
        enter, leave = np.minimum(a, b).max(1), np.maximum(a, b).min(1)
        hit = (leave >= np.maximum(enter, 0)) & (leave > 0)
        near = np.minimum(near, np.where(hit, np.maximum(enter, 0), np.inf))
    return near


def visibility(camera, walls, uv):
    from harness.e2e_rgb_vo import K, D
    origin = np.array(camera['camera_xyz'])
    rotation = np.array(camera['camera_rotation']).reshape(3, 3)
    normal = cv2.fisheye.undistortPoints(uv.reshape(-1, 1, 2), K, D).reshape(-1, 2) if len(uv) else np.empty((0, 2))
    dirs = np.column_stack([normal, np.ones(len(normal))])*[1, -1, -1]
    dirs = dirs@rotation.T
    with np.errstate(divide='ignore', invalid='ignore'):
        ground = np.where(dirs[:, 2] < 0, -origin[2]/dirs[:, 2], np.inf)
    wall_hits = ray_wall_distance(origin, dirs, walls) < ground
    visible_walls, visible_edges, visible_corners = [], [], []
    for wall in walls:
        x, y = wall['center_m']; hx, hy = wall['half_extents_m']
        corners = np.array([[x-hx, y-hy, .001], [x+hx, y-hy, .001],
                            [x+hx, y+hy, .001], [x-hx, y+hy, .001]])
        wall_visible = False
        for edge, (a, b) in enumerate(zip(corners, np.roll(corners, -1, axis=0))):
            pts = np.linspace(a, b, max(2, int(np.ceil(np.linalg.norm(b-a)/.025))+1))
            dirs = pts-origin
            optical = (dirs@rotation)*[1, -1, -1]
            front = optical[:, 2] > 0
            projected = cv2.fisheye.projectPoints(optical.reshape(-1, 1, 3),
                np.zeros(3), np.zeros(3), K, D)[0].reshape(-1, 2)
            valid = (front & (projected[:, 0] >= 4) & (projected[:, 0] < 636)
                & (projected[:, 1] >= 4) & (projected[:, 1] < 470)
                & (np.linalg.norm(dirs, axis=1) < 4.)
                & (ray_wall_distance(origin, dirs, walls) >= 1.-1e-6))
            if valid.sum() >= 2 and np.linalg.norm(np.ptp(projected[valid], axis=0)) >= 5:
                visible_edges.append(f"{wall['id']}:{edge}")
                wall_visible = True
            if valid[0]:
                visible_corners.append(f"{wall['id']}:{edge}")
        if wall_visible: visible_walls.append(wall['id'])
    return dict(floor_mask_orb_on_static_wall=int(wall_hits.sum()),
        floor_mask_orb_other=int((~wall_hits).sum()),
        expected_wall_objects=visible_walls, expected_wall_floor_edges=visible_edges,
        expected_wall_floor_corners=visible_corners)


def evaluate(raw, output, detected, pixels, replay_dirs):
    import json
    static_text, map_source = read(raw/'inputs/static_map.json')
    static = json.loads(static_text)
    cameras, camera_source = rows(raw/'eval_only/camera.jsonl')
    truth, truth_source = rows(raw/'eval_only/trajectory.jsonl')
    by_time = {round(c['t'], 8): c for c in cameras}
    comparisons = []
    for r, uv in zip(detected, pixels):
        c = by_time[round(r['t'], 8)]
        comparisons.append(dict(frame_id=r['frame_id'], t=r['t'],
            **visibility(c, static['obstacles'], uv)))
    dump(output/'eval-only-visibility.json', dict(
        scope='static wall boxes, actual camera pose, fixed fisheye; 4m range, >=5px edge; '
              'no render; dynamic/self occlusion and exact detectable ORB count unverified',
        sources=[map_source, camera_source], frames=comparisons))
    origin = [*truth[0]['robot_xyz_m'][:2], truth[0]['robot_yaw_rad']]
    replay_results = {}
    from harness.natural_floor_slam import compose, wrap
    for path in replay_dirs:
        snap_text, snap_source = read(path/'map.json')
        trace, trace_source = rows(path/'trace.jsonl')
        snap = json.loads(snap_text)
        summary = json.loads((path/'summary.json').read_text())
        if summary['status'] != 'RECORDED' or len(trace) != len(truth):
            raise ValueError('FULL_REPLAY_REQUIRED')
        errors, yaw = [], []
        for r, gt in zip(trace, truth):
            if abs(r['t']-gt['t']) > 1e-8: raise ValueError('TIME_MISMATCH')
            p = compose(origin, r['pose'])
            errors.append(np.linalg.norm(p[:2]-gt['robot_xyz_m'][:2]))
            yaw.append(wrap(p[2]-gt['robot_yaw_rad']))
        replay_results[path.name] = dict(
            summary=summary, evaluation=score(snap, static, origin),
            pose_rmse_m=float(np.sqrt(np.mean(np.square(errors)))),
            yaw_rmse_rad=float(np.sqrt(np.mean(np.square(yaw)))),
            raw_frontier_last=trace[-1]['raw_frontier_cells'],
            raw_frontier_max=max((r['raw_frontier_cells'] or 0) for r in trace),
            prior_frames=len(snap.get('prior_frame_ids', [])),
            prior_cells=len(snap.get('prior_cells', [])),
            sources=[snap_source, trace_source, truth_source, map_source])
    t0 = detected[0]['t']
    spin = [r for r in truth if t0+10 <= r['t'] <= t0+22.4+1e-8]
    rotation = float(np.unwrap([r['robot_yaw_rad'] for r in spin])[-1]-spin[0]['robot_yaw_rad'])
    stats = {}
    for key in ('floor_mask_orb', 'wall_floor_segments', 'floor_rays'):
        values = [r['detected_kinds'][key] for r in detected]
        stats[key] = dict(min=min(values), median=float(np.median(values)), max=max(values),
                          nonzero_frames=sum(v > 0 for v in values))
    expected = {key: dict(min=min(len(r[key]) for r in comparisons),
                         median=float(np.median([len(r[key]) for r in comparisons])),
                         max=max(len(r[key]) for r in comparisons))
                for key in ('expected_wall_objects', 'expected_wall_floor_edges', 'expected_wall_floor_corners')}
    result = dict(frames=len(detected), raw=str(raw), source_sha=(raw.parent/'SOURCE_SHA').read_text().strip(),
        detection=stats, reason_counts=dict(Counter(r['reason'] for r in detected)),
        expected_static_visibility=expected, actual_spin_eval_only_rad=rotation,
        spin_absolute_sim_range=[spin[0]['t'], spin[-1]['t']],
        comparisons=replay_results, research_result=False)
    dump(output/'analysis-summary.json', result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--replay', type=Path, action='append', default=[])
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    detected, pixels, sources = detect_frames(a.raw)
    dump(a.output/'frame-detections.json', dict(sources=sources, frames=detected))
    result = evaluate(a.raw, a.output, detected, pixels, a.replay)
    print({k: v for k, v in result.items() if k != 'comparisons'})


if __name__ == '__main__':
    main()
