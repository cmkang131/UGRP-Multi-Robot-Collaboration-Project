"""Owned-session host watchdog. Frozen policy/runner/action limits stay unchanged."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--arm', choices=('arm_c', 'arm_s'), required=True)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--vm-start-utc', required=True)
    a = p.parse_args()
    root = a.root
    meta_bytes = (root / 'RUN_META.json').read_bytes()
    meta = json.loads(meta_bytes)
    if meta['class'] != 'study' or not meta['execution_preflight_complete']:
        raise SystemExit('sealed study preflight required')
    out = root / a.arm.replace('_', '-')
    if out.exists():
        raise SystemExit('new arm output required')
    vm_start = dt.datetime.fromisoformat(a.vm_start_utc).timestamp()
    # Registered whole new study budget 5.3 GPU-h is stricter than the user's
    # per-arm 5.3 GPU-h and remaining approximate 6.9/20 GPU-h. This is a host
    # resource watchdog, never an action selection or planning wall-time limit.
    budget_deadline = vm_start + 5.3 * 3600
    if time.time() >= budget_deadline:
        raise SystemExit('GPU reservation exhausted before arm launch')
    source = '/home/ugrp/ugrp-sim/src/pairact-p5/root'
    command = ['python3', source + '/scripts/ugrp_session.py', 'run', '--min-free-gib', '8',
        'baseline-20261027-' + a.arm.replace('_', '-'), '--',
        '/home/ugrp/pairact-p3c2-20261021/venv/bin/python', '-B',
        '/home/ugrp/ugrp-sim/baseline-treatment/future_driver.py',
        '--arm', a.arm, '--out', str(out), '--execute']
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['UGRP_SESSION_DIR'] = str(root / 'owned-sessions')
    # Keep the original run's CPU thread settings; no policy or physics tuning.
    for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        env[name] = '1'
    started_utc, started = stamp(), time.monotonic()
    with (root / (a.arm + '.stdout.log')).open('xb') as stdout, \
         (root / (a.arm + '.stderr.log')).open('xb') as stderr:
        process = subprocess.Popen(command, cwd=source, env=env,
                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
        (root / (a.arm + '.launch.json')).write_text(json.dumps({
            'utc': started_utc, 'pid': process.pid, 'command': command,
            'owned_session': 'baseline-20261027-' + a.arm.replace('_', '-'),
            'host_resource_deadline_unix': budget_deadline}, indent=2))
        stop_reason = None
        while process.poll() is None:
            if time.time() >= budget_deadline:
                stop_reason = 'HOST_RESOURCE_GPU_BUDGET_CAP'
                process.send_signal(signal.SIGTERM)
                process.wait()
                break
            if out.is_dir() and not (out / 'RUN_META.json').exists():
                # Exact presealed metadata copy, after the original runner makes
                # its new output directory. The parent was sealed before launch.
                with (out / 'RUN_META.json').open('xb') as stream:
                    stream.write(meta_bytes)
            progress = None
            try:
                progress = json.loads((out / 'progress.json').read_text())
            except (OSError, ValueError):
                pass
            wall = time.monotonic() - started
            watch = {'utc': stamp(), 'arm': a.arm, 'pid': process.pid,
                     'arm_wall_s': wall, 'vm_allocated_wall_s': time.time() - vm_start,
                     'host_resource_deadline_unix': budget_deadline,
                     'progress': progress, 'new_gpu_cap_h': 5.3,
                     'C_9180s_followup_reservations_cancelled': a.arm == 'arm_c' and wall > 9180}
            (root / (a.arm + '.watch.json')).write_text(json.dumps(watch, indent=2))
            time.sleep(15)
        ended = stamp()
    receipt = {'schema': 'ugrp.baseline-arm-receipt.v1', 'arm': a.arm,
               'started_utc': started_utc, 'ended_utc': ended,
               'wall_s': time.monotonic() - started, 'exit_code': process.returncode,
               'resource_stop_reason': stop_reason,
               'administrative_scope': 'Host resource cap only; frozen SIM cap and action selection unchanged'}
    (root / (a.arm + '.receipt.json')).write_text(json.dumps(receipt, indent=2))
    if out.exists():
        (out / 'EXIT').write_text(str(process.returncode) + '\n')
    print(json.dumps(receipt), flush=True)
    raise SystemExit(process.returncode or (1 if stop_reason else 0))


if __name__ == '__main__':
    main()
