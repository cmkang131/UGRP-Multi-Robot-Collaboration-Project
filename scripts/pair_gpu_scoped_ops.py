"""Own-session launcher for scoped diagnostics; retains the 5.3 GPU-h watchdog.

This host resource budget is inherited from baseline run_arm.py, separate from
sealed SIM/action limits. It includes time since VM boot and is never extended.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def write(path, record):
    path.write_text(json.dumps(record, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--arm', choices=('arm_s', 'arm_c'), required=True)
    parser.add_argument('--vm-start-utc', required=True)
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.vm_start_utc).timestamp() + 5.3 * 3600
    if time.time() >= deadline:
        raise RuntimeError('HOST_RESOURCE_GPU_BUDGET_CAP before arm launch')
    root = args.root
    name = args.arm.replace('_', '-')
    source = Path('/home/ugrp/ugrp-sim/src/pairact-p5/root')
    session = root.name + '-' + name
    command = ['python3', str(source/'scripts/ugrp_session.py'), 'run', '--min-free-gib', '8',
        session, '--', '/home/ugrp/pairact-p3c2-20261021/venv/bin/python', '-B',
        str(root/'ops/pair_gpu_retry_subset.py'), '--arm', args.arm, '--out', str(root/name), '--execute']
    env = dict(os.environ, UGRP_SESSION_DIR=str(root/'owned-sessions'), PYTHONDONTWRITEBYTECODE='1')
    started = datetime.now(timezone.utc).isoformat()
    with (root/(name+'.stdout.log')).open('xb') as stdout, (root/(name+'.stderr.log')).open('xb') as stderr:
        process = subprocess.Popen(command, cwd=source, env=env, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr)
        write(root/(name+'.launch.json'), dict(command=command, pid=process.pid, started_utc=started,
              vm_start_utc=args.vm_start_utc, host_resource_deadline_unix=deadline, owned_session=session))
        reason = None
        try:
            while process.poll() is None:
                if time.time() >= deadline:
                    reason = 'HOST_RESOURCE_GPU_BUDGET_CAP'
                    process.send_signal(signal.SIGTERM)
                    break
                time.sleep(15)
            code = process.wait()
        except BaseException:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                process.wait()
            raise
        finally:
            write(root/(name+'.receipt.json'), dict(exit_code=process.returncode,
                started_utc=started, ended_utc=datetime.now(timezone.utc).isoformat(),
                resource_stop_reason=reason))
    raise SystemExit(code or (1 if reason else 0))


if __name__ == '__main__':
    main()
