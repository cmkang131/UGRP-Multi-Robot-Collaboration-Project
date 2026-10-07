"""Counterfactual static geometry only; never a new-view RGB/PF replay.

Evaluation trajectory is confined here. No simulator is constructed. Saved
HIGH pixels and held-object poses are not transplanted into a different view.
"""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_visibility import (old, lines, nominal_camera, wall_segments,
    bottom_projection, wall_depths, pixel_rays, robot_boxes, shadow_depths, high, K)
from harness.zone_solo_cyan_real_carry import CARRY

HERE = Path(__file__).resolve().parent


def opportunity_metrics(times, counts, window, minimum=6):
    """Ideal geometric opportunities, NOT measurements or last_fix_t."""
    ok = [float(t) for t, n in zip(times, counts) if n >= minimum]
    boundaries = [window[0], *ok, window[1]]
    gaps = np.diff(boundaries)
    i = int(np.argmax(gaps))
    return dict(frames=len(times), qualifying_frames=len(ok),
                max_opportunity_gap_sim_s=float(gaps[i]),
                longest_gap_endpoints=[boundaries[i], boundaries[i+1]])


def models(spec):
    out = {}
    for name in spec['geometry_variants']:
        pose = high.HIGH if name.startswith('HIGH') else CARRY
        model = nominal_camera(pose, np.linspace(8, 631, spec['columns']).astype(int))
        if name.endswith('fixed_sag'):
            c, s = np.cos(spec['fixed_sag_delta_rad']), np.sin(spec['fixed_sag_delta_rad'])
            model._rot = model._rot @ np.array([[1,0,0],[0,c,-s],[0,s,c]])
        out[name] = (model, robot_boxes({1:1500, **pose}, model))
    return out


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    dest = out/'geometry.json'
    if dest.exists() or (out/'rows.jsonl').exists():
        raise FileExistsError(out)
    spec = json.loads((HERE/'real-carry-criteria.json').read_text())
    static = old.contract.hp.resolve(old.contract.MAP_ID)[0]
    segments = wall_segments(static)
    cams = models(spec)
    summaries, hashes = [], {}
    with (out/'rows.jsonl').open('x') as log:
        for seed, sha in old.RUNS.items():
            raw = old.RAW/f's2-realism-{sha}-s{seed}-P1-2-place'
            window = old.carry_window(json.loads((raw/'student_record.json').read_text()))
            frames = [f for f in lines(raw/'robots/r3/frames.jsonl')
                      if window[0] <= f['sim_time'] < window[1]]
            gt = {round(g['t'],6):g for g in lines(raw/'eval_only/trajectory.jsonl')}
            actual = {round(g['t'],6):g for g in lines(raw/'eval_only/camera-pose.jsonl')}
            for rel in ('student_record.json', 'robots/r3/frames.jsonl',
                        'eval_only/trajectory.jsonl','eval_only/camera-pose.jsonl'):
                hashes[str(raw/rel)] = old.digest(raw/rel)
            counts = {k:dict(inside=[], map_clear=[], self_clear=[]) for k in cams}
            heights, pitches = [], []
            for i, f in enumerate(frames):
                t = f['sim_time']; g = gt[round(t,6)]; a = actual[round(t,6)]
                assert high.at_high({int(k):v for k,v in f['commanded_servo'].items()})
                heights.append(a['camera_cached_xyz_m'][2]); pitches.append(a['cached_pitch_deg'])
                pose = [*g['robot_xyz_m'][:2], g['robot_yaw_rad']]
                row = dict(seed=seed,t=t,variants={})
                for name, (cm, boxes) in cams.items():
                    rows, _, depth = bottom_projection(cm, pose, segments)
                    inside = np.isfinite(rows)&(rows>=4)&(rows<=470)
                    rays = pixel_rays(cm,cm.columns,np.nan_to_num(rows))
                    clear = inside&(wall_depths(cm,pose,rays,static)>=depth-1e-6)
                    shadows = shadow_depths(cm.origin,rays,boxes)
                    self_clear = clear&(np.minimum.reduce(list(shadows.values()))>=depth-1e-6)
                    values = dict(inside=int(inside.sum()),map_clear=int(clear.sum()),self_clear=int(self_clear.sum()))
                    row['variants'][name] = values
                    for key, value in values.items():counts[name][key].append(value)
                log.write(json.dumps(row,separators=(',',':'))+'\n')
                if i%2000 == 0:print(seed,i,len(frames),flush=True)
            times = [f['sim_time'] for f in frames]
            variants = {}
            for name, values in counts.items():
                variants[name] = {key:dict(
                    visible_columns=sum(v),total_columns=len(v)*spec['columns'],
                    visible_fraction=sum(v)/(len(v)*spec['columns']),
                    **opportunity_metrics(times,v,window,spec['minimum_columns']))
                    for key,v in values.items()}
                variants[name]['at_least_one_column'] = opportunity_metrics(times,values['map_clear'],window,1)
            summaries.append(dict(seed=seed,carry_window=list(window),variants=variants,
                actual_HIGH=dict(height_m_median=float(np.median(heights)),
                    pitch_deg_median=float(np.median(pitches)),pitch_deg_std=float(np.std(pitches)))))
            print('summary',seed,json.dumps(summaries[-1]),flush=True)
    posture = {}
    for name,(cm,_) in cams.items():
        rays = pixel_rays(cm,np.array([K[0,2],K[0,2]]),np.array([4.,470.]))
        floor = cm.origin+(-cm.origin[2]/rays[:,2,None])*rays
        posture[name] = dict(height_m=float(cm.origin[2]),
            pitch_deg=float(np.degrees(np.arcsin(cm._rot[2,2]))),floor_x_range_m=floor[:,0].tolist())
    result = dict(schema='ugrp.s2.real-carry.geometry.v1',criteria_sha256=old.digest(HERE/'real-carry-criteria.json'),
        script_sha256=old.digest(__file__),source_hashes=hashes,
        physics_runs=0,render_runs=0,model_calls=0,GT_usage='posthoc geometric evaluation only',
        actual_new_pose_fix_gap_s=None,actual_new_pose_carry_rmse_m=None,
        actual_new_pose_replay='unavailable: saved HIGH pixels cannot supply a different view',
        full_dev_admitted=False,criteria=spec,posture_geometry=posture,summaries=summaries,
        limitation='opportunities only; no image detection, pose prior/gate, cargo in new grasp, calibration or physical carrying stability measured',
        rows_sha256=old.digest(out/'rows.jsonl'))
    dest.write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    main(p.parse_args().output)
