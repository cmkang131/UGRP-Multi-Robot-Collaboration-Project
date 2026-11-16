"""Evaluation-only camera geometry sensitivity; no refit, no controller import."""
import json,math,hashlib
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
from harness.zone_solo_cyan_progress_noise import ground,rigid
OUT=Path('/Users/changmin/projects/ugrp/outputs/s2-ground-vo-20261007')
def main():
    r=json.loads((OUT/'replay-candidate-allposes.json').read_text());raw=Path(r['source_raw'])
    read=lambda p:[json.loads(x) for x in (raw/p).read_text().splitlines()]
    truth={round(v['t'],6):v for v in read('eval_only/trajectory.jsonl')}
    cams={round(v['t'],6):v for v in read('eval_only/camera-pose.jsonl')}
    def camera(t):
        tr=truth[round(t,6)];cam=cams[round(t,6)];a=tr['robot_yaw_rad'];c,s=np.cos(a),np.sin(a)
        rz=np.array([[c,-s,0],[s,c,0],[0,0,1]])
        return NS(origin=rz.T@(np.array(cam['camera_cached_xyz_m'])-np.r_[tr['robot_xyz_m'][:2],0.]),
            _rot=rz.T@np.array(cam['camera_cached_optical_rotation']))
    rows=[]
    for pulse in r['ground_vo']['rows']:
        for obs in pulse.get('intervals',[]):
            if obs['status']!='measured':continue
            a=ground(camera(obs['from_t']),np.array(obs['before_uv']))[0]
            b=ground(camera(obs['t']),np.array(obs['after_uv']))[0]
            rot,d=rigid(a,b);nom=np.array(obs['delta']);n=np.linalg.norm(d)
            rows.append(dict(t=obs['t'],pulse_t=pulse['t'],key=pulse['key'],loaded=pulse.get('loaded'),
                fixed_delta=nom.tolist(),eval_geometry_delta=[*d,float(np.arctan2(rot[1,0],rot[0,0]))],
                scale_fixed_over_eval=None if n<.001 else float(np.linalg.norm(nom[:2])/n),
                geometry_difference_m=float(np.linalg.norm(nom[:2]-d))))
    quant=lambda values:np.quantile(values,[0,.5,.95,1]).tolist() if values else None
    summary=[]
    for loaded in (False,True):
        subset=[x for x in rows if x['loaded']==loaded]
        summary.append(dict(loaded=loaded,intervals=len(subset),
            scale_ratio_quantiles=quant([x['scale_fixed_over_eval'] for x in subset if x['scale_fixed_over_eval'] is not None]),
            geometry_delta_difference_m_quantiles=quant([x['geometry_difference_m'] for x in subset])))
    result=dict(schema='ugrp.s2.ground_vo.scale_eval.v1',summary=summary,rows=rows,
        gt_use='evaluation only after frozen replay; same inlier pixels, no re-fitting or feedback',
        scale_definition='fixed camera geometry / per-frame evaluation camera geometry, translation >=1mm; not direct true-motion scale',
        files={p:hashlib.sha256((raw/p).read_bytes()).hexdigest() for p in ['eval_only/trajectory.jsonl','eval_only/camera-pose.jsonl']})
    with (OUT/'scale-eval.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
