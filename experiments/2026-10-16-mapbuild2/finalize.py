"""Archive only this completed run's large JSON, verifying exact restoration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--sources',type=Path,required=True);a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp2'):raise ValueError('GCP2_L4_ONLY')
    base=Path('/home/ugrp/ugrp-sim');root=base/'runs/mapbuild2';out=root/'delivery-extra-v1';out.mkdir(exist_ok=False)
    # Every physics/analysis consumer has finished before archival.
    if any(p.name.startswith('mapbuild2') for p in (base/'leases').glob('*.json')):raise ValueError('OWN_WORK_STILL_LEASED')
    dump(out/'obstacle-evaluation.json',json.loads((root/'obstacle-eval-r3.json').read_text()))
    attempts=json.loads((root/'delivery-v1/attempts.json').read_text())
    attempts[1].update(status='SUPERVISOR_ABORT',exit_code=-15,wall_cap=False,
        reason='latent invalid-range JSON path found by inspection; stopped before wheel stimulus; NaN failure not observed in partial data')
    for name,status,reason in [('obstacle-eval-r1','HOST_ERROR','scorer import collided with pinned renderer scripts package'),
        ('obstacle-eval-r2','HOST_ERROR','relative texture asset unavailable from caller cwd'),
        ('obstacle-eval-r3','COMPLETE','actual reset-cargo positive targets added only to evaluator')]:
        attempts.append(dict(attempt=name,status=status,category='evaluation_attempt',reason=reason,blocked_object=name,
            minimum_gap_m=None,gap_status='not_measured',output_state='not_created' if status=='HOST_ERROR' else 'saved'))
    dump(out/'attempts-final.json',attempts);dump(out/'source-receipt-extra.json',json.loads(a.sources.read_text()))
    own=[]
    for directory in Path('/proc').glob('[0-9]*'):
        if int(directory.name)==os.getpid():continue
        try:args=(directory/'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        if args and b'python' in Path(args[0].decode(errors='replace')).name.encode() and any(
            b'/mapbuild2' in value for value in args[1:]):own.append(int(directory.name))
    dump(out/'lifecycle-end.json',dict(own_python_pids=own,own_leases=[],remaining_leases=[p.name for p in (base/'leases').glob('*.json')],
        vm_stop_attempted=False,shared=True,disk_free_bytes=os.statvfs(base).f_bavail*os.statvfs(base).f_frsize,
        common_git_gc_auto=subprocess.check_output(['git','-C',str(base/'git-shared.git'),'config','--get','gc.auto'],text=True).strip()))
    if own:raise ValueError('OWN_PYTHON_STILL_ACTIVE')
    receipts=[]
    def archive(path):
        raw=path.read_bytes();target=path.with_name(path.name+'.zst')
        if target.exists():raise ValueError('ARCHIVE_ALREADY_EXISTS:'+str(target))
        subprocess.run(['zstd','-q','-3','-T1','-o',str(target),'--',str(path)],check=True)
        restored=subprocess.check_output(['zstd','-q','-d','-c','--',str(target)])
        if restored!=raw:raise ValueError('LOSSLESS_RESTORE_MISMATCH')
        receipts.append(dict(original=str(path.relative_to(root)),original_bytes=len(raw),original_sha256=hashlib.sha256(raw).hexdigest(),
            compressed=str(target.relative_to(root)),compressed_bytes=target.stat().st_size,compressed_sha256=sha(target),restored_sha256_verified=True))
        path.unlink()
    # Project64KiB text rule; no image, npz, source checkout or foreign data is removed.
    for path in sorted(root.rglob('*.json')):
        if path.is_file() and path.stat().st_size>65536:archive(path)
    dump(out/'archive-receipts.json',receipts)
    dump(out/'remote-file-hashes.json',{str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()})
    if (out/'remote-file-hashes.json').stat().st_size>65536:archive(out/'remote-file-hashes.json')
    dump(out/'archive-receipts.json',receipts)
    dump(out/'SHA256SUMS.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(dict(archived_json=len(receipts),restored_mismatch_n=0,delivery=str(out))))


if __name__=='__main__':main()
