"""Lossless compression of completed beamact2 JSON only; no dataset mutation."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    root=Path('/home/ugrp/ugrp-sim/ops-reviews/beamact2')
    gpu=(root/'training-supervisor.json').exists()
    if gpu:assert json.loads((root/'training-supervisor.json').read_text())['status']=='complete'
    else:assert json.loads((root/'heldout20-v1/summary.json').read_text())['complete']
    lease=Path('/home/ugrp/ugrp-sim/leases/beamact2-finalize.json');assert not lease.exists()
    lease.write_text(json.dumps(dict(task='beamact2-finalize',pid=os.getpid(),start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='finite completed-record compression')))
    ledger=root/'lossless-finalization.jsonl'
    try:
        candidates=[f for f in root.rglob('*.json') if f.stat().st_size>65536 and not f.is_symlink()]
        if gpu:
            candidates+=list(Path('/home/ugrp/ugrp-sim/src/ee1e2275b/outputs/simulation-runs').glob('*/manifest.json'))
        rows=[]
        for f in candidates:
            if f.stat().st_size<=65536:continue
            if 'simulation-runs' in f.parts:assert json.loads(f.read_text())['exit_code']==0
            target=f.with_name(f.name+'.zst');assert not target.exists()
            original=digest(f);size=f.stat().st_size
            subprocess.run(['zstd','-q','-3','-T1','-o',str(target),str(f)],check=True)
            restored=subprocess.check_output(['zstd','-qdc',str(target)])
            assert hashlib.sha256(restored).hexdigest()==original and len(restored)==size and digest(f)==original
            row=dict(path=str(f),bytes=size,sha256=original,compressed_path=str(target),compressed_bytes=target.stat().st_size,compressed_sha256=digest(target),verified='decompressed_sha256')
            with ledger.open('a') as out:out.write(json.dumps(row)+'\n');out.flush();os.fsync(out.fileno())
            f.unlink();rows.append(row)
        print(json.dumps(dict(files=len(rows),original_bytes=sum(r['bytes'] for r in rows),compressed_bytes=sum(r['compressed_bytes'] for r in rows))))
    finally:lease.unlink()


if __name__=='__main__':main()
