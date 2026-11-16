"""Execution metadata only; never provides a teacher observation."""
import os
from unittest.mock import patch

# Real project id comes from the environment; the repository keeps a placeholder.
GCP2_PROJECT = os.environ.get('UGRP_GCP2_PROJECT', '<project-id-gcp2>')


def gcp2_identity(identity):
    # The clean pinned dependency predates gcp2. Change its project admission
    # only while reading metadata; instance/project values remain truthful.
    module = __import__(identity.__module__, fromlist=['GCP_PROJECT'])
    with patch.object(module, 'GCP_PROJECT', GCP2_PROJECT):
        host = identity('gcp1')
    if (host['project_id'] != GCP2_PROJECT
            or host['instance'] != 'ugrp-sim-gcp2'
            or host['machine_type'] != 'n4-highcpu-64'):
        raise ValueError('gcp2 n4-highcpu-64 only; first project is prohibited')
    return host
