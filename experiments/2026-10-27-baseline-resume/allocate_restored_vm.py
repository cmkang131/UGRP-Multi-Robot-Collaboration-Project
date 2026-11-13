"""One recorded infrastructure attempt, with a UTC not-before time."""
import argparse
import datetime as dt
import json
import time
from restore_infra import ROOT, cloud


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--zone', required=True)
    p.add_argument('--not-before', required=True)
    p.add_argument('--label', required=True)
    p.add_argument('--disk-record', required=True)
    a = p.parse_args()
    until = dt.datetime.fromisoformat(a.not_before).timestamp()
    while time.time() < until:
        time.sleep(min(30, until - time.time()))
    disk = json.loads((ROOT / a.disk_record).read_text())
    if disk['returncode']:
        raise SystemExit('restored disk creation did not pass')
    result = cloud(a.label, ['compute', 'instances', 'create', 'ugrp-act-l4-gcp6',
        '--zone=' + a.zone, '--machine-type=g2-standard-8',
        '--accelerator=type=nvidia-l4,count=1', '--maintenance-policy=TERMINATE',
        '--provisioning-model=STANDARD', '--no-service-account', '--no-scopes',
        '--disk=name=ugrp-gcp6-baseline-20261027,boot=yes,auto-delete=no,interface=NVME',
        '--metadata-from-file=startup-script=' + str(ROOT / 'original-startup-script.txt') +
            ',ssh-keys=' + str(ROOT / 'original-ssh-keys.txt'),
        '--metadata=block-project-ssh-keys=true', '--labels=purpose=ugrp-sim,run=baseline-20261027'])
    if result.returncode:
        raise SystemExit(result.returncode)
    vm = json.loads(result.stdout)[0]
    (ROOT / 'restored-instance.json').write_text(json.dumps(vm, indent=2))
    ip = vm['networkInterfaces'][0]['accessConfigs'][0]['natIP']
    (ROOT / 'ssh_config').write_text('Host gcp6-baseline\n  HostName ' + ip +
        '\n  User ugrp\n  IdentityFile /home/ubuntu/.ssh/ugrp_gcp6\n  IdentitiesOnly yes\n'
        '  StrictHostKeyChecking accept-new\n  ServerAliveInterval 30\n  ServerAliveCountMax 4\n')
    record = {'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'zone': a.zone,
        'instance': vm['name'], 'instance_id': vm['id'], 'ip': ip,
        'status': vm['status'], 'protocol_change': False,
        'original_vm_and_disk_preserved': True}
    (ROOT / 'infra-ready.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
