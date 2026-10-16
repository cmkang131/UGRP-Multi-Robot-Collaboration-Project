"""Finite archive receive + hash verification on CPU gcp2; no credentials."""
import argparse,datetime,hashlib,json,os,sys,tarfile
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);a=p.parse_args()
    base=Path('/home/ugrp/ugrp-sim');out=base/'runs/warp10-gcp4-analysis';raw=out/'raw';raw.mkdir(parents=True,exist_ok=True)
    lease=base/'leases/warp10-analysis.json';claimed=False
    receipt=dict(label=a.label,pid=os.getpid(),started=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_host='gcp4',raw=str(raw))
    try:
        with lease.open('x') as f:json.dump(dict(task='warp10',stage='CPU archive verification',pid=os.getpid(),started_at=receipt['started'],expected_end='finite archive EOF and hash verification',concurrency=0,gpu=False),f)
        claimed=True
        with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
            for member in archive:
                target=raw/member.name
                if target.exists() and not member.isdir():raise ValueError('archive would overwrite '+str(target))
                archive.extract(member,raw,filter='data')
        manifest=raw/f'transfer-{a.label}.json';values=json.loads(manifest.read_text());mismatches=[]
        for name,expected in values['files'].items():
            actual=hashlib.sha256((raw/name).read_bytes()).hexdigest()
            if actual!=expected:mismatches.append(name)
        receipt.update(status='VERIFIED' if not mismatches else 'HASH_MISMATCH',files=len(values['files']),mismatches=mismatches,
            manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
        if mismatches:raise ValueError('transferred bytes changed')
    finally:
        if claimed:
            if json.loads(lease.read_text()).get('pid')!=os.getpid():raise RuntimeError('lease ownership changed')
            lease.unlink()
        receipt['other_leases']=[p.name for p in (base/'leases').glob('*.json')]
        receipt['vm_stop_attempts']=0
        (out/f'receive-{a.label}.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt))
if __name__=='__main__':main()
