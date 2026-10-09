"""GT scoring of completed replay; never imported by any controller."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent

def main(source,out):
    assert not out.exists();r=json.loads(source.read_text())
    assert not r['gt_inputs'] and not r['physics_runs']
    raw=Path(r['source_raw']);gt=[json.loads(l) for l in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
    tt=np.array([g['t'] for g in gt]);xy=np.array([g['robot_xyz_m'][:2] for g in gt]);yaw=np.unwrap([g['robot_yaw_rad'] for g in gt])
    rows=[]
    for m,a in zip(r['measurements'],r['amcl']['rows']):
        assert abs(m['t']-a['t'])<1e-9
        if not (71<=a['t']<236.8 and a['visual_weight_update']):continue
        t=m['t'];actual=np.array([np.interp(t,tt,xy[:,i]) for i in (0,1)])
        gtyaw=float(np.interp(t,tt,yaw));q=dict(t=t,columns=a['columns'],kl=a['kl'],actual_xy_m=actual.tolist())
        for mode in ('mean','estimate'):
            vals={}
            for stage in ('prior','weighted','resampled'):
                value=m[f'{stage}_{mode}']
                p=np.asarray(value[:3] if mode=='mean' else [value[k] for k in ('x','y','yaw')])
                vals[stage]=p
                q[f'{stage}_{mode}']=p.tolist()
                q[f'{stage}_{mode}_error_m']=float(np.linalg.norm(p[:2]-actual))
                q[f'{stage}_{mode}_yaw_error_deg']=float(np.degrees(np.arctan2(np.sin(p[2]-gtyaw),np.cos(p[2]-gtyaw))))
            v=actual-vals['prior'][:2]
            for stage in ('weighted','resampled'):
                d=vals[stage][:2]-vals['prior'][:2];norm=np.linalg.norm(d)*np.linalg.norm(v)
                q[f'{stage}_{mode}_delta_m']=d.tolist()
                q[f'{stage}_{mode}_step_m']=float(np.linalg.norm(d))
                q[f'{stage}_{mode}_toward_truth_cos']=float(d@v/norm) if norm>1e-15 else None
                q[f'{stage}_{mode}_error_reduction_m']=q[f'prior_{mode}_error_m']-q[f'{stage}_{mode}_error_m']
        rows.append(q)
    report=dict(schema='ugrp.s2.contact_update_scoring.v1',physics_runs=0,gt_usage='closed-file evaluation only',
        rows=rows,informative_updates=len(rows),
        weighted_mean_improved=sum(q['weighted_mean_error_reduction_m']>0 for q in rows),
        resampled_mean_improved=sum(q['resampled_mean_error_reduction_m']>0 for q in rows),
        reported_pose_improved=sum(q['resampled_estimate_error_reduction_m']>0 for q in rows),
        source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
if __name__=='__main__':main(*map(Path,sys.argv[1:]))
