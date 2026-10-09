"""Preparation-only held-out maps. Never imported by a controller or default suite."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_ID = 'zone_wide_two_doors_final_v3'
MAP_DIR = ROOT / 'maps/zones_final_v3'
CATALOG = MAP_DIR / 'hardmaps1_catalog.json'
IDS = ('zone_hardmaps1_h1_final_v3', 'zone_hardmaps1_h2_final_v3')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wall(name, x0, x1, y0, y1):
    return dict(id=name, center_m=[(x0+x1)/2, (y0+y1)/2],
                half_extents_m=[(x1-x0)/2, (y1-y0)/2], height_m=.4, kind='wall')


def door(name, x, y, width, connects):
    return dict(id=name, kind='door', center_m=[x, y], half_extents_m=[.025, width/2],
                width_m=width, lanes=1, axis='x', connects=connects)


def authored_maps():
    base = json.loads((MAP_DIR / (BASE_ID+'.json')).read_text())
    h1, h2 = copy.deepcopy(base), copy.deepcopy(base)
    for value, name in zip((h1, h2), IDS):
        value.update(map_id=name, version=1)
        # Keep the v3 parent/base fields used by the standard spawn convention.
        value['heldout'] = dict(suite='hardmaps1', split='held_out', status='prepared_only',
                               development_use=False, controller_trials=0,
                               reference_map=BASE_ID,
                               reference_file_sha256=sha(MAP_DIR/(BASE_ID+'.json')))
    h1['obstacles'] += [
        wall('wall_h1_east_lower', 3.725, 3.775, -3.15, -2.5),
        wall('wall_h1_east_middle', 3.725, 3.775, -1.7, 0.),
        wall('wall_h1_east_upper', 3.725, 3.775, .8, 1.45),
        wall('wall_h1_east_cross', 3.75, 5.4, -.875, -.825),
    ]
    h1['passages'] += [door('door_A', 3.75, .4, .8, ['central_C', 'dead_end_A']),
                       door('door_B', 3.75, -2.1, .8, ['central_C', 'dead_end_B'])]
    h1['heldout']['rooms'] = ['west_pickup', 'central_C', 'dead_end_A', 'dead_end_B']
    h1['heldout']['route_alternatives'] = ['door_narrow', 'door_wide']

    # Reuse each navigation rectangle rigidly in XY; only height changes to walls_v3.
    sources = [('narrow-door', 1., 2.05, 0.),
               ('staggered-obstacles', 1., 3.60, 2.40),
               ('blocked-branch', -1., 4.321, 1.15)]
    h2['obstacles'] = h2['obstacles'][:4]
    h2['heldout']['geometry_sources'] = []
    for source, sx, dx, dy in sources:
        path = ROOT/'maps/navigation'/f'{source}.json'
        data = json.loads(path.read_text())
        h2['heldout']['geometry_sources'].append(dict(file=str(path.relative_to(ROOT)),
            sha256=sha(path), x_scale=sx, translation_m=[dx, dy], height_override_m=.4))
        for obs in data['obstacles']:
            x, y = obs['center_m']
            h2['obstacles'].append(dict(id='wall_h2_'+obs['id'],
                center_m=[sx*x+dx, y+dy], half_extents_m=obs['half_extents_m'],
                height_m=.4, kind='wall'))
    h2['obstacles'] += [wall('wall_h2_south_extension', 2.16, 2.24, -3.15, -2.9),
                        wall('wall_h2_middle_extension', 2.16, 2.24, -1.15, .22),
                        wall('wall_h2_north_extension', 2.16, 2.24, .78, 1.45)]
    h2['passages'] = [door('door_56_south', 2.2, -2., .56, ['west_pickup', 'east_detour']),
                      door('door_56_north', 2.2, .5, .56, ['west_pickup', 'east_detour'])]
    # The reused narrow-door wall is 8 cm thick (not the base's 5 cm).
    for passage in h2['passages']:
        passage['half_extents_m'][0] = .04
    return h1, h2


def load(map_id):
    if map_id not in IDS:
        raise ValueError('UNKNOWN_HELDOUT_MAP')
    catalog = json.loads(CATALOG.read_text())
    entry = catalog['maps'][map_id]
    path = MAP_DIR/(map_id+'.json')
    if sha(path) != entry['file_sha256']:
        raise ValueError('HELDOUT_MAP_HASH_MISMATCH')
    value = json.loads(path.read_text())
    if value != authored_maps()[IDS.index(map_id)]:
        raise ValueError('HELDOUT_MAP_SOURCE_MISMATCH')
    return value
