#!/usr/bin/env python3
"""From the laptop: run the read-only bring-up check on each robot over SSH and print a table.

    python3 scripts/masterpi_fleet_check.py ugrp1 ugrp2 ugrp3      # SSH host names or aliases
    python3 scripts/masterpi_fleet_check.py --json out.json ugrp1

Nothing moves. Uses your own ~/.ssh/config; no credentials are stored here.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

CHECK = Path(__file__).resolve().parents[1] / 'real_robot' / 'pi_check.py'


def check(host: str, timeout_s: float) -> dict:
    try:
        p = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', f'ConnectTimeout={int(timeout_s)}', host, 'python3', '-'],
                           input=CHECK.read_text(), capture_output=True, text=True, timeout=timeout_s + 30)
    except subprocess.TimeoutExpired:
        return {'host': host, 'reachable': False, 'error': 'timeout'}
    if p.returncode == 255:
        return {'host': host, 'reachable': False, 'error': p.stderr.strip()[-200:]}
    try:
        return {'reachable': True, **json.loads(p.stdout.strip().splitlines()[-1]), 'ssh_host': host}
    except (json.JSONDecodeError, IndexError):
        return {'host': host, 'reachable': True, 'error': (p.stderr or p.stdout).strip()[-300:]}


def row(r: dict) -> list[str]:
    if not r.get('reachable'):
        return [r['host'], 'NO', '', '', '', '', '', r.get('error', '')[:60]]
    if 'battery' not in r:
        return [r.get('ssh_host', r.get('host')), 'yes', '', '', '', '', '', r.get('error', '')[:60]]
    bat = r['battery']
    frame = (r.get('camera') or {}).get('frame') or {}
    busy = [p['cmd'].split()[0].rsplit('/', 1)[-1] + ' ' + ' '.join(p['cmd'].split()[1:2])
            for procs in (r.get('busy') or {}).values() if isinstance(procs, list) for p in procs]
    return [r.get('ssh_host'), 'yes', (r.get('model') or '')[:28],
            f"{bat['mv']} mV" if bat.get('ok') else 'FAIL: ' + bat.get('error', '')[:30],
            'ok ' + 'x'.join(map(str, frame.get('shape') or [])) if frame.get('ok') else 'FAIL: ' + str(frame.get('error', ''))[:30],
            'yes' if r.get('smbus2') else 'no',
            ', '.join(r.get('services') or [])[:40],
            ('busy: ' + '; '.join(busy))[:60] if busy else '']


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('hosts', nargs='+')
    p.add_argument('--timeout', type=float, default=5.0)
    p.add_argument('--json', default=None)
    args = p.parse_args(argv)
    results = [check(h, args.timeout) for h in args.hosts]
    head = ['host', 'ssh', 'model', 'battery', 'camera', 'smbus2', 'vendor services', 'note']
    rows = [head] + [row(r) for r in results]
    widths = [max(len(str(x[i])) for x in rows) for i in range(len(head))]
    for x in rows:
        print('  '.join(str(v).ljust(w) for v, w in zip(x, widths)))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1, ensure_ascii=False))
    return 0 if all(r.get('reachable') and r.get('battery', {}).get('ok') for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
