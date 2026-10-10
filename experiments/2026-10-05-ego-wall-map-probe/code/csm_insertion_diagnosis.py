"""Frozen-v1-pose insertion ablation; no matching, tuning, physics or models."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import odom_grid_replay as base
from harness.self_odom_grid import OdomGrid, transform


def rebuild(robot, contacts, poses, decisions, include):
    grid = OdomGrid(robot, settle_s=None)
    pose_at = {r['t']: r['pose'] for r in poses}
    status = {r['frame_id']: r['status'] for r in decisions}
    seen = set()
    for row in contacts:
        key = (row['t'], row['frame_id'])
        if key in seen:
            continue
        seen.add(key)
        if status[row['frame_id']] not in include:
            continue
        pose = pose_at[row['t']]
        grid.insert(transform([row['camera']], pose)[0], [transform(s, pose) for s in row['segments']])
    return grid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    cases = []
    sources = {}
    for seed in ('s911', 's912', 's913'):
        for robot in ('r1', 'r2'):
            name = seed+'-'+robot
            split = 'development' if seed == 's911' else 'confirmation'
            root = ROOT/'outputs'/('self-map-csm-v1-'+split)/name
            cache = ROOT/'outputs/self-map-odom-grid-v1-complete'/name
            def read(path):
                sources[str(path)] = base.sha(path)
                return base.read_rows(path)
            # Saved estimated poses, never GT poses; geometry whitelist only.
            contacts = [{k: r[k] for k in ('t', 'frame_id', 'camera', 'segments')}
                        for r in read(cache/'observations.jsonl')]
            decisions = read(root/'on/corrections.jsonl')
            poses = {k: read(root/k/'poses.jsonl') for k in ('off', 'on')}
            accepted = {'accepted', 'bootstrap'}
            non_rejected = accepted | {'deferred'}
            all_status = non_rejected | {'rejected'}
            variants = [('v1', 'on', accepted), ('v1_plus_deferred', 'on', non_rejected),
                        ('v1_all_diagnostic', 'on', all_status),
                        ('off_same_nonrejected', 'off', non_rejected), ('off', 'off', all_status)]
            target = out/name
            target.mkdir()
            grids = {}
            for label, pose_source, include in variants:
                grid = rebuild(robot, contacts, poses[pose_source], decisions, include)
                base.dump(target/(label+'-grid.json'), grid.export())
                grids[label] = grid
            # Freeze all counterfactual grids before reading eval alignment/map.
            summary = json.loads((root/'off/summary.json').read_text())
            old_v1 = json.loads((root/'on/grid.json').read_text())
            old_off = json.loads((root/'off/grid.json').read_text())
            assert grids['v1'].export()['cells'] == old_v1['cells'], 'V1_REBUILD_MISMATCH'
            assert grids['off'].export()['cells'] == old_off['cells'], 'OFF_REBUILD_MISMATCH'
            static_path = Path(next(s['path'] for s in summary['sources'] if s['path'].endswith('static_map.json')))
            sources[str(static_path)] = base.sha(static_path)
            sources[str(root/'off/summary.json')] = base.sha(root/'off/summary.json')
            obstacles = json.loads(static_path.read_text())['obstacles']
            rects = np.array([list(o['center_m'])+list(o['half_extents_m']) for o in obstacles if o.get('kind') == 'wall'])
            samples = base.wall_samples(rects)
            result = {'name': name, 'scope': 'post-hoc fixed v1 estimated poses/decisions; insertion ablation, not v2',
                      'wall_boundary_samples': len(samples), 'variants': {}}
            for label, grid in grids.items():
                quality, _ = base.quality(transform(grid.occupied_points(), summary['origin_eval_only']), rects, samples)
                result['variants'][label] = {'frames': grid.frames, **quality}
            base.dump(target/'summary.json', result)
            cases.append(result)
            print(json.dumps({'name': name, 'frames_recall': {k: [v['frames'], v['wall_coverage']]
                                                            for k, v in result['variants'].items()}}), flush=True)
    base.dump(out/'summary.json', {'cases': cases})
    base.dump(out/'manifest.json', {'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                                  'script_sha256': base.sha(Path(__file__)), 'sources_sha256': sources,
                                  'hypothesis': 'restore deferred frames at frozen v1 best estimate; rejected-only upper diagnostic',
                                  'files_sha256': {str(p.relative_to(out)): base.sha(p) for p in out.rglob('*.json')}})


if __name__ == '__main__':
    main()
