"""Reproduce D1 role deletions in memory; never edit a pinned source file.

Run from the worktree root with its existing Python 3.12 environment. Each
invocation holds the shared host lock. --before-tests accepts the saved original
62-test module to demonstrate mutation survival before the test repair.
"""
import argparse
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'


class NoPhysics(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'glfw', 'torch', 'openai', 'anthropic', 'google'}:
            raise RuntimeError('T09a static-only boundary: ' + fullname)


def no_network(event, args):
    if event == 'socket.connect':
        raise RuntimeError('T09a tests cannot connect to network')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mutation', choices=['none', 'end_neg', 'end_pos', 'ci_before'], default='none')
    parser.add_argument('--before-tests', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args, pytest_args = parser.parse_known_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sys.meta_path.insert(0, NoPhysics())
    sys.addaudithook(no_network)
    from scripts import agent_lock
    deadline = time.monotonic() + 1200
    next_notice = 0.
    while True:
        try:
            lock = agent_lock.acquire(
                agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/two-door-route-interface',
                purpose='PR314 D1 offline regression/mutation, no physics/render/model',
                pid=os.getpid(), expected_minutes=3)
            break
        except RuntimeError as error:
            if time.monotonic() >= deadline:
                (args.output / 'lock-blocked.txt').write_text(str(error) + '\n')
                return 3
            if time.monotonic() >= next_notice:
                print('Host lock occupied; no tests started', flush=True)
                next_notice = time.monotonic() + 30
            time.sleep(1)
    record = {'mutation': args.mutation, 'python': sys.version, 'lock': lock,
              'pytest_args': pytest_args, 'before_tests': str(args.before_tests) if args.before_tests else None,
              'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                                for path in ['harness/zone_static_door_routes.py',
                                             'tests/test_zone_own_executor_door_routes.py',
                                             'tests/test_ci_fast_path.py', '.github/workflows/tests.yml']}}
    try:
        from harness import zone_static_door_routes as dr
        if args.mutation == 'ci_before':
            # Exact main revision merged before the CI-preservation correction.
            previous = subprocess.check_output([
                'git', 'show', 'b10907c5f2c84f2712030f48fb38061fd4f51281:.github/workflows/tests.yml'],
                text=True)
            read = Path.read_text
            def previous_workflow(path, *a, **kw):
                return previous if path == ROOT / '.github/workflows/tests.yml' else read(path, *a, **kw)
            Path.read_text = previous_workflow
        elif args.mutation != 'none':
            original = dr._formation
            def missing_carrier(*a, **kw):
                team = original(*a, **kw)
                if team.kind == 'long_beam':
                    team.parts = team.item_parts + [p for role in team.roles
                                                    if role != args.mutation
                                                    for p in team.carrier_parts[role]]
                return team
            dr._formation = missing_carrier
        import pytest
        class OriginalTests:
            def pytest_collection_modifyitems(self, items):
                for item in items:
                    if args.before_tests and Path(item.path) == args.before_tests:
                        item.module.ROOT = ROOT
                        item.module.MAP = ROOT / 'maps/zones_final/zone_wide_two_doors_final_v1.json'
        targets = [str(args.before_tests)] if args.before_tests else pytest_args
        record['exit_code'] = int(pytest.main([
            *targets, '-q', '--import-mode=importlib', '--tb=short',
            '--junitxml=' + str(args.output / 'junit.xml')], plugins=[OriginalTests()]))
        return record['exit_code']
    finally:
        held = agent_lock.status(agent_lock.DEFAULT_ROOT)
        if held and held['pid'] == os.getpid():
            record['released'] = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
        record['load_end'] = os.getloadavg()
        (args.output / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
