"""Rebuild the setup summary/funnel/hash manifest from retrieved evidence; no cloud calls."""
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
E = ROOT/'evidence'


def read(name):
    return json.loads((E/(name+'.json')).read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')


final = read('instances-final-after-guard')
assert len(final)==1 and final[0]['name']=='ugrp-act-l4-gcp3' and final[0]['status']=='TERMINATED'
assert read('instances-after-test')==read('disks-after-test')==[]
assert read('smoke-result')['status']=='PASS'
assert all(read('verification').values())
assert read('guard-final-verification')['guard_exact']
assert read('guard-final-stop')['returncode']==0
assert read('gcp2-function-reference')==read('gcp2-function-after')
assert read('gcp2-topic-policy-reference')==read('gcp2-topic-policy-after')
assert read('function-active')['serviceConfig']['environmentVariables']['TARGET_PROJECT']=='ugrp-sim-c-1016'
source = ROOT/'function/main.py'
assert source.read_bytes()==(ROOT.parent/'2026-10-15-gcp2setup/evidence/budget-stop-main.py').read_bytes()

windows=[]
for label, vm in [('install_and_smoke',read('instances-final')[0]),('idle_guard_final_boot',final[0])]:
    start=datetime.datetime.fromisoformat(vm['lastStartTimestamp'])
    stop=datetime.datetime.fromisoformat(vm['lastStopTimestamp'])
    windows.append(dict(label=label,start=vm['lastStartTimestamp'],stop=vm['lastStopTimestamp'],elapsed_s=(stop-start).total_seconds()))
elapsed=sum(w['elapsed_s'] for w in windows)
observations=read('test-observations')
storage=read('mac-storage-admission')
funnel=dict(scope='one infrastructure candidate; not a teacher/mission success gate',
            stages=[dict(gate=x,input=1,passed_cumulative=1,rejected=0) for x in (
                'authorized_project','scoped_budget_and_active_function','manual_stop_observed',
                'test_vm_and_disk_deleted','guarded_l4_created','cuda_two_world_one_step',
                'final_idle_guard_boot_and_credential_audit','own_lease_removed_no_other_processes','l4_terminated')],
            worlds=[dict(gate=x,input=2,passed_cumulative=2,rejected=0) for x in ('requested','stepped','finite_and_time_advanced')],
            failed_setup_attempts=read('setup-rejections')['rejections'],
            raw_paths=['gcp3:/home/ugrp/ugrp-sim/setup/',str(E.resolve())],
            reproduce=['python3 experiments/2026-10-16-gcp3setup/finalize.py',
                       'gcp3:/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python /home/ugrp/ugrp-sim/setup/smoke.py NEW_RESULT.json'])
write(E/'funnel.json',funnel)
manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.rglob('*'))
          if p.is_file() and '__pycache__' not in p.parts and p.name not in ('summary.json','SHA256.json')}
write(E/'SHA256.json',manifest)
write(ROOT/'summary.json',dict(schema='ugrp.gcp3setup.v1',ready=True,readiness_scope='GCP infrastructure only',
    project='ugrp-sim-c-1016',account='changmin5781@gmail.com',default_host='gcp2',host='gcp3',
    instance='ugrp-act-l4-gcp3',machine='g2-standard-8',gpu='NVIDIA L4 x1',disk_gb=140,
    vm_status=final[0]['status'],max_run_s=28800,termination_action='STOP',idle_s=1200,
    source_sha=read('probe-source')['source_sha'],results_pooled=False,
    budget=dict(net_krw=1000,credits='INCLUDE_ALL_CREDITS',filter_projects=['projects/443356522325'],
                default_billing_iam_email_enabled=True,email_delivery_tested=False,
                manual_publish_stopping_s=next(x['elapsed_s'] for x in observations if x['status']=='STOPPING'),
                manual_publish_terminated_s=observations[-1]['elapsed_s'],test_vm_and_disk_deleted=True),
    runs=[dict(name='budget_stop_test',status='PASS',host='gcp3-project',raw=str((E/'test-observations.json').resolve())),
          dict(name='mjwarp_import_batch_step',status='PASS',nworld=2,steps=1,sim_s_per_world=.002,raw='gcp3:/home/ugrp/ugrp-sim/setup/smoke-result.json'),
          dict(name='final_idle_guard_boot',status='PASS',raw='gcp3:/home/ugrp/ugrp-sim/setup/guest-audit-final.json')],
    host_error=0,cap_end=0,failed_setup_attempts=read('setup-rejections')['rejections'],
    verification=dict(nonphysics_tests='11 passed',gcp2_function_and_topic_unchanged=True,guest=read('verification'),
                      final_guard=read('guard-final-verification'),retrieved_hashes_verified=True,
                      other_work_before_stop=False,own_leases_remaining=0,mac_physics=0,mac_render=0,llm_calls=0,training=0),
    cost=dict(l4_windows=windows,l4_elapsed_s=elapsed,planning_rate_usd_h=1.096,
              planning_estimate_usd=elapsed/3600*1.096,rate_status='historical planning assumption from simalt5/work-log.md; current Seoul price not verified',
              actual_billed=None,actual_billed_status='billing aggregation/invoice not retrieved; not a zero-cost claim',
              excluded=['e2-micro test','persistent disk 140GB','build/function/artifact storage','network','tax','credits','currency conversion']),
    next_batch_ready=False,remaining=['Mac storage admission fails: projected free below 20GiB; no cleanup or bypass performed',
                                    'Research runner gcp2-specific host pins/scene-camera/teacher-student gates need separate work',
                                    'Existing Gemma endpoint price alert blocks new LLM batches',
                                    'PR CI/review/merge are separate from infrastructure readiness'],
    mac_storage=storage,rejection_table=str((E/'funnel.json').resolve()),
    manifest=dict(path='evidence/SHA256.json',sha256=hashlib.sha256((E/'SHA256.json').read_bytes()).hexdigest()),
    originals='gcp3:/home/ugrp/ugrp-sim/setup/; raw install/smoke logs and freeze retained on persistent disk',
    github_status='branch/PR publication reported separately; no merge claimed'))
print(json.dumps(dict(ready=True,scope='infrastructure',vm_status=final[0]['status'],l4_elapsed_s=elapsed,
                      planning_estimate_usd=elapsed/3600*1.096,manifest_files=len(manifest))))
