"""Frozen independent calibration runs only; never v149 or smoke GT."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scripts.fit_s2_pulse_calibration import training, interpolate
from harness.zone_s2_realism_contract_v122 import PULSE_MODEL
from harness.zone_solo_cyan_pulse_cal import response

RAW=Path('/Users/changmin/projects/ugrp/outputs/pulse-rotation-audit-v1/measurement')
OLD=Path('/Users/changmin/projects/ugrp/outputs/s2-pulse-cal-20261007/offline/pulses.jsonl')


def read(p): return json.loads(Path(p).read_text())


def fit():
    model=read(PULSE_MODEL)
    assert hashlib.sha256(OLD.read_bytes()).hexdigest()==model['input']['sha256']
    manifest=read(RAW/'artifacts.sha256.json')
    for name in ('eval_only/trajectory.jsonl','schedule.json','result.json'):
        assert hashlib.sha256((RAW/name).read_bytes()).hexdigest()==manifest[name]
    result=read(RAW/'result.json'); assert result['status']=='RECORDED'
    gt=[json.loads(s) for s in (RAW/'eval_only/trajectory.jsonl').read_text().splitlines()]
    ts=np.array([r['t'] for r in gt]);xy=np.array([r['robot_xyz_m'][:2] for r in gt]);yaw=np.unwrap([r['robot_yaw_rad'] for r in gt])
    times=np.arange(5)/20
    groups={sign:{'fit':[],'check':[]} for sign in (-1,1)}
    for block in read(RAW/'schedule.json')['blocks']:
        for i in range(block['pulses']):
            start=result['start_sim_s']+block['start_tick']/20+i*.2
            startxy=np.array([np.interp(start,ts,xy[:,j]) for j in range(2)])
            a=np.interp(start,ts,yaw);c,s=np.cos(a),np.sin(a)
            curve=np.zeros((len(times),3))
            curve[:,:2]=(np.array([np.interp(start+times,ts,xy[:,j]) for j in range(2)]).T-startxy)@np.array([[c,-s],[s,c]])
            curve[:,2]=np.interp(start+times,ts,yaw)-a
            groups[block['sign']][block['split']].append(curve)
    profiles={}; checks={}; rot_num=xy_num=den=0.
    for sign in (-1,1):
        key=f'0:turn:{sign*.35:.2f}:0.10';p=model['profiles'][key]
        train=np.array(groups[sign]['fit']);check=np.array(groups[sign]['check']);mean=train.mean(0)
        # User scope: correct XY, retain existing yaw gain and planner thresholds.
        mean[:,2]=[response(p,t)[2] for t in times]
        residual=train[:,-1]-mean[-1]
        rot_num+=float((residual[:,2]**2).sum());xy_num+=float((residual[:,:2]**2).sum());den+=len(train)*mean[-1,2]**2
        profiles[key]=dict(times=times.tolist(),xy_curve=mean[:,:2].tolist(),n=len(train),independent_repeats=3)
        before=check[:,-1,:2]-np.array(p['mean_delta'][:2]);after=check[:,-1,:2]-mean[-1,:2]
        checks[key]=dict(n=len(check),xy_rmse_before=float(np.sqrt((before**2).sum(1).mean())),
            xy_rmse_after=float(np.sqrt((after**2).sum(1).mean())),old_xy=p['mean_delta'][:2],new_xy=mean[-1,:2].tolist())
    forward=[r for r in map(json.loads,OLD.read_text().splitlines()) if not r['loaded'] and r['axis']=='forward' and training(r) and r['key'] in model['profiles']]
    xyn=yawn=td=0.
    for row in forward:
        p=model['profiles'][row['key']];d=np.array(p['mean_delta']);e=interpolate(row,[p['times'][-1]])[0]-d
        xyn+=e[0]**2+e[1]**2;yawn+=e[2]**2;td+=d[0]**2+d[1]**2
    return dict(option='rotation_xy_alpha_v1',runtime_gt=False,profiles=profiles,
        alpha_1_to_4=[rot_num/den,yawn/td,xyn/td,xy_num/den],
        scope='unloaded turn XY and noise only; existing yaw, forward, lateral, loaded unchanged',
        fit='rotation seed32001 repeats1-3; v122 existing unloaded forward training split',
        check='rotation repeats4-5; retrospective calibration check, not independent research',
        source_sha=result['source_sha'],base_model_sha256=hashlib.sha256(Path(PULSE_MODEL).read_bytes()).hexdigest(),
        input_hashes={str(RAW/name):manifest[name] for name in ('eval_only/trajectory.jsonl','schedule.json','result.json')},
        forward_input=dict(path=str(OLD),sha256=hashlib.sha256(OLD.read_bytes()).hexdigest())),checks


if __name__=='__main__':
    asset,checks=fit()
    out=Path('harness/calibrations/pulse_rotation_xy_alpha_v1.json');out.parent.mkdir(exist_ok=True)
    with out.open('x') as f:f.write(json.dumps(asset,indent=2,allow_nan=False)+'\n')
    Path(__file__).with_name('calibration-check.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps(dict(alpha=asset['alpha_1_to_4'],check=checks),indent=2))
