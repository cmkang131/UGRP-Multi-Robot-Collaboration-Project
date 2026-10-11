"""Committed-source Oracle/Azure runner, with finite Azure lifecycle by default.

Usage: remote_run.py [--host azure] WORKTREE NAME -- COMMAND [ARGS...]
The historical ORACLE_HOST default (oracle) is preserved. Azure waits, fetches
lite evidence, waits for verified ARM archival, then deallocates when no jobs remain.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

PRIMARY = Path('/Users/changmin/projects/ugrp')


def ssh(host, command, **kwargs):
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                           '--', host, command], check=True, **kwargs)


def fetch(host, name):
    target = PRIMARY / 'outputs' / ('azure-runs' if host == 'azure' else 'oracle-runs') / name
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(['rsync', '-aL', '--exclude=*.png', '--exclude=*.jpg', '--exclude=*.jpeg',
        '--exclude=*.mp4', '--exclude=*.gif', '--exclude=*.npz', '--exclude=*.npy',
        f'{host}:~/ugrp-sim/runs/{name}/', str(target) + '/'], check=True)
    return str(target)


def ship(host, worktree, sha):
    source = f'~/ugrp-sim/src/{sha}'
    exists = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', host, f'test -f {source}/.git/ugrp-source-complete'], capture_output=True)
    if exists.returncode == 0:
        return
    # Single shallow commit, including all its tree objects, preserves real Git SHA
    # without sending account credentials or the repository's history.
    objects = subprocess.check_output(['git', '-C', str(worktree), 'rev-list', '--objects', '--no-walk', sha])
    pack = subprocess.Popen(['git', '-C', str(worktree), 'pack-objects', '--stdout'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    # communicate cannot buffer the pack in memory; object list is small (~1 MiB).
    receiver = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', host,
        f'mkdir -p {source} && cd {source} && git init -q && git index-pack --stdin && '
        f'echo {sha} > .git/shallow && git update-ref HEAD {sha} && git reset --hard {sha} && '
        f'ln -sfn ~/ugrp-sim/ugrp/.venv-sim .venv-sim && echo {sha} > .git/ugrp-source-complete'], stdin=pack.stdout)
    pack.stdout.close()
    pack.stdin.write(objects)
    pack.stdin.close()
    if pack.wait() or receiver.wait():
        raise RuntimeError('Source transfer failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default=os.environ.get('ORACLE_HOST', 'oracle'))
    parser.add_argument('--detach', action='store_true', help='opt out of Azure wait/fetch/archive/stop; guards remain enabled')
    parser.add_argument('--per-run-mb', type=float, default=128)
    parser.add_argument('--pr', type=int)
    parser.add_argument('--class', dest='run_class', choices=('dev', 'milestone', 'study'), default='dev')
    parser.add_argument('first')
    parser.add_argument('name', nargs='?')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    host, name = args.host, args.name
    if host.startswith('-') or not re.fullmatch(r'[A-Za-z0-9_.-]+', host):
        raise ValueError('Invalid host')
    if args.first == 'status':
        ssh(host, "find ~/ugrp-sim/runs -mindepth 1 -maxdepth 2 -name EXIT -print; uptime")
        return
    if not name or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
        raise ValueError('A safe unique run name is required')
    if args.first in ('fetch', 'fetch-lite'):
        print(fetch(host, name))
        return
    if args.first == 'archive':
        ssh(host, 'UGRP_RUNS=$HOME/ugrp-sim/runs UGRP_ARCHIVE=$HOME/ugrp-sim/arm /usr/local/bin/ugrp-auto-archive')
        return
    worktree = Path(args.first).resolve()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        raise ValueError('Command is required')
    if subprocess.check_output(['git', '-C', str(worktree), 'status', '--porcelain']).strip():
        raise RuntimeError('Commit all source changes before execution')
    sha = subprocess.check_output(['git', '-C', str(worktree), 'rev-parse', 'HEAD'], text=True).strip()
    branch = subprocess.check_output(['git', '-C', str(worktree), 'branch', '--show-current'], text=True).strip()
    if host == 'azure':
        subprocess.run([sys.executable, str(Path(__file__).with_name('azctl.py')), 'start'], check=True)
        for attempt in range(12):
            ready = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                host, 'true'], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(5)
        else:
            raise RuntimeError('Azure VM started but SSH did not become ready; automatic guards remain active')
    root = f'$HOME/ugrp-sim/runs/{name}'
    lease = f'$HOME/ugrp-sim/leases/{name}'
    ssh(host, f'mkdir -p ~/ugrp-sim/leases && test ! -e {root} && touch {lease}')
    try:
        for budget_host, budget_ssh, path, estimate in (
            ('x86', host, '~/ugrp-sim/runs', args.per_run_mb),
            ('arm', 'oracle-codex', '~/ugrp-archive/runs', args.per_run_mb),
            ('mac', None, str(PRIMARY), min(args.per_run_mb, 16))):
            call = [sys.executable, str(Path(__file__).with_name('storage_budget.py')), '--host', budget_host,
                '--path', path, '--runs', '1', '--per-run-mb', str(estimate)]
            if budget_ssh:
                call += ['--ssh', budget_ssh]
            subprocess.run(call, check=True)
        ssh(host, "awk '/MemAvailable/{if ($2 < 6291456) exit 1}' /proc/meminfo; cat /proc/loadavg")
        ship(host, worktree, sha)
        metadata = json.dumps({'class': args.run_class, 'pr': args.pr, 'branch': branch, 'sha': sha, 'batch': name})
        # The shell wrapper and command use shlex.quote; $()/backticks stay literal.
        run_command = shlex.join(command)
        script = f'''#!/bin/bash
set -u
export MUJOCO_GL=osmesa OMP_NUM_THREADS=1 LP_NUM_THREADS={int(os.environ.get('LP_NUM_THREADS', '4'))}
cd "$HOME/ugrp-sim/src/{sha}"
mkdir -p outputs
ln -s "$HOME/ugrp-sim/runs/{name}" "outputs/{name}"
/usr/bin/time -f 'wall=%e cpu=%U+%S' {run_command} > "$HOME/ugrp-sim/runs/{name}/log.txt" 2>&1
result=$?
python3 scripts/remote_run_finish.py --source "$HOME/ugrp-sim/src/{sha}" --run "$HOME/ugrp-sim/runs/{name}" > "$HOME/ugrp-sim/runs/{name}/record-copy.log" 2>&1
echo "$result" > "$HOME/ugrp-sim/runs/{name}/EXIT"
find "$HOME/ugrp-sim/runs/{name}" -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$HOME/ugrp-sim/runs/{name}/SHA256SUMS"
'''
        ssh(host, f'mkdir {root} && printf %s {shlex.quote(metadata)} > {root}/RUN_META.json && '
            f'printf %s {sha} > {root}/SOURCE_SHA && printf %s {shlex.quote(run_command)} > {root}/COMMAND && '
            f'printf %s {shlex.quote(script)} > {root}/run_wrapper.sh && '
            f'cat /proc/loadavg > {root}/LOADAVG && '
            f'setsid -f bash {root}/run_wrapper.sh </dev/null >/dev/null 2>&1')
        print(f'Started {name} SHA={sha} host={host}', flush=True)
        if host != 'azure' or args.detach:
            return
        deadline = time.monotonic() + 7.5 * 3600
        while time.monotonic() < deadline:
            state = ssh(host, f'touch {lease}; test ! -f {root}/EXIT || cat {root}/EXIT', capture_output=True, text=True).stdout.strip()
            if state:
                print('Exit:', state, 'fetch-lite:', fetch(host, name), flush=True)
                break
            time.sleep(30)
        else:
            raise RuntimeError('Runner deadline exceeded; eight-hour VM guard remains active')
        # The archive script requires genuine 20-minute source quiescence.
        archive_deadline = time.monotonic() + 35 * 60
        while time.monotonic() < archive_deadline:
            ssh(host, f'touch {lease}; UGRP_RUNS=$HOME/ugrp-sim/runs UGRP_ARCHIVE=$HOME/ugrp-sim/arm /usr/local/bin/ugrp-auto-archive')
            result = ssh(host, f'test ! -L {root} || readlink {root}', capture_output=True, text=True).stdout.strip()
            if result:
                print('ARM archive:', result, flush=True)
                print('Final fetch-lite:', fetch(host, name), flush=True)
                break
            time.sleep(30)
        else:
            raise RuntimeError('Archive incomplete; raw preserved on persistent Azure disk')
    finally:
        ssh(host, f'rm -f {lease}')
        if host == 'azure' and not args.detach:
            subprocess.run([sys.executable, str(Path(__file__).with_name('azctl.py')), 'stop'], check=True)
    if state != '0':
        raise RuntimeError(f'Remote command failed with EXIT={state}; evidence archived and VM lifecycle completed')


if __name__ == '__main__':
    main()
