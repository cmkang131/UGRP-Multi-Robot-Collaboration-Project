"""Reviewable source/registration/test evidence. Does not execute a robot."""
import ast
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from scripts import run_zone_pair_dev as dev
from scripts.zone_pair_v6_contract import PREREG, contract
from harness.zone_pair_v6_policy import POLICIES

record=Path(__file__).resolve().parent
root=record.parents[2]
base='19b3a7b242ccecf63ac5087ba122b1cb559d0991'
head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert head==base
run=json.loads((record/'test_execution.json').read_text())
assert run['exit_code']==0 and run['temporary_directory_removed']
assert not any(run['suite_guards'].values())
assert not Path(run['child_step_audit']).exists()
assert not (root/'.pytest_tmp').exists()
suite=ET.parse(record/'pytest.xml').getroot().find('testsuite')
assert int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
log=(record/'pytest.log').read_text()
passed=int(re.search(r'(\d+) passed',log).group(1))
subtests=int(re.search(r'(\d+) subtests passed',log).group(1))
p=json.loads(PREREG.read_text())
assert p['v6_contract']==contract() and p['scene_contract']==dev.scene_contract()
refused=[]
for row in p['runs']:
 args=dev.parser().parse_args(['--prereg',str(PREREG),'--run-id',row['id'],'--pair-policy',row['pair_policy'],
                             '--output',str(record/'never-executed'/row['id'])])
 dev.load_config(args);args.execute=True
 try: dev.load_config(args)
 except ValueError as error:
  assert 'prepare-only' in str(error);refused.append(row['id'])
 else: raise AssertionError('DRAFT execution accepted')
assert len(refused)==6
flags={name:{k:v for k,v in vars(value).items() if k!='name'} for name,value in POLICIES.items()}
for a,b in [('v5h','b-only'),('b-only','a+b')]:
 assert sum(flags[a][k]!=flags[b][k] for k in flags[a])==1
frozen=[*sorted((root/'experiments/2026-09-27-zone-pair-dev').glob('prereg_v*.json')),
        root/'scripts/run_m2_pair.py',root/'harness/owncam_recovery_v6.py',
        root/'harness/owncam_observability_v6.py',root/'harness/zone_pair_v6_policy.py',
        root/'harness/zone_own_guards.py',root/'harness/zone_pair_geometry.py']
for path in frozen:
 assert path.read_bytes()==subprocess.check_output(['git','show',f'{base}:{path.relative_to(root)}'])
def definition(source, path):
 node=ast.parse(source)
 for name in path.split('.'):
  node=next(n for n in node.body if getattr(n,'name',None)==name)
 return ast.dump(node,include_attributes=False)
unchanged_sections={
 'harness/zone_pair_global.py':['GlobalPairSweepGuard.margin','GlobalPairSweepGuard.certificate',
                               'GlobalEnvelope._verified_reacquisition'],
 'harness/zone_pair_align.py':['PairAlignRelook.align_relook_expired']}
for path,names in unchanged_sections.items():
 old=subprocess.check_output(['git','show',f'{base}:{path}'],text=True)
 for name in names:
  assert definition(old,name)==definition((root/path).read_text(),name), (path,name)
changes=subprocess.check_output(['git','diff','--name-only'],text=True).splitlines()
changes+=['tests/test_zone_pair_v6_review2.py']
scenarios=[case.attrib['name'] for case in suite.findall('testcase')
           if 'test_zone_pair_v6_review2' in case.attrib['classname']]
skips=[{'test':case.attrib['name'],'reason':case.find('skipped').attrib.get('message')}
       for case in suite.findall('testcase') if case.find('skipped') is not None]
result={'schema':'zone_pair_v6_review2_regression.v1','base_and_current_head':head,
        'passed':passed,'failed':0,'skipped':int(suite.attrib['skipped']),'subtests_passed':subtests,
        'test_files':run['test_files'],'junit_tests_including_subtests':int(suite.attrib['tests']),
        'review2_scenarios':scenarios,'skips':skips,'suite_guards':run['suite_guards'],
        'child_physics_attempts':0,'model_calls':0,'pytest_temporary_removed':True,
        'adjacent_policy_flags':flags,'prereg_source_hashes_verified':len(contract()['source_sha256']),
        'prereg_sha256':hashlib.sha256(PREREG.read_bytes()).hexdigest(),
        'draft_execution_refused':refused,'frozen_files_unchanged':len(frozen),
        'unchanged_safety_definitions':unchanged_sections,
        'project_commit_created':False,'remote_refresh_verified':False,
        'scope':'offline command-response/analytic RGB source regression, not physics or cohort success',
        'changed_file_sha256':{path:hashlib.sha256((root/path).read_bytes()).hexdigest() for path in changes}}
(record/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='changed_file_sha256'},ensure_ascii=False,indent=2))
