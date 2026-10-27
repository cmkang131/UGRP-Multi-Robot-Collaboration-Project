"""Preserve this closed study on ARM; original execution-disk data stays put."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts import storage_common

SOURCE = '/home/ugrp/ugrp-sim/runs/baseline-resume-20261027T1936Z'
SEALED = '519723dcdaff812373da9628e8d13a23a119b742217fba5856e1d20d073e9507'
# User-approved ARM retention floor, AGENTS.md/docs/disk_management.md 2026-10-11.
ARM_FLOOR = 25 * 2**30


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ssh-config', type=Path, required=True)
    parser.add_argument('--records', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    assert not args.destination.exists(), 'never overwrite an existing archive'
    args.destination.parent.mkdir(parents=True,exist_ok=True)
    ssh = ['ssh','-F',str(args.ssh_config),'gcp6-baseline']
    remote = f'''from pathlib import Path
import sys,json,os,hashlib,subprocess,datetime
sys.path.insert(0,'/home/ugrp/ugrp-sim/src/pairact-p5/root')
from scripts import storage_common as m
r=Path({SOURCE!r});assert (r/'EXIT').read_text().strip()=='0'
assert hashlib.sha256((r/'RUN_META.json').read_bytes()).hexdigest()=={SEALED!r}
assert json.loads((r/'STUDY_CLOSED.json').read_text())['status']=='ALL_COHORTS_NORMAL_COMPLETE'
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
rows=[]
for p in m.files(r):
 before=m.snapshot(p);sha=m.sha256(p);assert m.snapshot(p)==before
 rows.append({{'path':p.relative_to(r).as_posix(),'bytes':before[2],'sha256':sha,'source_snapshot':before}})
links=[]
for base,dirs,names in os.walk(r,followlinks=False):
 for name in dirs+names:
  p=Path(base)/name
  if p.is_symlink():links.append({{'path':p.relative_to(r).as_posix(),'target':os.readlink(p)}})
print(json.dumps({{'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':str(r),'RUN_META_sha256':{SEALED!r},'files':rows,'symlinks':links}}))
'''
    raw = subprocess.check_output(ssh+[shlex.join(['python3','-B','-c',remote])])
    inventory = json.loads(raw)
    manifest = args.records/'study-final-source-inventory.json'
    with manifest.open('xb') as stream: stream.write(raw)
    size = sum(item['bytes'] for item in inventory['files'])
    stat = os.statvfs(args.destination.parent)
    free = stat.f_bavail*stat.f_frsize
    assert free-size >= ARM_FLOOR, 'ARM projected free below approved25GiB floor'
    incoming = args.destination.with_name('.incoming-'+args.destination.name+'-'+str(os.getpid()))
    incoming.mkdir(mode=0o750)
    command = ['rsync','-a','--no-owner','--no-group','-e',shlex.join(ssh[:-1]),
               'gcp6-baseline:'+SOURCE+'/',str(incoming)+'/']
    subprocess.run(command,check=True)
    expected = {item['path']:item for item in inventory['files']}
    actual = {path.relative_to(incoming).as_posix():path for path in storage_common.files(incoming)}
    assert actual.keys()==expected.keys(), 'archive file inventory mismatch'
    for name,path in actual.items():
        item=expected[name]
        assert path.stat().st_size==item['bytes'] and storage_common.sha256(path)==item['sha256'], name
    for item in inventory['symlinks']:
        path=incoming/item['path']
        assert path.is_symlink() and os.readlink(path)==item['target']
    verify = subprocess.run(['rsync','-anc','--no-owner','--no-group','--out-format=%i %n%L',
        '-e',shlex.join(ssh[:-1]),'gcp6-baseline:'+SOURCE+'/',str(incoming)+'/'],
        capture_output=True,text=True,check=True)
    assert not verify.stdout.strip(), 'source/archive checksum diff: '+verify.stdout
    assert not args.destination.exists()
    incoming.rename(args.destination)
    proof={'schema':'ugrp.baseline.verified-archive.v1',
        'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source':SOURCE,'source_host':'ugrp-act-l4-gcp6/asia-northeast1-c/id2102818194467198298',
        'archive':str(args.destination),'source_originals_retained':True,
        'verified_files':len(expected),'verified_symlinks':len(inventory['symlinks']),
        'verified_bytes':size,'sha256_every_regular_file':'PASS','rsync_checksum_diff':'empty',
        'source_inventory':str(manifest),'source_inventory_sha256':hashlib.sha256(raw).hexdigest(),
        'ARM_free_before':free,'ARM_projected_free_after':free-size,'ARM_floor':ARM_FLOOR,
        'sealed_RUN_META_sha256':SEALED}
    with (args.records/'study-archive-verification.json').open('x') as stream: json.dump(proof,stream,indent=2)
    print(json.dumps(proof,indent=2))


if __name__ == '__main__':
    main()
