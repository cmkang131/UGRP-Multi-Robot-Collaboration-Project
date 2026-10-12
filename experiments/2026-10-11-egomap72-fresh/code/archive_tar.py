"""Task-only lossless ARM archive; keep Azure originals and verify every member.

A single stream avoids SSHFS per-file round trips. Uses the existing lifecycle
inventory/source-state contracts; no cloud stop or other-run mutation.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import uuid

sys.path.insert(0, '/usr/local/lib/ugrp-storage')
from scripts.azure_shutdown import ROOT, inventory, source_state, run_processes, write_json, active_archive_processes


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_members(path, expected):
    proc=subprocess.Popen(['zstd','-qdc','--',str(path)],stdout=subprocess.PIPE)
    found={}
    try:
        with tarfile.open(fileobj=proc.stdout,mode='r|') as archive:
            for member in archive:
                name=member.name
                if name in found or name not in expected:
                    raise ValueError('unexpected or duplicate archive member: '+name)
                if member.issym():
                    found[name]={'symlink':member.linkname}
                elif member.isfile():
                    with archive.extractfile(member) as data:
                        found[name]={'bytes':member.size,'sha256':hashlib.file_digest(data,'sha256').hexdigest()}
                else:
                    raise ValueError('unsupported member: '+name)
        while proc.stdout.read(2**20):
            pass
        if proc.wait()!=0 or found!=expected:
            raise ValueError('ARM archive member checksum mismatch')
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill();proc.wait()
    return len(found)


def main(name):
    if Path(name).name!=name or not name.startswith('egomap72-'):
        raise ValueError('own egomap72 run required')
    run=ROOT/'runs'/name;arm=ROOT/'arm'
    marker=ROOT/'lifecycle/archives'/(name+'.json')
    if marker.exists():
        raise ValueError('existing archive receipt preserved')
    if not os.path.ismount(arm) or not (run/'EXIT').is_file() or run_processes(run):
        raise ValueError('finished immutable run and mounted ARM required')
    # Same manual archive-one coordination as the installed lifecycle helper.
    # The global lock belongs to scheduled archival/lifecycle, not manual jobs.
    locks=ROOT/'lifecycle/archive-locks';locks.mkdir(parents=True,exist_ok=True)
    with (locks/(name+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if marker.exists() or active_archive_processes(ROOT,run):
            raise ValueError('existing receipt or archive worker preserved')
        before=source_state(run);items=inventory(run)
        size=sum(v.get('bytes',0) for v in items.values())
        if shutil.disk_usage(arm).free-size<25*2**30 or shutil.disk_usage(run).free-size<8*2**30:
            raise ValueError('archive storage reserve')
        staging=ROOT/'packed';staging.mkdir(exist_ok=True)
        packed=staging/(name+'-'+uuid.uuid4().hex+'.tar.zst')
        with packed.open('xb') as out:
            proc=subprocess.Popen(['zstd','-q','-3','-T1','-c'],stdin=subprocess.PIPE,stdout=out)
            try:
                with tarfile.open(fileobj=proc.stdin,mode='w|',dereference=False) as archive:
                    for key in sorted(items):
                        archive.add(run/key,arcname=key,recursive=False)
            finally:
                proc.stdin.close()
            if proc.wait()!=0:raise RuntimeError('tar compression failed')
            out.flush();os.fsync(out.fileno())
        target=arm/('packed-'+name)
        temporary=arm/('.incoming-packed-'+name+'-'+uuid.uuid4().hex)
        if target.exists():raise ValueError('existing archive destination preserved')
        temporary.mkdir()
        destination=temporary/'raw.tar.zst'
        shutil.copyfile(packed,destination)
        with destination.open('rb') as stream:os.fsync(stream.fileno())
        digest=sha(packed)
        if sha(destination)!=digest:raise ValueError('ARM container hash mismatch')
        count=verify_members(destination,items)
        if before!=source_state(run) or items!=inventory(run) or run_processes(run):
            raise ValueError('source changed during archive')
        write_json(temporary/'inventory.json',items)
        temporary.rename(target)
        report=dict(verified=True,path=str(target),archive_kind='tar.zst',archive_file='raw.tar.zst',
            archive_sha256=digest,archive_bytes=packed.stat().st_size,member_count=count,
            inventory=items,source_state=before,originals_removed=False,
            verification='ARM container SHA256 plus every streamed member SHA256 equals local full inventory',
            helper_sha256=sha(Path(__file__)),local_container=str(packed),
            lifecycle_helper_sha256=sha(Path('/usr/local/lib/ugrp-storage/scripts/azure_shutdown.py')),
            lock=str(locks/(name+'.lock')))
        write_json(marker,report)
        print(json.dumps({k:v for k,v in report.items() if k not in ('inventory','source_state')}),flush=True)


if __name__=='__main__':main(sys.argv[1])
