"""Build configs/zone_study_scenarios_v4 from the eight v3 scenarios.

v4 = v3 (s1-s8) with only the map fields switched to the final robot-v3 maps:
``map_id`` and ``eval.setup.map_file_sha256`` (plus ``scenario_id`` suffix ``_v3`` -> ``_v4``).
The map geometry of v2 and v3 is identical (only ids, robot_model and the parent hash differ),
so orders, placements, events and budgets are carried over untouched. v2 and v3 files are
never edited, and an existing v4 file is never overwritten with different content.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V3 = ROOT / 'configs' / 'zone_study_scenarios_v3'
V4 = ROOT / 'configs' / 'zone_study_scenarios_v4'
MAP_V3_FILES = {
    'zone_wide_door_geometry_v2': ROOT / 'maps' / 'zones' / 'zone_wide_door_geometry_v3.json',
    'zone_wide_two_doors_final_v1': ROOT / 'maps' / 'zones_final_v3' / 'zone_wide_two_doors_final_v3.json',
    'zone_wide_corridor_final_v1': ROOT / 'maps' / 'zones_final_v3' / 'zone_wide_corridor_final_v3.json',
}
MAP_V3_IDS = {old: path.stem for old, path in MAP_V3_FILES.items()}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def convert(v3: dict) -> dict:
    out = copy.deepcopy(v3)
    assert out['scenario_id'].endswith('_v3'), out['scenario_id']
    out['scenario_id'] = out['scenario_id'][:-3] + '_v4'
    old = out['map_id']
    out['map_id'] = MAP_V3_IDS[old]
    out['eval']['setup']['map_file_sha256'] = _sha256(MAP_V3_FILES[old])
    return out


def main() -> int:
    V4.mkdir(exist_ok=True)
    for path in sorted(V3.glob('*.json')):
        value = convert(json.loads(path.read_text()))
        target = V4 / f"{value['scenario_id']}.json"
        text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if target.exists() and json.loads(target.read_text()) != value:
            print(f'refusing to change existing {target.name}', file=sys.stderr)
            return 1
        target.write_text(text)
        print('wrote', target.name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
