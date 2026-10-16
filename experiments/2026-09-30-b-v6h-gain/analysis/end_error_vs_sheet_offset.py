#!/usr/bin/env python3
"""L1 end error against the beam-minus-rounded-order-sheet offset (sheet-consistent cohorts sA/sB).

The order sheet is the setup pose rounded to a 0.1 m / 10 deg grid, so the route start follows the rounded pose while the beam sits
dx = x - round(x, 0.1) away from it. Usage: end_error_vs_sheet_offset.py <results json> <placements json>
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness.pair_owncam_approach import coarse_order_sheet  # noqa: E402

res = json.load(open(sys.argv[1]))[0]
pl = json.load(open(sys.argv[2]))
err = {u: float(np.mean([c['legs']['1']['end_error_m'] * 1000 for c in res['cases'] if c['unit'] == u])) for u in {c['unit'] for c in res['cases']}}
dx = []
e = []
for p in pl:
    s = coarse_order_sheet([p['x'], p['y'], math.radians(p['yaw_deg'])])['beam_xyyaw']
    dx.append((p['x'] - s[0]) * 1000)
    e.append(err[p['name']])
    print(f"{p['name']} beam-sheet dx {dx[-1]:+5.0f} mm  L1 end error {e[-1]:5.0f} mm")
dx, e = np.array(dx), np.array(e)
b, a = np.polyfit(dx, e, 1)
print(f'linear fit: end_error = {a:.0f} mm + {b:.2f} * dx   corr {np.corrcoef(dx, e)[0, 1]:.2f}   (gate: 100 mm)')
