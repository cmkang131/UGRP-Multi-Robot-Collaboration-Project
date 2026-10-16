"""Regenerate time_lower_bounds.json from the controller constants (no physics).

Usage: python time_lower_bounds.py <out.json> <source_sha>
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from harness import zone_pair_highpose_contract as contract  # noqa: E402
from harness import zone_pair_highpose_timing as timing  # noqa: E402


def main(dest, sha):
    rows = []
    for map_id, check in [('zone_wide_door_geometry_v3', 'p03'), ('zone_wide_door_geometry_v3', 'carry'),
                          ('zone_wide_two_doors_final_v3', 'carry'), ('zone_wide_corridor_final_v3', 'carry')]:
        static, _, _ = contract.resolve(map_id)
        rows += timing.bounds(static, check)
    out = {'schema': 'ugrp.pr363_time_lower_bounds.v2', 'source_sha': sha, 'module': 'harness/zone_pair_highpose_timing.py',
           'cap_s': timing.CAP_S, 'cap_source': 'configs/zone_pair_highpose_v96.json case_cap (v96-cap-2)',
           'calibration': 'none (measured lag counted as 0)', 'rows': rows}
    Path(dest).write_text(json.dumps(out, indent=1, sort_keys=True, allow_nan=False)+'\n')
    for r in rows:
        print(r['map_id'], r['case'], round(r['lower_bound_s'], 2), r['feasible'])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
