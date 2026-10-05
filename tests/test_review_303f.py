"""PR #303 review F regressions, from b13c9b97 against 37828875.

Both former strict xfails are required passes after the review F fixes.
Mutation detection and the optional CI dependency boundary are offline checks.
"""
import inspect
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET

import pytest

pytest.importorskip('harness.zone_evidence_key')
from harness.zone_study_contract import digest
from scripts import zone_study_evidence_cohort as cohort
from scripts.tensorboard_tools.zone_study import inspect_study
from tests.zone_evidence_fixtures import read


@pytest.mark.parametrize('damage,reason', [
    ('policy_hash', 'recorded referee policy differs'),
    ('profile', 'recorded referee policy differs'),
    ('events', 'raw referee event log missing'),
    ('summary', 'referee replay/summary conflict: orders_complete'),
])
@pytest.mark.parametrize('reverse', [False, True])
def test_e303_rejection_keeps_exact_owner_and_reason(tmp_path, damage, reason, reverse):
    from tests import test_review_303e as e
    plan, sources = e._conflicting_sources(tmp_path, 'run-1')
    admitted = plan['admitted']
    # These sources are individually accepted before damage; A is only invalid
    # because it has a duplicate, not because our fixture failed to load.
    for source in sources:
        inspect_study(source)
    baseline = cohort.collect(plan, digest(plan), sources)
    assert [r['status'] for r in baseline['trials']] == ['INVALID', 'VALID']
    assert baseline['successes'] == 0
    e._damage_referee(sources[-1], damage)
    affected, declarations, conflict = cohort.source_owners(sources[-1], admitted)
    assert affected == {0} and not conflict
    assert declarations and all(d['key'] == admitted[0]['key'] for d in declarations)
    with pytest.raises(ValueError, match=reason):
        inspect_study(sources[-1])
    result = cohort.collect(plan, digest(plan), list(reversed(sources)) if reverse else sources)
    assert (result['admitted_trials'], result['successes'], result['invalid_trials']) == (2, 0, 1)
    assert [r['status'] for r in result['trials']] == ['INVALID', 'VALID']
    receipt = next(r for r in result['sources'] if r['source'] == str(sources[-1]))
    assert receipt['affected_keys'] == [admitted[0]['key']]
    assert reason in receipt['reason']
    assert read(sources[-1], 'manifest.json')['evidence_key'] == admitted[0]['key']


def test_generated_property_detects_restored_rejected_owner_bug(tmp_path, monkeypatch):
    from tests.test_zone_referee_ownership import (
        test_192_generated_raw_record_transformations_never_increase_success as property_check,
    )
    old = "# Rejection cannot erase the source's owners or assign it elsewhere."
    new = ("affected = [i for i, r in enumerate(admitted) "
           "if r['key']['run_id'] == source.name] or range(len(admitted))")
    source = inspect.getsource(cohort.collect)
    if source.count(old) != 1:
        raise RuntimeError('Mutation location drifted; inspect the fix before updating this probe')
    namespace = dict(cohort.collect.__globals__)
    exec(compile(textwrap.dedent(source.replace(old, new)), '<restored E303-1>', 'exec'), namespace)
    monkeypatch.setattr(cohort, 'collect', namespace['collect'])
    detected = []
    for operation in ('permute', 'duplicate', 'move'):
        try:
            property_check(tmp_path / operation, operation)
        except AssertionError:
            detected.append(operation)
    # The generated directory moves must detect this bug themselves, without
    # relying on the eight direct E303 examples.
    assert detected, 'All 192 cases survived the mutation that restores wrong rejected-source ownership'


def test_tensorboard_ci_probe_needs_no_opencv(tmp_path):
    report = tmp_path / 'child.xml'
    code = '''
import sys
for name in ('cv2', 'mujoco', 'torch', 'sim.multi_masterpi_production'):
    sys.modules[name] = None
import pytest
raise SystemExit(pytest.main(['-q',
    'tests/test_tensorboard_export.py::test_p06_rejected_owners_with_real_tensorboard',
    '--tb=short', '--junitxml=' + sys.argv[1]]))
'''
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    result = subprocess.run([sys.executable, '-c', code, str(report)],
                            cwd=Path(__file__).resolve().parents[1], env=env,
                            capture_output=True, text=True, timeout=120)
    suite = ET.parse(report).getroot().find('testsuite')
    if suite is None or any(int(suite.get(k, 0)) for k in ('errors', 'skipped')):
        raise RuntimeError('Collection errors/skips cannot verify the optional CI dependency boundary')
    output = result.stdout + result.stderr
    if result.returncode and 'ModuleNotFoundError: import of cv2 halted' not in output:
        raise RuntimeError(output)
    assert result.returncode == 0, output
