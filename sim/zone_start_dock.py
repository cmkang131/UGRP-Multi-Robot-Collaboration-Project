"""Versioned static dock for pair dev v3; no live poses or simulator imports.

The authored row set is public. Seeded robot-to-row assignment stays setup-only.
Old maps without this profile keep their original layout and spawn column.
"""
from __future__ import annotations

import copy
import json

from sim.research_dispatch_arena import digest
from sim.zone_arena import MAP_DIR, layout

MAP_ID = 'zone_wide_door_tags_v2_dock_v3'
PARENT_MAP_ID = 'zone_wide_door_tags_v2'
PROFILE_ID = 'zone_start_dock_v3'


def profile_record():
    value = {'id': PROFILE_ID, 'version': 3, 'spawn_x_m': -.65,
             'spawn_rows_y_m': [-2.25, -.85, .55], 'spawn_yaw_rad': 0.,
             'idle_keepout_radius_m': .17,
             'source': 'authored static layout; no live robot positions or robot-to-row assignment'}
    return {**value, 'sha256': digest(value)}


def relocate_map(parent):
    if parent['map_id'] != PARENT_MAP_ID:
        raise ValueError('dock v3 requires the unchanged tags_v2 parent')
    value = copy.deepcopy(parent)
    value.update(map_id=MAP_ID, version=3, start_dock=profile_record(),
                 parent_map={'map_id': PARENT_MAP_ID, 'static_map_sha256': digest(parent)})
    return value


def build_dock_map():
    from sim.zone_landmarks import tagged_map
    return relocate_map(tagged_map(PARENT_MAP_ID))


def dock_map():
    value = json.loads((MAP_DIR / (MAP_ID + '.json')).read_text())
    if value != build_dock_map():
        raise ValueError('dock map differs from the parent and registered profile')
    return value


def spawn_layout(static):
    """One public source for scene placement and idle-spawn keepouts."""
    base = static.get('base_map', {}).get('map_id', static['map_id'])
    value = copy.deepcopy(layout(base))
    if 'start_dock' in static:
        if static['map_id'] != MAP_ID or static['start_dock'] != profile_record():
            raise ValueError('unsupported or altered static dock profile')
        value.update(spawn_x=static['start_dock']['spawn_x_m'],
                     spawn_rows_y=tuple(static['start_dock']['spawn_rows_y_m']))
    return value


def apply_spawn_layout(config):
    """Before world construction: preserve seed/row/z/yaw; change only x."""
    static = config['static_map']
    if 'start_dock' not in static:
        return
    spec = spawn_layout(static)
    old = layout(static['base_map']['map_id'])
    spawns = config['setup_only']['spawns']
    if (set(spawns) != {'r1', 'r2', 'r3'}
            or sorted(p[1] for p in spawns.values()) != sorted(spec['spawn_rows_y'])
            or any(p[0] != old['spawn_x'] or p[3] != 0. for p in spawns.values())):
        raise ValueError('dock relocation requires original seeded spawn slots')
    for pose in spawns.values():
        pose[0] = spec['spawn_x']


def static_spawn_keepouts(static):
    spec = spawn_layout(static)
    radius = static.get('start_dock', {}).get('idle_keepout_radius_m', .17)
    return [{'id': f'spawn_row_{i}', 'center_m': [float(spec['spawn_x']), float(y)],
             'radius_m': radius, 'source': 'static_layout_idle_spawn'}
            for i, y in enumerate(spec['spawn_rows_y'])]


def static_dock_text(static):
    if 'start_dock' not in static:
        return ''
    spec = spawn_layout(static)
    return (f"Static start dock {PROFILE_ID}: x={spec['spawn_x']:.2f} m; "
            f"rows y={list(spec['spawn_rows_y'])} m; yaw=0 rad (east). "
            'Idle-spawn keepouts have radius 0.17 m. These are authored slots, '
            'not current robot locations; robot-to-row assignment is not supplied.')


def static_map_text(static):
    from sim.zone_arena import static_map_text as parent_text
    return ' '.join(part for part in (parent_text(static), static_dock_text(static)) if part)
