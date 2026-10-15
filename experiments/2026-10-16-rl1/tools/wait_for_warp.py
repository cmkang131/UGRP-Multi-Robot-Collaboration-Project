"""Finite five-minute warp1 dependency watch; metadata only, no simulation."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
INITIAL = '142dbf04c2128c3d7ca1c3ceb03ee3b651d9a7e5'
ALERT = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/ops-alert.md')


def git(*args):
    p = subprocess.run(['git', '-C', str(ROOT), *args], text=True,
                       capture_output=True, timeout=45)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def inspect():
    lines = ALERT.read_text().splitlines() if ALERT.exists() else []
    alerts = [line for line in lines if line.startswith('warp1:') or ' warp1:' in line]
    commits = []
    for ref in ('claude/warp-act', 'origin/claude/warp-act'):
        code, head, _ = git('rev-parse', '--verify', ref)
        if code or head == INITIAL:
            continue
        code, paths, error = git('diff', '--name-only', INITIAL, head, '--', 'sim/', 'scripts/', 'harness/')
        backend = [p for p in paths.splitlines() if 'warp' in p.lower() and p.endswith('.py')]
        if backend:
            commits.append({'ref': ref, 'sha': head, 'backend_paths': backend})
    return {'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'signal': bool(alerts or commits), 'alerts': alerts[-3:], 'commits': commits}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--once', action='store_true')
    p.add_argument('--output', type=Path, default=ROOT/'outputs/rl1/warp-watch.jsonl')
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    # User-authorized dependency wait: five-minute checks, at most eight hours.
    deadline = started + 8*3600
    check = 0
    while True:
        row = inspect()
        row.update(check=check, elapsed_s=time.monotonic()-started,
                   max_wait_s=8*3600, poll_interval_s=300)
        with args.output.open('a') as f:
            f.write(json.dumps(row, ensure_ascii=False)+'\n')
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if row['signal'] or args.once:
            return 0
        if time.monotonic() >= deadline:
            return 2
        next_check = min(started+(check+1)*300, deadline)
        while time.monotonic() < next_check:
            time.sleep(min(30, next_check-time.monotonic()))
        check += 1
        # Fetch only the named dependency, never change another worktree.
        code, _, error = git('fetch', 'origin', 'refs/heads/claude/warp-act:refs/remotes/origin/claude/warp-act')
        if code:
            print(json.dumps({'fetch_error': error, 'check': check}), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
