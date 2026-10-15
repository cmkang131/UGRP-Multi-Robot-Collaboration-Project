"""ACT16 host, frozen-source and dataset-admission boundaries; no cloud writes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import subprocess
from urllib.request import Request, ProxyHandler, build_opener

PROJECT = 'ugrp-sim-b-1014'
ACT_SHA = '3f99d58c5ada0862e669ef4065c0ba957f1b4547'
# gcp2 L4 uses g2-standard-8 (live project docs/backend), unlike the historical
# gcp1 ACT pilot g2-standard-4. New b has the same type; no cost-downsize change.
HOSTS = {'ugrp-act-l4-gcp2': 'g2-standard-8',
         'ugrp-act-l4-gcp2b': 'g2-standard-8',
         'ugrp-sim-gcp2': 'n4-highcpu-64'}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_host(row, *, training=False):
    if (row.get('project_id') != PROJECT or row.get('instance') not in HOSTS
            or row.get('machine_type') != HOSTS[row['instance']]
            or not row.get('zone', '').startswith('asia-northeast3-')
            or (training and not row['instance'].startswith('ugrp-act-l4-gcp2'))):
        raise ValueError('ACT16 requires an authorized gcp2 host')
    return row


def require_gcp2(*, training=False):
    if platform.system() != 'Linux':
        raise RuntimeError('Linux gcp2 required; Mac training/physics/render forbidden')
    base = 'http://169.254.169.254/computeMetadata/v1/'
    def meta(key):
        req = Request(base + key, headers={'Metadata-Flavor': 'Google'})
        with build_opener(ProxyHandler({})).open(req, timeout=3) as response:
            return response.read(4096).decode().strip()
    return validate_host({k: meta(v).rsplit('/', 1)[-1] for k, v in {
        'project_id': 'project/project-id', 'instance': 'instance/name',
        'machine_type': 'instance/machine-type', 'zone': 'instance/zone'}.items()}, training=training)


def frozen_source(root, expected=None):
    root = Path(root).resolve()
    if subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=normal']):
        raise ValueError('committed clean execution source required')
    actual = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if expected is not None and actual != expected:
        raise ValueError('frozen source SHA mismatch')
    return actual


def training_admission(path, *, source, dataset, act_source):
    """An execution receipt produced only after reviewing the actual MJWarp gate.

    This is not a substitute for a queue's rejection_table or gate audit. Files
    and counts are bound to their reviewed hashes, including the scene decision.
    The user's instruction authorizes training after these conditions pass.
    """
    data = json.loads(Path(path).read_text())
    expected = {'approved': True, 'source_sha': source, 'act_source_sha': act_source,
                'dataset_manifest_sha256': sha256(Path(dataset) / 'manifest.json'),
                'backend': 'mjwarp_batch_v1', 'project_id': PROJECT,
                'training_rgb_during_gate': False, 'input_audit_violations': 0}
    if any(data.get(k) != v for k, v in expected.items()):
        raise ValueError('ACT16 admission provenance mismatch')
    n, N = data.get('teacher_success_n'), data.get('teacher_attempts_N')
    if type(n) is not int or type(N) is not int or N < 40 or not 0 <= n <= N or n / N < .95:
        raise ValueError('MJWarp teacher gate must pass >=95% over >=40 attempts')
    for name in ('gate_summary', 'rejection_table', 'scene_decision', 'dataset_audit'):
        item = data.get(name, {})
        if not item.get('path') or sha256(item['path']) != item.get('sha256'):
            raise ValueError('missing/hash-mismatched admission evidence: ' + name)
    manifest = json.loads((Path(dataset) / 'manifest.json').read_text())
    if manifest.get('complete') is not True or data.get('valid_future_action_targets_verified') is not True:
        raise ValueError('completed dataset with valid future action supervision required')
    return data
