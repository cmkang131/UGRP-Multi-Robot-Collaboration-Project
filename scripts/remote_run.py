"""Committed-source Oracle/Azure/GCP runner, with finite Azure/GCP lifecycle by default.

Usage: remote_run.py [--host azure] WORKTREE NAME -- COMMAND [ARGS...]
The historical ORACLE_HOST default (oracle) is preserved. Azure waits, fetches
lite evidence, waits for verified ARM archival, then deallocates when no jobs remain.
--host gcp1 (opt-in, GCP project ugrp-act-train-1014): starts the VM with gcloud, runs, waits,
verifies the VM-side SHA256SUMS, fetches lite evidence to outputs/gcp1-runs, records
outputs/gcp1-lifecycle/<run>.json and stops the VM (disk kept). Raw stays on the persistent
VM disk; there is no ARM archival for GCP yet. Results from different CPUs are never pooled.
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

from scripts.azure_api import AZURE_HOSTS
from scripts.gcpctl import GCP_HOSTS

PRIMARY = Path(os.environ.get('UGRP_REMOTE_LOCAL_ROOT', '/Users/changmin/projects/ugrp')).resolve()


def ssh(host, command, **kwargs):
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                           '--', host, command], check=True, **kwargs)


def fetch(host, name):
    target = PRIMARY / 'outputs' / ((host + '-runs') if host in AZURE_HOSTS or host in GCP_HOSTS else 'oracle-runs') / name
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(['rsync', '-aL', '--exclude=*.png', '--exclude=*.jpg', '--exclude=*.jpeg',
        '--exclude=*.mp4', '--exclude=*.gif', '--exclude=*.npz', '--exclude=*.npy',
        f'{host}:~/ugrp-sim/runs/{name}/', str(target) + '/'], check=True)
    if host in AZURE_HOSTS:
        fetch_lifecycle(host)
    return str(target)


def fetch_lifecycle(host='azure'):
    target = PRIMARY / 'outputs' / (host + '-lifecycle')
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(['rsync', '-ac', f'{host}:~/ugrp-sim/lifecycle/', str(target) + '/'], check=True)
    differences = subprocess.check_output(['rsync', '-anc', '--out-format=%n',
        f'{host}:~/ugrp-sim/lifecycle/', str(target) + '/'], text=True)
    if differences.strip():
        raise RuntimeError('Lifecycle record changed during Mac checksum verification; retry retrieval')
    return str(target)


def finish_lease(host, name, lease, archived, detached=False):
    if host in GCP_HOSTS:
        # archived == SHA256SUMS verified on the VM and lite evidence fetched. Otherwise the lease
        # stays, so gcpctl stop refuses; the VM idle guard and 8 h cap remain the backstops.
        if archived:
            ssh(host, f'rm -f {lease}')
        if not detached:
            subprocess.run([sys.executable, str(Path(__file__).with_name('gcpctl.py')), 'stop', host])  # 75 = deferred, not an error
        return
    if host not in AZURE_HOSTS or archived:
        ssh(host, f'rm -f {lease}')
    elif not detached:
        # Refresh and retain the lease even on fetch/SSH/archive exceptions.
        try:
            ssh(host, f'touch {lease}')
        except subprocess.CalledProcessError:
            pass
        target = PRIMARY / 'outputs' / (host + '-lifecycle') / 'pending'
        target.mkdir(parents=True, exist_ok=True)
        from scripts.azure_shutdown import write_json
        write_json(target / (name + '.json'), {'run': name, 'archive': 'pending',
                   'raw': f'{host}:~/ugrp-sim/runs/{name}', 'lease': 'retained', 'retry': 'next_start'})
    if host in AZURE_HOSTS and not detached:
        # azctl also refuses EXIT-only evidence and failed/stale archival leases.
        subprocess.run([sys.executable, str(Path(__file__).with_name('azctl.py')), 'stop', '--host', host], check=True)


def wait_gcp(host, name, root, lease, sha, started_unix):
    """GCP: wait for EXIT and the finisher, verify SHA256SUMS on the VM, fetch lite, record lifecycle.

    Returns (verified, exit_state). Raw stays on the VM's persistent disk (no ARM archive).
    """
    from scripts.azure_shutdown import write_json
    deadline = time.monotonic() + 7.5 * 3600
    state = ''
    while time.monotonic() < deadline:
        state = ssh(host, f'touch {lease}; test ! -f {root}/EXIT || cat {root}/EXIT', capture_output=True, text=True).stdout.strip()
        if state:
            break
        time.sleep(30)
    else:
        raise RuntimeError('Runner deadline exceeded; eight-hour VM guard remains active')
    # EXIT is written before SHA256SUMS; wait until the wrapper itself has finished.
    for _ in range(120):
        done = subprocess.run(['ssh', '-o', 'BatchMode=yes', host, f'! pgrep -f "{name}/[r]un_wrapper\\.sh" >/dev/null'])
        if done.returncode == 0:
            break
        time.sleep(5)
    verified = subprocess.run(['ssh', '-o', 'BatchMode=yes', host,
                               f'cd {root} && test -s SHA256SUMS && sha256sum -c --quiet SHA256SUMS']).returncode == 0
    fetched = fetch(host, name)
    from scripts.gcpctl import status
    vm_state, _, machine = status(host)
    manifest_sha = ssh(host, f'sha256sum {root}/SHA256SUMS | cut -d " " -f1', capture_output=True, text=True).stdout.strip()
    loadavg = ssh(host, f'cat {root}/LOADAVG', capture_output=True, text=True).stdout.strip()
    target = PRIMARY / 'outputs' / (host + '-lifecycle')
    target.mkdir(parents=True, exist_ok=True)
    write_json(target / (name + '.json'), {
        'run': name, 'host': host, 'machine_type': machine, 'vm_state_at_finish': vm_state, 'source_sha': sha,
        'exit': state, 'sha256sums_verified_on_vm': verified, 'sha256sums_file_sha256': manifest_sha,
        'loadavg_at_start': loadavg, 'started_unix': started_unix, 'finished_unix': time.time(),
        'raw': f'{host}:~/ugrp-sim/runs/{name}', 'fetched_lite': fetched,
        'archive': 'none; raw stays on the GCP persistent disk (no ARM archive for GCP yet)'})
    print('Exit:', state, 'verified:', verified, 'fetch-lite:', fetched, flush=True)
    return verified, state


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
    if host in AZURE_HOSTS:
        subprocess.run([sys.executable, str(Path(__file__).with_name('azctl.py')), 'start', '--host', host], check=True)
        for attempt in range(12):
            ready = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                host, 'true'], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(5)
        else:
            raise RuntimeError('Azure VM started but SSH did not become ready; automatic guards remain active')
    if host in GCP_HOSTS:
        subprocess.run([sys.executable, str(Path(__file__).with_name('gcpctl.py')), 'start', host], check=True)
        for attempt in range(24):
            ready = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                host, 'true'], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(5)
        else:
            raise RuntimeError('GCP VM started but SSH did not become ready; the VM idle guard and 8 h cap remain active')
    started_unix = time.time()
    root = f'$HOME/ugrp-sim/runs/{name}'
    lease = f'$HOME/ugrp-sim/leases/{name}'
    if host in AZURE_HOSTS:
        ssh(host, 'python3 /usr/local/lib/ugrp-storage/scripts/azure_shutdown.py admit')
    ssh(host, f'mkdir -p ~/ugrp-sim/leases && test ! -e {root} && touch {lease}')
    archived = False
    try:
        for budget_host, budget_ssh, path, estimate in (
            ('x86', host, '~/ugrp-sim/runs', args.per_run_mb),
            ('arm', 'oracle-codex', '~/ugrp-archive/runs', args.per_run_mb),
            ('mac', None, str(PRIMARY), min(args.per_run_mb, 16))):
            if host in GCP_HOSTS and budget_host == 'arm':
                continue  # GCP raw stays on the VM's persistent disk; no ARM archive
            call = [sys.executable, str(Path(__file__).with_name('storage_budget.py')), '--host', budget_host,
                '--path', path, '--runs', '1', '--per-run-mb', str(estimate)]
            if budget_ssh:
                call += ['--ssh', budget_ssh]
            subprocess.run(call, check=True)
        ssh(host, "awk '/MemAvailable/{if ($2 < 6291456) exit 1}' /proc/meminfo; cat /proc/loadavg")
        ship(host, worktree, sha)
        metadata = {'class': args.run_class, 'pr': args.pr, 'branch': branch, 'sha': sha, 'batch': name}
        if host in AZURE_HOSTS:
            metadata['runner_assets'] = {module: hashlib.sha256(Path(__file__).with_name(module).read_bytes()).hexdigest()
                                         for module in ('remote_run_finish.py', 'azure_shutdown.py')}
            checks = ' && '.join(f'test "$(sha256sum /usr/local/lib/ugrp-storage/scripts/{module} | cut -d " " -f1)" = {digest}'
                                 for module, digest in metadata['runner_assets'].items())
            ssh(host, checks)
        metadata = json.dumps(metadata)
        # The shell wrapper and command use shlex.quote; $()/backticks stay literal.
        run_command = shlex.join(command)
        if host in GCP_HOSTS:
            # Same committed finisher as the Oracle path; bash builtin time (no GNU time package needed).
            finish = f'''TIMEFORMAT='wall=%R cpu=%U+%S'
{{ time {run_command} ; }} > "$HOME/ugrp-sim/runs/{name}/log.txt" 2>&1
result=$?
python3 scripts/remote_run_finish.py --source "$HOME/ugrp-sim/src/{sha}" --run "$HOME/ugrp-sim/runs/{name}" > "$HOME/ugrp-sim/runs/{name}/record-copy.log" 2>&1
record_result=$?
if [ "$record_result" -ne 0 ]; then
  echo "$result" > "$HOME/ugrp-sim/runs/{name}/COMMAND_EXIT"
  result=70
fi
echo "$result" > "$HOME/ugrp-sim/runs/{name}/EXIT"
find "$HOME/ugrp-sim/runs/{name}" -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$HOME/ugrp-sim/runs/{name}/SHA256SUMS"'''
        elif host in AZURE_HOSTS:
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
        if (host not in AZURE_HOSTS and host not in GCP_HOSTS) or args.detach:
            return
        if host in GCP_HOSTS:
            archived, state = wait_gcp(host, name, root, lease, sha, started_unix)
        else:
            deadline = time.monotonic() + 7.5 * 3600
            while time.monotonic() < deadline:
                state = ssh(host, f'touch {lease}; test ! -f {root}/EXIT || cat {root}/EXIT', capture_output=True, text=True).stdout.strip()
                fetch_lifecycle(host)
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
                        fetch_lifecycle(host)
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
                fetch_lifecycle(host)
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
