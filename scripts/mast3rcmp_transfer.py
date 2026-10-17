"""Read-only gcp5 -> Mac pipe -> gcp4 transfer of allowlisted own RGB only.

No credentials or frame files are written on Mac. Does not start either VM.
The shared manifest itself is supplied locally after checking the ops-alert SHA.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def transfer(manifest,expected,source_host,destination_host,destination_root):
    b=Path(manifest).read_bytes()
    if hashlib.sha256(b).hexdigest()!=expected:raise ValueError('manifest_sha256_mismatch')
    data=json.loads(b);root=Path(data['recording_root'])
    selected=[]
    for f in data['files']:
        path=Path(f['path'])
        if path.name.startswith('r1-') and path.suffix in ('.png','.jpg'):
            if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(root):
                raise ValueError('source_path_outside_recording_root')
            selected.append(f)
    if len(selected)!=data['frames']:raise ValueError('own_frame_denominator_mismatch')
    dest=Path(destination_root)
    if not dest.is_absolute() or '..' in dest.parts:raise ValueError('invalid_destination')
    command='tar -cf - -C / --null -T -'
    source=subprocess.Popen(['ssh',source_host,command],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    sink=subprocess.Popen(['ssh',destination_host,'mkdir -p '+shlex.quote(str(dest))+' && tar -xf - -C '+shlex.quote(str(dest))],stdin=source.stdout)
    source.stdout.close()
    source.stdin.write(b'\0'.join(f['path'].lstrip('/').encode() for f in selected)+b'\0')
    source.stdin.close()
    rc=source.wait();sink.wait()
    if rc or sink.returncode:raise RuntimeError(f'transfer_failed:{rc}:{sink.returncode}')
    code='import sys,json,hashlib,pathlib; files=json.load(sys.stdin); root=pathlib.Path('+repr(str(dest))+'); bad=[f["path"] for f in files if hashlib.sha256((root/f["path"].lstrip("/")).read_bytes()).hexdigest()!=f["sha256"]]; print(json.dumps(dict(files=len(files),mismatches=bad))); assert not bad'
    result=subprocess.run(['ssh',destination_host,'python3 -c '+shlex.quote(code)],input=json.dumps(selected),capture_output=True,text=True,check=True)
    return dict(sender_manifest_sha256=expected,source=source_host,destination=destination_host,
        destination_root=str(dest),via='Mac pipe; no frame files saved on Mac',verification=json.loads(result.stdout),
        excluded_files=[f['path'] for f in data['files'] if f not in selected])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','manifest-sha256','destination-root','receipt'):p.add_argument('--'+name,required=True)
    p.add_argument('--source-host',default='gcp5');p.add_argument('--destination-host',default='gcp4')
    a=p.parse_args();result=transfer(a.manifest,a.manifest_sha256,a.source_host,a.destination_host,a.destination_root)
    with Path(a.receipt).open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['verification']))
