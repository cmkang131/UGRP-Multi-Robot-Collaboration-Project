#!/usr/bin/env python3
"""Make real_robot calibration JSON from bench measurements (T03) and the sim pulse reference.

For each sim wheel value v the board speed b is chosen so that the REAL displacement of a 0.1 s pulse
at b equals the SIM displacement at v (median over repeats, linear interpolation on the measured board
speeds). Values the real robot cannot reach inside 35..100 are left out and reported, never clamped.

    python3 scripts/fit_real_robot_calibration.py --bench bench.csv --robot-id ugrp1 \
        --wheel-map configs/real_robot/wheel_map_from_drive_map.json \
        --sim-reference experiments/2026-11-19-sim2real-dr/sim_pulse_reference.jsonl \
        --servo-min-duration-s <measured/specified> --out configs/real_robot/ugrp1.json
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

SIM_VALUES = (0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37, 0.38, 0.39, 0.40)


def interp_inverse(points, y):
    """points: [(x, y)] sorted by x with y increasing; return x for y (None outside range)."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if y0 <= y <= y1 and y1 > y0:
            return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
    return None


def fit(bench_rows, sim_rows, direction='forward', pulse_s=0.10):
    key = {'forward': 'forward_mm', 'left': 'lateral_mm'}[direction]
    real = defaultdict(list)
    for r in bench_rows:
        if r.get('mode') == 'floor' and r['direction'] == direction and r['split'] == 'fit' \
                and abs(float(r['pulse_s']) - pulse_s) < 1e-6 and r.get(f'd{"x" if direction == "forward" else "y"}_mm') not in ('', None):
            real[int(r['board_speed'])].append(float(r['dx_mm' if direction == 'forward' else 'dy_mm']))
    real_pts = sorted((b, statistics.median(v)) for b, v in real.items())
    if len(real_pts) < 2 or any(y1 <= y0 for (_, y0), (_, y1) in zip(real_pts, real_pts[1:])):
        raise ValueError(f'need >=2 board speeds with increasing median displacement, got {real_pts}')
    sim = defaultdict(list)
    for r in sim_rows:
        if r['direction'] == direction and abs(r['pulse_s'] - pulse_s) < 1e-6:
            sim[round(r['value'], 2)].append(r[key])
    points, skipped = [], []
    for v in SIM_VALUES:
        if v not in sim:
            continue
        target = statistics.median(sim[v])
        if target <= 0.5:  # sim dead zone (no motion): nothing to match; the contract value still maps to the floor rule
            skipped.append({'sim_value': v, 'sim_mm': target, 'why': 'sim does not move at this value'})
            continue
        b = interp_inverse(real_pts, target)
        if b is None or not 35 <= b <= 100:
            skipped.append({'sim_value': v, 'sim_mm': target, 'why': f'real board range {real_pts[0][0]}..{real_pts[-1][0]} does not reach it'})
            continue
        points.append([v, round(b, 1)])
    return points, skipped, real_pts


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bench', required=True)
    p.add_argument('--sim-reference', required=True)
    p.add_argument('--wheel-map', required=True)
    p.add_argument('--robot-id', required=True)
    p.add_argument('--servo-min-duration-s', type=float, required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args(argv)
    rows = list(csv.DictReader(open(a.bench)))
    checks = [r for r in rows if r.get('mode') == 'lifted']
    bench_ok = len(checks) >= 4 and all(r['check'] == 'pass' for r in checks[-4:])
    sim_rows = [json.loads(line) for line in open(a.sim_reference)]
    points, skipped, real_pts = fit(rows, sim_rows)
    if not points:
        raise SystemExit(f'no sim value could be matched: {skipped}')
    dead = [x['sim_value'] for x in skipped if x['why'].startswith('sim does not move')]
    dead_max = max(dead) if dead else None
    cal_points = list(points)
    # Bridge the continuous (dead_max, first_fitted_sim] gap for ACT commands: <= dead_max still maps
    # to 0 via sim_no_motion_max, while values strictly above dead_max interpolate from BOARD_MIN_ABS_SPEED.
    if dead_max is not None and cal_points[0][0] > dead_max:
        cal_points.insert(0, [dead_max, 35.0])
    wmap = json.loads(Path(a.wheel_map).read_text())['wheels']
    cal = {'robot_id': a.robot_id, 'measured': bench_ok,
           'source': {'bench_csv': a.bench, 'sim_reference': a.sim_reference, 'wheel_map': a.wheel_map,
                      'real_forward_median_mm_per_0.1s': real_pts, 'skipped': skipped,
                      'wheel_map_bench_checks': len(checks), 'measured_requires': 'last 4 lifted checks pass'},
           'wheels': {name: {'motor': m['motor'], 'sign': m['sign'], 'points': cal_points} for name, m in wmap.items()},
           'servo_min_duration_s': a.servo_min_duration_s,
           'sim_no_motion_max': dead_max}
    Path(a.out).write_text(json.dumps(cal, indent=1))
    print(json.dumps({'measured': bench_ok, 'points': points, 'skipped': skipped}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
