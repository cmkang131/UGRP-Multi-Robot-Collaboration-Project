"""Offline egomap20 back-end replay. No truth/simulator imports or reads."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parents[1]
SOURCE = Path('/Users/changmin/projects/ugrp/outputs/arena-wall-map-v1')
RAW = Path('/Users/changmin/projects/ugrp/outputs/robust-wall-map-v1')
sys.path.insert(0, str(ROOT))
from harness.self_loop_rejection import refine_cached_graph
from harness.self_pose_graph import rebuild
from harness.self_wall_evidence import build_evidence


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def write_rows(path, value):
    Path(path).write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False)+'\n' for r in value))


def verify_source(case):
    source = SOURCE/'predictions'/case
    for name in ('prediction.json', 'baseline-prediction.json'):
        receipt = load(source/name)
        assert all(sha(source/p)==h for p,h in receipt['hashes'].items()), 'EGOMAP20_CACHE_CHANGED'
    receipt = load(source/'prediction.json')
    assert all(sha(p)==h for p,h in receipt['inputs'].items()), 'OWN_INPUTS_CHANGED'
    freeze = load(ROOT/'experiments/2026-10-07-arena-wall-map/freeze.json')
    assert all(sha(ROOT/p)==h for p,h in freeze['files'].items()), 'FROZEN_FRONTEND_CHANGED'
    return source


def predict(case, *, resume_evidence=False):
    source = verify_source(case)
    output = RAW/case
    off, on = output/'off', output/'on'
    golden = ('graph-ledger.jsonl','graph-poses.jsonl','graph-diagnostics.json','grid.json','llm.txt')
    if resume_evidence:
        failure=load(output/'host-error.json')
        assert failure['stage']=='evidence_serialization' and failure['gt_read'] is False
        assert all(sha(output/p)==h for p,h in failure['hashes'].items()), 'PARTIAL_GRAPH_CHANGED'
        assert not (output/'prediction.json').exists() and not (on/'wall-evidence.json').exists()
        ledger, path=rows(on/'graph-ledger.jsonl'), rows(on/'graph-poses.jsonl')
        print(case, 'resume evidence only, completed graph preserved', flush=True)
    else:
        output.mkdir(parents=True, exist_ok=False)
        off.mkdir()
        on.mkdir()
        for name in golden:
            shutil.copyfile(source/name, off/name)
            assert sha(source/name)==sha(off/name), 'OFF_BYTES_DIFFER'
        original = (rows(off/'graph-ledger.jsonl'), rows(off/'graph-poses.jsonl'), load(off/'graph-diagnostics.json'))
        frontend = [dict(r, robot_id='r3') for r in rows(source/'frontend-ledger.jsonl')]
        poses = rows(source/'frontend-poses.jsonl')
        assert refine_cached_graph(frontend, poses, original, robot_id='r3') is original
        print(case, 'verified cache; graph', len(frontend), 'scans', flush=True)
        ledger, path, diagnostic = refine_cached_graph(frontend, poses, original,
            robot_id='r3', loop_rejection='switchable_v1')
        write_rows(on/'graph-ledger.jsonl', ledger)
        write_rows(on/'graph-poses.jsonl', path)
        # The full original candidates remain sealed at source; don't duplicate 76k events.
        summary = {k:diagnostic[k] for k in ('options','loop_counts','optimization','changed','loop_rejection','switch_counts')}
        summary['submaps'] = [{k:s[k] for k in ('id','local_pose','global_pose','members','interval')} for s in diagnostic['submaps']]
        dump(on/'graph-diagnostics.json', summary)
        print(case, 'switches', diagnostic['switch_counts'], flush=True)
    grid = rebuild('r3', ledger)
    if path:
        grid.odom._predictor.px[0] = path[-1]['pose']
    if resume_evidence:
        assert load(on/'grid.json')==json.loads(json.dumps(grid.export()))
    else:
        dump(on/'grid.json', grid.export())
    evidence = build_evidence(ledger, robot_id='r3', wall_evidence='tsdf_weight_v1')
    dump(on/'wall-evidence.json', evidence)
    # Existing text has geometry only. Module F export remains gated.
    (on/'llm.txt').write_text(grid.text().replace('drift uncorrected','own submap graph; drift uncertain')+'\n')
    dump(output/'prediction.json', dict(
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        preregistration='20409ff7', case=case, source_cache=str(source),
        resumed_evidence_only=resume_evidence,
        graph_source_sha=load(output/'host-error.json')['source_sha'] if resume_evidence else subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        cache_receipts={name:sha(source/name) for name in ('prediction.json','baseline-prediction.json')},
        options=dict(loop_rejection='switchable_v1', wall_evidence='tsdf_weight_v1'),
        source_options=load(source/'prediction.json')['options'],
        off_golden={name:sha(off/name) for name in golden},
        input_scope='sealed own frontend and identical loop candidates; no GT; no motion fitting',
        hashes={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    assert 'mujoco' not in sys.modules
    print(case, 'prediction sealed', flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('case', choices=('forward','reverse'))
    p.add_argument('--resume-evidence', action='store_true')
    args=p.parse_args()
    predict(args.case, resume_evidence=args.resume_evidence)
