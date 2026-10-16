"""Assert all gcp6 evidence, then write a scoped summary and cumulative funnel."""
import configparser
import datetime
import hashlib
import json
from pathlib import Path

from ops import ROOT, EVIDENCE as E, ACCOUNT, PROJECT


def read(name):
    return json.loads((E/(name+'.json')).read_text())


def write(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


vm, disk = read('l4-final'), read('l4-disk-final')
assert vm['name']=='ugrp-act-l4-gcp6' and vm['status']=='TERMINATED'
assert len(read('instances-final'))==len(read('disks-final'))==1
assert read('instances-after-test')==read('disks-after-test')==[]
assert not vm.get('serviceAccounts')
assert not {'maxRunDuration','terminationTime'} & vm['scheduling'].keys()
assert vm['machineType'].endswith('/g2-standard-8')
gpu = vm['guestAccelerators'][0]
assert gpu['acceleratorCount']==1 and gpu['acceleratorType'].endswith('/nvidia-l4')
assert disk['sizeGb']=='140' and disk['type'].endswith('/pd-balanced')
assert disk['sourceImage'].endswith('/common-cu129-ubuntu-2404-nvidia-580-v20261001')
verification = read('verification')
assert verification['other_jobs_before_stop'] is False
assert all(v for k,v in verification.items() if k!='other_jobs_before_stop')
fn = read('function-final')
assert fn['state']=='ACTIVE' and fn['buildConfig']['entryPoint']=='stop_on_budget'
assert fn['serviceConfig']['environmentVariables']['TARGET_PROJECT']==PROJECT
budget = read('budget-final')
assert budget['name'].startswith('billingAccounts/010CD7-4B991B-84AAC7/')
assert budget['budgetFilter']['projects']==['projects/503325597974']
assert budget['budgetFilter']['creditTypesTreatment']=='INCLUDE_ALL_CREDITS'
assert budget['amount']['specifiedAmount']==dict(currencyCode='KRW',units='1000')
assert budget['notificationsRule']['pubsubTopic']==f'projects/{PROJECT}/topics/budget-stop'
assert not budget['notificationsRule'].get('disableDefaultIamRecipients',False)
assert any(x.get('jsonPayload',{}).get('stopped')==['ugrp-budget-test-gcp6'] for x in read('test-function-log'))
users = {m for b in read('iam-final')['bindings'] for m in b['members'] if m.startswith('user:')}
assert users=={'user:'+ACCOUNT}, users
config_dir = Path.home()/'.config/gcloud'
active = (config_dir/'active_config').read_text().strip()
config = configparser.ConfigParser()
config.read(config_dir/'configurations'/('config_'+active))
assert config.get('core','account')=='changmin5781@gmail.com'
observations = read('test-observations')
stopping = next(x['elapsed_s'] for x in observations if x['status']=='STOPPING')
assert observations[-1]['status']=='TERMINATED'
smoke, training, transfer = read('smoke-result'), read('act-smoke-result'), read('data-transfer-verification')
reference = json.loads((ROOT.parent/'2026-10-16-gcp4setup/evidence/smoke-result.json').read_text())
assert smoke['status']=='PASS' and smoke['nworld']==2 and smoke['steps']==1
assert smoke['versions']==reference['versions'] and smoke['source_files_sha256']==reference['source_files_sha256']
assert training['status']=='PASS' and training['optimizer_steps']==50
assert training['predictions_bitwise_equal'] and training['train_shared_dependencies_imported']
assert transfer['all_files_sha256_equal'] and transfer['files_n']==1483
assert transfer['source_stats_unchanged'] and transfer['source_own_lease_removed']
assert not transfer['source_vm_stop_attempted']
command_count = 0
for p in E.glob('*-command.json'):
    command = json.loads(p.read_text()).get('command',[])
    if command and command[0]=='gcloud':
        assert command[command.index('--account')+1]==ACCOUNT
        assert command[command.index('--project')+1]==PROJECT
        command_count += 1
stages = ['authorized_project_and_quota','scoped_net_budget_and_active_function','manual_stop_observed',
          'test_vm_and_disk_deleted','uncapped_guarded_l4_created','fresh_versioned_environments',
          'cuda_two_world_one_step','beamact3_data_sha_verified','real_data_act_50_step_readback',
          'credential_idle_lease_audit','own_lease_removed_no_other_jobs','l4_terminated']
funnel = dict(scope='one infrastructure candidate; not a C2 research gate',
    stages=[dict(gate=s,input=1,passed_cumulative=1,rejected=0) for s in stages],
    files=[dict(gate=s,input=1483,passed_cumulative=1483,rejected=0) for s in ['source_hashed','streamed','destination_sha_equal']],
    failed_setup_attempts=read('setup-rejections'),
    raw_paths=['gcp6:/home/ugrp/ugrp-sim/setup/',str(E.resolve())],
    reproduce=['python3 experiments/2026-10-16-gcp6setup/finalize.py',
               'ssh gcp6 /home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python /home/ugrp/ugrp-sim/setup/smoke.py NEW_RESULT.json'])
write(E/'funnel.json',funnel)
start=datetime.datetime.fromisoformat(vm['lastStartTimestamp'])
stop=datetime.datetime.fromisoformat(vm['lastStopTimestamp'])
summary=dict(schema='ugrp.gcp6setup.v1',ready=True,readiness_scope='GCP infrastructure, ACT environment and beamact3 dataset only',
    account=ACCOUNT,project=PROJECT,project_number='503325597974',billing_account='010CD7-4B991B-84AAC7',
    host='gcp6',instance=vm['name'],vm_status=vm['status'],machine='g2-standard-8',gpu='NVIDIA L4 x1',
    disk_gb=140,max_run_s=None,idle_s=1200,default_host='gcp2',default_account_unchanged=True,
    results_pooled=False,source_sha=read('probe-source')['source_sha'],dependencies=['PR #554','PR #558','PR #559'],
    first_use='beamact3 C2; coordinator note supersedes initial act16w interpretation',
    budget=dict(net_krw=1000,credits='INCLUDE_ALL_CREDITS',default_billing_iam_email_enabled=True,
                email_receipt_verified=False,manual_publish_stopping_s=stopping,
                manual_publish_terminated_s=observations[-1]['elapsed_s'],test_vm_and_disk_deleted=True),
    data=transfer,runs=[dict(name='budget_stop_test',status='PASS'),
         dict(name='mjwarp_import_batch_step',status='PASS',worlds=2,steps=1,sim_s_each=.002),
         dict(name='beamact3_environment_50steps',status='PASS',steps=50,readback_verified=True,
              scope='existing B adapter compatibility only; not C2; no model selected for research')],
    host_error=0,cap_end=0,failed_setup_attempts=read('setup-rejections'),
    verification=dict(nonphysics_tests='18 passed',guest=verification,recorded_gcp6_commands_checked=command_count,
        only_human_iam_member=ACCOUNT,first_project_api_calls=0,other_project_mutations=0,
        gcp2_l4_reference_read_only=True,gcp2_source_lease_created_and_removed=True,
        mac_physics=0,mac_render=0,mac_training=0,llm_calls=0),
    cost=dict(l4_start=vm['lastStartTimestamp'],l4_stop=vm['lastStopTimestamp'],l4_elapsed_s=(stop-start).total_seconds(),
              actual_billed=None,actual_billed_status='not retrieved',billing_delay_tested=False,
              persistent_after_stop=['140GB L4 disk','function/build/artifact storage']),
    rejection_table=str((E/'funnel.json').resolve()),
    remaining=['C2 implementation/managed trainer gcp6 admission and main training belong to beamact3 task',
               'Teacher/student/render/E2E gates not tested by setup','Actual billing and email receipt unverified',
               'PR CI/review/merge reported separately'])
write(ROOT/'summary.json',summary)
print(json.dumps(dict(ready=True,vm_status=vm['status'],stopping_s=stopping,l4_elapsed_s=(stop-start).total_seconds())))
