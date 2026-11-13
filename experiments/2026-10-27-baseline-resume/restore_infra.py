"""Resume infrastructure only; no simulation, credentials, or frozen-file changes."""
from pathlib import Path
import datetime as dt
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parent
ACCOUNT = 'kcm5781kcm5781@gmail.com'
PROJECT = 'ugrp-sim-f-1016'
SNAPSHOT = 'ugrp-gcp6-baseline-20261026t1850'
ZONE = 'asia-northeast3-b'
DISK = 'ugrp-gcp6-baseline-20261027'
INSTANCE = 'ugrp-act-l4-gcp6'


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def cloud(label, args):
    cmd = ['gcloud', *args, '--account', ACCOUNT, '--project', PROJECT, '--format=json', '--quiet']
    start = utc()
    result = subprocess.run(cmd, capture_output=True, text=True)
    record = {'start_utc': start, 'end_utc': utc(), 'command': cmd,
              'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    with (ROOT / (label + '.command.json')).open('x') as stream:
        json.dump(record, stream, indent=2)
    print(utc(), label, result.returncode, flush=True)
    return result


def main():
    count = 0
    while True:
        result = cloud(f'snapshot-poll-{count:03d}', ['compute', 'snapshots', 'describe', SNAPSHOT])
        if result.returncode == 0 and json.loads(result.stdout)['status'] == 'READY':
            break
        count += 1
        time.sleep(30)
    result = cloud('restore-disk-b-02', ['compute', 'disks', 'create', DISK,
        '--source-snapshot=' + SNAPSHOT, '--zone=' + ZONE, '--type=pd-balanced', '--size=260GB'])
    if result.returncode:
        raise SystemExit(result.returncode)
    # User: 10-minute retry cadence. The prior start operation began at 18:45:45 UTC.
    earliest = dt.datetime.fromisoformat('2026-10-26T18:55:45+00:00').timestamp()
    while time.time() < earliest:
        time.sleep(min(30, earliest - time.time()))
    result = cloud('create-vm-b-01', ['compute', 'instances', 'create', INSTANCE,
        '--zone=' + ZONE, '--machine-type=g2-standard-8',
        '--accelerator=type=nvidia-l4,count=1', '--maintenance-policy=TERMINATE',
        '--provisioning-model=STANDARD', '--no-service-account', '--no-scopes',
        '--disk=name=' + DISK + ',boot=yes,auto-delete=no,interface=NVME',
        '--metadata-from-file=startup-script=' + str(ROOT / 'original-startup-script.txt') +
            ',ssh-keys=' + str(ROOT / 'original-ssh-keys.txt'),
        '--metadata=block-project-ssh-keys=true', '--labels=purpose=ugrp-sim,run=baseline-20261027'])
    if result.returncode:
        (ROOT / 'infra-next-action.json').write_text(json.dumps({
            'status': 'INFRASTRUCTURE_RETRY_REQUIRED', 'last_attempt_utc': utc(),
            'next_retry_not_before_unix': time.time() + 600, 'failed_zone': ZONE,
            'error': result.stderr, 'protocol_change': False}, indent=2))
        raise SystemExit(result.returncode)
    instance = json.loads(result.stdout)[0]
    (ROOT / 'restored-instance.json').write_text(json.dumps(instance, indent=2))
    ip = instance['networkInterfaces'][0]['accessConfigs'][0]['natIP']
    config = ('Host gcp6-baseline\n  HostName ' + ip + '\n  User ugrp\n'
              '  IdentityFile /home/ubuntu/.ssh/ugrp_gcp6\n  IdentitiesOnly yes\n'
              '  StrictHostKeyChecking accept-new\n  ServerAliveInterval 30\n'
              '  ServerAliveCountMax 4\n')
    (ROOT / 'ssh_config').write_text(config)
    (ROOT / 'infra-ready.json').write_text(json.dumps({'utc': utc(), 'zone': ZONE,
        'instance': INSTANCE, 'instance_id': instance['id'], 'ip': ip,
        'status': instance['status'], 'protocol_change': False,
        'original_vm_and_disk_preserved': True}, indent=2))
    print(utc(), 'INFRASTRUCTURE_READY', ZONE, ip, flush=True)


if __name__ == '__main__':
    main()
