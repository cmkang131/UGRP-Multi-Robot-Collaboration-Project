"""Only run after gcp5 budget-stop is ACTIVE; deletes only its named test VM/disk."""
import json
import subprocess
import time

from ops import ACCOUNT, EVIDENCE, PROJECT, cloud

VM = 'ugrp-budget-test-gcp5'
ZONE = 'asia-northeast3-a'
fn = cloud('function-active', 'functions', 'describe', 'budget-stop', '--gen2', '--region=us-central1')
assert fn['state'] == 'ACTIVE'
assert fn['serviceConfig']['environmentVariables']['TARGET_PROJECT'] == PROJECT


def state():
    return subprocess.check_output(['gcloud', 'compute', 'instances', 'describe', VM, '--zone', ZONE,
                                    '--account', ACCOUNT, '--project', PROJECT, '--format=value(status)'], text=True).strip()


assert state() == 'RUNNING'
payload = dict(costAmount=1000, budgetAmount=1000, currencyCode='KRW', budgetDisplayName='gcp5 manual stop test')
(EVIDENCE/'test-payload.json').write_text(json.dumps(payload, indent=2)+'\n')
start = time.monotonic()
observations = [dict(elapsed_s=0, status='RUNNING')]
cloud('test-publish', 'pubsub', 'topics', 'publish', 'budget-stop', '--message='+json.dumps(payload))
# This is an infrastructure watchdog, not a planner/behavior wall-clock cap.
while time.monotonic()-start < 240:
    current = state()
    observations.append(dict(elapsed_s=time.monotonic()-start, status=current))
    (EVIDENCE/'test-observations.json').write_text(json.dumps(observations, indent=2)+'\n')
    if current == 'TERMINATED':
        break
    time.sleep(1)
else:
    raise RuntimeError('Budget test timed out; do not create L4')
assert any(x['status'] == 'STOPPING' for x in observations)
cloud('test-function-log','logging','read','resource.type="cloud_run_revision" AND resource.labels.service_name="budget-stop" AND (jsonPayload.action="stop_all" OR textPayload:"stop_all")','--limit=10')
cloud('test-vm-delete','compute','instances','delete',VM,'--zone='+ZONE,'--delete-disks=all')
instances = cloud('instances-after-test','compute','instances','list','--filter=name='+VM)
disks = cloud('disks-after-test','compute','disks','list','--filter=name='+VM)
assert instances == disks == []
print(json.dumps(dict(stopping_s=next(x['elapsed_s'] for x in observations if x['status']=='STOPPING'),
                      terminated_s=observations[-1]['elapsed_s'], deleted_vm_and_disk=True)))
