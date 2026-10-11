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
import hashlib

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
    if host == 'azure':
        fetch_lifecycle()
    return str(target)


def fetch_lifecycle():
    target = PRIMARY / 'outputs/azure-lifecycle'
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(['rsync', '-ac', 'azure:~/ugrp-sim/lifecycle/', str(target) + '/'], check=True)
    differences = subprocess.check_output(['rsync', '-anc', '--out-format=%n',
        'azure:~/ugrp-sim/lifecycle/', str(target) + '/'], text=True)
    if differences.strip():
        raise RuntimeError('Lifecycle record changed during Mac checksum verification; retry retrieval')
    return str(target)


def finish_lease(host, name, lease, archived, detached=False):
    if host != 'azure' or archived:
        ssh(host, f'rm -f {lease}')
    elif not detached:
        # Refresh and retain the lease even on fetch/SSH/archive exceptions.
        try:
            ssh(host, f'touch {lease}')
        except subprocess.CalledProcessError:
            pass
        target = PRIMARY / 'outputs/azure-lifecycle/pending'
        target.mkdir(parents=True, exist_ok=True)
        from scripts.azure_shutdown import write_json
        write_json(target / (name + '.json'), {'run': name, 'archive': 'pending',
                   'raw': f'azure:~/ugrp-sim/runs/{name}', 'lease': 'retained', 'retry': 'next_start'})
    if host == 'azure' and not detached:
        # azctl also refuses EXIT-only evidence and failed/stale archival leases.
        subprocess.run([sys.executable, str(Path(__file__).with_name('azctl.py')), 'stop'], check=True)


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
    if host == 'azure':
        ssh(host, 'python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py admit')
    ssh(host, f'mkdir -p ~/ugrp-sim/leases && test ! -e {root} && touch {lease}')
    archived = False
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
        metadata = {'class': args.run_class, 'pr': args.pr, 'branch': branch, 'sha': sha, 'batch': name}
        if host == 'azure':
            metadata['runner_assets'] = {module: hashlib.sha256(Path(__file__).with_name(module).read_bytes()).hexdigest()
                                         for module in ('remote_run_finish.py', 'azure_shutdown.py')}
            checks = ' && '.join(f'test "$(sha256sum /usr/local/lib/ugrp-storage/scripts/{module} | cut -d " " -f1)" = {digest}'
                                 for module, digest in metadata['runner_assets'].items())
            ssh(host, checks)
        metadata = json.dumps(metadata)
        # The shell wrapper and command use shlex.quote; $()/backticks stay literal.
        run_command = shlex.join(command)
        if host == 'azure':
            finish = f'exec python3 /usr/local/lib/ugrp-storage/scripts/remote_run_finish.py --source "$HOME/ugrp-sim/src/{sha}" --run "$HOME/ugrp-sim/runs/{name}" -- {run_command}'
        else:
            # Keep older committed Oracle controller sources compatible.
            finish = f'''/usr/bin/time -f 'wall=%e cpu=%U+%S' {run_command} > "$HOME/ugrp-sim/runs/{name}/log.txt" 2>&1
result=$?
python3 scripts/remote_run_finish.py --source "$HOME/ugrp-sim/src/{sha}" --run "$HOME/ugrp-sim/runs/{name}" > "$HOME/ugrp-sim/runs/{name}/record-copy.log" 2>&1
record_result=$?
if [ "$record_result" -ne 0 ]; then
  echo "$result" > "$HOME/ugrp-sim/runs/{name}/COMMAND_EXIT"
  result=70
fi
echo "$result" > "$HOME/ugrp-sim/runs/{name}/EXIT"
find "$HOME/ugrp-sim/runs/{name}" -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$HOME/ugrp-sim/runs/{name}/SHA256SUMS"'''
        script = f'''#!/bin/bash
set -u
export MUJOCO_GL=osmesa OMP_NUM_THREADS=1 LP_NUM_THREADS={int(os.environ.get('LP_NUM_THREADS', '4'))}
cd "$HOME/ugrp-sim/src/{sha}"
mkdir -p outputs
ln -s "$HOME/ugrp-sim/runs/{name}" "outputs/{name}"
{finish}
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
            fetch_lifecycle()
            if state:
                print('Exit:', state, 'fetch-lite:', fetch(host, name), flush=True)
                break
            time.sleep(30)
        else:
            raise RuntimeError('Runner deadline exceeded; eight-hour VM guard remains active')
        # The archive script requires genuine 20-minute source quiescence.
        archive_deadline = time.monotonic() + 35 * 60
        while time.monotonic() < archive_deadline:
            try:
                ssh(host, f'touch {lease}; UGRP_RUNS=$HOME/ugrp-sim/runs UGRP_ARCHIVE=$HOME/ugrp-sim/arm /usr/local/bin/ugrp-auto-archive')
            except subprocess.CalledProcessError:
                print('ARM archive failed; lease retained, retrying', flush=True)
                try:
                    fetch_lifecycle()
                except (subprocess.CalledProcessError, RuntimeError):
                    pass
                time.sleep(30)
                continue
            result = ssh(host, f'test ! -L {root} || readlink {root}', capture_output=True, text=True).stdout.strip()
            if not result:
                # Recovery archives retain local originals and publish a separate marker.
                marker = ssh(host, f'test ! -f $HOME/ugrp-sim/lifecycle/archives/{name}.json || cat $HOME/ugrp-sim/lifecycle/archives/{name}.json',
                             capture_output=True, text=True).stdout.strip()
                if marker:
                    result = json.loads(marker)['path']
            fetch_lifecycle()
            if result:
                archived = True
                print('ARM archive:', result, flush=True)
                print('Final fetch-lite:', fetch(host, name), flush=True)
                break
            time.sleep(30)
        else:
            raise RuntimeError('Archive incomplete; raw preserved on persistent Azure disk')
    finally:
        finish_lease(host, name, lease, archived, args.detach)
    if state != '0':
        raise RuntimeError(f'Remote command failed with EXIT={state}; evidence archived and VM lifecycle completed')


if __name__ == '__main__':
    main()
