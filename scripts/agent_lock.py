#!/usr/bin/env python3
"""Exclusive host lock for timing-sensitive physics and training runs.

Several agents (Claude, Codex) share one Mac. Realtime native runs and wall-time
benchmarks are distorted by concurrent simulation or training, so such runs hold
this lock and other agents do not start new physics/training while it is held.
The lock is a directory created atomically under the primary checkout's
``outputs/agent-locks``; nothing here stops or signals another process.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

DEFAULT_ROOT = Path('/Users/changmin/projects/ugrp/outputs/agent-locks')


def _alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def status(root: Path, name: str = 'physics') -> dict | None:
    path = root / name / 'owner.json'
    if not path.is_file():
        return None
    owner = json.loads(path.read_text())
    owner.setdefault('timing_sensitive', False)
    owner['pid_alive'] = _alive(owner.get('pid'))
    return owner


def acquire(root: Path, *, owner: str, branch: str, purpose: str, pid: int,
            expected_minutes: float, name: str = 'physics', timing_sensitive: bool = False) -> dict:
    if name.startswith('sim-'):
        if timing_sensitive:
            raise RuntimeError('SIM slots cannot be timing-sensitive')
        return acquire_sim_slot(root, slot=name, owner=owner, branch=branch, purpose=purpose,
                                pid=pid, expected_minutes=expected_minutes)
    with _admission(root):
        if timing_sensitive and sim_holders(root):
            raise RuntimeError('SIM slots held; timing-sensitive lock unavailable')
        return _acquire(root, owner=owner, branch=branch, purpose=purpose, pid=pid,
                        expected_minutes=expected_minutes, name=name, timing_sensitive=timing_sensitive)


@contextmanager
def _admission(root):
    """Serialize admission only, not runs. flock is released even after a crash."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.admission.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _slot_name(slot):
    if not re.fullmatch(r'sim-[A-Za-z0-9][A-Za-z0-9_.-]*', slot):
        raise RuntimeError('SIM slot must be a safe name starting with sim-')
    return slot


def sim_holders(root):
    """Include dead/incomplete holders: explicit stale release is still required."""
    result = []
    for path in sorted(root.glob('sim-*')):
        if path.is_dir():
            result.append({'name': path.name, **(status(root, path.name) or {'incomplete': True})})
    return result


def sim_snapshot(root):
    """Read a coherent holder list without creating files in check-only plans."""
    try:
        stream = (root / '.admission.lock').open('r')
    except FileNotFoundError:
        return _sim_snapshot(root)  # No slot can exist before first admission.
    with stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        try:
            return _sim_snapshot(root)
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _sim_snapshot(root):
    return {'loadavg': list(os.getloadavg()), 'concurrent_holders': sim_holders(root),
            'physics_holder': status(root)}


def _require_no_timing_lock(root):
    held = status(root)
    if (root / 'physics').exists() and (held is None or held['timing_sensitive']):
        raise RuntimeError('exclusive timing-sensitive physics lock held')


def acquire_sim_slot(root, *, slot, owner, branch, purpose, pid, expected_minutes):
    name = _slot_name(slot)
    with _admission(root):
        _require_no_timing_lock(root)
        return _acquire(root, owner=owner, branch=branch, purpose=purpose, pid=pid,
                        expected_minutes=expected_minutes, name=name)


def require_sim_slot(root, *, slot, owner, branch):
    """Runner admission checks the named live owner and opposing timing lock."""
    with _admission(root):
        _require_no_timing_lock(root)
        held = status(root, _slot_name(slot))
        if not held or not held['pid_alive'] or held['owner'] != owner or held['branch'] != branch:
            raise ValueError('live owned SIM slot for this branch required')
        return _sim_snapshot(root)


def _acquire(root: Path, *, owner: str, branch: str, purpose: str, pid: int,
             expected_minutes: float, name: str = 'physics', timing_sensitive: bool = False) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    lock = root / name
    try:
        lock.mkdir()
    except FileExistsError:
        held = status(root, name)
        raise RuntimeError(f'lock held: {json.dumps(held, ensure_ascii=False)}') from None
    value = {'owner': owner, 'branch': branch, 'purpose': purpose, 'pid': pid,
             'acquired_unix': time.time(), 'expected_end_unix': time.time() + 60 * expected_minutes,
             'loadavg_at_acquire': os.getloadavg(), 'timing_sensitive': timing_sensitive}
    (lock / 'owner.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return value


def release(root: Path, *, owner: str, name: str = 'physics', stale: bool = False) -> dict:
    with _admission(root):
        return _release(root, owner=owner, name=name, stale=stale)


def _release(root: Path, *, owner: str, name: str = 'physics', stale: bool = False) -> dict:
    held = status(root, name)
    if held is None:
        raise RuntimeError('lock is not held')
    if held['owner'] != owner and not (stale and not held['pid_alive']):
        raise RuntimeError('only the owner may release; --stale requires a dead recorded pid')
    record = root / 'released.jsonl'
    with record.open('a') as stream:
        stream.write(json.dumps({**held, 'released_by': owner, 'released_unix': time.time(),
                                 'stale_release': bool(stale)}, ensure_ascii=False) + '\n')
    shutil.rmtree(root / name)
    return held


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    show = sub.add_parser('status')
    show.add_argument('--sim-slot', help='named v91 non-exclusive slot')
    show.add_argument('--sim-slots', action='store_true', help='all SIM holders and load average')
    get = sub.add_parser('acquire')
    get.add_argument('--owner', required=True, help='agent name, e.g. claude, codex or kiro')
    get.add_argument('--branch', required=True)
    get.add_argument('--purpose', required=True)
    get.add_argument('--pid', type=int, required=True, help='long-running driver PID that owns the runs')
    get.add_argument('--expected-minutes', type=float, required=True)
    get.add_argument('--timing-sensitive', action='store_true', help='warn concurrent offline tests about wall-time measurements')
    get.add_argument('--sim-slot', help='named v91 non-exclusive slot, e.g. sim-codex-corridor')
    put = sub.add_parser('release')
    put.add_argument('--owner', required=True)
    put.add_argument('--stale', action='store_true', help='release another owner only if its recorded pid is dead')
    put.add_argument('--sim-slot', help='release only this named SIM slot')
    args = parser.parse_args(argv)
    try:
        if args.command == 'status':
            value = (sim_snapshot(args.root) if args.sim_slots else
                     status(args.root, _slot_name(args.sim_slot) if args.sim_slot else 'physics'))
        elif args.command == 'acquire':
            if args.sim_slot:
                if args.timing_sensitive:
                    raise RuntimeError('SIM slots cannot be timing-sensitive')
                value = acquire_sim_slot(args.root, slot=args.sim_slot, owner=args.owner,
                    branch=args.branch, purpose=args.purpose, pid=args.pid,
                    expected_minutes=args.expected_minutes)
            else:
                value = acquire(args.root, owner=args.owner, branch=args.branch, purpose=args.purpose,
                                pid=args.pid, expected_minutes=args.expected_minutes,
                                timing_sensitive=args.timing_sensitive)
        else:
            value = release(args.root, owner=args.owner, stale=args.stale,
                            name=_slot_name(args.sim_slot) if args.sim_slot else 'physics')
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
