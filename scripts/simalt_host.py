"""Explicit gcp2-only diagnostic identity; never reads metadata credentials."""
import platform
from urllib.request import Request, ProxyHandler, build_opener


def gcp2_identity():
    if platform.system() != 'Linux':
        raise RuntimeError('simalt3 physics/render requires Linux gcp2')
    base = 'http://169.254.169.254/computeMetadata/v1/'
    def get(key):
        request = Request(base + key, headers={'Metadata-Flavor': 'Google'})
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            return response.read(4096).decode().strip()
    row = {'project_id': get('project/project-id'), 'instance': get('instance/name'),
           'machine_type': get('instance/machine-type').rsplit('/', 1)[-1],
           'zone': get('instance/zone').rsplit('/', 1)[-1]}
    allowed = {'ugrp-act-l4-gcp2': 'g2-standard-8', 'ugrp-sim-gcp2': 'n4-highcpu-64'}
    if (row['project_id'] != 'ugrp-sim-b-1014'
            or row['instance'] not in allowed
            or row['machine_type'] != allowed[row['instance']]
            or not row['zone'].startswith('asia-northeast3-')):
        raise RuntimeError(f'unapproved simalt3 host: {row}')
    return row
