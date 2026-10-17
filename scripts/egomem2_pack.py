"""Lossless >64KiB JSON packing for this task only, with original SHA recount.

AGENTS disk rule: verify decompressed SHA before removing the uncompressed
container. Images/videos are retained. Never touches egomem1 or other jobs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from datetime import datetime,timezone

BASE=Path('/home/ugrp/ugrp-sim/ops-reviews/egomem2')
RUNS=Path('/home/ugrp/ugrp-sim/runs/egomem2-round1')


def sha(path, *, decoded=False):
    process=None
    if decoded:
        process=subprocess.Popen(['zstd','-dc',str(path)],stdout=subprocess.PIPE)
        stream=process.stdout
    else:stream=path.open('rb')
    h=hashlib.sha256()
    with stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    if process is not None and process.wait():raise ValueError('DECOMPRESSION_FAILED')
    return h.hexdigest()


def read(path):
    return json.loads(path.read_bytes() if path.exists() else
                      subprocess.check_output(['zstd','-dc',str(path)+'.zst']))


def verify_raw():
    reports=[]
    for i in (1,2):
        raw=RUNS/f'recording{i}'
        if not (raw/'EXIT').is_file():raise ValueError('RECORDING_NOT_CLOSED')
        entries=read(raw/'SHA256SUMS.json')
        for name,expected in entries.items():
            path=raw/name
            actual=sha(path) if path.exists() else sha(Path(str(path)+'.zst'),decoded=True)
            if actual!=expected:raise ValueError('ORIGINAL_CHANGED:'+str(path))
        reports.append(dict(raw=str(raw),original_files_verified=len(entries)))
    return reports


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.execute or not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('EXPLICIT_GCP5_ONLY')
    if a.output.exists():raise ValueError('NEW_MANIFEST_REQUIRED')
    before=verify_raw();packed=[]
    for root in (BASE,RUNS):
        for path in sorted(root.rglob('*')):
            if not path.is_file() or path.is_symlink() or path.suffix not in ('.json','.jsonl') or path.stat().st_size<=64*1024:continue
            original_sha=sha(path);size=path.stat().st_size;archive=Path(str(path)+'.zst')
            if not archive.exists():subprocess.run(['zstd','-q','-T1','-k',str(path),'-o',str(archive)],check=True)
            if sha(archive,decoded=True)!=original_sha:raise ValueError('LOSSLESS_CHECK_FAILED:'+str(path))
            packed.append(dict(original=str(path),original_bytes=size,original_sha256=original_sha,
                               archive=str(archive),archive_bytes=archive.stat().st_size,archive_sha256=sha(archive)))
            path.unlink()
    after=verify_raw()
    result=dict(status='LOSSLESS_VERIFIED',utc=datetime.now(timezone.utc).isoformat(),before=before,after=after,
                packed=packed,raw_bytes=sum(x['original_bytes'] for x in packed),archive_bytes=sum(x['archive_bytes'] for x in packed),
                source_sha256=sha(Path(__file__)),images_removed=0,
                reproduction='Rehydrate only original paths listed in packed with zstd -d -k before replaying the original commands; keep preexisting compressed allowed input in its original format.')
    with a.output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(status=result['status'],files=len(packed),raw_bytes=result['raw_bytes'],archive_bytes=result['archive_bytes'],originals_verified=after)),flush=True)
