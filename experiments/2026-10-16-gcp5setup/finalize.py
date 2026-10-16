"""Build a concise setup receipt only after all live gates and guarded stop pass."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
from ops import ROOT, EVIDENCE, PROJECT


def read(name):
    return json.loads((EVIDENCE/name).read_text())


verification = read('verification.json')
assert verification['other_jobs_before_stop'] is False
assert all(v for k,v in verification.items() if k != 'other_jobs_before_stop')
vm, warp, training, dataset = [read(n) for n in
    ('l4-final.json', 'smoke-result.json', 'training-summary.json', 'dataset-verification.json')]
assert vm['status'] == 'TERMINATED'
assert warp['status'] == training['status'] == dataset['status'] == 'PASS'
assert training['steps_completed'] == 50 and training['readback_verified']
assert dataset['files'] == len(read('dataset-sha256.json')['files'])
assert read('instances-after-test.json') == read('disks-after-test.json') == []
observations = read('test-observations.json')
budget = read('budget-final.json')
assert budget['budgetFilter']['projects'] == ['projects/1034909621664']
assert budget['budgetFilter']['creditTypesTreatment'] == 'INCLUDE_ALL_CREDITS'
assert budget['amount']['specifiedAmount'] == dict(currencyCode='KRW', units='1000')
assert not budget['notificationsRule'].get('disableDefaultIamRecipients', False)
fn = read('function-final.json')
assert fn['state'] == 'ACTIVE' and fn['serviceConfig']['environmentVariables']['TARGET_PROJECT'] == PROJECT
stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
funnel_path = EVIDENCE/'funnel.json'


def stage(name, count, raw, command):
    return dict(gate=name, entered=count, cumulative_pass=count, rejected=0,
                reason_category='none', blocking_object='not_applicable_infrastructure',
                minimum_gap='not_measured_infrastructure', raw=raw, reproduce=command)


funnel = dict(schema='ugrp.gcp_setup.funnel.v1', created_utc=stamp,
    candidate_pipeline=[
        stage('project_quota', 1, str(EVIDENCE/'global-quota.json'), 'gcloud compute project-info describe --account changmin5781@gmail.com --project '+PROJECT),
        stage('budget_stop', 1, str(EVIDENCE/'test-observations.json'), 'Read test_budget.py; destructive replay requires a fresh named trial VM, never the finished setup'),
        stage('test_vm_disk_deleted', 1, str(EVIDENCE/'disks-after-test.json'), 'gcloud compute disks list --filter=name=ugrp-budget-test-gcp5 --account changmin5781@gmail.com --project '+PROJECT),
        stage('mjwarp_cuda_step', 1, str(EVIDENCE/'smoke-result.json'), "ssh gcp5 '/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python /home/ugrp/ugrp-sim/setup/smoke.py /home/ugrp/ugrp-sim/setup/NEW-result.json'"),
        stage('act_versions_exact', 1, str(EVIDENCE/'act-freeze.txt'), 'Compare set(act-freeze.txt lines) with act-freeze-reference.txt'),
        stage('act_50_save_reload', 1, str(EVIDENCE/'training-summary.json'), "ssh gcp5 '/home/ugrp/ugrp-rl1b-act-env/bin/python /home/ugrp/ugrp-sim/setup/training_smoke.py /home/ugrp/ugrp-sim/setup/beamact3-reference /home/ugrp/ugrp-sim/setup/training-smoke-NEW'"),
        stage('guarded_stop', 1, str(EVIDENCE/'verification.json'), 'python3 scripts/gcpctl.py status gcp5')],
    file_pipeline=[stage(k, dataset['files'], str(EVIDENCE/'dataset-sha256.json'),
        'Read transfer_dataset.py verification loop; compare all SHA256 without modifying source')
        for k in ('source_sha', 'allowlisted_transfer', 'destination_sha')],
    event_pipeline=[stage(k, 1, str(EVIDENCE/'test-observations.json'),
        'Read test-observations.json and test-function-log.json')
        for k in ('manual_pubsub', 'function_stop_all', 'vm_stopping')],
    version_candidates_pipeline=[dict(gate='exact_ACT_freeze', entered=2, cumulative_pass=1, rejected=1, reason_category='version_mismatch', package='torchcodec', blocking_object='not_applicable_infrastructure', minimum_gap='not_measured_infrastructure', raw=str(EVIDENCE/'environment-rejection-table.json'), reproduce='Compare initial PyTorch-index selection and pin_act_codec.sh repair')],
    frames=0, scope='infrastructure/environment only; not C2 or teacher/student acceptance')
funnel_path.write_text(json.dumps(funnel, indent=2)+'\n')
summary = dict(status='READY', created_utc=stamp, project=PROJECT, account='changmin5781@gmail.com',
    source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    stacked_dependencies=[554, 558, 559], default_host='gcp2',
    rejection_table=str(funnel_path.resolve()),
    budget=dict(net_monthly_krw=1000, project_filter=budget['budgetFilter']['projects'],
        default_billing_iam_email_enabled=True, email_receipt_verified=False,
        stopping_s=next(x['elapsed_s'] for x in observations if x['status']=='STOPPING'),
        terminated_s=observations[-1]['elapsed_s'], test_vm_disk_deleted=True,
        scope='manual Pub/Sub onward; billing ingestion latency not measured'),
    vm=dict(alias='gcp5', instance=vm['name'], machine='g2-standard-8', gpu='NVIDIA L4',
        disk_gb=140, status=vm['status'], runtime_cap=None, idle_guard_minutes=20,
        service_accounts=[], dedicated_key_private_on_mac_only=True),
    dataset=dataset, act_reference_packages=len((EVIDENCE/'act-freeze-reference.txt').read_text().splitlines()),
    versions_match=True, training=training, mjwarp=warp,
    resolved_issues=['torchcodec extra-index local CUDA version corrected to exact source PyPI version'],
    runs=[dict(name='initial-act-version-check', status='REJECTED', raw=str(EVIDENCE/'environment-rejection-table.json')),
          dict(name='corrected-act-version-check', status='PASS', raw=str(EVIDENCE/'act-freeze.txt')),
          dict(name='budget-manual-stop', status='PASS', raw=str(EVIDENCE/'test-observations.json')),
          dict(name='mjwarp-two-world-one-step', status='PASS', raw=str(EVIDENCE/'smoke-result.json')),
          dict(name='act-50-step-save-reload', status='PASS', raw='gcp5:/home/ugrp/ugrp-sim/setup/training-smoke-v1')],
    verification=verification, other_projects_cost_devices_modified=False, gcp1_accessed=False,
    raw_weights_retained='gcp5:/home/ugrp/ugrp-sim/setup/training-smoke-v1',
    remaining=['C2 production host admission belongs to beamact3 branch; no C2 training run here',
               'No student/teacher/mission or render gate measured',
               'Actual billing email receipt and ingestion lag not tested; stopped VM disk/build storage remain billable'])
(ROOT/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
        and p.name not in ('SHA256.json', 'ops-alert.md')}
(EVIDENCE/'SHA256.json').write_text(json.dumps(hashes, indent=2)+'\n')
print(json.dumps(dict(status=summary['status'], test_stop_s=summary['budget']['stopping_s'],
                      training_steps=training['steps_completed'], vm=vm['status'])), flush=True)
