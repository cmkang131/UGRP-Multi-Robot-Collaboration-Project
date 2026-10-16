"""Finite GCP2-only integrity, playback and release packaging; no physics."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from harness.grasp_act_data import read_json, sha256, write_json
from scripts.beamact1_runtime import require_gcp2


def main():
    require_gcp2(training=False)
    root=Path('/home/ugrp/ugrp-sim/ops-reviews/beamact2')
    batch=root/'heldout20-v1'
    lease=Path('/home/ugrp/ugrp-sim/leases/beamact2-postprocess.json')
    assert not lease.exists()
    write_json(lease,dict(task='beamact2-postprocess',pid=os.getpid(),start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='finite hash/playback/package phase'))
    try:
        runs=[]
        for run in sorted(batch.glob('seed-*')):
            if not run.is_dir():continue
            index=run/'SHA256.json'
            if not index.exists():index=index.with_name(index.name+'.zst')
            inventory=read_json(index)
            for rel,expected in inventory.items():
                assert sha256(run/rel)==expected,(run,rel)
            refs=0
            data=subprocess.check_output(['zstd','-qdc',str(run/'student-inputs.jsonl.zst')])
            for line in data.splitlines():
                obs=json.loads(line)
                for frame in obs['rgb']:
                    assert frame['robot_id']==obs['robot_id']
                    assert frame['path'].startswith('rgb/'+obs['robot_id']+'/')
                    assert inventory[frame['path']]==frame['sha256']
                    refs+=1
            runs.append(dict(seed=int(run.name.split('-')[1]),files=len(inventory),bytes=sum((run/f).stat().st_size for f in inventory),rgb_refs=refs,inventory_sha256=sha256(index)))
        assert len(runs)==20
        manifests=[]
        source=Path.cwd()
        for f in sorted((source/'outputs/simulation-runs').glob('*/manifest.json*')):
            d=read_json(f)
            if d['workflow_id']!='beamact2-student':continue
            assert d['exit_code']==0 and not d['inputs_changed_during_run'] and not d['source_changed_during_run'] and not d['finalization_errors']
            manifests.append(dict(path=str(f),sha256=sha256(f),source_sha=d['source']['source_sha'],workflow_version=d['workflow_version'],exit_code=d['exit_code'],source_changed=False,inputs_changed=False))
        assert len(manifests)==20
        write_json(root/'integrity.json',dict(verified=True,raw=str(batch),runs=runs,managed_runs=manifests,total_files=sum(r['files'] for r in runs),total_bytes=sum(r['bytes'] for r in runs),rgb_refs=sum(r['rgb_refs'] for r in runs),scope='all raw inventory files and all own RGB references; command/protocol/contact recount is summary.json'))
        print('integrity verified',flush=True)
        scripts=Path('experiments/2026-10-16-beamact2')
        for seed in (8329001,8329010):
            subprocess.run([sys.executable,str(scripts/'playback.py'),'--run',str(batch/f'seed-{seed}'),'--output',str(root/'playback'/f'seed-{seed}')],check=True)
        subprocess.run([sys.executable,str(scripts/'prepare_release.py'),'--model',str(root/'model-v1'),'--training-summary',str(root/'release-inputs/train/main/summary.json'),'--offline-summary',str(root/'release-inputs/offline-v1/summary.json'),'--evaluation-summary',str(batch/'summary.json'),'--output',str(root/'release-v1')],check=True)
        print('postprocess complete',flush=True)
    finally:
        lease.unlink()


if __name__=='__main__':main()
