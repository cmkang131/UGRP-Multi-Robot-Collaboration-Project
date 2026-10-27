"""Allocate exactly one restored gcp6 VM after the user-required retry interval."""
from pathlib import Path
import datetime as dt
import json
import time
from restore_infra import cloud, ROOT


def main():
    # Last original-zone start attempt ended at approximately 18:56 UTC.
    # No GPU is allocated while this controller waits for the 10-minute cadence.
    not_before = dt.datetime.fromisoformat('2026-10-26T19:06:00+00:00').timestamp()
    while time.time() < not_before:
        time.sleep(min(30, not_before - time.time()))
    disk_record = json.loads((ROOT / 'restore-disk-b-03.command.json').read_text())
    if disk_record['returncode']:
        raise SystemExit('restored disk not ready')
    zone = 'asia-northeast3-b'
    disk = 'ugrp-gcp6-baseline-20261027'
    result = cloud('create-vm-b-01', ['compute', 'instances', 'create', 'ugrp-act-l4-gcp6',
        '--zone=' + zone, '--machine-type=g2-standard-8',
        '--accelerator=type=nvidia-l4,count=1', '--maintenance-policy=TERMINATE',
        '--provisioning-model=STANDARD', '--no-service-account', '--no-scopes',
        '--disk=name=' + disk + ',boot=yes,auto-delete=no,interface=NVME',
        '--metadata-from-file=startup-script=' + str(ROOT / 'original-startup-script.txt') +
            ',ssh-keys=' + str(ROOT / 'original-ssh-keys.txt'),
        '--metadata=block-project-ssh-keys=true', '--labels=purpose=ugrp-sim,run=baseline-20261027'])
    if result.returncode:
        raise SystemExit(result.returncode)
    instance = json.loads(result.stdout)[0]
    (ROOT / 'restored-instance.json').write_text(json.dumps(instance, indent=2))
    ip = instance['networkInterfaces'][0]['accessConfigs'][0]['natIP']
    (ROOT / 'ssh_config').write_text('Host gcp6-baseline\n  HostName ' + ip +
        '\n  User ugrp\n  IdentityFile /home/ubuntu/.ssh/ugrp_gcp6\n  IdentitiesOnly yes\n'
        '  StrictHostKeyChecking accept-new\n  ServerAliveInterval 30\n  ServerAliveCountMax 4\n')
    ready = {'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'zone': zone,
        'instance': instance['name'], 'instance_id': instance['id'], 'ip': ip,
        'status': instance['status'], 'protocol_change': False,
        'original_vm_and_disk_preserved': True}
    (ROOT / 'infra-ready.json').write_text(json.dumps(ready, indent=2))
    print(json.dumps(ready), flush=True)


if __name__ == '__main__':
    main()
