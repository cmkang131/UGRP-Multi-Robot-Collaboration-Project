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
    # beamact2 user authorization: share the existing warp3 L4, never stop its
    # processes. The denied second-L4 proposal is no longer an execution host.
    expected = ('ugrp-act-l4-gcp2', 'g2-standard-8') if training else ('ugrp-sim-gcp2', 'n4-highcpu-64')
    if project != 'ugrp-sim-b-1014' or (instance, machine) != expected:
        raise ValueError('beamact host/project mismatch')
    return dict(project=project, instance=instance, machine_type=machine, zone=zone)


# pairact-r1 arm F / arm N parallel training (TRAIN_PLAN.json arms): the two L4 hosts of the
# 11/5 plan. Values from configs/gcp_hosts.json gcp6 and require_gcp2(training=True) above.
PAIRACT_L4_HOSTS = {('ugrp-sim-b-1014', 'ugrp-act-l4-gcp2', 'g2-standard-8'): 'gcp2',
                    ('ugrp-sim-f-1016', 'ugrp-act-l4-gcp6', 'g2-standard-8'): 'gcp6'}


def require_pairact_l4():
    if platform.system() != 'Linux':
        raise RuntimeError('pairact-r1 training requires a GCP L4 host; Mac compute forbidden')
    def metadata(key):
        request = urllib.request.Request(
            'http://metadata.google.internal/computeMetadata/v1/' + key,
            headers={'Metadata-Flavor': 'Google'})
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.read().decode().strip().split('/')[-1]
    project, instance, machine, zone = [metadata(k) for k in
        ('project/project-id', 'instance/name', 'instance/machine-type', 'instance/zone')]
    return dict(host_profile_check(project, instance, machine), zone=zone)


def host_profile_check(project, instance, machine):
    vm = PAIRACT_L4_HOSTS.get((project, instance, machine))
    if vm is None:
        raise ValueError('pairact-r1 host/project mismatch (gcp2 or gcp6 L4 only)')
    return dict(project=project, instance=instance, machine_type=machine, vm=vm)
