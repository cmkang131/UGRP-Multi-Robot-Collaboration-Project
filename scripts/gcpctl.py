"""Configured GCP simulation host lifecycle (gcp2 by default).

Every gcloud call names the account and project. Simulation VMs have a 24 h cap, STOP on
termination, no service account (no cloud credentials on the VM) and the 20-minute
idle guard from gcp_idle_guard_startup.sh. Stop refuses while a lease or a simulation
process exists. Cost cut-off: the existing budget -> Pub/Sub -> budget-stop function
stops every VM in the project; this module does not touch it.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

CONFIG = Path(os.environ.get('UGRP_GCP_CONFIG', Path(__file__).resolve().parents[1] / 'configs/gcp_hosts.json'))
SETTINGS = json.loads(CONFIG.read_text())
GCP_HOSTS = SETTINGS['hosts']
DEFAULT_HOST = SETTINGS['default_host']
STARTUP = Path(__file__).with_name('gcp_idle_guard_startup.sh')


def target(host):
    if host not in GCP_HOSTS:
        raise ValueError('Unknown GCP host')
    cfg = GCP_HOSTS[host]
    return tuple(cfg[key] for key in ('instance', 'zone', 'machine', 'disk_type'))


def require_lifecycle(host):
    target(host)
    if not GCP_HOSTS[host]['lifecycle_enabled']:
        raise RuntimeError(f'{host}: lifecycle disabled; preserve the stopped VM and disk after budget stop')


def gcloud(*args, capture=False, host=DEFAULT_HOST):
    cfg = GCP_HOSTS[host]
    command = ['gcloud', *args, '--account', cfg['account'], '--project', cfg['project']]
    return subprocess.run(command, check=True, capture_output=capture, text=capture)


def create_command(host, public_key, machine=None, image=None):
    require_lifecycle(host)
    cfg = GCP_HOSTS[host]
    name, zone, default_machine, disk = target(host)
    image_args = ['--image', image or cfg['image']] if image or cfg.get('image') else [
        '--image-family', cfg['image_family'], '--image-project', cfg['image_project']]
    # 24h: 2026-10-15 user decision, inherited by gcp2. 400GB: see gcp2setup disk plan.
    return ['gcloud', 'compute', 'instances', 'create', name, '--account', cfg['account'],
            '--project', cfg['project'], '--zone', zone,
            '--machine-type', machine or default_machine, *image_args,
            '--boot-disk-size', f"{cfg['disk_gb']}GB", '--boot-disk-type', disk,
            '--provisioning-model=STANDARD',
            f"--max-run-duration={cfg['max_run_duration']}", '--instance-termination-action=STOP',
            '--no-service-account', '--no-scopes',
            '--metadata-from-file', f'startup-script={STARTUP}',
            '--metadata', f'ssh-keys=ugrp:{public_key},block-project-ssh-keys=true',
            '--labels', 'purpose=ugrp-sim']


def status(host):
    name, zone, *_ = target(host)
    out = gcloud('compute', 'instances', 'describe', name, '--zone', zone,
                 '--format=json(status,machineType,networkInterfaces[0].accessConfigs[0].natIP)', capture=True, host=host).stdout
    data = json.loads(out)
    nics = data.get('networkInterfaces') or [{}]
    ip = ((nics[0].get('accessConfigs') or [{}])[0]).get('natIP')
    return data['status'], ip, data['machineType'].rsplit('/', 1)[-1]


def external_ip(host):
    return status(host)[1]


def guest_busy(host):
    """True when leases or simulation/archival processes exist on the VM."""
    probe = ("test -z \"$(ls -A ~/ugrp-sim/leases 2>/dev/null)\" && "
             "! pgrep -f 'scripts\\.sim_[c]li|[r]emote_run_finish|gcp_speed_[p]robe|[r]un_wrapper' >/dev/null")  # [x]: do not match this probe's own command line
    return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host, probe]).returncode != 0


def start(host):
    require_lifecycle(host)
    name, zone, *_ = target(host)
    if status(host)[0] != 'RUNNING':
        gcloud('compute', 'instances', 'start', name, '--zone', zone, host=host)
    print(f'{host}: RUNNING ip={external_ip(host)}', flush=True)


def stop(host, force=False):
    require_lifecycle(host)
    name, zone, *_ = target(host)
    state = status(host)[0]
    if state in ('TERMINATED', 'STOPPED'):
        print('Already stopped')
        return
    if not force and guest_busy(host):
        # Same contract as azctl stop: never stop under a live job; the VM idle guard and
        # the configured runtime cap remain the backstops.
        print('Leases or simulation processes present; stop deferred')
        return 75
    gcloud('compute', 'instances', 'stop', name, '--zone', zone, host=host)
    print(f'{host}: stopped (disk kept)')


def proxy(host, port):
    """ssh ProxyCommand: connect to the VM's current external IP (ephemeral per start)."""
    ip = external_ip(host)
    if not ip:
        raise RuntimeError('VM has no external IP (not running)')
    import socket
    with socket.create_connection((ip, int(port)), timeout=15) as sock:
        import selectors
        sel = selectors.DefaultSelector()
        sel.register(sock, selectors.EVENT_READ, 'net')
        sel.register(sys.stdin.buffer.raw, selectors.EVENT_READ, 'in')
        while True:
            for key, _ in sel.select():
                if key.data == 'net':
                    data = sock.recv(65536)
                    if not data:
                        return
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                else:
                    data = sys.stdin.buffer.raw.read(65536)
                    if not data:
                        return
                    sock.sendall(data)


SSH_CONFIG = """Host {host}
  HostName {host}
  User ugrp
  IdentityFile {identity_file}
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  ProxyCommand env UGRP_GCP_CONFIG={config} python3 {script} proxy {host} %p
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'start', 'stop', 'create', 'proxy', 'ssh-config'])
    parser.add_argument('host', nargs='?', default=DEFAULT_HOST)
    parser.add_argument('port', nargs='?')
    parser.add_argument('--pubkey', type=Path, help='create: public key file (private key stays on the Mac)')
    parser.add_argument('--machine', help='create: override machine type')
    parser.add_argument('--force', action='store_true', help='stop even with leases (never during a job)')
    args = parser.parse_args(argv)
    if args.action == 'status':
        print(*status(args.host))
    elif args.action == 'start':
        start(args.host)
    elif args.action == 'stop':
        return stop(args.host, args.force)
    elif args.action == 'create':
        subprocess.run(create_command(args.host, args.pubkey.read_text().strip(), args.machine), check=True)
    elif args.action == 'proxy':
        proxy(args.host, args.port or 22)
    else:
        print(SSH_CONFIG.format(host=args.host, script=Path(__file__).resolve(),
                               config=CONFIG.resolve(), identity_file=GCP_HOSTS[args.host]['identity_file']))


if __name__ == '__main__':
    sys.exit(main())
