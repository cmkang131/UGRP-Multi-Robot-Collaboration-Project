"""Finite five-minute warp1 dependency watch; metadata only, no simulation."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
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
        if code:
            continue
        code, paths, error = git('ls-tree', '-r', '--name-only', head, '--', 'sim/', 'scripts/', 'harness/')
        backend = [p for p in paths.splitlines() if 'warp' in p.lower() and p.endswith('.py')]
        methods, bases = {}, {}
        for path in backend:
            code, source, error = git('show', head+':'+path)
            if code:
                continue
            tree = ast.parse(source)
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    methods[path+':'+node.name] = [n.name for n in node.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    bases[path+':'+node.name] = [path+':'+b.id for b in node.bases
                                               if isinstance(b, ast.Name)]
            functions = [n.name for n in tree.body
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if functions:
                methods[path+':<module>'] = functions
        def inherited(name, seen=None):
            seen = set() if seen is None else seen
            if name in seen:
                return set()
            seen.add(name)
            result = set(methods.get(name, ()))
            for base in bases.get(name, ()):
                result |= inherited(base, seen)
            return result
        # Metadata trigger only, not runtime admission. A teacher-only transport
        # used to trigger the old watcher despite having no reset API.
        reset_classes = [name for name in methods
                         if {'reset', 'step'} <= inherited(name)]
        commits.append({'ref': ref, 'sha': head, 'backend_paths': backend,
                        'class_methods': methods, 'reset_step_classes': reset_classes})
    return {'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'signal': bool(alerts or any(c['reset_step_classes'] for c in commits)),
            'runtime_admitted': False, 'alerts': alerts[-3:], 'commits': commits}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--once', action='store_true')
    p.add_argument('--deadline-utc', help='Absolute restart deadline; cannot extend the eight-hour bound')
    p.add_argument('--output', type=Path, default=ROOT/'outputs/rl1/warp-watch.jsonl')
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    # User-authorized dependency wait: five-minute checks, at most eight hours.
    limit = 8*3600
    if args.deadline_utc:
        limit = min(limit, max(0., (dt.datetime.fromisoformat(args.deadline_utc) -
                    dt.datetime.now(dt.timezone.utc)).total_seconds()))
    deadline = started + limit
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
        # Shared local refs reveal committed updates without fetching or mutating
        # another task's worktree. Any remote ref already fetched is also checked.


if __name__ == '__main__':
    raise SystemExit(main())
