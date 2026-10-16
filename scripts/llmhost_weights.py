"""Mac -> CPU gcp2 streamed staging: no HF tokens, URL credentials or GPU on VM.

Each 8 MiB chunk is hashed on Mac before transfer. The receiver checks each chunk
and the complete upstream-pinned SHA before atomic publication. A disconnected
transfer remains .part; reruns refuse to overwrite completed destinations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from urllib.request import Request, urlopen

from scripts.llmhost_common import digest, settings, write_json

# Framing: one JSON header per file/chunk, followed by exactly n binary bytes.
# Only this receiver program is copied; authentication stays in the Mac HTTPS client.
RECEIVER = r'''
import contextlib,hashlib,json,os,pathlib,sys,time
root=pathlib.Path(sys.argv[1]); root.mkdir(parents=True,exist_ok=True)
lease=pathlib.Path('/home/ugrp/ugrp-sim/leases/llmhost-stage.json')
lease.parent.mkdir(parents=True,exist_ok=True)
with lease.open('x') as f:
 json.dump(dict(task='llmhost-stage',pid=os.getpid(),started_unix=time.time(),expected_end_unix=time.time()+28800),f)
stream=sys.stdin.buffer
try:
 while True:
  line=stream.readline()
  if not line: break
  meta=json.loads(line); target=root/meta['path']
  if not target.resolve().is_relative_to(root.resolve()): raise ValueError('path_escape')
  reuse=target.exists()
  if reuse:
   old=hashlib.sha256()
   with target.open('rb') as f:
    while data:=f.read(8*1024**2): old.update(data)
   if target.stat().st_size!=meta['bytes'] or old.hexdigest()!=meta['sha256']: raise ValueError('existing_destination_hash')
  target.parent.mkdir(parents=True,exist_ok=True)
  part=target.with_name(target.name+'.part'); total=0; full=hashlib.sha256()
  with (contextlib.nullcontext(None) if reuse else part.open('wb')) as f:
   while True:
    header=json.loads(stream.readline())
    if header['n']==0: break
    chunk=stream.read(header['n'])
    if len(chunk)!=header['n'] or hashlib.sha256(chunk).hexdigest()!=header['sha256']: raise ValueError('chunk_hash')
    if f is not None: f.write(chunk)
    full.update(chunk); total+=len(chunk)
  if total!=meta['bytes'] or full.hexdigest()!=meta['sha256']: raise ValueError('whole_file_hash')
  if not reuse: part.rename(target)
  print(json.dumps(dict(path=meta['path'],bytes=total,sha256=full.hexdigest())),flush=True)
finally:
 lease.unlink()
'''


def stage(candidate, output, *, token=None):
    cfg = settings(); model = cfg['models'][candidate]
    destination = f"{cfg['remote_root']}/models/{candidate}/{model['revision']}"
    # 50 GiB free reserve is the documented GCP disk budget, not a control constant.
    free = int(subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'gcp2',
        "python3 -c 'import shutil; print(shutil.disk_usage(\"/home/ugrp/ugrp-sim\").free)'"], text=True))
    if free < sum(f['bytes'] for f in model['files']) + 50 * 1024**3:
        raise ValueError('gcp2_disk_reserve_50GiB')
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    receiver = RECEIVER.replace('llmhost-stage.json', f'llmhost-stage-{candidate}.json')
    command = shlex.join(['python3', '-u', '-c', receiver, destination])
    with (output / 'remote-verified.jsonl').open('w') as received:
        proc = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', 'gcp2', command],
                                stdin=subprocess.PIPE, stdout=received)
        rows = []
        try:
            for item in model['files']:
                url = f"https://huggingface.co/{model['repo']}/resolve/{model['revision']}/{item['path']}"
                # Optional gated access: token read on Mac only, never argv or manifest.
                req = Request(url, headers={'Authorization': 'Bearer ' + token} if token else {})
                whole = hashlib.sha256(); size = 0; chunks = []
                proc.stdin.write(json.dumps(item).encode() + b'\n')
                with urlopen(req, timeout=180) as source:
                    while chunk := source.read(8 * 1024**2):
                        sha = digest(chunk); whole.update(chunk); size += len(chunk); chunks.append(sha)
                        proc.stdin.write(json.dumps({'n': len(chunk), 'sha256': sha}).encode() + b'\n')
                        proc.stdin.write(chunk)
                if size != item['bytes'] or whole.hexdigest() != item['sha256']:
                    raise ValueError('mac_whole_file_hash')
                proc.stdin.write(b'{"n":0}\n'); proc.stdin.flush()
                rows.append(dict(item, chunk_sha256=chunks))
                write_json(output / 'mac-verified.json', dict(candidate=candidate,
                    repo=model['repo'], revision=model['revision'], destination='gcp2:' + destination,
                    completed=False, files=rows))
            proc.stdin.close()
            if proc.wait() != 0:
                raise ValueError('remote_verification_failed')
        except BaseException:
            if not proc.stdin.closed:
                try: proc.stdin.close()
                except BrokenPipeError: pass
            proc.wait(timeout=30)
            write_json(output / 'failure.json', dict(status='HOST_ERROR',
                reason_category='transfer_or_hash_failure', completed=False,
                blocked_object='not_applicable_weight_transfer', minimum_gap='not_measured_weight_transfer'))
            raise
    remote = [json.loads(line) for line in (output / 'remote-verified.jsonl').read_text().splitlines()]
    if remote != [{k: v for k, v in f.items() if k in ('path', 'bytes', 'sha256')} for f in rows]:
        raise ValueError('receiver_manifest_mismatch')
    write_json(output / 'manifest.json', dict(candidate=candidate, repo=model['repo'],
        revision=model['revision'], destination='gcp2:' + destination, completed=True,
        credentials_transferred=False, files=rows))
    print(json.dumps(dict(candidate=candidate, completed=True, bytes=sum(f['bytes'] for f in rows))))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate', choices=settings()['models'])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--stage', action='store_true', help='CPU gcp2 only; no GPU start')
    p.add_argument('--gated', action='store_true', help='read existing HF login on Mac only; never write it to VM')
    a = p.parse_args()
    if a.stage:
        # HF stored-token access is deliberately optional and Mac-only.
        token = None
        if a.gated:
            from huggingface_hub import get_token
            token = get_token()
            if not token: raise ValueError('Mac_HF_login_required')
        stage(a.candidate, a.output, token=token)
    else:
        write_json(a.output, settings()['models'][a.candidate])


if __name__ == '__main__': main()
