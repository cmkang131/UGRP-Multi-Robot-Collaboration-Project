"""Evaluation-only posture/load/motion strata; no actor imports this module."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import sys
import numpy as np

EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]
OUT = Path('/Users/changmin/projects/ugrp/outputs/online-camera-pitch-v1')
sys.path[:0] = [str(ROOT), str(ROOT/'experiments/2026-10-07-camera-pose-projection/code'),
               str(ROOT/'experiments/2026-10-07-s2-projection-comparison/code')]
import audit as a
import s2_path

POSTURES = {'740,2320,1320,1500': 'SEARCH', '896,2035,1894,1500': 'HIGH',
            '600,2200,1400,1500': 'CARRY'}


def load_class(s):
    if all(s['finger_contacts']) and s['cyan_min_z_m'] > .01:
        return 'held_airborne'
    if not any(s['finger_contacts']) and s['cyan_min_z_m'] <= .005:
        return 'unloaded_ground'
    return 'ambiguous'


def kinematics(rows):
    t = np.array([r['t'] for r in rows])
    xy = np.array([r['robot_xyz_m'][:2] for r in rows])
    velocity = np.gradient(xy, t, axis=0)
    speed = np.linalg.norm(velocity, axis=1)
    acceleration = np.gradient(speed, t)
    omega = np.gradient(np.unwrap([r['robot_yaw_rad'] for r in rows]), t)
    return speed, acceleration, omega


def summarize(rows):
    result = dict(n=len(rows), matched_camera=sum(r['pitch_delta_deg'] is not None for r in rows))
    for key in ('pitch_delta_deg','loaded_counterfactual_delta_deg','actual_pitch_deg','body_tilt_deg',
                'non_body_residual_lower_bound_deg','speed_m_s','acceleration_m_s2'):
        values = [r[key] for r in rows if r[key] is not None]
        result[key] = a.stats(values)
        result[key]['max'] = max(values) if values else None
    return result


def main():
    dest = OUT/'conditions'
    dest.mkdir(parents=True, exist_ok=False)
    eps = {k:v for k,v in a.old.EPISODES.items() if k in ('s1045','s1046','s1047')}
    eps['s1050'] = Path('/Users/changmin/projects/ugrp/outputs/s2-realism-97fcb5d2-s1050-P1-2-place')
    _, models = s2_path.models()
    factories = {s:s2_path.column_model_factory(a.old.mp, a.COLS, loaded=s=='loaded')
                 for s in ('unloaded','loaded')}
    sources = {}
    summaries = {}
    csvrows = []
    for case,ep in eps.items():
        frames,_ = a.old.own_inputs(ep, 'r3')
        own,cache = [],{}
        last_key,last_change = None,-np.inf
        for f in frames:
            servo = {int(k):v for k,v in f['commanded_servo'].items()}
            key = ','.join(str(servo[k]) for k in (3,4,5,6))
            if key != last_key:
                last_key,last_change = key,f['sim_time']
            if key not in cache:
                cache[key] = {}
                if key in models['unloaded']:
                    for state, factory in factories.items():
                        cm = factory(servo)
                        cache[key][state] = np.degrees(a.angles(cm._rot))[1]
            own.append(dict(frame_id=f['frame_id'],t=f['sim_time'],key=key,
                            posture=POSTURES.get(key,'PICK_transition'),
                            settling='settling' if f['sim_time']-last_change < .5 else 'settled',
                            nominal=cache[key]))
        a.write(dest/f'{case}-own.json', own)
        seal = a.digest(dest/f'{case}-own.json')
        # All following logs are evaluation truth, never inputs to VP estimation.
        paths = {name:ep/f'eval_only/{name}.jsonl' for name in ('trajectory','camera-pose','supervisor')}
        bodylist = a.old.base.read_rows(paths['trajectory'])
        body = {round(r['t'],6):r for r in bodylist}
        actual = {round(r['t'],6):r for r in a.old.base.read_rows(paths['camera-pose'])}
        supervisor = {round(r['t'],6):r for r in a.old.base.read_rows(paths['supervisor'])}
        speed,acc,omega = kinematics(bodylist)
        motion = {round(r['t'],6):(speed[i],acc[i],omega[i]) for i,r in enumerate(bodylist)}
        rows,missing = [],Counter()
        for f in own:
            t = round(f['t'],6)
            if any(t not in d for d in (body,actual,supervisor,motion)):
                missing['time_join'] += 1
                continue
            ac = a.actual_camera(actual[t],body[t])
            pitch = float(np.degrees(a.angles(ac[1]))[1])
            diff = pitch-f['nominal']['unloaded'] if f['nominal'] else None
            loaded_diff = pitch-f['nominal']['loaded'] if f['nominal'] else None
            tilt = supervisor[t]['robot_tilt_deg']
            v,dv,w = motion[t]
            rows.append(dict(**f,load=load_class(supervisor[t]),
                motion='moving' if v>.01 or abs(w)>np.radians(1) else 'stopped',
                acceleration='accelerating' if dv>.05 else 'decelerating' if dv<-.05 else 'steady',
                pitch_delta_deg=diff,loaded_counterfactual_delta_deg=loaded_diff,
                actual_pitch_deg=pitch,body_tilt_deg=tilt,
                non_body_residual_lower_bound_deg=max(0.,abs(diff)-tilt) if diff is not None else None,
                speed_m_s=float(v),acceleration_m_s2=float(dv)))
        a.old.rows(dest/f'{case}-frames.jsonl',rows)
        groups = defaultdict(list)
        for r in rows:
            groups['all'].append(r)
            for dim in ('posture','key','load','motion','acceleration','settling'):
                groups[f'{dim}={r[dim]}'].append(r)
            joint = '|'.join(r[d] for d in ('posture','load','motion','acceleration','settling'))
            groups['cross='+joint].append(r)
            groups['pose_load='+r['posture']+'|'+r['load']+'|'+r['settling']].append(r)
            if 71. <= r['t'] <= 236.8 and case=='s1050':
                groups['s1050_prior_window'].append(r)
        result = dict(case=case,frames=len(frames),joined=len(rows),missing=dict(missing),
                      own_sha256=seal,groups={k:summarize(v) for k,v in groups.items()})
        summaries[case] = result
        for name,g in result['groups'].items():
            row = dict(case=case,group=name,n=g['n'],matched_camera=g['matched_camera'])
            for key in ('pitch_delta_deg','loaded_counterfactual_delta_deg','actual_pitch_deg','body_tilt_deg',
                        'non_body_residual_lower_bound_deg'):
                row.update({key+'_'+stat:g[key][stat] for stat in ('median','p05','p90','p95','max')})
            csvrows.append(row)
        assert seal == a.digest(dest/f'{case}-own.json')
        for p in [*paths.values(),ep/'robots/r3/frames.jsonl']:
            sources[str(p)] = a.digest(p)
        print(case,'frames/joined',len(frames),len(rows),'load',dict(Counter(r['load'] for r in rows)),flush=True)
    a.write(dest/'summary.json',summaries)
    a.write(EXP/'results/conditions.json',summaries)
    with (EXP/'results/conditions.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(csvrows[0]))
        writer.writeheader()
        writer.writerows(csvrows)
    a.write(dest/'sources.json',sources)


if __name__ == '__main__':
    main()
