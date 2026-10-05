"""Zero check: relation() (command-geometry grip check) on recorded own RGB.

Scores harness.zone_pair_highpose_grip.relation on every recorded frame of
the seed-911 render run (record_rendered_frames.py), per condition, robot and
phase window. eval_label (window, gripper commands) is used ONLY to group the
scores. This is why v96 keeps relation() log-only.

Usage: python relation_zero_check.py <out.json>
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from harness import zone_pair_highpose_grip as grip  # noqa: E402
from harness import owncam_pair_hold_v3 as hv3  # noqa: E402

RAW = Path('/Users/changmin/projects/ugrp/outputs/pr363-render-frames-20261003')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(dest):
    index = json.loads((RAW/'index.json').read_text())
    groups = {}
    floor = {}
    for f in index['frames']:
        image = (RAW/f['file']).read_bytes()
        servo = {int(k): v for k, v in f['issued_servo'].items()}
        rel = grip.relation(image, servo)
        key = f"{f['condition']}/{f['rid']}/{f['eval_label']['window']}"
        g = groups.setdefault(key, {'frames': 0, 'relation_ok': 0, 'coverage': []})
        g['frames'] += 1
        g['relation_ok'] += bool(rel['ok'])
        if rel.get('coverage') is not None:
            g['coverage'].append(float(rel['coverage']))
        if f['t'] == 3.5:
            floor[f"{f['condition']}/{f['rid']}"] = int(hv3.hold_view_mask(image).sum())
    for g in groups.values():
        cov = g.pop('coverage')
        g['coverage_min'] = round(min(cov), 3) if cov else None
        g['coverage_max'] = round(max(cov), 3) if cov else None
    out = {'schema': 'pr363_relation_zero_check_v1', 'driver_sha256': sha(__file__),
           'raw_index': str(RAW/'index.json'), 'raw_index_sha256': sha(RAW/'index.json'),
           'source_sha': index['source_sha'], 'min_coverage': grip.MIN_COVERAGE,
           'groups': groups,
           'floor_grasp_view_hold_mask_px': floor,
           'floor_note': 'hold_view_mask at the floor grasp pose (t=3.5 s): 0 px means the wrist view shows no beam'}
    Path(dest).write_text(json.dumps(out, indent=1, allow_nan=False)+'\n')
    for k, v in sorted(groups.items()):
        print(k, v)
    print(floor)


if __name__ == '__main__':
    main(sys.argv[1])
