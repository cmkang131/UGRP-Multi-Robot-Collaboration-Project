"""Build the command-only input table for the v101 unloaded gain calibration.

Reads ONLY the commands (never poses) of the recorded v98 DEV probe to (a) weight the fit by how the approach actually
uses each command amplitude and (b) provide the first drive leg of r1 and r2 as a held-out command replay. Ground truth
of the probe is not read. Output: configs/final_environment_gain_calibration_v101_inputs.json
"""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path('/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high-1f7fb800/zone_wide_door_geometry_v3')
OUT = ROOT / 'configs/final_environment_gain_calibration_v101_inputs.json'
LEVELS = {'forward': [0.03, 0.06, 0.09, 0.12], 'left': [0.02, 0.04, 0.06, 0.08], 'turn': [0.02, 0.05, 0.08, 0.10]}
AXES = ('forward', 'left', 'turn')
DT = 0.1
LEASE = 0.15


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def commands(rid):
    rows = [json.loads(line) for line in (PROBE / f'robots/{rid}/commands.jsonl').read_text().splitlines()]
    return [r for r in rows if r['kind'] == 'mecanum']


def usage(rows_by_robot):
    share = {}
    for axis in AXES:
        energy = np.zeros(len(LEVELS[axis]))
        count = np.zeros(len(LEVELS[axis]), int)
        levels = np.asarray(LEVELS[axis])
        for rows in rows_by_robot.values():
            for r in rows:
                u = abs(float(r[axis]))
                i = int(np.argmin(np.abs(levels - u)))
                energy[i] += u * u
                count[i] += int(u > 1e-9)
        total = energy.sum()
        share[axis] = {'levels': LEVELS[axis], 'energy_share': [round(float(e / total), 6) for e in energy],
                       'commands_nearest': [int(c) for c in count], 'total_energy': float(total)}
    return share


def first_leg(rows, gap=0.35):
    """First drive run (gap > 0.35 s splits runs), gridded on 0.1 s with the 0.15 s lease semantics."""
    start = 0
    for i in range(1, len(rows)):
        if rows[i]['t'] - rows[i - 1]['t'] > gap:
            break
        start = i
    leg = rows[:start + 1]
    t0, t1 = leg[0]['t'], leg[-1]['t']
    n = int(np.floor((t1 - t0) / DT + 1e-9)) + 2
    grid = []
    for j in range(n):
        tg = t0 + DT * j
        live = [r for r in leg if r['t'] <= tg + 1e-6 and tg - r['t'] <= LEASE + 1e-9]
        r = live[-1] if live else None
        grid.append([round(float(r[a]), 6) if r else 0.0 for a in AXES])
    return {'start_t_s': t0, 'end_t_s': t1, 'n_commands': len(leg), 'grid_dt_s': DT, 'commands': grid}


def main():
    nonzero = {}
    legs = {}
    for rid in ('r1', 'r2'):
        rows = commands(rid)
        nonzero[rid] = [r for r in rows if any(abs(r[a]) > 1e-9 for a in AXES)]
        legs[rid] = first_leg(nonzero[rid])
    value = {'schema': 'ugrp.final_environment_gain_calibration_inputs.v101',
             'qualification': 'command-only inputs; no probe pose/ground truth read',
             'source': {rid: {'path': str(PROBE / f'robots/{rid}/commands.jsonl'),
                              'sha256': sha(PROBE / f'robots/{rid}/commands.jsonl'),
                              'nonzero_mecanum_commands': len(nonzero[rid])} for rid in nonzero},
             'usage': usage(nonzero), 'replay_legs': legs}
    OUT.write_text(json.dumps(value, indent=1, sort_keys=True) + '\n')
    print(OUT, OUT.stat().st_size)
    for axis in AXES:
        print(axis, value['usage'][axis]['energy_share'], value['usage'][axis]['commands_nearest'])
    for rid in legs:
        print(rid, legs[rid]['start_t_s'], legs[rid]['end_t_s'], legs[rid]['n_commands'], len(legs[rid]['commands']))


if __name__ == '__main__':
    main()
