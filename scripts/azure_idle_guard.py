"""VM-local deallocation guard. Identity token is held only in memory."""
import argparse
import json
import os
from pathlib import Path
import shutil
import time
import urllib.request

IDLE_SECONDS = 1200
MAX_UPTIME = 28800


def reason(uptime, idle):
    if uptime >= MAX_UPTIME:
        return 'eight_hour_cap'
    if idle >= IDLE_SECONDS:
        return 'twenty_minutes_idle'
    return None


def active():
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            command = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        except (OSError, ProcessLookupError):
            continue
        executable = command.split(' ', 1)[0].rsplit('/', 1)[-1]
        if executable == 'rsync' or (executable.startswith(('python', 'time', 'bash')) and
                ('/ugrp-sim/src/' in command or 'ugrp-auto-archive' in command or 'compress_json_traces.py' in command)):
            return True
    # Runner leases prevent a guard from interrupting source transfer/admission.
    leases = Path('/home/ugrp/ugrp-sim/leases')
    return leases.exists() and any(time.time() - p.stat().st_mtime < 120 for p in leases.iterdir())


def deallocate():
    def imds(path):
        req = urllib.request.Request('http://169.254.169.254' + path, headers={'Metadata': 'true'})
        # Bypass any model/network proxy for the link-local identity endpoint.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=20) as response:
            return json.load(response)
    info = imds('/metadata/instance/compute?api-version=2021-02-01')
    token = imds('/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fmanagement.azure.com%2F')['access_token']
    url = 'https://management.azure.com' + info['resourceId'] + '/deallocate?api-version=2024-11-01'
    request = urllib.request.Request(url, data=b'', method='POST', headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(request, timeout=60) as response:
        print(json.dumps({'operation': 'deallocate', 'http_status': response.status}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/ugrp-guard'))
    args = parser.parse_args()
    state = args.state_dir
    state.mkdir(parents=True, exist_ok=True)
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    boot_file, busy_file = state / 'boot', state / 'busy'
    now = time.time()
    if not boot_file.exists() or boot_file.read_text() != boot_id:
        boot_file.write_text(boot_id)
        busy_file.write_text(str(now))
    busy = active()
    if busy:
        busy_file.write_text(str(now))
    idle = now - float(busy_file.read_text())
    uptime = float(Path('/proc/uptime').read_text().split()[0])
    trigger = reason(uptime, idle)
    free = shutil.disk_usage('/home/ugrp/ugrp-sim').free
    print(json.dumps({'busy': busy, 'idle_seconds': round(idle), 'uptime_seconds': round(uptime),
        'reason': trigger, 'disk_free_bytes': free, 'disk_alarm': free < 8 * 2**30}), flush=True)
    if trigger and not args.dry_run:
        deallocate()


if __name__ == '__main__':
    main()
