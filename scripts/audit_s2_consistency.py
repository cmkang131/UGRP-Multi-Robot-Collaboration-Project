"""s2v44 retrospective bias/covariance decomposition; no controller changes."""
import argparse
import bisect
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scripts.audit_s2_formal_stops import RUNS, OUTPUTS, decisions, read, rows, sha, uncertain

REPLAY=OUTPUTS/'s2-rotation-left-v42-20261008/replay'
CRITERIA=Path('experiments/2026-10-06-s2-realism/consistency-criteria.json')


def summarize(samples):
    if not samples:return dict(n=0)
    e=np.array([q['error'] for q in samples]); cov=np.array([q['cov'] for q in samples])
    bias=e.mean(0); centered=e-bias; inv=np.linalg.inv(cov[:,:2,:2])
    raw=np.einsum('ni,nij,nj->n',e[:,:2],inv,e[:,:2])
    de=np.einsum('ni,nij,nj->n',centered[:,:2],inv,centered[:,:2])
    yaw=e[:,2]**2/cov[:,2,2]; yawde=centered[:,2]**2/cov[:,2,2]
    scale=np.array([1,1,180/math.pi]);mse=(e**2).mean(0);variance=(centered**2).mean(0)
    return dict(n=len(samples),bias_xy_m_yaw_deg=(bias*scale).tolist(),
        variance_xy_m2_yaw_deg2=(variance*scale**2).tolist(),
        mse_xy_m2_yaw_deg2=(mse*scale**2).tolist(),
        reported_mean_variance_xy_m2_yaw_deg2=(np.diagonal(cov,axis1=1,axis2=2).mean(0)*scale**2).tolist(),
        xy_bias_mse_fraction=float((bias[:2]**2).sum()/mse[:2].sum()),
        xy_nees_mean=float(raw.mean()),xy_nees_centered_mean=float(de.mean()),
        xy_nees_rate=float((raw>5.991464547107979).mean()),
        xy_nees_centered_rate=float((de>5.991464547107979).mean()),
        yaw_nees_rate=float((yaw>3.841458820694124).mean()),
        yaw_nees_centered_rate=float((yawde>3.841458820694124).mean()),
        warnings=sum(q['alarm'] for q in samples),misses=sum(q['miss'] for q in samples))


def collect(seed,opt):
    raw=OUTPUTS/RUNS[seed];record=read(raw/'student_record.json')
    pred=read(REPLAY/f's{seed}-{opt}.json');ps={round(p['t'],6):p for p in pred['poses']}
    truth=rows(raw/'eval_only/trajectory.jsonl');tt=np.array([q['t'] for q in truth])
    tx=np.array([q['robot_xyz_m'][:2]+[q['robot_yaw_rad']] for q in truth]);tx[:,2]=np.unwrap(tx[:,2])
    commands=[c for c in record['commands'] if c['kind'] in ('drive','mecanum') and any(c.get(k,0) for k in ('forward','left','turn'))]
    ct=[q['t'] for q in commands]
    states=[e for e in record['events'] if e['event']=='state'];st=[q['t'] for q in states]
    accepted={round(q['t'],6) for q in pred['amcl']['rows'] if q.get('accepted')}
    # Features and acceptance are recorded own-RGB results, never GT-derived.
    # The old v42 ON replay did not save feature packets. Do not splice baseline
    # feature timestamps into its changed update schedule and invent landmark age.
    landmarks=sorted(q['t'] for q in record['sensor_landmarks']['rows'] if q['features'] and round(q['t'],6) in accepted) if opt=='off' else []
    out=[];excluded=[]
    for decision in decisions(record):
        p=ps[round(decision['t'],6)];m=p['observation_quality']['diagnostics'].get('pose_estimate',{})
        cov=np.array(m.get('selected_cluster_cov',[]))
        if not (m.get('cluster_count')==1 and cov.shape==(3,3) and
                np.isclose(np.trace(cov[:2,:2]),p['std_xy_m']**2,rtol=1e-7,atol=1e-10) and np.linalg.eigvalsh(cov).min()>0):
            excluded.append(decision['t']);continue
        gt=np.array([np.interp(p['t_est'],tt,tx[:,j]) for j in range(3)])
        error=np.array([p['x'],p['y'],p['yaw']])-gt;error[2]=math.atan2(math.sin(error[2]),math.cos(error[2]))
        state=states[max(0,bisect.bisect_right(st,p['t_est'])-1)]['state']
        phase=('SEARCH' if state in ('scan','search') else 'carry' if state=='carry' else
               'place' if state in ('real_carry_return','lower','released','done') else 'approach')
        idx=bisect.bisect_right(ct,p['t_est'])-1;motion='stationary';command=None
        if idx>=0:
            command=commands[idx]
            if p['t_est']-command['t']-command.get('duration_s',0)<=1:
                motion='turn' if command.get('turn') else 'lateral' if command.get('left') else 'forward'
        li=bisect.bisect_right(landmarks,p['t_est'])-1
        age=None if li<0 else p['t_est']-landmarks[li]
        age_bin='none' if age is None else ('0-1' if age<1 else '1-5' if age<5 else '5-15' if age<15 else '15-30' if age<30 else '30+')
        alarm=uncertain(p)
        out.append(dict(seed=seed,t=decision['t'],t_est=p['t_est'],phase=phase,state=state,motion=motion,
            preceding_command=command,landmark_age_s=age,age_bin=age_bin,fix_age_s=None if p['last_fix_t'] is None else p['t_est']-p['last_fix_t'],
            error=error.tolist(),cov=cov.tolist(),alarm=alarm,miss=bool(not alarm and np.linalg.norm(error[:2])>.25),
            std_xy_m=p['std_xy_m'],std_yaw_rad=p['std_yaw_rad']))
    return out,excluded


def grouped(samples):
    return {key:{value:summarize([q for q in samples if q[key]==value]) for value in values}
            for key,values in [('phase',['SEARCH','approach','carry','place']),
               ('motion',['turn','forward','lateral','stationary']),('age_bin',['none','0-1','1-5','5-15','15-30','30+'])]}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);result=dict(criteria=read(CRITERIA),criteria_sha256=sha(CRITERIA),physics=0,controller_changes=0,conditions={},on_landmark_age='unavailable: v42 on saved no feature packets; fix age remains available',hashes={})
    for opt in ('off','on'):
        allrows=[];runs=[]
        for seed in RUNS:
            sample,excluded=collect(seed,opt);allrows.extend(sample)
            result['hashes'][str(REPLAY/f's{seed}-{opt}.json')]=sha(REPLAY/f's{seed}-{opt}.json')
            for name in ('student_record.json','eval_only/trajectory.jsonl'):
                source=OUTPUTS/RUNS[seed]/name;result['hashes'][str(source)]=sha(source)
            (a.output/f's{seed}-{opt}-rows.json').write_text(json.dumps(sample)+'\n')
            runs.append(dict(seed=seed,all=summarize(sample),groups=grouped(sample),excluded_times=excluded,
                misses=[q for q in sample if q['miss']]))
        assert len(allrows)==1602
        result['conditions'][opt]=dict(all=summarize(allrows),runs=runs,groups=grouped(allrows))
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    for k,v in result['conditions'].items():print(k,json.dumps(v['all']))


if __name__=='__main__':main()
