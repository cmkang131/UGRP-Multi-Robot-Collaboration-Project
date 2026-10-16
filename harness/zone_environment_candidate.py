"""Explicit environment inputs for unsealed candidates, including #292 composition.

Python import discovery cannot see JSON reads or registry-selected Scene modules.
An opt-in candidate combines its base contract with this manifest. Existing
registered entry points do not import this adapter and acquire no new inputs.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from harness import zone_environment_registry as env
from harness.python_source_closure import source_closure

ROOT = env.ROOT
SCHEMA = 'ugrp.zone_environment_candidate.v1'


def source_files(map_id, *, root=ROOT):
    root = Path(root)
    reg = env.registry(root)
    entry = env.environment_entry(map_id, root=root)
    static, _ = env.resolve_static_map(map_id, root=root)
    paths = {env.REGISTRY_FILE, 'harness/zone_environment_candidate.py',
             'sim/zone_environment_scene_provider.py',
             *(row['file'] for row in reg['catalogs'].values())}
    # The standard Scene also reads its authored base / v3 parent map.
    pending = [static]
    seen = set()
    while pending:
        current = pending.pop()
        mid = current['map_id']
        if mid in seen:
            continue
        seen.add(mid)
        paths.add(env.static_map_path(mid, root=root).relative_to(root).as_posix())
        for key in ('base_map', 'parent_scene', 'parent_map'):
            parent = current.get(key)
            if isinstance(parent, dict) and parent.get('map_id'):
                pending.append(env.resolve_static_map(parent['map_id'], root=root)[0])
    modules = ()
    if entry:
        modules = (entry['scene_factory'].partition(':')[0],)
        paths.update(row['calibration'] for row in entry['providers'].values() if row.get('calibration'))
    return source_closure(root, sorted(paths), modules=modules)


def candidate_contract(base_contract, map_id, *, root=ROOT):
    """Compose a base (e.g. v6h preview) without mutating or re-sealing it."""
    entry = env.environment_entry(map_id, root=root)
    base_pins = base_contract.get('source_sha256', {})
    # The base owns its closure (including dated experiment scripts which are
    # file entry points, not importable module names). Preserve and verify it.
    files = sorted(set(source_files(map_id, root=root)) | set(base_pins))
    for path in files:
        if not (Path(root) / path).resolve().is_relative_to(Path(root).resolve()):
            raise ValueError('nonlocal environment source')
    pins = {p: hashlib.sha256((Path(root) / p).read_bytes()).hexdigest() for p in files}
    if any(pins[p] != expected for p, expected in base_pins.items()):
        raise ValueError('base candidate source hash mismatch')
    return {'schema': SCHEMA, 'status': 'DRAFT_UNSEALED', 'runnable': False,
            'research_result': False, 'map_id': map_id,
            'base_contract': copy.deepcopy(base_contract),
            'dynamic_imports': [entry['scene_factory'].partition(':')[0]] if entry else [],
            'source_sha256': pins}


def verify_candidate_contract(candidate, base_contract, *, root=ROOT):
    """Reject changed/missing data and modules before any Scene construction."""
    for path, expected in candidate['source_sha256'].items():
        source = Path(root) / path
        if not source.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError('nonlocal environment source')
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f'environment source hash mismatch: {path}')
    if candidate != candidate_contract(base_contract, candidate['map_id'], root=root):
        raise ValueError('environment candidate contract mismatch')
    return candidate
