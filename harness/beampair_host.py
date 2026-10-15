"""Execution metadata only; never provides a teacher observation."""
from unittest.mock import patch


def gcp2_identity(identity):
    # The clean pinned dependency predates gcp2. Change its project admission
    # only while reading metadata; instance/project values remain truthful.
    module = __import__(identity.__module__, fromlist=['GCP_PROJECT'])
    with patch.object(module, 'GCP_PROJECT', 'ugrp-sim-b-1014'):
        host = identity('gcp1')
    if (host['project_id'] != 'ugrp-sim-b-1014'
            or host['instance'] != 'ugrp-sim-gcp2'
            or host['machine_type'] != 'n4-highcpu-64'):
        raise ValueError('gcp2 n4-highcpu-64 only; first project is prohibited')
    return host
