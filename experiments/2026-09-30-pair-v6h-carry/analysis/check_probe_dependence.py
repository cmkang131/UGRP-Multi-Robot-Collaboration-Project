#!/usr/bin/env python3
"""Verify saved 29 probe configurations and their coordinate/proximity structure."""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = HERE / 'sizing_20260930/placement_freshness.json'
data = json.loads(source.read_text())
rows = data['probe_placements']
for row in rows:
    path = Path(row['case_path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['case_sha256']
    assert json.loads(path.read_text())['beam_xyyaw'] == row['beam_xyyaw']
parent = list(range(len(rows)))

def find(i):
    while parent[i] != i:
        i = parent[i]
    return i

for i, a in enumerate(rows):
    for j, b in enumerate(rows[:i]):
        x, y = a['beam_xyyaw'], b['beam_xyyaw']
        if math.dist(x[:2], y[:2]) < .01 and abs(math.degrees(x[2] - y[2])) < .5:
            parent[find(i)] = find(j)
groups = {}
for i, row in enumerate(rows):
    groups.setdefault(find(i), []).append(f"{row['cohort']}/{row['cell']}")
result = {'configurations': len(rows), 'unique_coordinates': len({tuple(r['beam_xyyaw']) for r in rows}),
          'near_connected_groups': len(groups), 'groups': list(groups.values()),
          'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'scope': 'Descriptive structure, not an effective independent sample size or verified population bound'}
assert [result[k] for k in ('configurations', 'unique_coordinates', 'near_connected_groups')] == [29, 26, 20]
print(json.dumps(result, indent=2))
