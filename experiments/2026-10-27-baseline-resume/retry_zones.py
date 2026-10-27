"""Keep trying authorized L4 zones. Never launches a workload or edits registration."""
import datetime as dt
import json
import time
from pathlib import Path
from restore_infra import ROOT, cloud

DISK = 'ugrp-gcp6-baseline-20261027'
SNAPSHOT = 'ugrp-gcp6-baseline-20261026t1850'
VM = 'ugrp-act-l4-gcp6'
ZONES = ['asia-northeast1-b', 'asia-northeast1-c',
         'us-central1-a', 'us-central1-b', 'us-central1-c',
         'asia-northeast3-a', 'asia-northeast3-b', 'asia-northeast1-a']


def wait_until(until):
    while time.time() < until:
        time.sleep(min(30, until - time.time()))


def save_ready(instance, zone):
    (ROOT / 'restored-instance.json').write_text(json.dumps(instance, indent=2))
    ip = instance['networkInterfaces'][0]['accessConfigs'][0]['natIP']
    (ROOT / 'ssh_config').write_text('Host gcp6-baseline\n  HostName ' + ip +
        '\n  User ugrp\n  IdentityFile /home/ubuntu/.ssh/ugrp_gcp6\n  IdentitiesOnly yes\n'
        '  StrictHostKeyChecking accept-new\n  ServerAliveInterval 30\n  ServerAliveCountMax 4\n')
    info = {'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'zone': zone,
            'instance': instance['name'], 'instance_id': instance['id'], 'ip': ip,
            'status': instance['status'], 'protocol_change': False,
            'original_vm_and_disk_preserved': True,
            'original_vm_restarted': zone == 'asia-northeast3-a'}
    (ROOT / 'infra-ready.json').write_text(json.dumps(info, indent=2))
    print('INFRASTRUCTURE_READY', json.dumps(info), flush=True)


def ensure_disk(zone, label):
    region = zone.rsplit('-', 1)[0]
    disks_result = cloud(label + '-disks', ['compute', 'disks', 'list', '--filter=name=' + DISK])
    if disks_result.returncode:
        return False
    disks = json.loads(disks_result.stdout)
    same = [d for d in disks if d['zone'].endswith('/' + zone)]
    if same:
        return same[0]['status'] == 'READY' and not same[0].get('users')
    # A new region's 260GB quota admits one restored disk. Remove only our own
    # unattached, never-booted duplicate from another zone in that region.
    # The original disk has a different name and cannot match this selection.
    for disk in disks:
        old_zone = disk['zone'].rsplit('/', 1)[-1]
        if old_zone.rsplit('-', 1)[0] != region:
            continue
        if disk.get('users'):
            print('RESTORE_DISK_IN_USE', old_zone, flush=True)
            return False
        deleted = cloud(label + '-delete-unused-' + old_zone, [
            'compute', 'disks', 'delete', DISK, '--zone=' + old_zone])
        if deleted.returncode:
            return False
    made = cloud(label + '-restore-disk', ['compute', 'disks', 'create', DISK,
        '--source-snapshot=' + SNAPSHOT, '--zone=' + zone, '--type=pd-balanced', '--size=260GB'])
    return made.returncode == 0


def main():
    earliest = dt.datetime.fromisoformat('2026-10-26T19:26:20+00:00').timestamp()
    attempt = 0
    while True:
        zone = ZONES[attempt % len(ZONES)]
        label = f'zone-retry-{attempt:03d}-' + zone
        # Existing cost-stop guard is never disabled or bypassed on a zone change.
        cost = cloud(label + '-cost', ['logging', 'read',
            'resource.type="cloud_run_revision" AND resource.labels.service_name="budget-stop" AND jsonPayload.costAmount:*',
            '--freshness=2h', '--limit=1'])
        if cost.returncode == 0:
            logs = json.loads(cost.stdout)
            if logs:
                value = logs[0].get('jsonPayload', {})
                if float(value.get('costAmount', 0)) >= float(value.get('budgetAmount', 1000)):
                    (ROOT / 'budget-stop-confirmed.json').write_text(json.dumps(logs[0], indent=2))
                    raise SystemExit('COST_STOP_CONFIRMED; no alternate-host bypass')
        ready_disk = zone == 'asia-northeast3-a' or ensure_disk(zone, label)
        wait_until(earliest)
        started = time.time()
        if ready_disk:
            if zone == 'asia-northeast3-a':
                result = cloud(label + '-allocate', ['compute', 'instances', 'start', VM, '--zone=' + zone])
            else:
                result = cloud(label + '-allocate', ['compute', 'instances', 'create', VM,
                    '--zone=' + zone, '--machine-type=g2-standard-8',
                    '--accelerator=type=nvidia-l4,count=1', '--maintenance-policy=TERMINATE',
                    '--provisioning-model=STANDARD', '--no-service-account', '--no-scopes',
                    '--disk=name=' + DISK + ',boot=yes,auto-delete=no,interface=NVME',
                    '--metadata-from-file=startup-script=' + str(ROOT / 'original-startup-script.txt') +
                        ',ssh-keys=' + str(ROOT / 'original-ssh-keys.txt'),
                    '--metadata=block-project-ssh-keys=true', '--labels=purpose=ugrp-sim,run=baseline-20261027'])
            entry = {'zone': zone, 'start_utc': dt.datetime.fromtimestamp(started, dt.timezone.utc).isoformat(),
                     'returncode': result.returncode, 'record': label + '-allocate.command.json'}
            with (ROOT / 'infra-attempts.jsonl').open('a') as stream:
                stream.write(json.dumps(entry) + '\n')
            if result.returncode == 0:
                got = cloud(label + '-running', ['compute', 'instances', 'describe', VM, '--zone=' + zone])
                if got.returncode == 0 and json.loads(got.stdout)['status'] == 'RUNNING':
                    save_ready(json.loads(got.stdout), zone)
                    return
        else:
            print('INFRASTRUCTURE_PREPARATION_RETRY', zone, flush=True)
        earliest = started + 600
        attempt += 1


if __name__ == '__main__':
    main()
