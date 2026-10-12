"""Fresh-process offline probability comparison. Prediction freezes before GT.

Use one condition/case per process for isolated peak RSS. Existing v1/v2 reports
are historical baselines, not reclassified or pooled with this cohort.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import odom_grid_replay as base
from own_map_csm_replay import acceptance, path_errors, predict as old_predict, write_rows
from harness.self_wall_memory import SelfWallMemory


def predict(commands, frames, contacts, robot, condition):
    option = 'own_map_csm_prob_v1' if condition == 'prob' else 'own_map_rbpf_v1'
    options = {} if condition == 'prob' else {'particles': int(condition[4:]), 'seed': 20261006}
    memory = SelfWallMemory(robot, self_map='odom_grid_v1', pose_correction=option,
                            pose_correction_options=options,
                            self_map_options={'start_time': frames[0]['sim_time']})
    memory.command({'t': frames[0]['sim_time'], 'kind': 'initial_servo_command',
                    'pulses': frames[0]['commanded_servo']})
    commands = sorted(commands, key=lambda row: row['t'])
    by_frame = {r['frame_id']: r for r in contacts}
    if len(by_frame) != len(contacts):
        raise ValueError('DUPLICATE_CONTACT_FRAME')
    grid = memory.self_map
    poses, obs, states, covariance = [], [], [], []
    cursor = 0
    for frame in frames:
        if frame['robot_id'] != robot or frame['camera'] != 'robot_cam':
            raise ValueError('FOREIGN_CAMERA')
        t = float(frame['sim_time'])
        while cursor < len(commands) and float(commands[cursor]['t']) < t-1e-8:
            memory.command(commands[cursor])
            cursor += 1
        grid.odom.advance(t)
        contact = by_frame.get(frame['frame_id'])
        if contact is not None:
            if abs(contact['t']-t) > 1e-8:
                raise ValueError('CONTACT_TIME_MISMATCH')
            local = grid.observe_contacts(t=t, frame_id=frame['frame_id'], segments=contact['segments'],
                                          camera_xy=contact['camera'], robot_id=robot)
            if len(local):
                obs.append({'t': t, 'pose': grid.odom.pose, 'camera': contact['camera'],
                            'segments': [s.tolist() for s in local], 'frame_id': frame['frame_id']})
            # Selection can change an RBPF map even when the chosen scan is rejected.
            states.append({'t': t, 'occupied': grid.occupied_points().tolist()})
        poses.append({'t': t, 'pose': grid.odom.pose})
        covariance.append({'t': t, 'covariance': grid.odom.covariance.tolist()})
    if condition != 'prob':
        # Oracle comparison uses this final particle's accepted scans, not the
        # online sequence of potentially different best-particle ancestors.
        obs = [dict(row) for row in grid.ledger]
    return memory, poses, obs, states, covariance


def particle_artifacts(grid):
    return [{'particle': i, 'weight': float(grid.weights[i]), 'pose': grid.poses[i].tolist(),
             'cells': [[int(x), int(y), float(v)] for (x, y), v in sorted(g.cells.items())],
             'history': grid.histories[i]}
            for i, g in enumerate(grid.maps)]


def evaluate_prediction(episode, robot, poses, obs, states):
    # Historical evaluator zips one inserted observation with one map state.
    # RBPF selection can change on rejection, so align oracle inputs explicitly
    # and score the full online map series separately, including its final state.
    by_time = {s['t']: s for s in states}
    result, oracle_series, _, rects, samples = base.evaluate(
        episode, robot, poses, obs, [by_time[o['t']] for o in obs])
    oracle_at = {r['t']: {k: v for k, v in r.items() if k.startswith('oracle_')} for r in oracle_series}
    ever = np.zeros(len(samples), bool)
    series = []
    for state in states:
        points = base.transform(np.asarray(state['occupied']).reshape(-1, 2), result['origin_eval_only'])
        quality, cover = base.quality(points, rects, samples)
        ever |= cover
        series.append({'t': state['t'], **quality, 'wall_coverage_ever': float(ever.mean()),
                       **oracle_at.get(state['t'], {})})
    if series:
        result['final'] = {**series[-1], **(oracle_at[obs[-1]['t']] if obs else {})}
    return result, series


def run_case(name, condition, baseline, output):
    robot = name.split('-')[1]
    cache = baseline/name
    previous = json.loads((cache/'summary.json').read_text())
    episode = Path(previous['episode'])
    command_path, frame_path = (episode/f'robots/{robot}/{f}.jsonl' for f in ('commands', 'frames'))
    for source in previous['sources']:
        if Path(source['path']) in (command_path, frame_path) and base.sha(source['path']) != source['sha256']:
            raise ValueError('OWN_INPUT_HASH_CHANGED')
    commands, frames = base.read_rows(command_path), base.read_rows(frame_path)
    contacts = [{k: row[k] for k in ('t', 'frame_id', 'camera', 'segments')}
                for row in base.read_rows(cache/'observations.jsonl')]
    target = output/condition/name
    target.mkdir(parents=True, exist_ok=False)
    load_start = os.getloadavg()
    start = time.perf_counter()
    memory, poses, obs, states, covariance = predict(commands, frames, contacts, robot, condition)
    resources = {'prediction_wall_s': time.perf_counter()-start,
                 'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform == 'darwin' else 1024),
                 'loadavg_start': load_start, 'loadavg_end': os.getloadavg(),
                 'scope': 'fresh process peak through prediction; wall excludes file writing and GT evaluation',
                 'pid': os.getpid(), 'python': sys.version, 'platform': sys.platform}
    grid = memory.self_map
    base.dump(target/'grid.json', grid.export())
    (target/'llm.txt').write_text(grid.text()+'\n')
    for filename, rows in [('poses', poses), ('observations', obs), ('covariance', covariance),
                           ('corrections', grid.decisions), ('map_ledger', grid.ledger)]:
        write_rows(target/f'{filename}.jsonl', rows)
    base.dump(target/'resources.json', resources)
    if condition != 'prob':
        base.dump(target/'final_particles.json', particle_artifacts(grid))
    # Freeze predictions before reading any truth. Off replay is a byte audit.
    off_memory, off_poses, _, _, _ = old_predict(commands, frames, contacts, robot, 'off')
    golden = {'poses_bytes': ''.join(json.dumps(r, allow_nan=False)+'\n' for r in off_poses).encode() == (cache/'poses.jsonl').read_bytes(),
              'cells_bytes': json.dumps(off_memory.self_map.export()['cells']).encode() ==
                             json.dumps(json.loads((cache/'grid.json').read_text())['cells']).encode()}
    old_grid = base.OdomGrid(robot)
    old_grid.cells = {(x, y): v for x, y, v in json.loads((cache/'grid.json').read_text())['cells']}
    golden['llm_bytes'] = off_memory.self_map.text().encode() == old_grid.text().encode()
    base.dump(target/'off_golden.json', golden)
    if not all(golden.values()):
        raise ValueError('OFF_GOLDEN_MISMATCH')
    source_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    # GT starts here, including off path errors. No further predictor writes.
    result, series = evaluate_prediction(episode, robot, poses, obs, states)
    result.update(path_position_error=path_errors(episode, robot, poses)[0], name=name, condition=condition,
                  source_sha=source_sha, split='development' if name.startswith('s911') else 'confirmation_replay',
                  inserted_frames=grid.frames, resources=resources,
                  correction_status_counts=dict(Counter(e['status'] for e in grid.decisions)),
                  correction_reason_counts=dict(Counter(e['reason'] for e in grid.decisions)),
                  sources=[{'path': str(p), 'sha256': base.sha(p)} for p in
                           (command_path, frame_path, cache/'observations.jsonl', episode/'scene.xml',
                            episode/'eval_only/trajectory.jsonl', episode/'inputs/static_map.json')])
    off = dict(previous)
    off['path_position_error'] = path_errors(episode, robot, off_poses)[0]
    if condition != 'prob':
        result.update(resamples=grid.resamples, neff_min=min(e.get('neff', len(grid.maps)) for e in grid.decisions),
                      particle_reasons=dict(Counter(p['reason'] for e in grid.decisions for p in e.get('particle_events', []))),
                      selection='online MAP path; final map belongs to final selected particle; no GT selection')
    else:
        result['insertion_weight_range'] = [min(grid.insertion_weights), max(grid.insertion_weights)]
    base.dump(target/'summary.json', result)
    base.dump(target/'comparison.json', {**acceptance(off, result), 'off_golden': golden})
    write_rows(target/'series.jsonl', series)
    write_rows(target/'path_errors.jsonl', path_errors(episode, robot, poses)[1])
    base.dump(target/'prediction_hashes.json', {p.name: base.sha(p) for p in target.iterdir()
                                               if p.name in ('grid.json', 'poses.jsonl', 'observations.jsonl', 'corrections.jsonl', 'final_particles.json')})
    print(json.dumps({'name': name, 'condition': condition, 'end_m': result['end_position_error_m'],
                      'wall_s': resources['prediction_wall_s'], 'rss_mib': resources['peak_rss_mib'],
                      **acceptance(off, result)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True, choices=[f's{s}-{r}' for s in (911, 912, 913) for r in ('r1', 'r2')])
    parser.add_argument('--condition', required=True, choices=['prob', 'rbpf30', 'rbpf100'])
    parser.add_argument('--baseline', type=Path, default=ROOT/'outputs/self-map-odom-grid-v1-complete')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run_case(args.case, args.condition, args.baseline, args.output)
