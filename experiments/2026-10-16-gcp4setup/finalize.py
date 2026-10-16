"""Assert retrieved gcp4 infrastructure evidence and build the local summary/funnel."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
E=ROOT/'evidence'

def read(name): return json.loads((E/(name+'.json')).read_text())
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

vm=read('l4-final')
assert vm['name']=='ugrp-act-l4-gcp4' and vm['status']=='TERMINATED'
assert len(read('instances-final'))==len(read('disks-final'))==1
assert read('instances-after-test')==read('disks-after-test')==[]
verification=read('verification')
assert verification.pop('other_jobs_before_stop') is False and all(verification.values())
assert 'maxRunDuration' not in vm['scheduling'] and 'terminationTime' not in vm['scheduling']
assert not vm.get('serviceAccounts')
fn=read('function-active')
assert fn['state']=='ACTIVE' and fn['buildConfig']['entryPoint']=='stop_on_budget'
assert fn['serviceConfig']['environmentVariables']['TARGET_PROJECT']=='ugrp-sim-d-1016'
budget=read('budget-final')
assert budget['budgetFilter']['projects']==['projects/298701037365']
assert budget['budgetFilter']['creditTypesTreatment']=='INCLUDE_ALL_CREDITS'
assert budget['amount']['specifiedAmount']==dict(currencyCode='KRW',units='1000')
assert budget['notificationsRule']['pubsubTopic']=='projects/ugrp-sim-d-1016/topics/budget-stop'
assert not budget['notificationsRule'].get('disableDefaultIamRecipients',False)
assert budget['thresholdRules']==[dict(spendBasis='CURRENT_SPEND',thresholdPercent=.5),dict(spendBasis='CURRENT_SPEND',thresholdPercent=1)]
for name in ['main.py','requirements.txt']:
 assert (ROOT/'function'/name).read_bytes()==(ROOT.parent/'2026-10-16-gcp3setup/function'/name).read_bytes()
smoke=read('smoke-result')
reference=json.loads((ROOT.parent/'2026-10-16-gcp3setup/evidence/smoke-result.json').read_text())
assert smoke['status']=='PASS' and smoke['nworld']==2 and smoke['steps']==1 and smoke['device']=='cuda:0'
assert smoke['versions']==reference['versions'] and smoke['source_files_sha256']==reference['source_files_sha256']
observations=read('test-observations')
assert any(x['status']=='STOPPING' for x in observations) and observations[-1]['status']=='TERMINATED'
disk=read('l4-disk-final')
assert disk['sourceImage'].endswith('/global/images/common-cu129-ubuntu-2404-nvidia-580-v20261001')
assert disk['sizeGb']=='140' and disk['type'].endswith('/pd-balanced')
assert vm['machineType'].endswith('/g2-standard-8')
assert vm['guestAccelerators'][0]['acceleratorType'].endswith('/nvidia-l4') and vm['guestAccelerators'][0]['acceleratorCount']==1
failures=[]
commands=[]
for p in sorted(E.glob('*-command.json')):
 record=json.loads(p.read_text()); command=record.get('command',[])
 if command and command[0]=='gcloud':
  assert command[command.index('--account')+1]=='changmin5781@gmail.com'
  assert command[command.index('--project')+1]=='ugrp-sim-d-1016'
  commands.append(p.name)
 if record.get('returncode',0):
  failures.append(dict(category='infrastructure_command_error',evidence=str(p.resolve()),blocked_object='not_applicable_infrastructure',minimum_gap_m=None,measurement_status='not_measured_infrastructure'))
write(E/'setup-rejections.json',dict(rejections=failures,total=len(failures),reason_distribution={'infrastructure_command_error':len(failures)},scope='Infrastructure provisioning; no robot rejection/geometry measurements'))
funnel=dict(scope='One infrastructure candidate; no research mission gate',stages=[dict(gate=stage,input=1,passed_cumulative=1,rejected=0) for stage in ['authorized_project_and_quota','scoped_net_budget_and_active_function','manual_stop_observed','test_vm_and_disk_deleted','uncapped_guarded_l4_created','cuda_two_world_one_step','source_and_retrieved_hash_audit','own_lease_removed_no_other_jobs','l4_terminated']],worlds=[dict(gate=stage,input=2,passed_cumulative=2,rejected=0) for stage in ['requested','stepped','finite_time_advanced']],failed_setup_attempts=failures,raw_paths=['gcp4:/home/ugrp/ugrp-sim/setup/',str(E.resolve())],reproduce=['python3 experiments/2026-10-16-gcp4setup/finalize.py','ssh gcp4 /home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python /home/ugrp/ugrp-sim/setup/smoke.py NEW_RESULT.json'])
write(E/'funnel.json',funnel)
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name not in ('summary.json','SHA256.json')}
write(E/'SHA256.json',manifest)
start=datetime.datetime.fromisoformat(vm['lastStartTimestamp']); stop=datetime.datetime.fromisoformat(vm['lastStopTimestamp'])
write(ROOT/'summary.json',dict(schema='ugrp.gcp4setup.v1',ready=True,readiness_scope='GCP infrastructure only',project='ugrp-sim-d-1016',project_number='298701037365',account='changmin5781@gmail.com',host='gcp4',default_host='gcp2',instance=vm['name'],vm_status=vm['status'],machine='g2-standard-8',gpu='NVIDIA L4 x1',disk_gb=140,max_run_s=None,idle_s=1200,results_pooled=False,source_sha=read('probe-source')['source_sha'],dependencies=['PR #554 codex/gcp3setup','PR #558 codex/nocap'],budget=dict(net_krw=1000,credits='INCLUDE_ALL_CREDITS',project_filter=budget['budgetFilter']['projects'],default_billing_iam_email_enabled=True,email_delivery_tested=False,manual_publish_stopping_s=next(x['elapsed_s'] for x in observations if x['status']=='STOPPING'),manual_publish_terminated_s=observations[-1]['elapsed_s'],test_vm_and_disk_deleted=True),runs=[dict(name='budget_stop_test',status='PASS',raw=str((E/'test-observations.json').resolve())),dict(name='mjwarp_import_batch_step',status='PASS',nworld=2,steps=1,sim_s_per_world=.002,raw='gcp4:/home/ugrp/ugrp-sim/setup/smoke-result.json')],host_error=0,cap_end=0,failed_setup_attempts=failures,verification=dict(nonphysics_tests='17 passed',guest=read('verification'),gcp2_gcp3_api_calls=0,first_project_api_calls=0,recorded_gcloud_commands_checked=len(commands),mac_physics=0,mac_render=0,llm_calls=0,training=0),cost=dict(l4_start=vm['lastStartTimestamp'],l4_stop=vm['lastStopTimestamp'],l4_elapsed_s=(stop-start).total_seconds(),actual_billed=None,actual_billed_status='Not retrieved; no zero-cost claim',persistent_after_stop=['140GB L4 disk','Cloud Build/function/source/artifact storage'],billing_delay_tested=False),rejection_table=str((E/'funnel.json').resolve()),manifest=dict(path='evidence/SHA256.json',sha256=hashlib.sha256((E/'SHA256.json').read_bytes()).hexdigest()),originals='gcp4:/home/ugrp/ugrp-sim/setup/; installation and smoke logs retained on disk',remaining=['Research scene/render/teacher/student/E2E gates not run by this infrastructure setup','Actual billing and email receipt unverified','PR CI/review/merge reported separately']))
print(json.dumps(dict(ready=True,vm_status=vm['status'],stopping_s=next(x['elapsed_s'] for x in observations if x['status']=='STOPPING'),l4_elapsed_s=(stop-start).total_seconds(),manifest_files=len(manifest))))
