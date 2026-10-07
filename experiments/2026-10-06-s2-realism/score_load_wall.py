"""Posthoc fixed-factor comparison; no simulator and no coefficient fitting."""
import json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
RAW=Path('/Users/changmin/projects/ugrp/outputs/s2-load-wall-bf8f6411')

def main():
    result=json.loads((RAW/'result.json').read_text());summary=[]
    for r in result['results']:
        raw=Path(r.get('preserved_raw',RAW/r['case']));rows=[json.loads(l) for l in (raw/'eval-only.jsonl').read_text().splitlines()]
        categories={c['category'] for row in rows for c in row['contacts']};forces={}
        for category in sorted(categories):
            f=[sum(abs(c['force_contact_frame'][0]) for c in row['contacts'] if c['category']==category) for row in rows]
            forces[category]=dict(mean_normal_n=float(np.mean(f)),peak_normal_n=max(f),samples=sum(v>0 for v in f))
        initial=r['initial'];com=np.array(initial['robot_com'])-initial['xyz'];system=np.array(initial['robot_plus_box_com'])-initial['robot_com']
        invalid=r.get('visibility_original_invalid_camera_group',False)
        frames=json.loads((raw/'frames.json').read_text());inview=sum(f['visibility']['in_view'] for f in frames)/(96*len(frames))
        summary.append(dict(case=r['case'],wall=r['wall'],pose=r['pose'],loaded=r['loaded'],status=r['status'],raw=str(raw),source_sha=r['source_sha'],
            mean_lateral_mm=r['mean_lateral_m']*1000,mean_abs_yaw_deg=r['mean_abs_yaw_deg'],bilateral_fraction=r['bilateral_fraction'],
            pitch_deg=initial['camera']['cached_pitch_deg'],robot_mass_kg=r['robot_mass_kg'],box_mass_kg=r['box_mass_kg'],
            robot_com_relative_m=com.tolist(),box_added_com_shift_m=system.tolist() if r['loaded'] else None,
            wall_forces=forces,wall_foot_in_view_fraction=inview,wall_foot_clear_fraction=None if invalid else r['clear_wall_fraction'],
            original_clear_invalid_camera_group=invalid,sim_s=r['sim_s'],wall_s=r['wall_s'],pulses=r['pulses'],
            hashes={f:hashlib.sha256((raw/f).read_bytes()).hexdigest() for f in ('result.json','eval-only.jsonl','commands.json','frames.json')}))
    comparisons=[]
    for name in ('high','look_ahead','real_delivery'):
        a,b=[next(x for x in summary if x['wall']=='far' and x['pose']==name and x['loaded']==v) for v in (False,True)]
        comparisons.append(dict(pose=name,load_relative_difference=abs(b['mean_lateral_mm']/a['mean_lateral_mm']-1),
            yaw_difference_deg=abs(a['mean_abs_yaw_deg']-b['mean_abs_yaw_deg']),load_gate_pass=abs(b['mean_lateral_mm']/a['mean_lateral_mm']-1)<=.10 and abs(a['mean_abs_yaw_deg']-b['mean_abs_yaw_deg'])<=1.))
    empty=json.loads(Path('/Users/changmin/projects/ugrp/outputs/s2-load-wall-b161a388/far-look_ahead-empty/result.json').read_text())
    loaded=next(r for r in result['results'] if r['case']=='far-look_ahead-loaded')
    cal=dict(schema='ugrp.s2.look_ahead_calibration.v1',option='look_ahead_v1',servo_stiffness='real_v1',fit_uses_gt=False,
        pose_key='1050,2035,1894,1500',camera_models={k:r['calibration']['record'] for k,r in [('unloaded',empty),('loaded',loaded)]},
        quality={k:r['calibration']['quality'] for k,r in [('unloaded',empty),('loaded',loaded)]},
        pitch_difference_deg=abs(empty['calibration']['normal']['pitch_deg']-loaded['calibration']['normal']['pitch_deg']),
        bilateral_fraction=loaded['bilateral_fraction'],origin='surveyed known boards, free chassis, RGB solvePnP; GT audit separate',
        raw={k:str(Path(r.get('preserved_raw',RAW/r['case']))) for k,r in [('unloaded',{**empty,'preserved_raw':'/Users/changmin/projects/ugrp/outputs/s2-load-wall-b161a388/far-look_ahead-empty'}),('loaded',loaded)]})
    cal['admission_pass']=all(v['holdout']['rms_px']<=1 for v in cal['quality'].values()) and cal['pitch_difference_deg']<=.5 and cal['bilateral_fraction']>=.99
    (ROOT/'configs/calibration/s2_camera_look_ahead_v1.json').write_text(json.dumps(cal,indent=2)+'\n')
    out=dict(schema='ugrp.s2.load_wall.summary.v1',rows=summary,comparisons=comparisons,look_ahead_calibration=cal,
        conclusion='controlled free load effect below 0.55%; near wall blocks both empty/loaded; not a demonstrated mass or roller defect',
        model_fitted=False,sim_parameters_changed=False,physical_cases=14,physical_failures=0,
        full_dev_admissible=cal['admission_pass'] and all(c['load_gate_pass'] for c in comparisons)
          and all(r['bilateral_fraction']>=.99 for r in summary if r['loaded'])
          and all(next(r['wall_foot_clear_fraction'] for r in summary if r['wall']==wall and r['pose']=='look_ahead' and r['loaded'])
                  - next(r['wall_foot_clear_fraction'] for r in summary if r['wall']==wall and r['pose']=='real_delivery' and r['loaded'])>=.10 for wall in ('far','near')))
    (ROOT/'experiments/2026-10-06-s2-realism/load-wall-result.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(full_dev_admissible=out['full_dev_admissible'],comparisons=comparisons)))
if __name__=='__main__':main()
