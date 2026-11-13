"""Approved-host identity for the separate beamact5 teacher caller.

This module is default-off: nothing imports it unless the caller explicitly
uses --gcp6-isolated-v1. It reads only the GCE metadata identity and fails
closed unless the exact project/instance/machine/zone matches one approved
host row. No credential, key or environment secret is read.

2026-10-25 prereg amendment: approved hosts expanded from gcp6 only to
gcp6/gcp3/gcp4 (user decision; see 2026-10-25-host-approval-amendment.md).
The function name gcp6_identity is kept for caller compatibility; the
returned row now also carries host_id.
"""
import platform
from urllib.request import Request, ProxyHandler, build_opener


APPROVED_HOSTS = {
    'gcp6': ('ugrp-sim-f-1016', 'ugrp-act-l4-gcp6', 'g2-standard-8',
             'asia-northeast3-a', 'kcm5781kcm5781@gmail.com'),
    'gcp3': ('ugrp-sim-c-1016', 'ugrp-act-l4-gcp3', 'g2-standard-8',
             'asia-northeast3-a', 'changmin5781@gmail.com'),
    'gcp4': ('ugrp-sim-d-1016', 'ugrp-act-l4-gcp4', 'g2-standard-16',
             'asia-northeast3-a', 'changmin5781@gmail.com'),
}


def gcp6_identity():
    if platform.system() != 'Linux':
        raise RuntimeError('approved-host physics/render requires Linux')
    base = 'http://169.254.169.254/computeMetadata/v1/'
    def get(key):
        request = Request(base + key, headers={'Metadata-Flavor': 'Google'})
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            return response.read(4096).decode().strip()
    row = {'project_id': get('project/project-id'), 'instance': get('instance/name'),
           'machine_type': get('instance/machine-type').rsplit('/', 1)[-1],
           'zone': get('instance/zone').rsplit('/', 1)[-1]}
    observed = (row['project_id'], row['instance'], row['machine_type'], row['zone'])
    for host_id, expected in APPROVED_HOSTS.items():
        if observed == expected[:4]:
            row.update(account=expected[4], provider='gcp',
                       schema='ugrp.grasp_act.host.v1', host_id=host_id,
                       cpu_count=len(__import__('os').sched_getaffinity(0)))
            return row
    raise RuntimeError(f'unapproved beamact5 host: {row}')
