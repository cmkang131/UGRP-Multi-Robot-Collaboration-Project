"""V91 SIM-time slots under one non-timing-sensitive physics coordinator.

The frozen agent_lock module is intentionally unchanged. On an empty host the
first slot reserves its legacy physics directory; subsequent slots must belong
to the same owner and live coordinator PID. That PID must outlive every worker.
An existing non-timing lock may be borrowed only by its owner/coordinator and
is never released here. Do not release physics or stale-clean the coordinator
with the legacy tool until all its workers have exited. No wall-time benchmarks.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

from scripts import agent_lock as legacy


@contextmanager
def _admission(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.v91-admission.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _slot_name(slot):
    if not re.fullmatch(r'sim-[A-Za-z0-9][A-Za-z0-9_.-]*', slot):
        raise RuntimeError('SIM slot must be a safe name starting with sim-')
    return slot


def _status(root, name='physics'):
    # The frozen legacy writer publishes directly to owner.json after mkdir.
    # Its directory already excludes contenders even while JSON is incomplete.
    try:
        return legacy.status(root, name)
    except (json.JSONDecodeError, UnicodeDecodeError, FileNotFoundError) as exc:
        raise RuntimeError(f'lock owner metadata incomplete or unreadable: {name}') from exc


def sim_holders(root):
    """Dead/incomplete slots remain visible until explicit recovery."""
    return [{'name': path.name, **(_status(root, path.name) or {'incomplete': True})}
            for path in sorted(root.glob('sim-*')) if path.is_dir()]


def _snapshot(root):
    return {'loadavg': list(os.getloadavg()), 'concurrent_holders': sim_holders(root),
            'physics_holder': _status(root)}


def sim_snapshot(root):
    """Check-only plans do not create any files."""
    try:
        stream = (root / '.v91-admission.lock').open('r')
    except FileNotFoundError:
        return _snapshot(root)
    with stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        try:
            return _snapshot(root)
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _identity(held):
    return {key: held.get(key) for key in ('owner', 'pid', 'acquired_unix', 'v91_group')}


def _require_physics(root, owner, pid=None):
    held = _status(root)
    if (not held or not held['pid_alive'] or held['timing_sensitive']
            or held['owner'] != owner):
        raise RuntimeError('live same-owner non-timing-sensitive physics coordinator required')
    if pid is not None and held['pid'] != pid:
        raise RuntimeError('SIM slots must share the physics coordinator PID')
    return held


def _write_owner(root, name, value):
    target = root / name / 'owner.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(target)


def _acquire(root, *, name, owner, branch, purpose, pid, expected_minutes):
    # Keep legacy mkdir arbitration, but publish complete JSON atomically so an
    # unmodified legacy contender cannot observe our empty/partial owner file.
    try:
        (root / name).mkdir()
    except FileExistsError:
        raise RuntimeError(f'lock held: {name}') from None
    value = {'owner': owner, 'branch': branch, 'purpose': purpose, 'pid': pid,
             'acquired_unix': time.time(), 'expected_end_unix': time.time() + 60 * expected_minutes,
             'loadavg_at_acquire': os.getloadavg(), 'timing_sensitive': False}
    _write_owner(root, name, value)
    return value


def acquire_sim_slot(root, *, slot, owner, branch, purpose, pid, expected_minutes):
    name = _slot_name(slot)
    with _admission(root):
        if not legacy._alive(pid):
            raise RuntimeError('live coordinator PID required')
        holders = sim_holders(root)
        if (root / name).exists():
            raise RuntimeError('SIM slot held; explicit release required')
        if not (root / 'physics').exists():
            if holders:
                raise RuntimeError('orphan SIM slots held; explicit recovery required')
            held = _acquire(root, name='physics', owner=owner, branch=branch, purpose=purpose,
                            pid=pid, expected_minutes=expected_minutes)
            held['v91_group'] = uuid.uuid4().hex
            _write_owner(root, 'physics', held)
        held = _require_physics(root, owner, pid)
        for other in holders:
            if (not other.get('pid_alive') or other.get('physics_identity') != _identity(held)):
                raise RuntimeError('stale or foreign SIM slot held; explicit recovery required')
        value = _acquire(root, name=name, owner=owner, branch=branch, purpose=purpose,
                         pid=pid, expected_minutes=expected_minutes)
        value['physics_identity'] = _identity(held)
        _write_owner(root, name, value)
        return value


def require_sim_slot(root, *, slot, owner, branch):
    with _admission(root):
        slot_record = _status(root, _slot_name(slot))
        if (not slot_record or not slot_record['pid_alive']
                or slot_record['owner'] != owner or slot_record['branch'] != branch):
            raise ValueError('live owned SIM slot for this branch required')
        physics = _require_physics(root, owner, slot_record['pid'])
        if slot_record.get('physics_identity') != _identity(physics):
            raise RuntimeError('physics coordinator replaced since slot admission')
        return _snapshot(root)


def release(root, *, owner, name, stale=False):
    name = _slot_name(name)
    with _admission(root):
        held = _status(root, name)
        if stale and held and held['pid_alive']:
            raise RuntimeError('--stale requires a dead recorded pid')
        released = legacy.release(root, owner=owner, name=name, stale=stale)
        physics = _status(root)
        # Never release a borrowed, replaced or incomplete physics lock.
        if (not sim_holders(root) and physics and physics.get('v91_group')
                and released.get('physics_identity') == _identity(physics)):
            legacy.release(root, owner=owner, stale=stale)
        return released


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=legacy.DEFAULT_ROOT)
    sub = p.add_subparsers(dest='command', required=True)
    show = sub.add_parser('status')
    show.add_argument('--sim-slot')
    get = sub.add_parser('acquire')
    get.add_argument('--sim-slot', required=True)
    get.add_argument('--owner', required=True)
    get.add_argument('--branch', required=True)
    get.add_argument('--purpose', required=True)
    get.add_argument('--pid', required=True, type=int, help='coordinator PID shared by all slots')
    get.add_argument('--expected-minutes', required=True, type=float)
    put = sub.add_parser('release')
    put.add_argument('--sim-slot', required=True)
    put.add_argument('--owner', required=True)
    put.add_argument('--stale', action='store_true')
    args = p.parse_args(argv)
    try:
        if args.command == 'status':
            result = (_status(args.root, _slot_name(args.sim_slot)) if args.sim_slot
                      else sim_snapshot(args.root))
        elif args.command == 'acquire':
            result = acquire_sim_slot(args.root, slot=args.sim_slot, owner=args.owner,
                branch=args.branch, purpose=args.purpose, pid=args.pid,
                expected_minutes=args.expected_minutes)
        else:
            result = release(args.root, owner=args.owner, name=args.sim_slot, stale=args.stale)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
