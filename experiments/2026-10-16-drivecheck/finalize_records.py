"""Preserve diagnostic evidence metadata and hash every payload file, Linux only."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import subprocess


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,required=True);p.add_argument('--payload',action='store_true');a=p.parse_args()
    if platform.system()!='Linux' or platform.node().split('.')[0] not in ('ugrp-sim-gcp2','ugrp-act-l4-gcp5') or a.raw.name!='drivecheck':raise ValueError('drivecheck Linux evidence only')
    changed=[]
    for result in sorted(a.raw.glob('*/result.json')):
        run=result.parent;r=json.loads(result.read_text())
        if r['status']=='running':raise ValueError('running capture cannot be finalized')
        meta=run/'RUN_META.json'
        if not meta.is_file():continue
        original=run/'RUN_META.capture.json'
        if not original.exists():original.write_bytes(meta.read_bytes())
        manifest=run/'SHA256SUMS.json';capture=run/'SHA256SUMS.capture.json'
        if manifest.is_file() and not capture.exists():capture.write_bytes(manifest.read_bytes())
        value=json.loads(original.read_text());value.update(pr=564,**{'class':'milestone'})
        write(meta,value)
        write(run/'retention-receipt.json',dict(reason='drivecheck root-cause diagnostic evidence; failures and comparisons preserved',
            capture_meta_sha256=digest(original),retained_meta_sha256=digest(meta),payload_arrays_changed=False))
        write(manifest,{str(f.relative_to(run)):digest(f) for f in sorted(run.rglob('*')) if f.is_file() and f!=manifest})
        changed.append(run.name)
    if a.payload:
        files={str(f.relative_to(a.raw)):dict(sha256=digest(f),bytes=f.stat().st_size) for f in sorted(a.raw.rglob('*'))
            if f.is_file() and not f.name.startswith('payload-')}
        manifest=a.raw/'payload-manifest.json';write(manifest,files);raw=manifest.read_bytes()
        receipt=dict(files=len(files),bytes=sum(r['bytes'] for r in files.values()),uncompressed_sha256=hashlib.sha256(raw).hexdigest())
        if len(raw)>65536:
            subprocess.run(['zstd','-q','-f',str(manifest)],check=True)
            if subprocess.check_output(['zstd','-dc',str(manifest)+'.zst'])!=raw:raise ValueError('manifest compression round trip')
            manifest.unlink();receipt.update(path=str(manifest)+'.zst',compressed_sha256=digest(Path(str(manifest)+'.zst')),decompression_verified=True)
        else:receipt.update(path=str(manifest),decompression_verified='not_compressed')
        write(a.raw/'payload-receipt.json',receipt)
    print(json.dumps(dict(retained_runs=changed,payload=a.payload)))


if __name__=='__main__':main()
