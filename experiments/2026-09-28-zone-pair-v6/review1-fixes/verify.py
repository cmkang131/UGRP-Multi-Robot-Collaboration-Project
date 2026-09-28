"""Verify final offline records, fixed sources, fairness and draft refusal."""
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts import run_zone_pair_dev as dev
from scripts.zone_pair_v6_contract import PREREG, contract

record = Path(__file__).resolve().parent
root = record.parents[2]
base = '837a110ae15e46a45291100f161b3a33c83eb3d9'
run = json.loads((record/'test_execution.json').read_text())
assert run['exit_code'] == 0 and run['temporary_directory_removed']
assert not any(run['sentinels'].values()) and not any(run['suite_guards'].values())
assert not (root/'.pytest_tmp').exists()
tripwire = Path('/private/tmp/v6-review1-step-audit.log')
assert not tripwire.exists(), 'a child attempted a forbidden physical step'
log = (record/'pytest.log').read_text()
counts = re.search(r'(\d+) passed, (\d+) skipped, (\d+) subtests passed', log)
assert counts, log[-1000:]
passed, skipped, subtests = map(int, counts.groups())
suite = ET.parse(record/'pytest.xml').getroot().find('testsuite')
assert int(suite.attrib['failures']) == int(suite.attrib['errors']) == 0
p = json.loads(PREREG.read_text())
assert p['v6_contract'] == contract() and p['scene_contract'] == dev.scene_contract()
refusals = []
for row in p['runs']:
    args = dev.parser().parse_args(['--prereg',str(PREREG),'--run-id',row['id'],
                                   '--pair-policy',row['pair_policy'],
                                   '--output',str(record/'never-executed'/row['id'])])
    dev.load_config(args)
    args.execute = True
    try:
        dev.load_config(args)
    except ValueError as error:
        assert 'prepare-only' in str(error)
        refusals.append(row['id'])
    else:
        raise AssertionError('DRAFT execution accepted')
assert len(refusals) == 6
frozen = [*sorted((root/'experiments/2026-09-27-zone-pair-dev').glob('prereg_v*.json')),
          root/'scripts/run_m2_pair.py', root/'harness/owncam_recovery_v6.py']
for path in frozen:
    old = subprocess.check_output(['git','show',f'{base}:{path.relative_to(root)}'],cwd=root)
    assert old == path.read_bytes(), str(path)
head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert head == base
paths = [arg for arg in run['pytest_args'] if arg.startswith('tests/')]
skips = [{'file':case.attrib['classname'],'test':case.attrib['name'],'reason':case.find('skipped').attrib.get('message')}
         for case in suite.findall('testcase') if case.find('skipped') is not None]
changed = ['harness/zone_pair_global.py','harness/zone_pair_guards.py',
           'harness/zone_pair_relative.py','harness/zone_pair_obstruction.py',
           'tests/test_zone_pair_v6_review1.py',str(PREREG.relative_to(root))]
summary = {'schema':'zone_pair_v6_review1_regression.v1','base_and_current_head':head,
           'passed':passed,'failed':0,'skipped':skipped,'subtests_passed':subtests,
           'test_files':len(paths),'test_paths':paths,'skipped_physics_tests':skips,
           'junit_tests_including_subtests':int(suite.attrib['tests']),
           'sentinels':run['sentinels'],'suite_guards':run['suite_guards'],
           'python_child_step_attempts':0,'model_calls':0,'pytest_temporary_removed':True,
           'prereg_source_hashes_verified':len(p['v6_contract']['source_sha256']),
           'prereg_sha256':hashlib.sha256(PREREG.read_bytes()).hexdigest(),
           'draft_execution_refused':refusals,'frozen_files_unchanged':len(frozen),
           'project_commit_created':False,'remote_refresh_verified':False,
           'scope':'local nonphysical source regression; no physics/model execution, CI, cohort or completion claim',
           'source_sha256':{path:hashlib.sha256((root/path).read_bytes()).hexdigest() for path in changed}}
(record/'validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ('test_paths','source_sha256')},ensure_ascii=False,indent=2))
