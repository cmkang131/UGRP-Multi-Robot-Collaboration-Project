"""Immediate completed-job archive while the sibling conditions still run.

Send this committed script to the remote Python stdin with group root/job name.
Uses the installed lifecycle inventory/active-writer checks, keeps local files,
and publishes a distinct immutable ARM directory after full SHA-256 comparison.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    sys.path.insert(0,'/usr/local/lib/ugrp-storage')
    from scripts.azure_shutdown import inventory, run_processes, write_json
    root=Path('/home/ugrp/ugrp-sim'); group=root/'runs'/sys.argv[1]
    job=group/'data'/sys.argv[2]
    if (not group.name.startswith('egojump-') or '/' in sys.argv[1] or '/' in sys.argv[2]
            or job.is_symlink() or not (job/'EXIT').is_file() or run_processes(job)):
        raise RuntimeError('COMPLETED_OWN_JOB_REQUIRED')
    marker=group/'per-run-archives'/(job.name+'.json')
    if marker.exists():
        saved=json.loads(marker.read_text())
        if saved['verified'] and saved['inventory']==inventory(job):
            print(json.dumps({k:v for k,v in saved.items() if k!='inventory'}));return
        raise RuntimeError('ARCHIVED_JOB_CHANGED')
    subprocess.run([sys.executable,'/usr/local/lib/ugrp-storage/scripts/compress_json_traces.py',str(job),'--execute'],check=True)
    hashes=inventory(job);size=sum(v.get('bytes',0) for v in hashes.values())
    arm=root/'arm'
    if not arm.is_mount() or shutil.disk_usage(arm).free-size<25*2**30:
        raise RuntimeError('ARM_RESERVE_OR_MOUNT')
    final=arm/(group.name+'-'+job.name);incoming=arm/('.incoming-'+final.name)
    if not final.exists():
        incoming.mkdir(exist_ok=True)
        subprocess.run(['rsync','-ac','--',str(job)+'/',str(incoming)+'/'],check=True)
        if hashes!=inventory(incoming) or hashes!=inventory(job) or run_processes(job):
            raise RuntimeError('ARCHIVE_CHANGED_OR_HASH_MISMATCH')
        incoming.rename(final)
    if hashes!=inventory(final) or hashes!=inventory(job):
        raise RuntimeError('EXISTING_ARCHIVE_MISMATCH')
    report=dict(verified=True,source=str(job),path=str(final),bytes=size,inventory=hashes,
        inventory_sha256=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        preserved_local=True,scope='individual terminated condition; sibling runs not complete')
    write_json(marker,report)
    print(json.dumps({k:v for k,v in report.items() if k!='inventory'}))


if __name__=='__main__':main()
