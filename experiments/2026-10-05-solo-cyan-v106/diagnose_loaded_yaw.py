"""Offline command-model comparison; saved eval truth is used only for scoring.

Cargo bearing relative to robot centre is a rigid-grasp heading proxy, not a
recorded robot yaw. Its radius and agreement with cargo orientation are audited.
"""
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness import zone_solo_cyan_contract_v106 as c
from harness import zone_solo_cyan_v106 as s


def solo_yaw(params):
    unloaded, loaded = params['motion'], params['motion_loaded']
    loaded['gain'][2] = copy.deepcopy(unloaded['gain'][2])
    loaded['tau_axis_s'][2] = unloaded['tau_axis_s'][2]
    loaded['deadband']['u1'][2] = 1e-6


def main():
    root, output = map(Path, sys.argv[1:])
    r = json.loads((root/'student_record.json').read_text())
    truth = [json.loads(x) for x in (root/'eval_only/trajectory.jsonl').read_text().splitlines()]
    starts = [e['t'] for e in r['events'] if e['event'] == 'state' and e['state'] == 'carry']
    ends = [e['t'] for e in r['events'] if e['event'] == 'cyan_setdown_relook']
    legs = list(zip(starts, ends))
    predictions = {}
    for name in ('v102_pair', 'unloaded_yaw'):
        src = s.partial.build_source_class()(c.hp.resolve(c.MAP_ID)[0], c.ROOT/c.CALIBRATION, c.CALIBRATION_SHA, 911)
        src.carry_yaw_fallback = None
        if name == 'unloaded_yaw':
            solo_yaw(src.loc._pf.params)
        src.init_prior((0., 0., 0.), (.001, .001, .001), source='offline command prediction only')
        events = [(q['t'], 0, q) for q in r['commands']] + [(t, 1, None) for leg in legs for t in leg]
        estimates = {}
        for t, kind, row in sorted(events, key=lambda e: (e[0], e[1])):
            if kind == 0:
                src.on_command(row)
            else:
                q = src.report(t)
                estimates[t] = q.yaw_rad
        predictions[name] = [math.degrees(estimates[b]-estimates[a]) for a, b in legs]
        src.close()
    rows = []
    for i, (a, b) in enumerate(legs):
        subset = [q for q in truth if a <= q['t'] <= b]
        def bearing(q):
            d = np.array(q['cyan_xyz_m'][:2])-q['robot_xyz_m'][:2]
            return math.atan2(d[1], d[0])
        actual = np.array(subset[-1]['robot_xyz_m'][:2])-subset[0]['robot_xyz_m'][:2]
        poses = [min(r['poses'], key=lambda q: abs(q['t']-t)) for t in (a,b)]
        estimated = np.array([poses[1][k]-poses[0][k] for k in ('x','y')])
        radii = [np.linalg.norm(np.array(q['cyan_xyz_m'][:2])-q['robot_xyz_m'][:2]) for q in subset]
        rows.append({'start_s': a, 'end_s': b, 'actual_xy_delta_m': actual.tolist(),
            'estimated_xy_delta_m': estimated.tolist(), 'distance_ratio': float(np.linalg.norm(actual)/np.linalg.norm(estimated)),
            'direction_error_deg': math.degrees(math.atan2(actual[1],actual[0])-math.atan2(estimated[1],estimated[0])),
            'cargo_bearing_delta_deg': math.degrees(bearing(subset[-1])-bearing(subset[0])),
            'cargo_radius_min_max_m': [min(radii),max(radii)],
            'predicted_yaw_delta_deg': {name: values[i] for name, values in predictions.items()}})
    result = {'source': str(root), 'truth_yaw_recorded': False, 'scope': 'offline exploratory scoring; rigid cargo bearing is a proxy',
        'source_sha256': {f: hashlib.sha256((root/f).read_bytes()).hexdigest() for f in ('student_record.json','eval_only/trajectory.jsonl')},
        'legs': rows}
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
