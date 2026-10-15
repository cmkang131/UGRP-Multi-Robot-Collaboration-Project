"""Saved-RGB replay and a separate evaluation-only scoring command; no renderer."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
from scipy.ndimage import label
from scipy.spatial import cKDTree


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    if not path.exists():
        path = Path(str(path)+'.zst')
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else path.read_bytes()
    return raw.decode(), {'path': str(path.resolve()), 'sha256': digest(path)}


def rows(path):
    raw, source = read(path)
    return [json.loads(line) for line in raw.splitlines() if line.strip()], source


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def safe_rgb_path(root, relative, robot):
    root = Path(root).resolve()
    path = (root/relative).resolve()
    if not path.is_relative_to(root/'robots'/robot/'rgb'):
        raise ValueError('OWN_RGB_PATH_REQUIRED')
    return path


def replay(raw, images, robot, output, motion_model, self_map_integration='off',
           pose_rebuild='off', navigation_support='off'):
    # No evaluation file is opened in this function or passed to the mapper.
    from harness.self_map_integration import Options, OPTION, make_mapper
    if self_map_integration == 'off':
        return {'status': 'DISABLED', 'toggle': 'off'}
    if self_map_integration != OPTION:
        raise ValueError('UNKNOWN_SELF_MAP_INTEGRATION')
    raw, images, output = Path(raw), Path(images), Path(output)
    frames, frame_source = rows(raw/'robots'/robot/'frames.jsonl')
    commands, command_source = rows(raw/'robots'/robot/'commands.jsonl')
    if not frames or not commands:
        raise ValueError('EMPTY_REPLAY_INPUT')
    output.mkdir(parents=True, exist_ok=False)
    start = min(float(frames[0]['sim_time']), float(commands[0]['t']))
    mapper = make_mapper(robot_id=robot, start_time=start,
                         options=Options(self_map_integration=OPTION, motion_model=motion_model,
                                         pose_rebuild=pose_rebuild, navigation_support=navigation_support))
    ci, missing, used, rejected = 0, [], [], []
    status = 'RECORDED'
    failure = None
    try:
        with (output/'trace.jsonl').open('w') as trace:
            for row in frames:
                if row['robot_id'] != robot:
                    raise ValueError('REPLAY_PEER_FRAME')
                t = float(row['sim_time'])
                # Frames precede commands at the same timestamp; setup servo is the
                # exception and is issued before the first capture in saved runs.
                while ci < len(commands):
                    cmd = commands[ci]
                    same_setup = abs(cmd['t']-start) < 1e-8 and cmd['kind'] in ('initial_servo_command', 'arm', 'look')
                    if not (cmd['t'] < t-1e-8 or same_setup):
                        break
                    mapper.command(cmd)
                    ci += 1
                image_path = safe_rgb_path(images, row['path'], robot)
                if not image_path.exists():
                    missing.append(row['frame_id'])
                    continue
                sha = digest(image_path)
                if sha != row['sha256']:
                    raise ValueError('SAVED_RGB_SHA256_MISMATCH')
                bgr = cv2.imdecode(np.frombuffer(image_path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
                if bgr is None:
                    raise ValueError('SAVED_RGB_DECODE_FAILED')
                # Commanded servo metadata is checked, never measured actuator_state.
                servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
                if servo != mapper.servo:
                    raise ValueError('COMMAND_HISTORY_SERVO_MISMATCH')
                result = mapper.receive(robot_id=robot, t=t, frame_id=int(row['frame_id']),
                                        rgb=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), sha256=sha)
                used.append({'frame_id': row['frame_id'], 't': t,
                             'path': str(image_path), 'sha256': sha})
                trace.write(json.dumps(result, allow_nan=False)+'\n')
                if not result['map_updated']:
                    rejected.append(row['frame_id'])
    except Exception as exc:
        status, failure = 'HOST_ERROR', f'{type(exc).__name__}: {exc}'
    dump(output/'map.json', mapper.snapshot())
    dump(output/'inputs.json', {'sources': [frame_source, command_source], 'rgb': used,
                              'missing_frame_ids': missing})
    summary = dict(status=status, failure=failure, robot_id=robot,
                   source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                   toggle=OPTION, motion_model=motion_model, replay_start_t=start,
                   pose_rebuild=pose_rebuild, navigation_support=navigation_support,
                   declared_frames=len(frames), replayed_frames=len(used), missing_frames=len(missing),
                   unprocessed_frames=len(frames)-len(used)-len(missing),
                   map_updated_frames=sum(e['map_updated'] for e in mapper.events),
                   pose_sources=dict(Counter(e['pose_source'] for e in mapper.events)),
                   insertion_blockers=dict(Counter(b for e in mapper.events for b in e['insertion_blockers'])),
                   completion_declarations=sum(e['complete'] for e in mapper.events),
                   frontier_proposals=sum(e['selected_frontier'] is not None for e in mapper.events),
                   observed_cells=len(mapper.grid.navigation.odds),
                   selected_time_range=None if not used else [used[0]['t'], used[-1]['t']],
                   scope='saved RGB subset; recorded behavior, proposals not executed',
                   artifacts={p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()})
    dump(output/'summary.json', summary)
    return summary


def score(snapshot, static_map, origin):
    """Fixed-frame static occupancy IoU and coverage; GT never returns to runtime.

    Raster: a cell is occupied if its open interior intersects any fixed obstacle
    rectangle. Unknown prediction is neither free nor correct. Outside predictions
    remain false positives. The initial SE(2) is fixed, never fitted to the map.
    """
    from harness.self_odom_grid import transform
    r = float(snapshot['resolution_m'])
    bounds = np.asarray(static_map['bounds_m'], float)
    rects = np.array([list(o['center_m'][:2])+list(o['half_extents_m'][:2])
                      for o in static_map['obstacles']], float).reshape(-1, 4)
    if not len(rects):
        raise ValueError('EVALUATION_REQUIRES_FIXED_OBSTACLES')
    lo = np.floor([bounds[0]/r, bounds[2]/r]).astype(int)
    hi = np.ceil([bounds[1]/r, bounds[3]/r]).astype(int)
    if np.prod(hi-lo) > 1_000_000 or np.any(hi <= lo):
        raise ValueError('EVALUATION_GRID_RESOURCE_LIMIT')
    yy, xx = np.mgrid[lo[1]:hi[1], lo[0]:hi[0]]
    keys = np.stack([xx.ravel(), yy.ravel()], axis=1)
    centers = (keys+.5)*r
    occupied = (np.abs(centers[:, None, :]-rects[None, :, :2]) < rects[None, :, 2:]+r/2-1e-10).all(2).any(1)
    domain = {tuple(k) for k in keys}
    truth_occ = {tuple(k) for k in keys[occupied]}
    truth_free = domain-truth_occ
    predicted_occ, predicted_free = set(), set()
    for x, y, odds in snapshot['cells']:
        point = transform([[(x+.5)*r, (y+.5)*r]], origin)[0]
        cell = tuple(np.floor(point/r).astype(int))
        if odds > 0: predicted_occ.add(cell)
        elif odds < 0: predicted_free.add(cell)
    predicted_free -= predicted_occ
    union = predicted_occ | truth_occ
    components, _ = label((~occupied).reshape(tuple((hi-lo)[::-1])))
    start = np.floor(np.asarray(origin[:2])/r).astype(int)-lo
    valid_start = bool(np.all(start >= 0) and np.all(start < hi-lo))
    cid = components[start[1], start[0]] if valid_start else 0
    reachable = {tuple(k) for k in keys[(components.ravel() == cid)]} if cid else set()
    walls = np.array([list(o['center_m'][:2])+list(o['half_extents_m'][:2])
                      for o in static_map['obstacles'] if o.get('kind') == 'wall'], float).reshape(-1, 4)
    samples = []
    for cx, cy, hx, hy in walls:
        corners = np.array([[cx-hx, cy-hy], [cx+hx, cy-hy], [cx+hx, cy+hy], [cx-hx, cy+hy]])
        for a, b in zip(corners, np.roll(corners, -1, axis=0)):
            samples.extend(np.linspace(a, b, max(2, int(np.ceil(np.linalg.norm(b-a)/r))+1)))
    pts = np.asarray([[(x+.5)*r, (y+.5)*r] for x, y in sorted(predicted_occ)]).reshape(-1, 2)
    rmse = reverse_p95 = None
    if len(pts) and len(walls):
        q = np.abs(pts[:, None, :]-walls[None, :, :2])-walls[None, :, 2:]
        distances = np.abs(np.linalg.norm(np.maximum(q, 0), axis=2)+np.minimum(q.max(2), 0)).min(1)
        rmse = float(np.sqrt(np.mean(distances**2)))
        reverse_p95 = float(np.quantile(cKDTree(pts).query(np.asarray(samples))[0], .95))
    return dict(scope='static geometry only; all predicted occupied cells scored against wall surfaces',
                occupancy_iou=None if not union else len(predicted_occ & truth_occ)/len(union),
                occupancy_intersection=len(predicted_occ & truth_occ), occupancy_union=len(union),
                predicted_occupied=len(predicted_occ), truth_occupied=len(truth_occ),
                false_occupied_outside_domain=len(predicted_occ-domain),
                free_coverage_n=len(predicted_free & truth_free), free_coverage_N=len(truth_free),
                free_coverage=None if not truth_free else len(predicted_free & truth_free)/len(truth_free),
                reachable_free_coverage_n=len(predicted_free & reachable), reachable_free_coverage_N=len(reachable),
                known_coverage_n=len((predicted_occ | predicted_free) & domain), known_coverage_N=len(domain),
                wall_error_rmse_m=rmse, wall_error_predicted_N=len(pts),
                all_wall_to_prediction_p95_m=reverse_p95, all_wall_samples_N=len(samples),
                origin_eval_only=list(origin))


def evaluate(replay_dir, raw, output):
    replay_dir, raw, output = Path(replay_dir), Path(raw), Path(output)
    summary = json.loads((replay_dir/'summary.json').read_text())
    if summary['status'] != 'RECORDED':
        raise ValueError('INCOMPLETE_REPLAY_NOT_SCOREABLE')
    prediction_raw, prediction_source = read(replay_dir/'map.json')
    snapshot = json.loads(prediction_raw)
    map_raw, map_source = read(raw/'inputs/static_map.json')
    trajectory, trajectory_source = rows(raw/'eval_only'/summary['robot_id']/'trajectory.jsonl')
    start = trajectory[0]
    if abs(start['t']-summary['replay_start_t']) > 1e-7:
        raise ValueError('EVAL_ORIGIN_TIMESTAMP_MISMATCH')
    origin = [*start['robot_xyz_m'][:2], start['robot_yaw_rad']]
    metrics = score(snapshot, json.loads(map_raw), origin)
    metrics['sources'] = [map_source, trajectory_source, prediction_source]
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    dump(output, metrics)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('replay')
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--images', type=Path, required=True)
    p.add_argument('--robot', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--motion-model', choices=['s2_pulse_v122', 's2_pulse_v122_rotL_v1'], required=True)
    p.add_argument('--self-map-integration', choices=['off', 'natural_floor_frontier_v1'], default='off')
    p.add_argument('--pose-rebuild', choices=['off', 'refit_history_v1'], default='off')
    p.add_argument('--navigation-support', choices=['off', 'current_footprint_v1'], default='off')
    p = sub.add_parser('evaluate')
    p.add_argument('--replay-dir', type=Path, required=True)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = vars(parser.parse_args())
    mode = args.pop('mode')
    result = replay(**args) if mode == 'replay' else evaluate(**args)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 1 if result.get('status') == 'HOST_ERROR' else 0


if __name__ == '__main__':
    raise SystemExit(main())
