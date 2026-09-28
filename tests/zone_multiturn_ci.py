"""Opt-in CI sharding and timing for the model/physics-free multiturn suite.

Each seeded test keeps its original parameters. Sorted seeds of each test
family are partitioned into contiguous ranges; unseeded cases run once too.
Load explicitly with ``-p tests.zone_multiturn_ci`` (never global conftest).
"""
from collections import defaultdict
import json
from pathlib import Path
import socket
import sys
import time

import pytest


def shard_assignments(cases, count):
    """Return one owner per (family, integer seed or None), in input order."""
    if count < 1:
        raise ValueError('shard count must be positive')
    seeds = defaultdict(set)
    for family, seed in cases:
        if seed is not None:
            if type(seed) is not int:
                raise ValueError('seed must be an integer')
            seeds[family].add(seed)
    owners = {family: {seed: rank * count // len(values)
                      for rank, seed in enumerate(sorted(values))}
              for family, values in seeds.items()}
    unseeded = 0
    result = []
    for family, seed in cases:
        if seed is None:
            result.append(unseeded % count)
            unseeded += 1
        else:
            result.append(owners[family][seed])
    return result


def pytest_addoption(parser):
    group = parser.getgroup('multiturn CI')
    group.addoption('--multiturn-shard', help='zero-based INDEX/COUNT; omitted runs every case')
    group.addoption('--multiturn-report', help='JSON with selected IDs and per-test phase costs')


def pytest_configure(config):
    value = config.getoption('--multiturn-shard')
    try:
        index, count = map(int, value.split('/')) if value else (0, 1)
        if not 0 <= index < count:
            raise ValueError
    except ValueError as error:
        raise pytest.UsageError('--multiturn-shard must be INDEX/COUNT with 0 <= INDEX < COUNT') from error
    config._multiturn_timing = {
        'shard': index, 'count': count, 'started': time.perf_counter(),
        'selected': [], 'tests': {},
    }
    # Apply before collection/module-scoped fixtures as well as test calls.
    guard = pytest.MonkeyPatch()
    guard.setitem(sys.modules, 'mujoco', None)
    def forbidden(*args, **kwargs):
        raise AssertionError('network/model calls forbidden in multiturn CI')
    guard.setattr(socket.socket, 'connect', forbidden)
    guard.setattr(socket.socket, 'connect_ex', forbidden)
    config.add_cleanup(guard.undo)


def pytest_collection_modifyitems(config, items):
    state = config._multiturn_timing
    cases = [(f'{item.path.name}::{item.originalname}',
              getattr(item, 'callspec', None).params.get('seed')
              if hasattr(item, 'callspec') else None) for item in items]
    owners = shard_assignments(cases, state['count'])
    selected, excluded = [], []
    for item, owner in zip(items, owners):
        (selected if owner == state['shard'] else excluded).append(item)
    state['total_collected'] = len(items)
    state['selected'] = [item.nodeid for item in selected]
    items[:] = selected
    config.hook.pytest_deselected(items=excluded)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    row = item.config._multiturn_timing['tests'].setdefault(item.nodeid, {})
    row[report.when] = {'seconds': report.duration, 'outcome': report.outcome}


def pytest_sessionfinish(session, exitstatus):
    state = session.config._multiturn_timing
    state['elapsed_s'] = time.perf_counter() - state.pop('started')
    state['exit_code'] = int(exitstatus)
    target = session.config.getoption('--multiturn-report')
    if target:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2) + '\n')
