#!/usr/bin/env python3
"""Check batch storage before submission; print JSON and exit 0/1 (fail closed)."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.storage_common import files, persistent

GIB = 2**30
FLOORS = {'x86': 8, 'arm': 25, 'mac': 20}
ALARMS = {'x86': 8, 'arm': 25, 'mac': 15}
HOSTS = {'x86': ('oracle-x86', '~/ugrp-sim/runs'),
         'arm': ('oracle', '~/ugrp-archive/runs'), 'mac': (None, str(Path.home()))}


def estimate(batch: Path, past_runs: int | None) -> int:
    measured = list(files(batch))
    if not measured:
        raise ValueError('past batch is empty')
    # Recovered archives may already be compressed; estimate original raw peak.
    original_sizes = {}
    for manifest in measured:
        if manifest.name == 'COMPRESSED.jsonl':
            for line in manifest.read_text().splitlines():
                item = json.loads(line)
                original_sizes[manifest.parent / item['compressed_path']] = int(item['bytes'])
    if any(p.name.endswith(('.json.zst', '.jsonl.zst')) and p not in original_sizes for p in measured):
        raise ValueError('compressed past batch lacks original sizes; supply --per-run-mb from raw evidence')
    def size_of(paths):
        return sum(max(p.stat().st_size, original_sizes.get(p, 0)) for p in paths)
    runs = [p.parent for p in measured if p.name == 'RUN_META.json' and (p.parent / 'EXIT').exists()]
    if runs and past_runs is None:
        # Use the largest finished run, not a mean that hides heavy failures.
        size = max(size_of(files(run)) for run in runs)
    else:
        if not past_runs or past_runs < 1:
            raise ValueError('legacy batch needs --past-runs (including failures/HOST_ERROR)')
        if not (batch / 'EXIT').is_file():
            raise ValueError('past batch is not complete (EXIT absent)')
        size = size_of(measured) / past_runs
    return math.ceil(size * 1.25)  # explicit 25% estimate margin


def free_bytes(path: str, ssh: str | None) -> int:
    if ssh:
        if ssh.startswith('-'):
            raise ValueError('invalid SSH host')
        code = ('import os,shutil,subprocess; p=os.path.realpath(os.path.expanduser(' + repr(path) + ')); '
                'assert not any(p==t or p.startswith(t+"/") for t in '
                '("/tmp","/var/tmp","/dev/shm","/run")), "ephemeral evidence location"; '
                'fs=subprocess.check_output(["findmnt","-n","-o","FSTYPE","-T",p],text=True).strip(); '
                'assert fs not in ("tmpfs","ramfs"), "tmpfs evidence location"; '
                'print(shutil.disk_usage(p).free)')
        command = shlex.join(['python3', '-c', code])
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                                 '--', ssh, command], capture_output=True, text=True,
                                check=True, timeout=30)
        return int(result.stdout.strip())
    local = Path(path).expanduser()
    persistent(local)
    return shutil.disk_usage(local).free


def check(host: str, free: int, runs: int, per_run: int, reserved: int = 0, alert=False) -> dict:
    expected = runs * per_run + reserved
    floor = (ALARMS if alert else FLOORS)[host] * GIB
    return {'host': host, 'free_bytes': free, 'expected_bytes': expected,
            'projected_free_bytes': free - expected, 'floor_bytes': floor,
            'ok': free - expected >= floor}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', type=int, default=0)
    p.add_argument('--per-run-mb', type=float, help='MiB; full raw size, before compression')
    p.add_argument('--past-batch', type=Path)
    p.add_argument('--past-runs', type=int)
    p.add_argument('--host', choices=FLOORS)
    p.add_argument('--all-hosts', action='store_true')
    p.add_argument('--ssh', help='remote df-equivalent query over SSH')
    p.add_argument('--path', help='existing directory on the evidence filesystem')
    p.add_argument('--mac-per-run-mb', type=float, help='fetch-lite only; default full estimate (conservative)')
    p.add_argument('--reserved-mb', type=float, default=0, help='remaining output of already admitted jobs (MiB)')
    p.add_argument('--alert-only', action='store_true', help='free-space alarm; no batch')
    p.add_argument('--notify', action='store_true', help='Mac notification on alarm')
    a = p.parse_args(argv)
    try:
        if not a.host and not a.all_hosts:
            raise ValueError('--host or --all-hosts required')
        if a.all_hosts and (a.ssh or a.path):
            raise ValueError('--ssh/--path require one --host')
        for value in (a.per_run_mb, a.mac_per_run_mb, a.reserved_mb):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError('size must be finite and nonnegative')
        if not a.alert_only and a.runs < 1:
            raise ValueError('--runs must be positive')
        if a.alert_only:
            per_run = 0
        elif a.per_run_mb is not None and a.per_run_mb > 0:
            per_run = math.ceil(a.per_run_mb * 2**20)
        elif a.past_batch:
            per_run = estimate(a.past_batch, a.past_runs)
        else:
            raise ValueError('--per-run-mb or --past-batch required')
        rows = []
        for host in (FLOORS if a.all_hosts else [a.host]):
            ssh, path = HOSTS[host] if a.all_hosts else (a.ssh, a.path or str(Path.home()))
            size = math.ceil(a.mac_per_run_mb * 2**20) if host == 'mac' and a.mac_per_run_mb is not None else per_run
            rows.append(check(host, free_bytes(path, ssh), 0 if a.alert_only else a.runs,
                              size, 0 if a.alert_only else math.ceil(a.reserved_mb * 2**20), a.alert_only))
        ok = all(r['ok'] for r in rows)
        print(json.dumps({'schema': 'ugrp.storage-budget.v1', 'ok': ok, 'checks': rows}))
        if not ok:
            print('UGRP STORAGE ALERT: disk floor would be breached; submission refused', file=sys.stderr)
            if a.notify and sys.platform == 'darwin':
                subprocess.run(['osascript', '-e', 'display notification "UGRP 저장 공간 하한 도달. 새 배치 제출 금지." with title "UGRP 저장 공간 경보"'], check=False)
        return 0 if ok else 1
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
