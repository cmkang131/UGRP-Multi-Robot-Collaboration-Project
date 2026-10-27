"""SIGINT only this diagnostic's verified runner for host-resource exhaustion.

Original runner/guard finalizers can close logs; actors are closed by their
original owner. Never signal a process name, all GPU clients, or another task.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal

ROOT = Path('/home/ugrp/ugrp-sim/runs/pair-gpu-scoped-20261027')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=('arm_s', 'arm_c'), required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    name = args.arm.replace('_', '-')
    if (ROOT/(name+'.receipt.json')).exists():
        print(json.dumps(dict(status='already_exited', receipt=str(ROOT/(name+'.receipt.json')))))
        return
    launch = json.loads((ROOT/(name+'.launch.json')).read_text())
    expected_session = ROOT.name+'-'+name
    if launch['owned_session'] != expected_session:
        raise RuntimeError('owned session mismatch')
    parent = int(launch['pid'])
    parent_args = (Path('/proc')/str(parent)/'cmdline').read_bytes().split(b'\0')
    if not any(arg.endswith(b'/ugrp_session.py') for arg in parent_args) or expected_session.encode() not in parent_args:
        raise RuntimeError('owned session parent identity mismatch')
    children = (Path('/proc')/str(parent)/'task'/str(parent)/'children').read_text().split()
    matches = []
    for child in children:
        proc = Path('/proc')/child
        argv = proc.joinpath('cmdline').read_bytes().decode().rstrip('\0').split('\0')
        if str(ROOT/'ops/pair_gpu_retry_subset.py') in argv:
            if argv[argv.index('--arm')+1] != args.arm or argv[argv.index('--out')+1] != str(ROOT/name):
                raise RuntimeError('owned runner arguments mismatch')
            if proc.stat().st_uid != os.getuid():
                raise RuntimeError('owned runner uid mismatch')
            matches.append((int(child), argv))
    if len(matches) != 1:
        raise RuntimeError('exactly one owned runner required: '+str(matches))
    pid, argv = matches[0]
    event = dict(reason='HOST_RESOURCE_ESTIMATED_GLOBAL_GPU_BUDGET', arm=args.arm,
        utc=datetime.now(timezone.utc).isoformat(), session=expected_session,
        parent_pid=parent, runner_pid=pid, command=argv, signal='SIGINT', execute=args.execute)
    if args.execute:
        # pidfd pins the process identity across a concurrent exit/PID reuse.
        fd = os.pidfd_open(pid)
        try:
            with (ROOT/(name+'.host-resource-stop.json')).open('x') as stream:
                json.dump(event, stream, indent=2)
            signal.pidfd_send_signal(fd, signal.SIGINT)
        finally:
            os.close(fd)
    print(json.dumps(event, indent=2))


if __name__ == '__main__':
    main()
