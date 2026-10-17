"""Recompute the native teacher gate from original evaluation samples on L4.

The frozen teacher Score, physical thresholds and command-completion condition
are reused verbatim. This is retrospective scoring, with no physics or render.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

from act16w_runtime import frozen_source, require_gcp2, sha256

ROOT = Path(__file__).resolve().parents[1]
T = Path('/home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e')


def original(path, *, lines=False):
    actual = path if path.exists() else path.with_name(path.name+'.zst')
    raw = actual.read_bytes() if actual.suffix != '.zst' else subprocess.check_output(['zstd', '-dc', str(actual)])
    value = [json.loads(line) for line in raw.splitlines() if line.strip()] if lines else json.loads(raw)
    return value, dict(path=str(actual), sha256=sha256(actual))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    host, source = require_gcp2(training=True), frozen_source(ROOT)
    frozen_source(T, '6f057f7e97c1a3aec9e8c398b8d9068e27b25df8')
    sys.path.insert(0, str(T))
    from sim.grasp_act_solo_evaluation import Score
    gate = json.loads((a.run/'gate-recount.json').read_text())
    if not gate['complete'] or gate['N'] != 40 or gate['contact_profile'] != 'warp_native_contact_v1':
        raise ValueError('all40 completed native originals required before independent score audit')
    rows, receipts, manifest_files = [], [], 0
    for folder in sorted(a.run.glob('group-*/controller')):
        summary = json.loads((folder/'summary.json').read_text())
        for name, digest in summary['sha256'].items():
            path = folder/name
            if not path.is_file() or sha256(path) != digest:
                raise ValueError('original native manifest mismatch '+str(path))
            manifest_files += 1
        for world in sorted(folder.glob('world-*')):
            if not world.is_dir():
                continue
            result, result_receipt = original(world/'result.json')
            samples, receipt = original(world/'eval-only.jsonl', lines=True)
            plan = json.loads((world/'plan.json').read_text())
            score = Score(); n_samples = 0
            keys = ('min_z', 'support_z', 'tilt_deg', 'finger_forces', 'speed',
                    'open_issued', 'placement_offset', 'weld_active')
            for sample in samples:
                if 'min_z' not in sample:
                    continue
                score.add(sample['t'], **{key: sample[key] for key in keys}); n_samples += 1
            command_complete = result['teacher']['command_result'] == 'command_complete'
            recalculated = score.record(command_complete)
            if not n_samples or any(result[key] != value for key, value in recalculated.items()):
                raise ValueError('native raw Score differs from original result '+str(plan['seed']))
            success = (result['status'] == 'complete' and recalculated['physical_success']
                and not result['cap_end'] and result['training_rgb'] is False
                and all(result['input_audit'][key] == 0 for key in ('invisible_measurements', 'held_world_reads')))
            rows.append(dict(seed=plan['seed'], kind=plan['kind'], success=success,
                evaluation_samples=n_samples, raw_score_matches=True, **recalculated,
                original_result=result_receipt, evaluation_ledger=receipt))
            receipts.append(receipt)
    if len(rows) != 40 or len({row['seed'] for row in rows}) != 40:
        raise ValueError('unique independent40 denominator changed')
    n = sum(row['success'] for row in rows)
    if n != gate['n']:
        raise ValueError('independent native count differs from dispatcher')
    report = {**gate, 'independent_score_audit': dict(source_sha=source, host=host,
        n=n, N=40, original_score_matches=40, manifest_files_verified=manifest_files,
        evaluator_source_sha256=sha256(T/'sim/grasp_act_solo_evaluation.py'),
        raw_evaluation_receipts=receipts, rows=rows, teacher_library='6f057f7e',
        original_dispatcher_recount=dict(path=str(a.run/'gate-recount.json'),sha256=sha256(a.run/'gate-recount.json')),
        kinds={kind: dict(n=sum(row['success'] for row in rows if row['kind'] == kind),
                         N=sum(row['kind'] == kind for row in rows)) for kind in ('cyan','red','green','yellow')},
        scope='raw native evaluation Score and every closed controller manifest verified; no new teacher rollout or physics')}
    with a.out.open('x') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(n=n, N=40, raw_scores_match=40, manifest_files=manifest_files,
        kind_counts=dict(Counter(row['kind'] for row in rows)), out=str(a.out))))


if __name__ == '__main__':
    main()
