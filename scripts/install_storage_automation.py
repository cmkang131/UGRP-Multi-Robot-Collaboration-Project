#!/usr/bin/env python3
"""Install Mac coordinator and (optionally) ARM tools; never contacts Azure/x86."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tarfile
import tempfile
import time

TOOLS = ['storage_automation.py', 'storage_common.py', 'storage_budget.py',
         'evidence_prune.py', 'compress_json_traces.py', 'worktree_guard.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-arm', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    destination = Path.home() / 'Library/Application Support/ugrp-storage-tools'
    destination.mkdir(parents=True, exist_ok=True)
    tag = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    backup = destination / 'backups' / tag
    hashes = {}
    for name in TOOLS:
        src, dst = repo / 'scripts' / name, destination / 'scripts' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and digest(dst) != digest(src):
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup / name)
        shutil.copy2(src, dst)
        assert digest(src) == digest(dst)
        hashes[name] = digest(dst)
    python = shutil.which('python3')
    assert python and shutil.which('gh') and shutil.which('zstd')
    project = Path.home() / 'projects/ugrp'
    logs = project / 'outputs/cleanup-records'
    logs.mkdir(parents=True, exist_ok=True)
    plist = {'Label': 'com.ugrp.storage-auto', 'ProgramArguments': [python,
        str(destination / 'scripts/storage_automation.py'), '--host', 'mac', '--root',
        str(project / 'outputs'), '--records', str(logs), '--execute', '--remote-arm', '--scheduled'],
        'StartCalendarInterval': {'Hour': 4, 'Minute': 15}, 'StartInterval': 300,
        'EnvironmentVariables': {'PATH': os.environ['PATH'], 'UGRP_PROJECT_PATH': str(project)},
        'WorkingDirectory': str(destination), 'ProcessType': 'Background'}
    # No KeepAlive and no unbounded stdout/stderr logs; receipts hold outcomes.
    target = Path.home() / 'Library/LaunchAgents/com.ugrp.storage-auto.plist'
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup / target.name)
    target.write_bytes(plistlib.dumps(plist))
    subprocess.run(['plutil', '-lint', str(target)], check=True)
    if args.install_arm:
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / 'tools.tar'
            with tarfile.open(archive, 'w') as tar:
                for name in TOOLS:
                    tar.add(repo / 'scripts' / name, arcname='scripts/' + name)
            # Only our dedicated tools are backed up/replaced. No server timers/crontab.
            command = ('mkdir -p ~/ugrp-storage-tools/backups/' + tag + '; '
                'cp -a ~/ugrp-storage-tools/scripts ~/ugrp-storage-tools/backups/' + tag + '/; '
                'tar -xf - -C ~/ugrp-storage-tools')
            with archive.open('rb') as stream:
                subprocess.run(['ssh', '-o', 'BatchMode=yes', 'oracle', command], stdin=stream, check=True)
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', 'oracle',
            "python3 -c 'import pathlib,hashlib,json; p=pathlib.Path.home()/\"ugrp-storage-tools/scripts\"; "
            "print(json.dumps({f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob(\"*.py\")}))'"],
            text=True, capture_output=True, check=True)
        remote = json.loads(result.stdout)
        assert all(remote[k] == v for k, v in hashes.items()), 'remote installed hash mismatch'
    label = f'gui/{os.getuid()}/com.ugrp.storage-auto'
    status = subprocess.run(['launchctl', 'print', label], capture_output=True).returncode
    if status == 0:
        subprocess.run(['launchctl', 'bootout', label], check=True)
    subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(target)], check=True)
    (logs / 'INSTALL-storage-auto.json').write_text(json.dumps({
        'schema': 'ugrp.storage-auto-install.v1', 'at': tag, 'mac': str(destination),
        'arm_installed': args.install_arm, 'sha256': hashes, 'plist': str(target)}, indent=2)+'\n')
    print(json.dumps({'installed': str(target), 'arm_verified': args.install_arm, 'sha256': hashes}))

if __name__ == '__main__':
    main()
