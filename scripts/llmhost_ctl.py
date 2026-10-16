"""Mac lifecycle for an isolated, opt-in self-host pilot. Default action is plan.

GPU start requires a fresh coordinator approval JSON; status/plan are read-only.
Stop only stops our systemd unit, leaving shared VM shutdown to existing guards.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import time

from scripts.llmhost_common import CONFIG, ROOT, check_alerts, settings


def cloud(*args, capture=True):
    c = settings()
    return subprocess.run(['gcloud', *args, '--account', c['account'], '--project', c['project']],
                          check=True, capture_output=capture, text=True)


def describe():
    c = settings()
    return json.loads(cloud('compute', 'instances', 'describe', c['instance'],
                           '--zone', c['zone'], '--format=json').stdout)


def guest(command):
    c = settings()
    return cloud('compute', 'ssh', 'ugrp@' + c['instance'], '--zone', c['zone'],
                 '--command', command).stdout


def validate_vm(vm):
    c = settings(); scheduling = vm.get('scheduling', {})
    if (vm.get('name') != c['instance'] or vm.get('machineType', '').rsplit('/', 1)[-1] != c['machine']
            or int(scheduling.get('maxRunDuration', {}).get('seconds', 0)) != 28800
            or scheduling.get('instanceTerminationAction') != 'STOP'
            or vm.get('serviceAccounts')):
        raise ValueError('vm_identity_8h_STOP_or_no_credentials_mismatch')


def approval(path, candidate):
    data = json.loads(Path(path).read_text())
    if (data.get('task') != 'llmhost' or data.get('candidate') != candidate
            or data.get('approved') is not True or data.get('gpu_exclusive') is not True
            or data.get('budget_stop_clear') is not True
            or not time.time() < data.get('expires_unix', 0)):
        raise ValueError('fresh_coordinator_approval_required')
    return data


def start(candidate, approval_file):
    c = settings(); approval(approval_file, candidate); check_alerts()
    vm = describe(); validate_vm(vm)
    # Existing budget-stop must be ACTIVE, and is never changed by this script.
    function = json.loads(cloud('functions', 'describe', 'budget-stop', '--gen2',
        '--region', 'us-central1', '--format=json').stdout)
    if (function.get('state') != 'ACTIVE'
            or function.get('buildConfig', {}).get('entryPoint') != 'stop_on_budget'
            or function.get('eventTrigger', {}).get('pubsubTopic') != 'projects/ugrp-sim-b-1014/topics/budget-stop'):
        raise ValueError('budget_stop_not_active_or_wrong_target')
    if vm['status'] == 'TERMINATED':
        cloud('compute', 'instances', 'start', c['instance'], '--zone', c['zone'])
    elif vm['status'] != 'RUNNING':
        raise ValueError('vm_transitional_state')
    # These probes are required before copying or launching anything on the L4.
    probe = r'''set -eu
test -z "$(find /home/ugrp/ugrp-sim/leases -maxdepth 1 -name '*.json' -print)"
test -z "$(nvidia-smi --query-compute-apps=pid --format=csv,noheader)"
systemctl is-active --quiet ugrp-idle-guard.timer
test -x /usr/local/sbin/ugrp-idle-guard
test -z "$(pgrep -u ugrp -f '[p]ython|[m]ujoco|[f]fmpeg' || true)"
command -v docker
docker info --format '{{.ServerVersion}}'
'''
    guest(probe)
    remote = c['remote_root']; model = c['models'][candidate]
    # Stage models on the CPU host ahead of time. This transfer needs no VM token.
    guest(shlex.join(['mkdir', '-p', remote]))
    # Mac relays verified CPU-host weights to the free L4. No SSH/HF credentials
    # are placed on either VM; no giant temporary model is written on the Mac.
    relative = f"models/{candidate}/{model['revision']}"
    destination = remote + '/' + relative
    exists = guest('test -d ' + shlex.quote(destination) + ' && echo present || true').strip()
    if exists != 'present':
        needed = sum(item['bytes'] for item in model['files'])
        free = int(guest("python3 -c 'import shutil; print(shutil.disk_usage(\"/home/ugrp/ugrp-sim\").free)'"))
        if free < needed + 50 * 1024**3: raise ValueError('L4_disk_reserve_50GiB')
        producer = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', 'gcp2',
            shlex.join(['tar', '-C', remote, '-cf', '-', relative])], stdout=subprocess.PIPE)
        try:
            args = ['gcloud', 'compute', 'ssh', 'ugrp@'+c['instance'], '--zone', c['zone'],
                    '--account', c['account'], '--project', c['project'],
                    '--command', shlex.join(['tar', '-C', remote, '-xf', '-'])]
            subprocess.run(args, stdin=producer.stdout, check=True)
        finally:
            producer.stdout.close()
            if producer.wait() != 0: raise ValueError('CPU_to_L4_transfer_failed')
    cloud('compute', 'scp', str(CONFIG), str(ROOT / 'scripts/llmhost_guest.py'),
          'ugrp@' + c['instance'] + ':' + remote + '/', '--zone', c['zone'])
    cmd = ['sudo', 'systemd-run', '--unit=ugrp-llmhost', '--collect',
           '--property=User=ugrp', '--property=RuntimeMaxSec=28800',
           '--property=ExecStopPost=-/usr/bin/docker stop --time 30 ugrp-llmhost',
           '--property=KillMode=control-group', 'python3', remote + '/llmhost_guest.py',
           remote + '/llmhost.json', candidate]
    guest(shlex.join(cmd))
    print('Submitted; inspect status and /health before any benchmark. No automatic retry/restart.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('plan', 'status', 'start', 'stop', 'tunnel'), nargs='?', default='plan')
    p.add_argument('--candidate', choices=settings()['models'], default='31b_awq')
    p.add_argument('--coordinator-approval', type=Path)
    a = p.parse_args(); c = settings()
    if a.action == 'plan':
        print(json.dumps(dict(enabled=c['enabled'], gpu_started=False, candidate=a.candidate,
            requires=['coordinator approval', 'clear endpoint alerts', 'exclusive free L4',
                      'budget-stop active', 'verified weights on L4', 'same llmalt corpus'],
            start=f'python3 -m scripts.llmhost_ctl start --candidate {a.candidate} --coordinator-approval /tmp/llmhost-approval.json'), indent=2))
    elif a.action == 'status':
        vm = describe(); validate_vm(vm)
        print(json.dumps(dict(name=vm['name'], status=vm['status'], scheduling=vm['scheduling'])))
        if vm['status'] == 'RUNNING':
            print(guest('systemctl show ugrp-llmhost --property=ActiveState,SubState; cat /home/ugrp/ugrp-sim/llmhost/last-stop.json 2>/dev/null || true'))
    elif a.action == 'start':
        if not a.coordinator_approval: p.error('--coordinator-approval is required; GPU launch is not authorized yet')
        start(a.candidate, a.coordinator_approval)
    elif a.action == 'stop':
        # Never stop a shared VM, even when another task forgot its lease.
        print(guest('sudo systemctl stop ugrp-llmhost; systemctl show ugrp-llmhost --property=ActiveState,SubState'))
    else:
        cloud('compute', 'ssh', 'ugrp@' + c['instance'], '--zone', c['zone'], '--',
              '-N', '-o', 'ExitOnForwardFailure=yes', '-L', '127.0.0.1:18080:127.0.0.1:8000', capture=False)


if __name__ == '__main__': main()
