"""Read-only admission before launching the sealed door-only study runtime.

This gate reads the selected episode/scenario's map identity and public map
geometry only. Setup, hidden events, poses, roles and communication condition
never determine admission. It constructs no Scene, host, provider or world.
"""
from __future__ import annotations

import json
from pathlib import Path

from harness.zone_corridor_admission import require_door_runtime
from harness.zone_map_schematic import map_path


def require_study_runtime(root: Path, prereg_path: Path, episode_id: str) -> None:
    """Reject unsupported selection without changing a sealed source or bundle.

The final-map directory is inspected to refuse corridor proposals explicitly;
it does not register those maps with the old runner. All existing source,
provider, scene and execution-approval checks still belong to that runner.
"""
    prereg = json.loads(prereg_path.read_text())
    if prereg.get('schema') != 'ugrp.zone_study_integration_prereg.v1':
        raise ValueError('not an integration prereg')
    episodes = [e for e in prereg.get('episodes', []) if e.get('episode_id') == episode_id]
    if len(episodes) != 1:
        raise ValueError(f'expected exactly one episode {episode_id!r}')
    episode = episodes[0]
    map_id = episode.get('map')
    paths = [map_path(map_id, maps_dir=root / 'maps' / directory)
             for directory in ('zones', 'zones_final')]
    present = [p for p in paths if p.is_file()]
    if len(present) != 1:
        raise ValueError(f'expected exactly one static map file for {map_id!r}')
    static = json.loads(present[0].read_text())
    if static.get('map_id') != map_id:
        raise ValueError('static map identity differs from selected episode')
    require_door_runtime(static)
    scenario = json.loads((root / episode['scenario']).read_text())
    if scenario.get('map_id') != map_id:
        raise ValueError('scenario map differs from selected episode')
