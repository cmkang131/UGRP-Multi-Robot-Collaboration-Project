"""Read-only audit of historical registrations against their committed blobs.

This verifies provenance, not admission to execute with the current checkout.
run_zone_pair_dev.load_config deliberately retains its current-source checks.
No historical Python is imported or executed and no working tree is changed.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


@lru_cache(maxsize=2048)
def committed_blob(root, commit, path):
    relative = PurePosixPath(path)
    if (not re.fullmatch('[0-9a-f]{40}', commit) or relative.is_absolute()
            or '..' in relative.parts or str(relative) != path):
        raise ValueError('expected a full source commit and repository-relative path')
    try:
        return subprocess.check_output(['git', 'show', f'{commit}:{path}'], cwd=root,
                                       stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        raise ValueError(f'committed source unavailable: {commit}:{path}') from exc


def verify_contract_sources(value, commit, *, root=ROOT):
    """Check the sealed receipt and each declared source at the same commit."""
    body = {k: v for k, v in value.items() if k != 'sha256'}
    if value.get('sha256') != digest(body) or not value.get('source_sha256'):
        raise ValueError('registered contract seal/source closure mismatch')
    sources = dict(value['source_sha256'])
    for key in ('map', 'parent_map'):
        if key in value:
            sources[value[key]['path']] = value[key]['sha256']
    for path, expected in sources.items():
        actual = hashlib.sha256(committed_blob(str(root), commit, path)).hexdigest()
        if actual != expected:
            raise ValueError(f'registered source hash mismatch at {commit}: {path}')
    return sources


def verify_registered_source(registration, *, root=ROOT, source_commit=None):
    """Audit the receipt's own source commit; never substitute current hashes.

    These archived registrations have null execution_source_sha. Their last
    registration-changing commit supplies the source snapshot; every declared
    blob must match it. Missing history fails closed instead of using HEAD files.
    """
    root = Path(root).resolve()
    registration = Path(registration).resolve()
    relative = registration.relative_to(root).as_posix()
    if source_commit is None:
        source_commit = subprocess.check_output(
            ['git', 'log', '-1', '--format=%H', 'HEAD', '--', relative],
            cwd=root, text=True).strip()
    original = committed_blob(str(root), source_commit, relative)
    if registration.read_bytes() != original:
        raise ValueError('registration bytes differ from their committed record')
    record = json.loads(original)
    if record.get('status') != 'REGISTERED' or 'scene_contract' not in record:
        raise ValueError('expected a committed historical dock registration')
    sources, contracts = {}, {}
    for key in ('scene_contract', 'grasp_contract', 'contact_profile_contract'):
        if key in record:
            sources.update(verify_contract_sources(record[key], source_commit, root=root))
            contracts[key] = record[key]['sha256']
    for spec in (*record.get('inputs', {}).values(), record.get('supersedes')):
        if isinstance(spec, dict) and 'path' in spec and 'sha256' in spec:
            actual = hashlib.sha256(committed_blob(str(root), source_commit, spec['path'])).hexdigest()
            if actual != spec['sha256']:
                raise ValueError(f'registered input hash mismatch: {spec["path"]}')
            sources[spec['path']] = actual
    return {'registration_path': relative, 'registration_sha256': hashlib.sha256(original).hexdigest(),
            'source_commit': source_commit, 'contract_sha256': contracts, 'source_sha256': sources,
            'qualification': 'historical provenance only; not current-source execution admission'}
