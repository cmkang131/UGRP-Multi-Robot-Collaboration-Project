"""Relocate verified Oracle delivery metadata for native TensorBoard; no replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(run, output, evaluation_name='evaluation'):
    output.mkdir(parents=True, exist_ok=False)
    interrupted = run / 'interruption-record.json'
    if interrupted.exists():
        record = json.loads(interrupted.read_text())
        for rel, digest in record['source_hashes'].items():
            assert sha(run / rel) == digest, rel
        view = dict(derived_view_only=True, source_sha=record['source_sha'],
            case=run.name, policy='Oracle infrastructure interruption',
            host='oracle-a1', status=record['status'],
            physical_success=None, evaluation=record,
            offline_source=dict(path=str(interrupted), sha256=sha(interrupted)),
            offline_scalar_scope='Confirmed reboot interruption; no completed physical outcome or timing',
            offline_scalars={'offline/infrastructure_interruptions': 1})
    else:
        report = run / evaluation_name / 'report.json'
        evaluation = json.loads(report.read_text())
        view = json.loads((run / 'delivery/result.json').read_text())
        assert view['offline_source']['sha256'] == sha(report)
        manifest = json.loads((run / 'raw/artifacts.sha256.json').read_text())
        for rel, digest in manifest.items():
            assert sha(run / 'raw' / rel) == digest, rel
        video = run / 'delivery/execution.mp4'
        assert sha(video) == view['video']['sha256']
        os.link(video, output / 'execution.mp4')
        view['video']['path'] = str(output / 'execution.mp4')
        view['offline_source']['path'] = str(report)
        view.update(host='oracle-a1', case=run.name,
            condition=evaluation['alignment_entry'],
            policy='Oracle staged own RGB; ' + evaluation['stage_scope'])
        view['offline_scalars']['offline/infrastructure_interruptions'] = 0
        view['offline_scalars']['offline/physical_stops'] = int(evaluation['status'] == 'PHYSICAL_STOP')
        view['provenance_note'] = 'Video overlay off names the unchanged visual_pose_mpc option; alignment_entry is recorded separately.'
    (output / 'result.json').write_text(json.dumps(view, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--evaluation-name', default='evaluation')
    a = p.parse_args()
    for run in a.run:
        build(run.resolve(), (a.output / run.name).resolve(), a.evaluation_name)
