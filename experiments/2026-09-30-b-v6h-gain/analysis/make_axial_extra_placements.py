#!/usr/bin/env python3
"""Extra placements for the axial-lag check (2026-09-30): the previously failing F_hR2_04 pose with the sheet-consistent order sheet,
plus 6 fresh draws (rng seed 20260951): 3 in the order-sheet-0.9 family (x in [0.92, 0.95), where all earlier failures were) and 3
anywhere in the exploratory range. Redrawn if within (0.01 m, 0.5 deg) of any exploratory placement OR any placement of the DRAFT
confirmatory list (the confirmatory set must stay unseen). Usage: make_axial_extra_placements.py"""
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE.parent / 'placements/axial_extra_7.json'
PRIORS = ['hR2_%02d' % i for i in range(1, 11)]
SEED = 20260951
FILES = [ROOT / 'experiments/2026-09-30-b-v6h-gain/placements/held_out_12.json',
         ROOT / 'experiments/2026-09-30-b-v6h-gain/placements/held_out_sheet_12.json',
         ROOT / 'experiments/2026-09-30-pair-v6h-carry/placements_confirmatory_DRAFT.json']


def main():
    taken = [(e['x'], e['y'], e['yaw_deg']) for f in FILES for e in json.loads(f.read_text())]
    rng = np.random.default_rng(SEED)
    rows = [{'name': 'X00_F_hR2_04', 'x': 0.9298, 'y': -0.0204, 'yaw_deg': -3.901, 'prior': 'hR2_04', 'sheet': 'coarse',
             'note': 'the previously failing pose (PR #283), with the sheet rounded from the beam'}]
    for i in range(6):
        xr = (0.92, 0.95) if i < 3 else (0.92, 1.07)
        while True:
            x, y = round(float(rng.uniform(*xr)), 3), round(float(rng.uniform(-0.03, 0.11)), 3)
            yaw = round(float(rng.uniform(-4.5, 4.5)), 2)
            prior = PRIORS[int(rng.integers(10))]
            if not any(math.hypot(x - a, y - b) < 0.01 and abs(yaw - c) < 0.5 for a, b, c in taken):
                break
        taken.append((x, y, yaw))
        rows.append({'name': f'X{i + 1:02d}', 'x': x, 'y': y, 'yaw_deg': yaw, 'prior': prior, 'sheet': 'coarse'})
    OUT.write_text(json.dumps(rows, indent=1) + '\n')
    print(OUT)
    for r in rows:
        print(r['name'], r['x'], r['y'], r['yaw_deg'], r['prior'], 'dx %+.0f' % ((r['x'] - round(r['x'] / .1) * .1) * 1000))


if __name__ == '__main__':
    main()
