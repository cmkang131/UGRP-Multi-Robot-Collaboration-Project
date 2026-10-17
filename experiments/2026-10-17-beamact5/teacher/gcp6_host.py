"""Truthful gcp6-only host identity for the separate beamact5 teacher caller.

This module is default-off: nothing imports it unless the caller explicitly
uses --gcp6-isolated-v1. It reads only the GCE metadata identity and fails
closed unless the exact assigned project/instance/machine/zone matches.
No credential, key or environment secret is read.
"""
import platform
from urllib.request import Request, ProxyHandler, build_opener


def gcp6_identity():
    if platform.system() != 'Linux':
        raise RuntimeError('gcp6 physics/render requires Linux')
    base = 'http://169.254.169.254/computeMetadata/v1/'
    def get(key):
        request = Request(base + key, headers={'Metadata-Flavor': 'Google'})
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            return response.read(4096).decode().strip()
    row = {'project_id': get('project/project-id'), 'instance': get('instance/name'),
           'machine_type': get('instance/machine-type').rsplit('/', 1)[-1],
           'zone': get('instance/zone').rsplit('/', 1)[-1]}
    expected = ('ugrp-sim-f-1016', 'ugrp-act-l4-gcp6', 'g2-standard-8', 'asia-northeast3-a')
    observed = (row['project_id'], row['instance'], row['machine_type'], row['zone'])
    if observed != expected:
        raise RuntimeError(f'unapproved beamact5 gcp6 host: {row}')
    row.update(account='kcm5781kcm5781@gmail.com', provider='gcp',
               schema='ugrp.grasp_act.host.v1', cpu_count=len(__import__('os').sched_getaffinity(0)))
    return row
