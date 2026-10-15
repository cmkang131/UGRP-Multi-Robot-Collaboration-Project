"""Narrow host admission; no cloud mutation or credential access."""
import platform
import urllib.request


def require_gcp2(*, training):
    if platform.system() != 'Linux':
        raise RuntimeError('beamact1 requires GCP2; Mac compute forbidden')
    def metadata(key):
        request = urllib.request.Request(
            'http://metadata.google.internal/computeMetadata/v1/' + key,
            headers={'Metadata-Flavor': 'Google'})
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.read().decode().strip().split('/')[-1]
    project, instance, machine, zone = [metadata(k) for k in
        ('project/project-id', 'instance/name', 'instance/machine-type', 'instance/zone')]
    expected = ('ugrp-act-l4-gcp2b', 'g2-standard-8') if training else ('ugrp-sim-gcp2', 'n4-highcpu-64')
    if project != 'ugrp-sim-b-1014' or (instance, machine) != expected:
        raise ValueError('beamact1 host/project mismatch; warp3 L4 is excluded')
    return dict(project=project, instance=instance, machine_type=machine, zone=zone)
