"""CSM v2 offline replay: identical v1 criteria, geometry and command input.

v1 matching code/settings stay frozen; only memory-grid insertion is changed.
Development and confirmation are separate invocations with source/hash records.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import odom_grid_replay as base
from harness.self_map_csm import CSMOptions
from own_map_csm_replay import predict, path_errors, acceptance, write_rows


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
    for label, option in [('off', 'off'), ('on', 'own_map_csm_v2')]:
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
    v1_split = 'development' if name.startswith('s911') else 'confirmation'
    v1_root = ROOT/'outputs'/('self-map-csm-v1-'+v1_split)/name/'on'
    v1_pose_golden = (out/'on/poses.jsonl').read_bytes() == (v1_root/'poses.jsonl').read_bytes()
    base.dump(out/'off_golden.json', golden)
    base.dump(out/'v1_pose_golden.json', {'v2_matches_frozen_v1_pose_bytes': v1_pose_golden})
    if not v1_pose_golden:
        raise ValueError('V2_CHANGED_V1_POSE')
    if not all(golden.values()):
        raise ValueError('OFF_GOLDEN_MISMATCH: '+str(golden))
    summaries = {}
    # Evaluation starts here. No subsequent writes to prediction/memory state.
    for label, (memory, poses, obs, states) in frozen.items():
        result, series, _, _, _ = base.evaluate(episode, robot, poses, obs, states)
        distribution, errors = path_errors(episode, robot, poses)
        result.update(name=name, robot=robot, source_sha=source_sha,
                      pose_correction='off' if label == 'off' else 'own_map_csm_v2',
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
    base.dump(out/'comparison.json', {'name': name, 'off_golden': golden, 'v1_pose_golden': v1_pose_golden, **verdict})
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
    source_paths = ['harness/self_map_csm.py', 'harness/self_map_csm_v2.py', 'harness/self_wall_memory.py', 'harness/self_odom_grid.py',
                    'experiments/2026-10-05-ego-wall-map-probe/code/own_map_csm_replay.py',
                    'experiments/2026-10-05-ego-wall-map-probe/code/own_map_csm_v2_replay.py',
                    'experiments/2026-10-05-ego-wall-map-probe/code/odom_grid_replay.py']
    provenance = {'source_sha': sha, 'split': args.split, 'options': asdict(CSMOptions()),
                  'preregistered_criteria_sha': 'e44f12c9', 'v2_unchanged_criteria_commit': '5538499b',
                  'insertion_policy': 'accepted/bootstrap/deferred current-estimate mapping; actual rejections excluded; unchanged v1 matching keyframes',
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
