"""Offline verification on the merged tree; mutations exist only in memory.

Uses the existing Python environment, no host lock (PR #328), no physics/model
imports or network. Each invocation writes fresh logs under the supplied output.
"""
import argparse
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'


class NoPhysics(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'glfw', 'torch', 'openai', 'anthropic', 'google'}:
            raise RuntimeError('T09a offline-only boundary: ' + fullname)


def no_network(event, args):
    if event == 'socket.connect':
        raise RuntimeError('T09a offline tests cannot connect to network')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mutation', choices=['none', 'end_neg', 'end_pos'], default='none')
    parser.add_argument('--output', type=Path, required=True)
    args, targets = parser.parse_known_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sys.meta_path.insert(0, NoPhysics())
    sys.addaudithook(no_network)
    from harness import zone_static_door_routes as dr
    from scripts.zone_pair_v6_contract import PREREG_V6E
    sealed = json.loads(PREREG_V6E.read_text())['v6_contract']['source_sha256']
    workflows = subprocess.check_output(
        ['git', 'ls-tree', '-r', '--name-only', 'origin/main', '.github/workflows'], text=True).splitlines()
    pinned = ['tests/test_zone_pair_registered_source.py', 'tests/test_zone_study_source_pinning.py']
    protected = set(sealed) | set(workflows) | set(pinned)
    before = {name: sha(ROOT / name) for name in sorted(protected)}
    assert all(before[name] == expected for name, expected in sealed.items())
    assert all((ROOT / name).read_bytes() == subprocess.check_output(
        ['git', 'show', 'origin/main:' + name]) for name in workflows + pinned)
    record = {
        'mutation': args.mutation, 'python': sys.version, 'targets': targets,
        'head_before_merge': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'integrated_main': subprocess.check_output(['git', 'rev-parse', 'origin/main'], text=True).strip(),
        'host_lock_acquired': False, 'load_start': os.getloadavg(),
        'sealed_sources_matched': len(sealed), 'workflow_files_matched_main': workflows,
        'pinned_tests_matched_main': pinned, 'protected_sha256': before,
        'source_sha256': {name: sha(ROOT / name) for name in [
            'harness/zone_static_door_routes.py', 'tests/test_zone_own_executor_door_routes.py',
            'tests/test_ci_fast_path.py', 'CONTRIBUTING.md']},
    }
    if args.mutation != 'none':
        original = dr._formation

        def missing_carrier(*a, **kw):
            team = original(*a, **kw)
            if team.kind == 'long_beam':
                team.parts = team.item_parts + [part for role in team.roles
                                                if role != args.mutation
                                                for part in team.carrier_parts[role]]
            return team

        dr._formation = missing_carrier
    import pytest
    try:
        record['exit_code'] = int(pytest.main([
            *targets, '-q', '--tb=short', '--junitxml=' + str(args.output / 'junit.xml')]))
        return record['exit_code']
    finally:
        record['protected_files_unchanged'] = all(sha(ROOT / name) == value for name, value in before.items())
        record['load_end'] = os.getloadavg()
        (args.output / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
        assert record['protected_files_unchanged']


if __name__ == '__main__':
    raise SystemExit(main())
