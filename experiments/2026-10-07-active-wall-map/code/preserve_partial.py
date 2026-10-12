"""Seal a HOST_BUDGET partial frontend without restarting physics or matching.

Never reads eval_only, scene geometry, or images. The graph is UNFINISHED.
Existing acquisition files are not overwritten.
"""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.run_active_wall_map import dump
from harness.self_wall_evidence import build_evidence

RAW = Path('/Users/changmin/projects/ugrp/outputs/active-wall-map-v1')
ep = RAW/'speckle'
out = RAW/'speckle-partial'
assert not out.exists()
assert not (ep/'result.json').exists() and not (ep/'graph.json').exists()
workflow = json.loads((RAW/'workflow-speckle/manifest.json').read_text())
assert workflow['status'] != 'running'
out.mkdir()
inputs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in ep.iterdir()
          if p.is_file() and p.name in ('frontend-ledger.json', 'frontend-poses.json',
                                        'frontend-grid.json', 'bundle.json', 'graphs.json')}
assert len(inputs) == 5
load = lambda name: json.loads((ep/name).read_text())
ledger, poses = load('frontend-ledger.json'), load('frontend-poses.json')
for row in ledger:
    row['robot_id'] = 'r3'
evidence = build_evidence(ledger, robot_id='r3', wall_evidence='tsdf_weight_v1')
dump(out/'graph.json', dict(ledger=ledger, poses=poses, wall_evidence=evidence,
    diagnostics=dict(loop_counts=None, switch_counts=None),
    qualification='UNFINISHED GRAPH. Saved RBPF frontend only; no graph rerun or new scan matching.'))
dump(out/'grid.json', load('frontend-grid.json'))
stop = json.loads((RAW/'speckle-budget-stop.json').read_text())
dump(out/'result.json', dict(status='HOST_BUDGET', source_sha=load('bundle.json')['source_sha'],
    case='speckle', frames=len((ep/'robots/r3/frames.jsonl').read_text().splitlines()),
    total_sim_s=poses[-1]['t'], start_sim_s=poses[0]['t']-2.,
    failure=dict(type='TimeoutError', message='HOST_BUDGET_30_MINUTES'),
    wall_s=stop['elapsed_wall_s'], model_calls=0, freeze=False,
    qualification='Partial acquisition; interrupted graph checkpoint and finalization, frontend-only metric view.'))
dump(out/'prediction.json', dict(input_hashes=inputs, input_root=str(ep),
    qualification='Preservation after owned-process budget stop, before partial GT scoring; no optimizer replay.',
    files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}))
assert 'mujoco' not in sys.modules
print(out)
