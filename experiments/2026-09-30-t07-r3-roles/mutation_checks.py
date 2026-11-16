"""F1/F2 reproducible source mutations, in a disposable snapshot only.

Use the same optional host lock/no-physics policy as offline_checks.py. Each mutant
must cause assertion failures (pytest exit 1, no import/collection errors).
No registered bytes in the actual worktree are ever edited by this driver.
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
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
TEST = 'tests/test_zone_pair_role_exchange.py'
ROLE = 'harness/zone_pair_role_executor.py'
LEGACY = 'harness/zone_pair_executor.py'
GEOMETRY = 'fixed_beam_and_partner_exclusion_geometry or fixed_role_exclusion_geometry'
BASELINE = GEOMETRY + ' or preserves_each_registered_source or opt_in_host_and_study_leave_legacy_dispatch_available'
PRE_FIX = '1a17829e79cdf7771ee2d09ca25e444c39cf37be'


def link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def mutations():
    role = (ROOT / ROLE).read_text()
    old = (ROOT / LEGACY).read_text()
    anchor = '    plan.update(role_to_robot=roles.mapping(), role_assignment_sha256=roles.sha256())'
    assert role.count(anchor) == 1
    needle = "'keepouts': keepouts"
    assert old.count(needle) == 1
    yield 'all_keepouts_removed', LEGACY, old.replace(needle, "'keepouts': {r: [] for r in PAIR}"), GEOMETRY
    for index, name in enumerate(('beam', 'partner_station', 'partner_prestation')):
        code = f"    plan['keepouts'] = {{rid: [k for i, k in enumerate(ks) if i != {index}] for rid, ks in plan['keepouts'].items()}}\n"
        yield name + '_removed', ROLE, role.replace(anchor, code + anchor), GEOMETRY
    code = "    plan['keepouts'] = {rid: plan['keepouts'][roles.partner(rid)] for rid in roles.participants}\n"
    yield 'plan_wrong_role', ROLE, role.replace(anchor, code + anchor), GEOMETRY
    for name, needle, replacement in (
        ('beam_padding_removed', 'm2.KEEPOUT_PAD_M', '0.'),
        ('partner_padding_removed', 'm2.PARTNER_KEEPOUT_HALF_M', '0.'),
    ):
        assert old.count(needle) == 1
        yield name, LEGACY, old.replace(needle, replacement), GEOMETRY
    needle = "keepouts=plan['keepouts'][rid]"
    assert role.count(needle) == 1
    for name, replacement in (('driver_keepouts_removed', 'keepouts=[]'),
                              ('driver_wrong_role', "keepouts=plan['keepouts'][execution.partner_id]")):
        yield name, ROLE, role.replace(needle, replacement), 'fixed_role_exclusion_geometry'
    for name in ('zone_own_team_host', 'zone_own_executor', 'zone_pair_executor',
                 'zone_pair_status', 'zone_study_integration'):
        path = f'harness/{name}.py'
        prior = subprocess.check_output(['git', 'show', PRE_FIX + ':' + path], cwd=ROOT).decode()
        yield 'unsealed_' + name, path, prior, f'preserves_each_registered_source and {name}'


def execute(output):
    output.mkdir(parents=True, exist_ok=False)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    evidence = []
    # Hardlinks save disk; replace() below unlinks each target BEFORE writing.
    # Thus neither mutation nor restoration can write through to an original.
    with tempfile.TemporaryDirectory(prefix='t07-mutations-') as temp:
        snapshot = Path(temp)
        for directory in ('harness', 'scripts', 'sim', 'tests', 'configs', 'maps', 'experiments'):
            shutil.copytree(ROOT / directory, snapshot / directory, copy_function=link_or_copy,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   VECLIB_MAXIMUM_THREADS='1',
                   PYTHONPATH=str(snapshot) + os.pathsep + str(snapshot / 'experiments/2026-09-30-t07-r3-roles'),
                   GIT_DIR=str((ROOT / subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, text=True).strip()).resolve()),
                   GIT_WORK_TREE=str(snapshot))

        def replace(path, value):
            path.unlink()
            path.write_bytes(value)

        def run(name, selection):
            junit = output / (name + '.xml')
            command = [sys.executable, '-m', 'pytest', '-q', '-p', 'offline_guard', '-p', 'no:cacheprovider',
                       TEST, '-k', selection, f'--junitxml={junit}']
            result = subprocess.run(command, cwd=snapshot, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (output / (name + '.log')).write_text(result.stdout)
            suites = list(ET.parse(junit).getroot().iter('testsuite'))
            counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
            assertions = sum('AssertionError' in (failure.text or '')
                             for suite in suites for failure in suite.iter('failure'))
            row = dict(name=name, exit_code=result.returncode, assertion_failures=assertions, **counts)
            print(json.dumps(row), flush=True)
            evidence.append(row)
            return row

        baseline = run('baseline', BASELINE)
        if baseline['exit_code'] or baseline['tests'] != 18 or baseline['skipped']:
            raise RuntimeError('mutation baseline did not pass all 18 regressions')
        for name, relative, mutated, selection in mutations():
            path = snapshot / relative
            original = path.read_bytes()
            try:
                replace(path, mutated.encode())
                row = run(name, selection)
                row.update(path=relative, original_sha256=hashlib.sha256(original).hexdigest(),
                           mutated_sha256=hashlib.sha256(mutated.encode()).hexdigest())
                if (row['exit_code'] != 1 or row['failures'] != row['tests']
                        or row['assertion_failures'] != row['tests'] or row['errors'] or row['skipped']):
                    raise RuntimeError(f'mutation survived or had non-assertion errors: {name}')
            finally:
                replace(path, original)
        # Revert F1 as a whole as well: the pre-fix legacy host again accepts
        # explicit r3 roles. The side-by-side API regression must reject that.
        changes = [(relative, mutated) for name, relative, mutated, _ in mutations()
                   if name.startswith('unsealed_')]
        originals = {relative: (snapshot / relative).read_bytes() for relative, _ in changes}
        try:
            for relative, mutated in changes:
                replace(snapshot / relative, mutated.encode())
            row = run('legacy_dispatch_isolation_removed', 'opt_in_host_and_study_leave_legacy_dispatch_available')
            row['paths'] = list(originals)
            if (row['exit_code'] != 1 or row['tests'] != 1 or row['assertion_failures'] != 1
                    or row['failures'] != 1 or row['errors'] or row['skipped']):
                raise RuntimeError('legacy dispatch isolation mutation survived or had non-assertion errors')
        finally:
            for relative, original in originals.items():
                replace(snapshot / relative, original)
        restored = run('restored', BASELINE)
        if restored['exit_code'] or restored['tests'] != 18:
            raise RuntimeError('restored snapshot failed')
    return evidence


def main():
    sys.path.insert(0, str(ROOT))
    if len(sys.argv) == 3 and sys.argv[1] == '--worker':
        output = Path(sys.argv[2])
        try:
            records = execute(output)
            (output / 'result.json').write_text(json.dumps(records, indent=2) + '\n')
        except Exception:
            raise
        return 0
    from scripts.run_ci_tests import local_lock_root, run_locked
    raw = Path('/Users/changmin/projects/ugrp/outputs/t07-r3-roles')
    output = raw / ('mutations-' + uuid.uuid4().hex[:12])
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', str(output)]
    print(output, flush=True)
    lock = local_lock_root() if os.environ.get('UGRP_TEST_HOST_LOCK') == '1' else None
    return run_locked(command, dict(os.environ), lock) if lock else subprocess.call(command, cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
