"""Runtime/admission checks; no cloud mutations or credentials."""
import json
import platform
import subprocess
import urllib.request
from pathlib import Path

PROJECT = 'ugrp-act-train-1014'
ROOT = Path(__file__).resolve().parents[1]


def source_sha():
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT):
        raise ValueError('commit all source before execution')
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def require_gcp(*, training):
    if platform.system() != 'Linux':
        raise RuntimeError('GCP Linux only; Mac training/physics/render forbidden')
    def meta(key):
        request = urllib.request.Request('http://metadata.google.internal/computeMetadata/v1/' + key,
                                         headers={'Metadata-Flavor': 'Google'})
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.read().decode().strip()
    project, machine, instance, zone = [meta(k) for k in
        ('project/project-id', 'instance/machine-type', 'instance/name', 'instance/zone')]
    machine, zone = machine.split('/')[-1], zone.split('/')[-1]
    if project != PROJECT or (training and machine != 'g2-standard-4'):
        raise ValueError('wrong GCP project/machine')
    if not training and (instance != 'ugrp-sim-gcp1' or machine != 'n4-highcpu-64'):
        raise ValueError('student simulation belongs to gcp1 n4-highcpu-64')
    return {'project': project, 'instance': instance, 'machine_type': machine, 'zone': zone}


def authorize_main(approval, *, source, dataset_hash, smoke_hash, steps, blank):
    data = json.loads(Path(approval).read_text()) if approval else {}
    expected = {'approved': True, 'stage': 'main', 'source_sha': source,
                'dataset_manifest_sha256': dataset_hash, 'smoke_summary_sha256': smoke_hash,
                'steps': steps, 'blank_images': blank,
                'gate_promotion_authorized_if_all_conditions_pass': False}
    if not smoke_hash or any(data.get(k) != v for k, v in expected.items()):
        raise ValueError('main training requires coordinator approval tied to source/data/smoke')
    return data
