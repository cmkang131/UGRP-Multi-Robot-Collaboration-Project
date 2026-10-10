"""Offline off/on comparison using the frozen odom_grid_v1 detector outputs.

Prediction accepts only own commands, frame timestamps/initial commanded servo,
and own camera contacts. Saved baseline poses are read for the off-byte audit
only AFTER both prediction artifacts have been frozen. GT is evaluation-only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from harness.self_wall_memory import SelfWallMemory
from harness.self_odom_grid import transform
from harness.self_map_csm import CSMOptions
import odom_grid_replay as base


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(r, allow_nan=False)+'\n' for r in rows))


def predict(commands, frames, contacts, robot, option):
    memory = SelfWallMemory(robot, self_map='odom_grid_v1', pose_correction=option,
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
            camera = np.asarray(contact['camera'])
            if option == 'off':
                # These frozen contacts already passed the historical range/settle
                # gates. Exact float geometry preserves the old cells byte-for-byte.
                local = [np.asarray(s) for s in contact['segments']]
                grid.insert(transform([camera], grid.odom.pose)[0], [transform(s, grid.odom.pose) for s in local])
            else:
                local = grid.observe_contacts(t=t, frame_id=frame['frame_id'], segments=contact['segments'],
                                              camera_xy=camera, robot_id=robot)
            if len(local):
                obs.append({'t': t, 'pose': grid.odom.pose, 'camera': camera.tolist(),
                            'segments': [s.tolist() for s in local], 'frame_id': frame['frame_id']})
                states.append({'t': t, 'occupied': grid.occupied_points().tolist()})
        poses.append({'t': t, 'pose': grid.odom.pose})
        if option != 'off':
            covariance.append({'t': t, 'covariance': grid.odom.covariance.tolist()})
    return memory, poses, obs, states, covariance


def path_errors(episode, robot, poses):
    times, truth = base.ground_truth(episode, robot)
    stamps = np.array([r['t'] for r in poses])
    indices = np.searchsorted(times, stamps)
    indices = np.minimum(indices, len(times)-1)
    left = np.maximum(0, indices-1)
    indices = np.where(abs(times[left]-stamps) < abs(times[indices]-stamps), left, indices)
    if np.max(abs(times[indices]-stamps)) > 1e-6:
        raise ValueError('UNMATCHED_PATH_TRUTH')
    origin = truth[indices[0]]
    predicted = np.array([r['pose'] for r in poses])
    errors = np.linalg.norm(transform(predicted[:, :2], origin)-truth[indices, :2], axis=1)
    yaw = np.abs((origin[2]+predicted[:, 2]-truth[indices, 2]+np.pi) % (2*np.pi)-np.pi)
    distribution = {name: float(np.quantile(errors, q)) for name, q in
                    [('median_m', .5), ('p90_m', .9), ('p95_m', .95), ('max_m', 1.)]}
    distribution.update(rmse_m=float(np.sqrt(np.mean(errors**2))), count=len(errors))
    return distribution, [{'t': float(t), 'xy_error_m': float(e), 'yaw_error_deg': float(np.degrees(y))}
                          for t, e, y in zip(stamps, errors, yaw)]


def acceptance(off, on):
    a, b = off['path_position_error'], on['path_position_error']
    x, y = off['final'], on['final']
    checks = {'terminal_30pct_and_075m': on['end_position_error_m'] <= min(.75, .70*off['end_position_error_m']),
              'path_median_not_worse': b['median_m'] <= a['median_m'],
              'path_p95_not_worse': b['p95_m'] <= a['p95_m'],
              'path_rmse_20pct': b['rmse_m'] <= .8*a['rmse_m'],
              'map_precision_not_worse': y['precision_015'] is not None and y['precision_015'] >= x['precision_015'],
              'map_recall_within_2pp': y['wall_coverage'] >= x['wall_coverage']-.02,
              'map_rmse_20pct': y['wall_error_rmse_m'] is not None and y['wall_error_rmse_m'] <= .8*x['wall_error_rmse_m']}
    return {'success': all(checks.values()), 'checks': checks}


def run_case(name, baseline, output, source_sha):
    robot = name.split('-')[1]
    cache = baseline/name
    # Episode location/input hashes are provenance only, never mapping evidence.
    prior_summary = json.loads((cache/'summary.json').read_text())
    episode = Path(prior_summary['episode'])
    command_path = episode/f'robots/{robot}/commands.jsonl'
    frame_path = episode/f'robots/{robot}/frames.jsonl'
    for source in prior_summary['sources']:
        if Path(source['path']) in (command_path, frame_path) and base.sha(source['path']) != source['sha256']:
            raise ValueError('OWN_INPUT_HASH_CHANGED')
    commands, frames = base.read_rows(command_path), base.read_rows(frame_path)
    # Explicit whitelist drops the old DR pose; no eval material in the predictor.
    contacts = [{k: row[k] for k in ('t', 'frame_id', 'camera', 'segments')}
                for row in base.read_rows(cache/'observations.jsonl')]
    out = output/name
    out.mkdir()
    frozen = {}
    for label, option in [('off', 'off'), ('on', 'own_map_csm_v1')]:
        target = out/label
        target.mkdir()
        memory, poses, obs, states, cov = predict(commands, frames, contacts, robot, option)
        base.dump(target/'grid.json', memory.self_map.export())
        (target/'llm.txt').write_text(memory.self_map.text()+'\n')
        for filename, rows in [('poses.jsonl', poses), ('observations.jsonl', obs), ('covariance.jsonl', cov)]:
            write_rows(target/filename, rows)
        if label == 'on':
            write_rows(target/'corrections.jsonl', memory.self_map.decisions)
            write_rows(target/'map_ledger.jsonl', memory.self_map.ledger)
        frozen[label] = (memory, poses, obs, states)
    # Verify pre-CSM output only after prediction, never as a pose source.
    old_grid = json.loads((cache/'grid.json').read_text())
    off_grid = frozen['off'][0].self_map
    old_text_grid = base.OdomGrid(robot)
    old_text_grid.cells = {(x, y): value for x, y, value in old_grid['cells']}
    golden = {'poses_bytes': (out/'off/poses.jsonl').read_bytes() == (cache/'poses.jsonl').read_bytes(),
              'cells_bytes': json.dumps(off_grid.export()['cells']).encode() == json.dumps(old_grid['cells']).encode(),
              'llm_bytes': off_grid.text().encode() == old_text_grid.text().encode(),
              'frames': off_grid.frames == old_grid['frames']}
    base.dump(out/'off_golden.json', golden)
    if not all(golden.values()):
        raise ValueError('OFF_GOLDEN_MISMATCH: '+str(golden))
    summaries = {}
    # Evaluation starts here. No subsequent writes to prediction/memory state.
    for label, (memory, poses, obs, states) in frozen.items():
        result, series, _, _, _ = base.evaluate(episode, robot, poses, obs, states)
        distribution, errors = path_errors(episode, robot, poses)
        result.update(name=name, robot=robot, source_sha=source_sha,
                      pose_correction='off' if label == 'off' else 'own_map_csm_v1',
                      path_position_error=distribution, inserted_frames=memory.self_map.frames,
                      cached_input_frames=len(contacts), historical_prefilter_rejected=prior_summary['rejected'],
                      split='development' if name.startswith('s911') else 'confirmation_replay',
                      sources=[{'path': str(p), 'sha256': base.sha(p)} for p in
                               (command_path, frame_path, cache/'observations.jsonl', cache/'poses.jsonl',
                                cache/'grid.json', episode/'scene.xml', episode/'eval_only/trajectory.jsonl',
                                episode/'inputs/static_map.json')])
        if label == 'on':
            decisions = memory.self_map.decisions
            result.update(correction_status_counts=dict(Counter(r['status'] for r in decisions)),
                          correction_reason_counts=dict(Counter(r['reason'] for r in decisions)),
                          submaps=memory.self_map.submap_id, options=asdict(memory.self_map.options))
        base.dump(out/label/'summary.json', result)
        write_rows(out/label/'series.jsonl', series)
        write_rows(out/label/'path_errors.jsonl', errors)
        summaries[label] = result
    verdict = acceptance(summaries['off'], summaries['on'])
    base.dump(out/'comparison.json', {'name': name, 'off_golden': golden, **verdict})
    print(json.dumps({'name': name, 'end_off_on_m': [summaries[k]['end_position_error_m'] for k in ('off', 'on')],
                      'path_rmse_off_on_m': [summaries[k]['path_position_error']['rmse_m'] for k in ('off', 'on')],
                      'on_reasons': summaries['on']['correction_reason_counts'], **verdict}), flush=True)
    return {'name': name, **verdict, 'off_golden': golden}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['development', 'confirmation_replay'], required=True)
    parser.add_argument('--baseline', default=str(ROOT/'outputs/self-map-odom-grid-v1-complete'))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    source_paths = ['harness/self_map_csm.py', 'harness/self_wall_memory.py', 'harness/self_odom_grid.py',
                    'experiments/2026-10-05-ego-wall-map-probe/code/own_map_csm_replay.py',
                    'experiments/2026-10-05-ego-wall-map-probe/code/odom_grid_replay.py']
    provenance = {'source_sha': sha, 'split': args.split, 'options': asdict(CSMOptions()),
                  'preregistered_criteria_sha': 'e44f12c9',
                  'design_sha256': 'c60948eb734c8489663d402a73ff62ee3469bd0a09bdd40e0821b43291304fab',
                  'files_sha256': {p: base.sha(ROOT/p) for p in source_paths},
                  'input_scope': 'frozen own contacts after historical settle/range gates; own commands; own frame times; no GT/peer/static map',
                  'invocation': sys.argv}
    base.dump(out/'manifest.json', provenance)
    seeds = ['s911'] if args.split == 'development' else ['s912', 's913']
    cases = [run_case(seed+'-'+robot, Path(args.baseline), out, sha) for seed in seeds for robot in ('r1', 'r2')]
    base.dump(out/'verdict.json', {'split': args.split, 'success': all(c['success'] for c in cases), 'cases': cases})


if __name__ == '__main__':
    main()
