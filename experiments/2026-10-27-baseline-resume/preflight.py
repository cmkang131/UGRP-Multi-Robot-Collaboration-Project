"""CPU-only restored-host checks; never launches or imports the simulator/policy."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import urllib.request

PACKAGE = Path('/home/ugrp/ugrp-sim/baseline-treatment')


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True)
    return {'argv': argv, 'exit_code': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr}


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def metadata(path):
    request = urllib.request.Request('http://metadata.google.internal/computeMetadata/v1/' + path,
                                     headers={'Metadata-Flavor': 'Google'})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode()


def main():
    root = Path(sys.argv[1])
    root.mkdir(parents=True, exist_ok=False)
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PACKAGE))
    from verify_baseline import verify
    reference = json.loads((PACKAGE / 'baseline-reference.json').read_text())
    verified = verify(reference)
    (root / 'verify-baseline.json').write_text(json.dumps(verified, indent=2))
    manifest = json.loads(Path(sys.argv[2]).read_text())
    package_files = []
    for name, record in manifest['current_package_files'].items():
        actual = digest(PACKAGE / name)
        package_files.append({'name': name, 'sha256': actual,
                              'expected_sha256': record['sha256'], 'match': actual == record['sha256']})
    idle_gpu = command(['nvidia-smi', '--query-gpu=index,name,driver_version,memory.used,utilization.gpu',
                        '--format=csv,noheader,nounits'])
    gpu_processes = command(['nvidia-smi', '--query-compute-apps=pid,process_name,used_gpu_memory',
                             '--format=csv,noheader,nounits'])
    processes = command(['ps', '-u', str(os.getuid()), '-o', 'pid=,ppid=,pcpu=,comm=,args='])
    competing = []
    for line in processes['stdout'].splitlines():
        parts = line.split(None, 4)
        if len(parts) == 5 and int(parts[0]) != os.getpid():
            if re.fullmatch(r'python[0-9.]*|mujoco|ffmpeg|rsync|scp|tar|zstd', parts[3]):
                competing.append(line)
    leases = []
    lease_root = Path('/home/ugrp/ugrp-sim/leases')
    if lease_root.exists():
        for path in sorted(lease_root.iterdir()):
            if path.is_file():
                leases.append({'path': str(path), 'sha256': digest(path),
                               'contents': path.read_text(errors='replace')})
    guard = command(['systemctl', 'is-active', 'ugrp-idle-guard.timer'])
    fs = command(['findmnt', '-n', '-o', 'SOURCE,FSTYPE,TARGET', '-T', '/home/ugrp/ugrp-sim'])
    u = shutil.disk_usage('/home/ugrp/ugrp-sim')
    # Registered C-07 upper estimate: one complete 20-world arm = 1 GiB.
    # No second arm/retry is admitted here. Other remaining writers are checked above.
    disk = {'free_bytes': u.free, 'total_bytes': u.total,
            'expected_arm_bytes': 2**30, 'concurrent_reserved_bytes': 0,
            'concurrent_reservation_basis': 'fresh restored VM, no other user work or GPU processes',
            'projected_free_bytes': u.free - 2**30, 'floor_bytes': 8 * 2**30,
            'ok': u.free - 2**30 >= 8 * 2**30}
    host = {'hostname': platform.node(), 'architecture': platform.machine(),
            'id': metadata('instance/id'), 'name': metadata('instance/name'),
            'zone': metadata('instance/zone'), 'project': metadata('project/project-id'),
            'machine_type': metadata('instance/machine-type')}
    checks = {'frozen_33_files_and_heads_clean': verified['all_match'] and len(verified['files']) == 33,
              'current_package_10_files': len(package_files) == 10 and all(x['match'] for x in package_files),
              'disk_budget': disk['ok'], 'gpu_l4_available': idle_gpu['exit_code'] == 0 and 'L4' in idle_gpu['stdout'],
              'gpu_idle': gpu_processes['exit_code'] == 0 and not gpu_processes['stdout'].strip(),
              'no_competing_user_work': not competing, 'idle_guard_active': guard['stdout'].strip() == 'active',
              'approved_host_identity': host['project'] == 'ugrp-sim-f-1016' and host['name'] == 'ugrp-act-l4-gcp6'}
    record = {'schema': 'ugrp.baseline-restored-host-preflight.v1',
              'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'host': host, 'disk': disk, 'package_files': package_files, 'nvidia_smi': idle_gpu,
              'gpu_processes': gpu_processes, 'user_processes': processes,
              'competing_user_processes': competing, 'snapshot_lease_files': leases,
              'idle_guard': guard, 'filesystem': fs, 'checks': checks, 'pass': all(checks.values()),
              'gpu_episodes': 0, 'policy_forward_calls': 0,
              'scope': 'Host/hash/disk checks only. Cloud budget, actual all-host storage, source Git and RUN_META are separate.'}
    (root / 'host-preflight.json').write_text(json.dumps(record, indent=2))
    print(json.dumps({'pass': record['pass'], 'checks': checks, 'host': host, 'disk': disk,
                      'matched_files': sum(x['match'] for x in verified['files'])}, indent=2))
    raise SystemExit(0 if record['pass'] else 1)


if __name__ == '__main__':
    main()
