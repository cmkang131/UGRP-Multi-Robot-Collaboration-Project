"""Write maps/zones_e2e/zone_wide_door_e2e_b80_cones_v1.json (b_marker_style=corner_cones_v1 on the b80 map)."""
import json
from pathlib import Path
from sim.zone_arena import apply_b_marker_style, digest

ROOT = Path(__file__).resolve().parents[1]/'maps/zones_e2e'


def build():
    base = json.loads((ROOT/'zone_wide_door_e2e_b80_v1.json').read_text())
    value = apply_b_marker_style(base, 'corner_cones_v1')
    value['map_id'] = base['map_id']+'_cones_v1'
    value['parent_map'] = {'map_id': base['map_id'], 'sha256': digest(base)}
    return value


if __name__ == '__main__':
    (ROOT/'zone_wide_door_e2e_b80_cones_v1.json').write_text(json.dumps(build(), indent=1)+'\n')
