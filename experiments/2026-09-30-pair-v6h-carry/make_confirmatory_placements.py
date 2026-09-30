#!/usr/bin/env python3
"""DRAFT: the confirmatory placement list for the b-v6h chain cohort (NOT run, NOT sealed).

60 placements, drawn once from a fixed numpy rng seed, in the distribution of the exploratory ``sheet: coarse`` cohorts
(``experiments/2026-09-30-b-v6h-gain/placements/held_out_sheet_12.json``): x in [0.92, 1.07] m, y in [-0.03, 0.11] m, yaw in
[-4.5, 4.5] deg, order sheet = the beam pose rounded to the sheet grid (0.1 m, 10 deg). PF priors are drawn uniformly from the ten
recorded hR2 approach-end samples. A draw that lands within DISTINCT_XY_M / DISTINCT_YAW_DEG of any placement already used in the
exploratory cohorts (base-sheet or sheet-consistent) is redrawn, so the confirmatory set contains no exploratory placement. Accepted confirmatory draws are also added to ``taken``:
this sequential proximity-rejection design is NOT IID, and its law differs from the original uniform box.
Count/Wilson/binomial calculations are descriptive/nominal design sensitivities, not population guarantees.

Usage: make_confirmatory_placements.py [--check]     (--check verifies the committed file is what this script draws)
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
OUT = HERE / 'placements_confirmatory_DRAFT.json'
EXPLORATORY = [ROOT / 'experiments/2026-09-30-b-v6h-gain/placements/held_out_12.json',
               ROOT / 'experiments/2026-09-30-b-v6h-gain/placements/held_out_sheet_12.json']
RNG_SEED = 20260941
N = 60
X_RANGE, Y_RANGE, YAW_RANGE_DEG = (0.92, 1.07), (-0.03, 0.11), (-4.5, 4.5)
DISTINCT_XY_M, DISTINCT_YAW_DEG = 0.01, 0.5


def hr2_ids():
    from harness import pair_stage_probe as sp
    return [s['id'] for s in json.loads(sp.SAMPLE_FILES['hR2'].read_text())['samples']]


def used():
    out = []
    for f in EXPLORATORY:
        out += [(e['x'], e['y'], e['yaw_deg']) for e in json.loads(f.read_text())]
    return out


def draw():
    rng = np.random.default_rng(RNG_SEED)
    priors = hr2_ids()
    taken = used()
    rows = []
    while len(rows) < N:
        x, y = round(float(rng.uniform(*X_RANGE)), 3), round(float(rng.uniform(*Y_RANGE)), 3)
        yaw = round(float(rng.uniform(*YAW_RANGE_DEG)), 2)
        prior = priors[int(rng.integers(len(priors)))]
        if any(math.hypot(x - a, y - b) < DISTINCT_XY_M and abs(yaw - c) < DISTINCT_YAW_DEG for a, b, c in taken):
            continue
        taken.append((x, y, yaw))
        rows.append({'name': f'C{len(rows) + 1:02d}', 'x': x, 'y': y, 'yaw_deg': yaw, 'prior': prior, 'sheet': 'coarse'})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()
    rows = draw()
    text = json.dumps(rows, indent=1) + '\n'
    if a.check:
        raise SystemExit(0 if OUT.read_text() == text else 'committed placements differ from the draw')
    OUT.write_text(text)
    print(f'wrote {OUT} ({len(rows)} placements)')


if __name__ == '__main__':
    main()
