"""Read-only map/Scene/model/provider binding. No scene, worker or model construction.

Published map catalogs remain byte-identical. This unsealed extension records
support, including explicit refusal of new-map and robot-v3 calibrations.
Provider registration/lifecycle belongs to P03; it is never rewritten here.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from harness.zone_map_schematic import digest, load_map

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = 'configs/zone_final_environment_registry_v1.json'
SCHEMA = 'ugrp.zone_final_environment_registry.v1'


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registry(root=ROOT):
    value = json.loads((Path(root) / REGISTRY_FILE).read_text())
    if value.get('schema') != SCHEMA or value.get('status') != 'DRAFT_UNSEALED':
        raise ValueError('invalid unsealed environment registry')
    return value


def environment_entry(map_id, *, root=ROOT):
    """A registered binding, or None for existing legacy maps (no default change)."""
    if not isinstance(map_id, str) or not map_id or '/' in map_id or map_id.startswith('.'):
        raise ValueError(f'bad map_id: {map_id!r}')
    root = Path(root)
    from harness import e2e_environment as e2e
    if map_id == e2e.MAP_ID:
        _, row, _ = e2e.resolve(root=root)
        return {**row, 'map_file': row['file'], 'file_sha256': row['sha256'],
                'catalog': 'e2e', 'catalog_file': e2e.REGISTRY, 'catalog_sha256': _sha(root/e2e.REGISTRY)}
    reg = registry(root)
    if map_id not in reg['maps']:
        from harness.zone_final_env import V3_MAP_PARENTS
        if map_id in V3_MAP_PARENTS:
            from harness import zone_final_environment as final_v3
            static, pin, _ = final_v3.resolve(map_id, root=root)
            return {'map_id': map_id, 'map_file': pin['file'], 'file_sha256': pin['sha256'],
                    'static_map_sha256': digest(static), 'catalog': 'final_v3',
                    'catalog_file': final_v3.REGISTRY, 'catalog_sha256': _sha(root / final_v3.REGISTRY),
                    'scene_factory': 'sim.zone_final_v3_scene:FinalV3Scene',
                    'robot_model': 'masterpi_v3', 'wall_profile': 'walls_v3',
                    'providers': {}, 'research_result': False}
        return None
    entry = copy.deepcopy(reg['maps'][map_id])
    catalog = reg['catalogs'][entry['catalog']]
    if _sha(root / catalog['file']) != catalog['sha256']:
        raise ValueError('environment catalog hash mismatch')
    rows = json.loads((root / catalog['file']).read_text())
    pin = rows['maps' if entry['catalog'] == 'final' else 'scenes'][map_id]
    entry.update(map_id=map_id, map_file=pin.get('file', pin.get('map_file')),
                 file_sha256=pin['file_sha256'], static_map_sha256=pin['static_map_sha256'],
                 catalog_file=catalog['file'], catalog_sha256=catalog['sha256'])
    return entry


def static_map_path(map_id, *, root=ROOT):
    entry = environment_entry(map_id, root=root)
    return Path(root) / (entry['map_file'] if entry else f'maps/zones/{map_id}.json')


def resolve_static_map(map_id, *, root=ROOT, robot_model=None, static_map_sha256=None):
    """Exact JSON + file hash. Unknown maps and identity mismatches fail before factories."""
    entry = environment_entry(map_id, root=root)
    data, file_sha = load_map(map_id, maps_dir=static_map_path(map_id, root=root).parent)
    if entry is None and 'landmarks' in data and Path(root) == ROOT:
        # Keep the existing tagged path's authored-definition/base check. This
        # computes static metadata only; it neither constructs nor renders a Scene.
        from sim.zone_landmarks import tagged_map
        from sim.zone_start_dock import MAP_ID as DOCK_MAP_ID, dock_map
        expected = dock_map() if map_id == DOCK_MAP_ID else tagged_map(map_id)
        if data != expected:
            raise ValueError('tagged map identity mismatch')
    model = data.get('robot_model', 'masterpi_v2')
    if (model not in ('masterpi_v2', 'masterpi_v3') or (entry and entry['robot_model'] != model)
            or (robot_model is not None and robot_model != model)):
        raise ValueError(f'map/model mismatch: {map_id} requires {model}')
    actual = digest(data)
    if static_map_sha256 is not None and actual != static_map_sha256:
        raise ValueError('requested static map hash mismatch')
    if entry:
        if file_sha != entry['file_sha256'] or actual != entry['static_map_sha256']:
            raise ValueError('registered map file/static hash mismatch')
        if data.get('wall_profile', {}).get('id') != entry['wall_profile'] or 'landmarks' in data:
            raise ValueError('registered map wall/landmark identity mismatch')
        if entry['catalog'] == 'robot_v3':
            parent, _ = resolve_static_map('zone_wide_door_geometry_v2', root=root)
            if data.get('parent_scene') != {'map_id': parent['map_id'], 'sha256': digest(parent)}:
                raise ValueError('v3 scene parent identity mismatch')
        elif entry['catalog'] == 'final_v3':
            from harness.zone_final_environment import resolve
            if data != resolve(map_id, root=root)[0]:
                raise ValueError('final v3 scene identity mismatch')
    return data, file_sha


def maps_dir_for(map_id, *, root=ROOT):
    resolve_static_map(map_id, root=root)
    return static_map_path(map_id, root=root).parent


def load_scenario(scenario_id):
    """Explicit version routing; the legacy loader and its default list stay frozen."""
    from harness.zone_study_scenarios import load, SCENARIO_DIR
    if scenario_id == 'e2e_one_beam_ownmap':
        return load(scenario_id, directory=ROOT/'configs/zone_study_dev')
    directory = SCENARIO_DIR
    for version in (2, 3, 4):
        if scenario_id.endswith(f'_v{version}'):
            directory = ROOT / 'configs' / f'zone_study_scenarios_v{version}'
            break
    return load(scenario_id, directory=directory)


def bundle_for(scenario, *, schematic=False):
    """Opt-in public map projection; legacy scenario defaults stay frozen."""
    from harness.zone_study_scenarios import bundle_for as legacy_bundle
    return legacy_bundle(scenario, maps_dir=maps_dir_for(scenario['map_id']), schematic=schematic)


def validate(scenario):
    """Use the existing non-raising validator with the selected map directory."""
    from harness.zone_study_scenarios import CHECK_NAMES, Report, validate as legacy_validate
    if not isinstance(scenario, Mapping):
        return legacy_validate(scenario)
    try:
        directory = maps_dir_for(scenario.get('map_id'))
    except (OSError, ValueError) as error:
        report = Report(str(scenario.get('scenario_id')), {name: [] for name in CHECK_NAMES})
        report.checks['schema'].append(f'the pinned map could not be read: {error}')
        return report
    return legacy_validate(scenario, maps_dir=directory)


def provider_binding(map_id, provider, calibration, *, root=ROOT, robot_model=None, static_map_sha256=None):
    """Validate the actual executor calibration and provider before any construction.

Legacy tagged routes retain their existing registry behavior. A tag-free
provider can never accept a tagged map even if its allow-list is misconfigured.
"""
    static, _ = resolve_static_map(map_id, root=root, robot_model=robot_model,
                                  static_map_sha256=static_map_sha256)
    if not provider['uses_landmark_tags'] and 'landmarks' in static:
        raise ValueError('tag-free provider cannot receive a map with landmarks')
    entry = environment_entry(map_id, root=root)
    if entry is None:
        return None
    support = entry['providers'].get(provider['provider_id'])
    if not support or not support['supported']:
        reason = support['reason'] if support else 'provider/model combination not registered'
        raise ValueError(f'unsupported environment provider: {map_id}: {reason}')
    if (map_id not in provider['maps'] or provider['uses_landmark_tags']
            or provider['research_result'] or entry['research_result']):
        raise ValueError('environment provider registration/research status mismatch')
    if calibration != support['calibration'] or _sha(Path(root) / calibration) != support['calibration_sha256']:
        raise ValueError('environment calibration file/hash mismatch')
    return {**entry, 'registry_file': REGISTRY_FILE, 'registry_sha256': _sha(Path(root) / REGISTRY_FILE),
            'provider_id': provider['provider_id'], 'calibration': calibration,
            'calibration_sha256': support['calibration_sha256'], 'status': 'DRAFT_UNSEALED'}
