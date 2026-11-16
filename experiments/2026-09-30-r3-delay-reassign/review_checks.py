"""T12 review verification: offline only, no host lock or sealed-file edits.

Run with the existing Mac Python. Logs/JUnit stay in primary outputs; mutants
touch only unsealed modules/tests in a temporary copy, never the worktree.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
RAW = Path('/Users/changmin/projects/ugrp/outputs/cap-t12-r3-delay')
GUARD = Path('experiments/2026-09-30-t07-r3-roles')
T12 = ['tests/test_zone_pair_rendezvous.py', 'tests/test_zone_pair_rendezvous_t07.py']
CORE = T12 + ['tests/test_zone_pair_role_exchange.py', 'tests/test_zone_pair_executor.py',
              'tests/test_zone_pair_registered_source.py', 'tests/test_zone_study_source_pinning.py']
RELATED = CORE + [
    'tests/test_zone_pair_status.py',
    *[f'tests/test_zone_pair_review{i or ""}.py' for i in range(8) if i != 1],
    'tests/test_zone_pair_v6e.py', 'tests/test_zone_pair_v6e_yaw.py',
    'tests/test_zone_study_integration.py', 'tests/test_zone_study_integration_pair.py',
    'tests/test_zone_pair_door_relax.py', 'tests/test_zone_mixed_jobs.py',
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(root, out, name, tests, selection=None):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
               VECLIB_MAXIMUM_THREADS='1', PYTHONPATH=str(root) + os.pathsep + str(root / GUARD))
    # Real-worktree tests may create their OWN repositories. Never redirect
    # those git commands to this worktree. Only mutation snapshots need the
    # original object database for read-only historical blob checks.
    env.pop('GIT_DIR', None)
    env.pop('GIT_WORK_TREE', None)
    if root != ROOT:
        env.update(GIT_DIR=subprocess.check_output(['git', 'rev-parse', '--absolute-git-dir'],
                                                  cwd=ROOT, text=True).strip(),
                   GIT_WORK_TREE=str(root))
    command = [sys.executable, '-m', 'pytest', '-q', '-p', 'offline_guard', '-p', 'no:cacheprovider',
               *tests, f'--junitxml={out / (name + ".xml")}']
    if selection:
        command += ['-k', selection]
    (out / (name + '_command.json')).write_text(json.dumps(command, indent=2) + '\n')
    with (out / (name + '.log')).open('w') as stream:
        result = subprocess.run(command, cwd=root, env=env, text=True, stdout=stream, stderr=subprocess.STDOUT)
    suites = list(ET.parse(out / (name + '.xml')).getroot().iter('testsuite'))
    counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
    assertions = sum('AssertionError' in (f.text or '') for s in suites for f in s.iter('failure'))
    row = dict(name=name, command=command, exit_code=result.returncode, assertion_failures=assertions, **counts)
    print(json.dumps({k: v for k, v in row.items() if k != 'command'}), flush=True)
    with (out / 'checks.jsonl').open('a') as stream:
        stream.write(json.dumps(row) + '\n')
    return row


def passed(row):
    assert row['tests'] > 0 and row['exit_code'] == 0, row
    assert not any(row[k] for k in ('failures', 'errors', 'skipped')), row


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def mutate(out):
    recovery = 'harness/zone_pair_rendezvous.py'
    role = 'harness/zone_pair_role_executor.py'
    fixture = 'tests/test_zone_pair_rendezvous_t07.py'
    geometry = 'fixed_beam_and_partner_exclusion_geometry or fixed_role_exclusion_geometry'
    role_test = ['tests/test_zone_pair_role_exchange.py']
    anchor = '    plan.update(role_to_robot=roles.mapping(), role_assignment_sha256=roles.sha256())'
    mutants = [
        ('stale_cancel_removed', recovery,
         'if self.job_id is None or job_id != self.job_id or not self._owns():', 'if False:', T12,
         'explicit_reassignment_cancels_only_old_job or host_reassigns_only_after_own_cancel', 18),
        ('timeout_removed', recovery, 'if now >= self.deadline - EPS:', 'if False:', T12,
         'before_just_before_at_and_after_deadline', 32),
        ('legacy_fixture_restored', fixture, 'from tests.test_zone_pair_role_exchange import setup',
         'from tests.test_zone_pair_executor import setup', [fixture],
         'role_exchange_requires_independent_complementary_request', 1),
        ('role_keepouts_removed', role, anchor,
         "    plan['keepouts'] = {rid: [] for rid in roles.participants}\n" + anchor,
         role_test, geometry, 12),
        ('driver_wrong_role', role, "keepouts=plan['keepouts'][rid]",
         "keepouts=plan['keepouts'][execution.partner_id]", role_test, 'fixed_role_exclusion_geometry', 6),
    ]
    paths = {row[1] for row in mutants}
    originals = {path: (ROOT / path).read_bytes() for path in paths}
    selected = ' or '.join(dict.fromkeys(row[5] for row in mutants))
    with tempfile.TemporaryDirectory(prefix='t12-review-mutations-') as temp:
        snapshot = Path(temp)
        for directory in ('harness', 'scripts', 'sim', 'tests', 'configs', 'maps', 'experiments'):
            shutil.copytree(ROOT / directory, snapshot / directory, copy_function=link_or_copy,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        passed(run(snapshot, out, 'mutation_baseline', T12 + role_test, selected))
        for name, relative, needle, replacement, tests, selection, expected in mutants:
            original = originals[relative]
            text = original.decode()
            assert text.count(needle) == 1, (name, needle)
            mutated = text.replace(needle, replacement).encode()
            path = snapshot / relative
            try:
                # Break the hardlink BEFORE writing, including restoration.
                path.unlink()
                path.write_bytes(mutated)
                row = run(snapshot, out, name, tests, selection)
                assert row['exit_code'] == 1 and row['failures'] == expected, row
                assert row['assertion_failures'] == expected and not row['errors'] and not row['skipped'], row
                (out / (name + '_mutation.json')).write_text(json.dumps({
                    'path': relative, 'needle': needle, 'replacement': replacement,
                    'original_sha256': digest(original), 'mutated_sha256': digest(mutated)}, indent=2) + '\n')
            finally:
                path.unlink()
                path.write_bytes(original)
        passed(run(snapshot, out, 'mutation_restored', T12 + role_test, selected))
    assert all((ROOT / path).read_bytes() == original for path, original in originals.items())


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='review-checks-', dir=RAW))
    print(out, flush=True)
    (out / 'driver.py').write_bytes(Path(__file__).read_bytes())
    tests = [arg for arg in sys.argv[1:] if arg.startswith('tests/')]
    label = 'selected' if tests else ('related' if '--related' in sys.argv else 'core')
    tests = tests or (RELATED if '--related' in sys.argv else CORE)
    sources = subprocess.check_output(['git', 'ls-files', 'harness', 'scripts', 'tests', 'configs', 'maps'],
                                      cwd=ROOT, text=True).splitlines()
    (out / 'source_sha256.json').write_text(json.dumps({p: digest((ROOT / p).read_bytes()) for p in sources
                                                     if (ROOT / p).is_file()}, indent=2) + '\n')
    (out / 'environment.json').write_text(json.dumps({
        'python': sys.version, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'host_lock': False, 'physics_render_model_calls': 0,
    }, indent=2) + '\n')
    if '--mutations-only' not in sys.argv:
        passed(run(ROOT, out, label, tests))
    if '--tests-only' not in sys.argv:
        mutate(out)


if __name__ == '__main__':
    main()
