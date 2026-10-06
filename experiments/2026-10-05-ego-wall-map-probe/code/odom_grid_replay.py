"""Offline replay only: own saved C detections/frames + own issued commands.

Evaluation is a separate pass after prediction, with no callback into memory.
No MuJoCo calls, renderers, models, fitting or static-map input to the mapper.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

from harness.self_wall_memory import SelfWallMemory
from harness.self_odom_grid import CALIBRATION, CALIBRATION_SHA256, OdomGrid, transform


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def replay(episode, robot, cached_c=None):
    import markerless_probe as mp
    import ego_wall_map as ewm
    import height_free_wall as hfw
    import wall_probe as wp
    import cv2

    command_path = episode/f'robots/{robot}/commands.jsonl'
    frames_path = episode/f'robots/{robot}/frames.jsonl'
    commands, frames = read_rows(command_path), read_rows(frames_path)
    # Stable order preserves same-time issued command order.
    commands.sort(key=lambda r: r['t'])
    memory = SelfWallMemory(robot, self_map='odom_grid_v1', self_map_options={'start_time': frames[0]['sim_time']})
    memory.command({'t': frames[0]['sim_time'], 'kind': 'initial_servo_command',
                    'pulses': frames[0]['commanded_servo']})
    grid = memory.self_map
    cache, header = {}, None
    sources = [command_path, frames_path]
    if cached_c:
        header, records = ewm.EgoWallMap.load(cached_c)
        cache = {r['view_index']: r for r in records}
        sources.append(cached_c)
    columns = mp.column_positions(96, 2)
    params = {'floor_patch_max_m': .81, 'run_step_window': 3, 'top_edge_px': 4}
    rows, observations, states = [], [], []
    cursor = 0
    for idx, frame in enumerate(frames):
        if frame.get('robot_id') != robot or frame.get('camera') != 'robot_cam':
            raise ValueError('FOREIGN_CAMERA')
        t = float(frame['sim_time'])
        # These recordings capture before dispatch at the same scheduler tick.
        while cursor < len(commands) and float(commands[cursor]['t']) < t-1e-8:
            memory.command(commands[cursor]); cursor += 1
        grid.odom.advance(t)
        servo = {int(k): int(v) for k, v in frame['commanded_servo'].items()}
        record = None
        cm = None
        if cached_c:
            record = cache.get(frame['frame_id'])
            if record:
                record = json.loads(json.dumps(record))
                # The old C default stores FK/arm-axis endpoints. Apply the
                # explicitly recorded fixed offset once, never infer from GT.
                offset = header['arm_axis_offset_recorded_m'] - header['arm_axis_offset_m']
                for s in record['seg']:
                    for ri, ai in ((0, 1), (2, 3)):
                        x, y = s[ri]*math.cos(s[ai])+offset, s[ri]*math.sin(s[ai])
                        s[ri], s[ai] = math.hypot(x, y), math.atan2(y, x)
        elif idx % 2 == 0:
            settled = grid.odom.t-grid.odom.servo_since+1e-8 >= grid.settle_s[int(grid.odom.loaded)]
            if settled:
                image_path = episode/frame['path']
                if sha(image_path) != frame['sha256']:
                    raise ValueError('FRAME_HASH_MISMATCH')
                image = cv2.imread(str(image_path))
                if image is None:
                    raise ValueError('UNREADABLE_FRAME')
                cm = mp.column_model(servo, wp.detector_bias(servo, wp.is_loaded(servo), True), columns)
                scan = hfw.detect(mp.undistort(image), cm, params=params, loaded=wp.is_loaded(servo))
                segments = hfw.link_segments(scan, params)
                if segments:
                    record = {'t_sim': t, 'view_index': frame['frame_id'], 'posture': ewm.posture_label(servo),
                              'load': wp.is_loaded(servo),
                              'seg': [ewm.segment_to_chassis(s, cm.origin[:2], ewm.ARM_AXIS_OFFSET_M) for s in segments]}
        if record:
            record['t_sim'] = t
            if cm is None:
                cm = mp.column_model(servo, wp.detector_bias(servo, wp.is_loaded(servo), True), columns)
            camera = np.array(cm.origin[:2]) + [ewm.ARM_AXIS_OFFSET_M, 0.]
            local = memory.observe_wall(record, camera_xy=camera, robot_id=robot)
            if local:
                observations.append({'t': t, 'pose': grid.odom.pose, 'camera': camera.tolist(),
                                     'segments': [s.tolist() for s in local], 'frame_id': frame['frame_id']})
                states.append({'t': t, 'occupied': grid.occupied_points().tolist()})
        rows.append({'t': t, 'pose': grid.odom.pose})
    return memory, rows, observations, states, sources


def ground_truth(episode, robot):
    """Evaluation-only. Parse saved qpos; never instantiate or forward a simulator."""
    address = 0
    for node in ET.fromstring((episode/'scene.xml').read_text()).find('worldbody').iter():
        if node.tag not in ('joint', 'freejoint'):
            continue
        kind = node.get('type', 'free' if node.tag == 'freejoint' else 'hinge')
        if node.get('name') == f'{robot}__base_free':
            break
        address += {'free': 7, 'ball': 4}.get(kind, 1)
    else:
        raise ValueError('MISSING_ROBOT_JOINT')
    rows = read_rows(episode/'eval_only/trajectory.jsonl')
    poses = []
    for row in rows:
        q = row['qpos'][address:address+7]
        w, x, y, z = q[3:]
        poses.append([q[0], q[1], math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))])
    return np.array([r['t'] for r in rows]), np.array(poses)


def wall_samples(rects, cell=.1):
    # Fixed all-wall boundary denominator, not only correct/visible detections.
    samples = {}
    for cx, cy, hx, hy in rects:
        corners = np.array([[cx-hx, cy-hy], [cx+hx, cy-hy], [cx+hx, cy+hy], [cx-hx, cy+hy]])
        for a, b in zip(corners, np.roll(corners, -1, axis=0)):
            n = int(math.ceil(np.linalg.norm(b-a)/cell))
            for p in np.linspace(a, b, n, endpoint=False):
                samples[tuple(np.floor(p/cell).astype(int))] = p
    return np.array(list(samples.values()))


def boundary_dist(points, rects):
    if not len(points):
        return np.array([])
    q = np.abs(points[:, None, :] - rects[None, :, :2]) - rects[None, :, 2:]
    signed = np.linalg.norm(np.maximum(q, 0), axis=2) + np.minimum(q.max(2), 0)
    return np.abs(signed).min(1)


def quality(points, rects, samples, tol=.15):
    if not len(points):
        return {'occupied_cells': 0, 'precision_015': None, 'precision_cell': None,
                'wall_coverage': 0., 'wall_error_rmse_m': None}, np.zeros(len(samples), bool)
    dist = boundary_dist(points, rects)
    cover = cKDTree(points).query(samples)[0] <= tol
    return {'occupied_cells': len(points), 'precision_015': float((dist <= tol).mean()),
            'precision_cell': float((dist <= math.sqrt(2)*.05).mean()),
            'wall_coverage': float(cover.mean()), 'wall_error_rmse_m': float(np.sqrt((dist**2).mean()))}, cover


def evaluate(episode, robot, poses, observations, states):
    times, truth = ground_truth(episode, robot)
    origin_idx = int(np.argmin(abs(times-poses[0]['t'])))
    if abs(times[origin_idx]-poses[0]['t']) > 1e-6:
        raise ValueError('NO_MATCHING_START_TRUTH')
    origin = truth[origin_idx]
    obstacles = json.loads((episode/'inputs/static_map.json').read_text())['obstacles']
    rects = np.array([list(o['center_m'])+list(o['half_extents_m']) for o in obstacles if o.get('kind')=='wall'])
    samples = wall_samples(rects)
    ever = np.zeros(len(samples), bool)
    series = []
    oracle = OdomGrid(robot, settle_s=None)
    errors, terminal_observation_errors = [], []
    for obs, state in zip(observations, states):
        idx = int(np.argmin(abs(times-obs['t'])))
        if abs(times[idx]-obs['t']) > 1e-6:
            raise ValueError('UNMATCHED_OBSERVATION_TRUTH')
        # Actual map aligned once using start GT only. No ICP or per-frame fixes.
        pts = transform(np.asarray(state['occupied']).reshape(-1, 2), origin)
        metrics, cover = quality(pts, rects, samples)
        ever |= cover
        row = {'t': obs['t'], **metrics, 'wall_coverage_ever': float(ever.mean())}
        # Explicit eval-only counterfactual: the SAME admitted detections with
        # per-frame truth poses isolates pose error; never passed back to memory.
        local = [np.asarray(s) for s in obs['segments']]
        oracle.insert(transform([obs['camera']], truth[idx])[0], [transform(s, truth[idx]) for s in local])
        oracle_metrics, _ = quality(oracle.occupied_points(), rects, samples)
        row['oracle_precision_015'] = oracle_metrics['precision_015']
        row['oracle_wall_coverage'] = oracle_metrics['wall_coverage']
        row['oracle_wall_error_rmse_m'] = oracle_metrics['wall_error_rmse_m']
        predicted = transform(np.vstack([transform(s, obs['pose']) for s in local]), origin)
        target = np.vstack([transform(s, truth[idx]) for s in local])
        e = np.linalg.norm(predicted-target, axis=1)
        errors.extend(e.tolist()); terminal_observation_errors = e.tolist()
        series.append(row)
    end = poses[-1]
    idx = int(np.argmin(abs(times-end['t'])))
    if abs(times[idx]-end['t']) > 1e-6:
        raise ValueError('UNMATCHED_END_TRUTH')
    predicted_xy = transform([end['pose'][:2]], origin)[0]
    pos_error = float(np.linalg.norm(predicted_xy-truth[idx, :2]))
    yaw_error = abs((origin[2]+end['pose'][2]-truth[idx, 2]+math.pi)%(2*math.pi)-math.pi)
    final = series[-1] if series else quality(np.empty((0, 2)), rects, samples)[0]
    return {'wall_boundary_samples': len(samples), 'wall_tolerance_m': .15, 'final': final,
            'end_sim_s': end['t'], 'last_wall_sim_s': observations[-1]['t'] if observations else None,
            'end_position_error_m': pos_error, 'end_yaw_error_deg': math.degrees(yaw_error),
            'end_4m_point_error_bound_m': pos_error+8*math.sin(yaw_error/2),
            'mapped_endpoint_pose_rmse_m': float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
            'last_wall_endpoint_pose_rmse_m': float(np.sqrt(np.mean(np.square(terminal_observation_errors)))) if errors else None,
            'alignment': 'actual grid: start GT SE(2) only; oracle grid: eval-only counterfactual per-frame GT',
            'origin_eval_only': origin.tolist()}, series, oracle.occupied_points(), rects, samples


def plots(out, robot, grid, result, series, oracle, rects, origin):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for ax, pts, title in zip(axes, (transform(grid.occupied_points(), origin), oracle),
                              ('Command odom + initial GT alignment', 'EVAL ONLY: per-frame GT counterfactual')):
        for x, y, hx, hy in rects:
            ax.add_patch(Rectangle((x-hx, y-hy), 2*hx, 2*hy, color='grey', alpha=.35))
        if len(pts):
            ax.scatter(pts[:, 0], pts[:, 1], s=7, color='#b93e35', label='occupied cells')
        ax.set(title=title, xlabel='evaluation world x (m)', ylabel='y (m)', aspect='equal')
        ax.grid(alpha=.2)
    fig.suptitle(f'{out.name} / {robot}: private map, no map fusion')
    fig.savefig(out/'map.png', dpi=125); plt.close(fig)
    return out/'map.png'


def run(args):
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    episode = Path(args.episode).resolve()
    memory, poses, obs, states, sources = replay(episode, args.robot, Path(args.cached_c) if args.cached_c else None)
    # Freeze all mapping outputs BEFORE reading any evaluation file.
    dump(out/'grid.json', memory.self_map.export())
    for name, rows in [('poses.jsonl', poses), ('observations.jsonl', obs)]:
        (out/name).write_text(''.join(json.dumps(r)+'\n' for r in rows))
    result, series, oracle, rects, samples = evaluate(episode, args.robot, poses, obs, states)
    result.update(robot=args.robot, split=args.split, episode=str(episode),
                  source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  options={'self_map': 'odom_grid_v1', 'resolution_m': .1, 'max_range_m': 4.,
                           'settle_s': [.25, 2.25], 'p_hit': .7, 'p_miss': .4,
                           'uncertainty_weight': 'off', 'text_top_k': 6, 'text_max_tokens': 384},
                  calibration={'path': CALIBRATION, 'sha256': CALIBRATION_SHA256, 'scope': 'old M1 DEV fit; no v3 refit'},
                  llm_text=memory.snapshot()['self_map_text'], frames=memory.self_map.frames,
                  rejected=memory.self_map.rejected, physical_runs=0, model_calls=0)
    sources += [episode/'scene.xml', episode/'inputs/static_map.json', episode/'eval_only/trajectory.jsonl', ROOT/CALIBRATION]
    result['sources'] = [{'path': str(p), 'sha256': sha(p)} for p in sources]
    dump(out/'summary.json', result)
    (out/'series.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in series))
    plots(out, args.robot, memory.self_map, result, series, oracle, rects, result['origin_eval_only'])
    final = result['final']
    fields = ('precision_015', 'precision_cell', 'wall_coverage', 'wall_coverage_ever', 'wall_error_rmse_m',
              'oracle_precision_015', 'oracle_wall_coverage', 'oracle_wall_error_rmse_m')
    dump(out/'result.json', {'derived_view_only': True, 'family': 'self_map', 'policy': 'odom_grid_v1',
                            'case': out.name, 'split': args.split, 'source_sha': result['source_sha'],
                            'offline_source': {'path': str(out/'summary.json'), 'sha256': sha(out/'summary.json')},
                            'offline_scalar_scope': 'offline private wall mapping; no new physics or model calls',
                            'offline_scalars': {**{'offline/'+k: final[k] for k in fields if final.get(k) is not None},
                                                'offline/end_position_error_m': result['end_position_error_m'],
                                                'offline/end_yaw_error_deg': result['end_yaw_error_deg']},
                            'offline_series': {'source': {'path': str(out/'series.jsonl'), 'sha256': sha(out/'series.jsonl')},
                                                'format': 'jsonl', 'sim_time_field': 't',
                                                'tags': [{'tag': 'trace/'+k, 'path': [k]} for k in fields]},
                            'hparam_metrics': ['offline/precision_015', 'offline/wall_coverage', 'offline/end_position_error_m']})
    print(json.dumps({'output': str(out), 'robot': args.robot, 'frames': result['frames'],
                      'final': final, 'end_position_error_m': result['end_position_error_m'],
                      'end_yaw_error_deg': result['end_yaw_error_deg']}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--episode', required=True)
    p.add_argument('--robot', choices=('r1', 'r2'), required=True)
    p.add_argument('--cached-c')
    p.add_argument('--split', choices=('development', 'confirmation_replay'), required=True)
    p.add_argument('--output', required=True)
    run(p.parse_args())
