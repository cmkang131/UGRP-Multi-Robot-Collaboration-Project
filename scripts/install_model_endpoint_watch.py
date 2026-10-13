#!/usr/bin/env python3
"""Install the hourly Mac LaunchAgent for scripts/model_endpoint_watch.py.

Copies the watcher and configs/model_endpoints.json to
~/Library/Application Support/ugrp-model-watch and writes
~/Library/LaunchAgents/com.ugrp.model-endpoint-watch.plist (no KeepAlive).
Re-run after changing the config. Remove with --uninstall.
"""
import argparse
import hashlib
import plistlib
import shutil
import subprocess
from pathlib import Path

LABEL = 'com.ugrp.model-endpoint-watch'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uninstall', action='store_true')
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[1]
    home = Path.home()
    dest = home / 'Library/Application Support/ugrp-model-watch'
    target = home / f'Library/LaunchAgents/{LABEL}.plist'
    domain = f'gui/{subprocess.run(["id", "-u"], capture_output=True, text=True, check=True).stdout.strip()}'
    subprocess.run(['launchctl', 'bootout', domain, str(target)], check=False, capture_output=True)
    if a.uninstall:
        if target.exists():
            target.unlink()
        print('uninstalled', target)
        return
    pairs = [(repo / 'scripts/model_endpoint_watch.py', dest / 'model_endpoint_watch.py'),
             (repo / 'configs/model_endpoints.json', dest / 'model_endpoints.json')]
    dest.mkdir(parents=True, exist_ok=True)
    for src, dst in pairs:
        shutil.copy2(src, dst)
        assert digest(src) == digest(dst)
    python = shutil.which('python3')
    alerts = home / 'projects/ugrp/outputs/model-endpoint-alerts'
    plist = {'Label': LABEL,
             'ProgramArguments': [python, str(dest / 'model_endpoint_watch.py'), '--config',
                                  str(dest / 'model_endpoints.json'), '--alerts', str(alerts), '--notify'],
             'StartInterval': 3600, 'RunAtLoad': True, 'ProcessType': 'Background',
             'StandardOutPath': str(dest / 'last-run.jsonl'), 'StandardErrorPath': str(dest / 'last-run.err')}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(plistlib.dumps(plist))
    subprocess.run(['plutil', '-lint', str(target)], check=True)
    subprocess.run(['launchctl', 'bootstrap', domain, str(target)], check=True)
    print('installed', target, {d.name: digest(d) for _, d in pairs})


if __name__ == '__main__':
    main()
