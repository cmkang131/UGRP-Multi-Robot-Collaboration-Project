"""Read-only execution identity and machine-bound grasp admission.

No provisioning, credentials, or model observations. Metadata requests read
only project/instance/machine identifiers; never service-account tokens.
"""
import json
import math
import os
import platform
import socket
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

GCP_PROJECT = 'ugrp-act-train-1014'
AZURE_SUBSCRIPTION = '88b7ee7f-f2f3-4a0d-a0ce-cf7306943676'


def metadata(url, headers):
    # Link-local metadata must not go through a host-configured HTTP proxy.
    with build_opener(ProxyHandler({})).open(Request(url, headers=headers), timeout=3) as response:
        return response.read(4096).decode().strip()


def identity(execution_host):
    if platform.system() != 'Linux':
        raise ValueError('grasp physics requires an admitted Linux execution host')
    if execution_host in ('gcp1','gcp2'):
        base = 'http://169.254.169.254/computeMetadata/v1/'
        get = lambda key: metadata(base + key, {'Metadata-Flavor': 'Google'})
        project = get('project/project-id')
        if project != (GCP_PROJECT if execution_host=='gcp1' else 'ugrp-sim-b-1014'):
            raise ValueError('unapproved GCP project')
        if execution_host=='gcp2' and get('instance/name')!='ugrp-sim-gcp2':
            raise ValueError('gcp2 VM required')
        row = {'provider': 'gcp', 'project_id': project, 'instance': get('instance/name'),
               'machine_type': get('instance/machine-type').rsplit('/', 1)[-1],
               'zone': get('instance/zone').rsplit('/', 1)[-1]}
    elif execution_host == 'azure':
        if not socket.gethostname().split('.')[0].startswith('ugrp-sim-azure'):
            raise ValueError('Azure host identity required')
        base = 'http://169.254.169.254/metadata/instance/compute/'
        get = lambda key: metadata(base + key + '?api-version=2021-02-01&format=text', {'Metadata': 'true'})
        subscription = get('subscriptionId')
        if subscription != AZURE_SUBSCRIPTION:
            raise ValueError('unapproved Azure subscription')
        row = {'provider': 'azure', 'project_id': subscription, 'instance': get('name'),
               'machine_type': get('vmSize'), 'zone': get('location')}
    else:
        raise ValueError('explicit azure or gcp1 execution host required')
    if any(not isinstance(v, str) or not v for v in row.values()):
        raise ValueError('incomplete execution identity')
    row['cpu_count'] = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count()
    row['schema'] = 'ugrp.grasp_act.host.v1'
    return row


def require_run_root(root):
    runs = (Path.home() / 'ugrp-sim/runs').resolve()
    target = Path(root).resolve()
    if target == runs or not target.is_relative_to(runs):
        raise ValueError('persistent managed run subdirectory required')


def same_machine(before, after):
    keys = ('schema', 'provider', 'project_id', 'instance', 'machine_type', 'zone', 'cpu_count')
    if not before or not after or any(before.get(k) is None or before.get(k) != after.get(k) for k in keys):
        raise ValueError('execution host or machine changed; a new gate is required')


def measured_speed_baseline(root, host, concurrency):
    root = Path(root)
    admission = json.loads((root / 'resource-admission.json').read_text())
    gate = json.loads((root / 'speed-gate.json').read_text())
    same_machine(admission.get('execution_host'), host)
    ratio = gate.get('median_wall_per_sim')
    if (admission.get('concurrency') != concurrency or gate.get('completed') != concurrency
            or gate.get('invalid_samples') or not isinstance(ratio, (int, float))
            or not math.isfinite(ratio) or ratio <= 0):
        raise ValueError('completed same-machine same-concurrency speed measurement required')
    return {'path': str(root.resolve()), 'concurrency': concurrency, 'median_wall_per_sim': ratio}
