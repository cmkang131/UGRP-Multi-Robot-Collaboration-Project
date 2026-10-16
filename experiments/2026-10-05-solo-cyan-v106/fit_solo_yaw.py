"""Exploratory zero-intercept batch least squares; no simulator or controller.

Usage: python fit_solo_yaw.py RUN3 RUN4 OUTPUT_JSON
Uses raw issued command integrals and rigid-grasp cargo bearing as yaw proxy.
Run3 fits two coefficients, run4 is a retrospective check, both s911.
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np


def rows_for(root):
    r = json.loads((root/'student_record.json').read_text())
    truth = [json.loads(x) for x in (root/'eval_only/trajectory.jsonl').read_text().splitlines()]
    starts = [e['t'] for e in r['events'] if e['event'] == 'state' and e['state'] == 'carry']
    ends = [e['t'] for e in r['events'] if e['event'] == 'cyan_setdown_relook']
    rows = []
    for i, (a, b) in enumerate(zip(starts, ends)):
        u, expires, last, integral = np.zeros(3), 0., a, np.zeros(3)
        for q in r['commands']:
            t = q['t']
            if t > b:
                break
            if t >= a:
                integral += max(0., min(t, expires)-last)*u
                last = t
            if q['kind'] == 'mecanum':
                u = np.array([q[k] for k in ('forward', 'left', 'turn')])
                expires = t+q['duration_s']
            else:
                u, expires = np.zeros(3), t
        integral += max(0., min(b, expires)-last)*u
        actual = [min(truth, key=lambda q: abs(q['t']-t)) for t in (a, b)]
        bearings = [math.atan2(q['cyan_xyz_m'][1]-q['robot_xyz_m'][1],
                               q['cyan_xyz_m'][0]-q['robot_xyz_m'][0]) for q in actual]
        samples = [q for q in truth if a <= q['t'] <= b]
        radii = [math.dist(q['cyan_xyz_m'][:2], q['robot_xyz_m'][:2]) for q in samples]
        rows.append({'source': str(root), 'leg': i, 'start_s': a, 'end_s': b,
                     'command_integral': integral.tolist(), 'yaw_proxy_delta_rad': bearings[1]-bearings[0],
                     'cargo_radius_min_max_m': [min(radii), max(radii)]})
    return rows


def main():
    train, check, output = map(Path, sys.argv[1:])
    rows = rows_for(train)+rows_for(check)
    x = np.array([r['command_integral'][1:] for r in rows[:3]])
    y = np.array([r['yaw_proxy_delta_rad'] for r in rows[:3]])
    coef, _, rank, singular = np.linalg.lstsq(x, y, rcond=None)
    assert rank == 2
    for r in rows:
        r['residual_deg'] = math.degrees(r['yaw_proxy_delta_rad']-np.dot(r['command_integral'][1:], coef))
    result = {'method': 'zero-intercept least squares; raw left+turn command integrals',
              'scope': 'train run3, retrospective check run4; both exploratory s911; robot yaw unrecorded',
              'yaw_gain_raw_left_turn': coef.tolist(), 'rank': int(rank), 'singular_values': singular.tolist(),
              'source_sha256': {str(root/f): hashlib.sha256((root/f).read_bytes()).hexdigest()
                                for root in (train, check) for f in ('student_record.json', 'eval_only/trajectory.jsonl')},
              'rows': rows}
    with output.open('x') as f:
        f.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'coefficients': coef.tolist(), 'max_check_residual_deg': max(abs(r['residual_deg']) for r in rows[3:])}))


if __name__ == '__main__':
    main()
