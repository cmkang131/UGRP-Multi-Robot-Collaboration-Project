"""Own gcp6 immutable delivery verification and lossless JSON archival."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
from datetime import datetime,timezone

ROOT=Path('/home/ugrp/ugrp-sim/runs/warpfit2')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n')


def main():
    if not platform.node().startswith('ugrp-act-l4-gcp6'):raise ValueError('own gcp6 only')
    if (ROOT/'archive-receipt.json').exists():raise ValueError('already archived; never replace receipt')
    managed=[];runs=[];verified=[]
    for round_,expected in ((1,8),(2,8),(3,9)):
        phase=ROOT/f'R{round_}'
        jobs=json.loads((phase/'attempts.json').read_text())
        if len(jobs)!=expected or any(j['status'] not in ('complete','HOST_ERROR') for j in jobs):
            raise ValueError('unfinished queue')
        for job in jobs:
            folder=Path(job['output']);r=json.loads((folder/'result.json').read_text())
            if r['status'] not in ('complete','HOST_ERROR'):raise ValueError('unfinished result')
            original=json.loads((folder/'SHA256.json').read_text())
            for name,value in original.items():
                if sha(folder/name)!=value:raise ValueError('original run hash mismatch: '+str(folder/name))
            verified.append(str(folder/'SHA256.json'))
            mp=Path(str(folder)+'-managed')/'manifest.json';m=json.loads(mp.read_text())
            if m.get('source_changed_during_run') or m.get('inputs_changed_during_run') or m.get('finalization_errors'):
                raise ValueError('managed provenance changed')
            if m.get('status') in ('running','initializing'):raise ValueError('managed record incomplete')
            managed.append(dict(path=str(mp),status=m['status'],source_changed=m.get('source_changed_during_run'),
                inputs_changed=m.get('inputs_changed_during_run'),finalization_errors=m.get('finalization_errors',[])))
            runs.append(dict(path=str(folder),source_sha=r['source_sha'],completed=r['completed'],
                HOST_ERROR=r['HOST_ERROR'],cap_end=r['cap_end'],result_sha256=sha(folder/'result.json')))
    fixtures=json.loads((ROOT/'fixture-hashes.json').read_text())
    for path,value in fixtures.items():
        if sha(ROOT/'fixtures'/path)!=value:raise ValueError('fixture changed after preparation')
    report=ROOT/'analysis-final'
    s=json.loads((report/'summary.json').read_text())
    if s['runs']!=25 or s['completed']+s['HOST_ERROR']!=25:raise ValueError('final analysis incomplete')
    receipt=dict(created_utc=datetime.now(timezone.utc).isoformat(),runs=runs,managed=managed,
        original_run_manifests_verified=verified,fixture_files_verified=len(fixtures),metadata_association=[],compressed=[],
        manifest_resolution='original RUN_META hash resolves to RUN_META.before-warpfit2-association.json; compressed logical files resolve through this receipt; final inventory describes stored bytes')
    for r in runs:
        p=Path(r['path'])/'RUN_META.json';old=p.with_name('RUN_META.before-warpfit2-association.json')
        old.write_bytes(p.read_bytes());m=json.loads(p.read_text())
        m.update(pr=562,batch='warpfit2',**{'class':'milestone'},
            note='fixed runtime comparison evidence; not teacher/student/E2E acceptance; original metadata preserved')
        dump(p,m);receipt['metadata_association'].append(dict(file=str(p),before_sha256=sha(old),after_sha256=sha(p)))
    dump(ROOT/'RUN_META.json',dict(schema='ugrp.run_meta.v1',**{'class':'milestone'},pr=562,
        branch='codex/warpfit',sha=runs[0]['source_sha'],batch='warpfit2',active=False))
    dump(ROOT/'archive-receipt.json',receipt)
    # Approved project disk policy: >64KiB JSON is compressed without loss;
    # verify restored SHA and persist the mapping BEFORE unlinking logical bytes.
    for p in sorted(ROOT.rglob('*')):
        if p.is_symlink():raise ValueError('symlink in own output root')
        if not p.is_file() or p.suffix not in ('.json','.jsonl') or p.stat().st_size<=65536 or p.name=='archive-receipt.json':continue
        before=sha(p);size=p.stat().st_size;packed=Path(str(p)+'.zst')
        if not packed.exists():subprocess.run(['zstd','-q','-3','-T1',str(p),'-o',str(packed)],check=True)
        restored=subprocess.check_output(['zstd','-q','-dc',str(packed)])
        if hashlib.sha256(restored).hexdigest()!=before:raise ValueError('restore mismatch')
        receipt['compressed'].append(dict(file=str(p.relative_to(ROOT)),sha256=before,bytes=size,
            archive=str(packed.relative_to(ROOT)),archive_sha256=sha(packed),archive_bytes=packed.stat().st_size,
            restored_sha256_verified=True))
        dump(ROOT/'archive-receipt.json',receipt)
        if sha(p)!=before:raise ValueError('source changed before compression')
        p.unlink()
    if (ROOT/'archive-receipt.json').stat().st_size>65536:
        p=ROOT/'archive-receipt.json';payload=p.read_bytes();packed=ROOT/'archive-receipt-full.json.zst'
        packed.write_bytes(subprocess.check_output(['zstd','-q','-3','-c'],input=payload))
        if subprocess.check_output(['zstd','-q','-dc',str(packed)])!=payload:raise ValueError('receipt restore mismatch')
        dump(p,dict(details_file=packed.name,archive_sha256=sha(packed),logical_sha256=hashlib.sha256(payload).hexdigest(),
            compressed=len(receipt['compressed']),original_run_manifests_verified=len(verified)))
    inventory={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=sha(p))
               for p in sorted(ROOT.rglob('*')) if p.is_file()}
    payload=(json.dumps(inventory,sort_keys=True)+'\n').encode()
    packed=ROOT/'final-inventory.json.zst'
    packed.write_bytes(subprocess.check_output(['zstd','-q','-3','-c'],input=payload))
    if subprocess.check_output(['zstd','-q','-dc',str(packed)])!=payload:raise ValueError('inventory restore mismatch')
    bad=[k for k,v in inventory.items() if sha(ROOT/k)!=v['sha256']]
    if bad:raise ValueError('final inventory mismatch')
    delivery=Path('/home/ugrp/ugrp-sim/ops-reviews/warpfit2-delivery');delivery.mkdir(exist_ok=True)
    dump(delivery/'final-inventory-verification.json',dict(files=len(inventory),bytes=sum(v['bytes'] for v in inventory.values()),
        mismatches=bad,inventory_sha256=sha(packed),inventory_bytes=packed.stat().st_size,
        original_run_manifests_verified=len(verified),managed_records=len(managed),
        source_or_input_changes=0,compressed=len(receipt['compressed']),raw=str(ROOT),
        backup_scope='persistent gcp6 disk only; selected summaries and playback retrieved to Mac'))
    print(json.dumps(dict(files=len(inventory),compressed=len(receipt['compressed']),mismatches=0)))


if __name__=='__main__':main()
