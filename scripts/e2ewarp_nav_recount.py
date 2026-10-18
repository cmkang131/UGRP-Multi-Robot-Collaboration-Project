#!/usr/bin/env python3
"""Eval-only recount for the two-robot navigation gate (no success claim).

Nav mode has no evaluator, so ``run_e2e_warp --mode nav`` never writes a
physical evaluation. This script recomputes, from raw state only:

- final base xy per robot, distance travelled, and whether the final base lies
  inside the authored destination zone rectangle;
- the controller's own arrival claim (``nav-events.json``) next to the GT
  inside/outside result, so a claim can never be reported as success.

Inputs are the raw run directory (``evaluation-state.npz``, per-world
``eval-geometry.json``, ``result.json``, ``nav-events.json``). Output is a new
``nav-evaluation.json``; it never re-enters the run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

SCHEMA = 'ugrp.e2ewarp.nav_evaluation.v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(run):
    run = Path(run)
    result = json.loads((run / 'result.json').read_text())
    state = np.load(run / 'evaluation-state.npz')
    qpos = np.asarray(state['qpos'])
    if qpos.ndim != 3:
        raise ValueError('evaluation-state qpos must be [ticks, worlds, nq]')
    events = {}
    path = run / 'nav-events.json'
    if path.is_file():
        events = json.loads(path.read_text())
    return run, result, qpos, events


def inside(xy, center, half):
    return bool(abs(float(xy[0]) - float(center[0])) <= float(half[0])
                and abs(float(xy[1]) - float(center[1])) <= float(half[1]))


def world_rows(run, qpos, events, world, dt):
    geometry_path = run / f'world-{world:02d}' / 'eval-geometry.json'
    geometry = json.loads(geometry_path.read_text())
    destination = geometry['destination']
    rows = []
    for robot, adr in sorted(geometry['robot_qpos_adr'].items()):
        adr = int(adr)
        track = qpos[:, world, adr:adr + 2]
        final = track[-1]
        steps = np.linalg.norm(np.diff(track, axis=0), axis=1)
        claimed = any(event.get('after') == 'ARRIVED' for event in events.get(f'{world}:{robot}', []))
        rows.append(dict(robot=robot, final_xy=[round(float(v), 4) for v in final],
                         distance_m=round(float(steps.sum()), 4),
                         inside_destination_gt=inside(final, destination['center_m'],
                                                      destination['half_extents_m']),
                         own_arrival_claim=bool(claimed),
                         claim_matches_gt=bool(claimed == inside(final, destination['center_m'],
                                                                 destination['half_extents_m']))))
    return dict(world=world, ticks=int(qpos.shape[0]), dt_s=float(dt),
                eval_geometry_sha256=sha(geometry_path),
                destination=destination, robots=rows,
                arrival_gt_n=sum(1 for r in rows if r['inside_destination_gt']),
                arrival_claim_n=sum(1 for r in rows if r['own_arrival_claim']),
                claim_mismatch_n=sum(1 for r in rows if not r['claim_matches_gt']))


def recount(run_dir):
    run, result, qpos, events = load(run_dir)
    worlds = sorted(int(p.name.split('-')[1]) for p in run.glob('world-*') if p.is_dir())
    if not worlds:
        raise ValueError('no world directories in run')
    if qpos.shape[1] != len(worlds):
        raise ValueError('evaluation-state world count does not match world dirs')
    dt = float(np.load(run / 'evaluation-state.npz')['dt'])
    rows = [world_rows(run, qpos, events, w, dt) for w in worlds]
    robots = sum(len(w['robots']) for w in rows)
    return dict(schema=SCHEMA, eval_only=True, no_pooling=True, research_result=False,
                success_claim='not_available',
                run=str(run.resolve()), source_sha=result.get('source_sha'),
                status=result.get('status'), sim_s=result.get('sim_s'),
                world_n=len(rows), robot_n=robots,
                arrival_gt_n=sum(w['arrival_gt_n'] for w in rows),
                arrival_claim_n=sum(w['arrival_claim_n'] for w in rows),
                claim_mismatch_n=sum(w['claim_mismatch_n'] for w in rows),
                wall_contacts='not_measured',
                inputs=dict(evaluation_state_sha256=sha(run / 'evaluation-state.npz'),
                            result_sha256=sha(run / 'result.json')),
                scope='eval-only GT recount of raw base qpos; not an E2E or physical-success claim',
                worlds=rows)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, help='default: <run>/nav-evaluation.json')
    a = p.parse_args(argv)
    value = recount(a.run)
    out = a.out or (a.run / 'nav-evaluation.json')
    out.write_text(json.dumps(value, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps({k: value[k] for k in ('world_n', 'robot_n', 'arrival_gt_n',
                                            'arrival_claim_n', 'claim_mismatch_n', 'status')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
