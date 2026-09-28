"""Verify the final local regression and preservation claims without execution."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

record = Path(__file__).resolve().parent
root = record.parents[3]
sys.path.insert(0, str(root))
from scripts import run_zone_pair_dev as dev
from scripts.zone_pair_v6_contract import PREREG, contract

base = '19b3a7b242ccecf63ac5087ba122b1cb559d0991'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip() == base
run = json.loads((record / 'test_execution.json').read_text())
assert run['exit_code'] == 0 and run['temporary_directory_removed']
assert not any(run['suite_guards'].values())
assert not Path(run['child_step_audit']).exists()
assert not (root / '.pytest_tmp').exists()
suite = ET.parse(record / 'pytest.xml').getroot().find('testsuite')
assert int(suite.attrib['failures']) == int(suite.attrib['errors']) == 0
previous = json.loads((record.parent / 'validation.json').read_text())
for path, sha in previous['changed_file_sha256'].items():
    assert hashlib.sha256((root / path).read_bytes()).hexdigest() == sha, path
p = json.loads(PREREG.read_text())
assert p['v6_contract'] == contract() and p['scene_contract'] == dev.scene_contract()
assert hashlib.sha256(PREREG.read_bytes()).hexdigest() == previous['prereg_sha256']
frozen = [*sorted((root / 'experiments/2026-09-27-zone-pair-dev').glob('prereg*.json')),
          *(root / f for f in ('scripts/run_zone_pair_dev.py', 'scripts/zone_pair_registered_source.py',
                              'sim/zone_cargo.py', 'sim/zone_tagged_cargo_scene.py', 'sim/session_scenes.py'))]
for path in frozen:
    assert path.read_bytes() == subprocess.check_output(['git', 'show', f'{base}:{path.relative_to(root)}'], cwd=root)
subprocess.run(['git', 'diff', '--check'], cwd=root, check=True)
log = (record / 'pytest.log').read_text()
result = {'base_and_current_head': base, 'passed': int(re.search(r'(\d+) passed', log).group(1)),
          'failed': 0, 'skipped': int(suite.attrib['skipped']),
          'subtests_passed': int(re.search(r'(\d+) subtests passed', log).group(1)),
          'test_files': run['test_files'], 'suite_guards': run['suite_guards'],
          'child_physics_attempts': 0, 'model_calls': 0, 'temporary_directory_removed': True,
          'unchanged_review2_source_files': len(previous['changed_file_sha256']),
          'unchanged_frozen_files': [str(path.relative_to(root)) for path in frozen],
          'v6_source_hashes_verified': len(contract()['source_sha256']),
          'v6_prereg_sha256': previous['prereg_sha256'], 'policy_flags': contract()['policy_flags'],
          'new_scene_regressions': [c.attrib['name'] for c in suite.findall('testcase')
                                    if c.attrib['name'].startswith('test_v5_scene_admission')],
          'test_change_sha256': hashlib.sha256((root / 'tests/test_zone_pair_v5.py').read_bytes()).hexdigest(),
          'native_ubuntu_run': False, 'remote_ci_rerun': False, 'project_commit_created': False}
assert len(result['new_scene_regressions']) == 6
full = json.loads((record / 'full-checkout.json').read_text())
assert full['all_tracked_files_present'] and full['cleanup_verified']
assert full['pytest_exit_code'] == 0 and not any(full['suite_guards'].values())
assert full['returned_to_original_sparse_file_set'] and full['temporary_directory_removed']
full_suite = ET.parse(record / 'full-checkout.xml').getroot().find('testsuite')
assert int(full_suite.attrib['tests']) == 104
assert int(full_suite.attrib['failures']) == int(full_suite.attrib['errors']) == int(full_suite.attrib['skipped']) == 0
result['full_checkout_presence_regression'] = {
    'tracked_files_present': full['tracked_count'], 'passed': 104, 'failed': 0,
    'includes_original_head_tests': 2, 'hydrated_files': full['restored_files'],
    'hydrated_copies_verified_and_removed': full['restored_copies_removed']}
(record / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k not in ('policy_flags', 'unchanged_frozen_files')}, indent=2))
