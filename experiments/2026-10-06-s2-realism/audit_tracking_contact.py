"""Posthoc contact/particle diagnostic; never imported by the controller."""
import argparse
import json
from collections import Counter
from pathlib import Path
import numpy as np
from replay_tracking_recovery import RAW, read, rows, sha


def audit(out,option):
    raw=read(RAW/'student_record.json');pred=read(out/option/'prediction.json')
    truth=rows(RAW/'eval_only/trajectory.jsonl');tt=np.array([x['t'] for x in truth])
    gt=np.array([x['robot_xyz_m'][:2]+[x['robot_yaw_rad']] for x in truth]);gt[:,2]=np.unwrap(gt[:,2])
    def actual(t):return np.array([np.interp(t,tt,gt[:,i]) for i in range(3)])
    def error(p):
        e=np.array([p['x'],p['y'],p['yaw']])-actual(p['t_est']);e[2]=np.arctan2(np.sin(e[2]),np.cos(e[2]));return e
    poses=pred['poses'];contacts=rows(RAW/'eval_only/wall-contacts.jsonl')
    positive=[dict(t=q['t'],contacts=[c for c in q['contacts'] if c['normal_force_n']>0]) for q in contacts]
    positive=[q for q in positive if q['contacts']];start,end=positive[0]['t'],positive[-1]['t']
    cells=[]
    for t in (82.05,91.95,184.55,start,191.15,end,270.8):
        p=min(poses,key=lambda p:abs(p['t']-t));e=error(p)
        cells.append(dict(t=p['t'],t_est=p['t_est'],actual=actual(p['t_est']).tolist(),
          estimated=[p['x'],p['y'],p['yaw']],error_xy_m=float(np.linalg.norm(e[:2])),error_yaw_deg=float(np.degrees(e[2])),
          std_xy=p['std_xy_m'],last_fix=p['last_fix_t']))
    a,b=actual(start),actual(end);delta=b-a
    segment=gt[(tt>=start)&(tt<=end)]
    pulse=[p for p in raw['pulse_motion_model']['transformations'] if start<=p['t']<=end]
    cloud=np.load(out/option/'clouds.npz');support=[]
    for s in pred['snapshots']:
        px=cloud[s['key']];w=cloud[s['key']+'w'];g=actual(s['t'])
        xy=np.linalg.norm(px[:,:2]-g[:2],axis=1);yaw=np.abs(np.arctan2(np.sin(px[:,2]-g[2]),np.cos(px[:,2]-g[2])))
        mask=(xy<=.10)&(yaw<=np.radians(5));wide=(xy<=.25)&(yaw<=np.radians(5))
        support.append(dict(**s,near_count=int(mask.sum()),near_mass=float(w[mask].sum()),wide_count=int(wide.sum()),
            wide_mass=float(w[wide].sum()),nearest_xy=float(xy.min()),ess=float(1/sum(w*w))))
    states=[e for e in raw['events'] if e['event']=='state'];carry=next(e['t'] for e in states if e['state']=='carry')
    carry_end=next(e['t'] for e in states if e['state']=='real_carry_return')
    windows={}
    for name,lo,hi in [('carry',carry,carry_end),('post_contact',end,carry_end)]:
        samples=[p for p in poses if lo<=p['t']<hi];es=np.array([error(p) for p in samples])
        fixes=sorted(set(p['last_fix_t'] for p in samples if p['last_fix_t'] is not None and lo<=p['last_fix_t']<hi))
        windows[name]=dict(rmse_m=float(np.sqrt(np.mean(np.sum(es[:,:2]**2,axis=1)))),
            updates=len(fixes),max_gap_s=float(np.diff([lo,*fixes,hi]).max()))
    valid=[p for p in poses if end<=p['t']<=carry_end and p['std_xy_m']<=.05 and np.linalg.norm(error(p)[:2])<=.25]
    endpose=min(poses,key=lambda p:abs(p['t']-carry_end))
    rec=pred.get('recovery') or {};rr=rec.get('rows',[])
    result=dict(option=option,physics_runs=0,gt_use='posthoc only after prediction sealed',
      contact=dict(start=start,end=end,samples=len(positive),points=dict(Counter(c['category'] for q in positive for c in q['contacts'])),
        geom_pairs=dict(Counter('|'.join(c['geoms']) for q in positive for c in q['contacts'])),
        max_force_n=max(c['normal_force_n'] for q in positive for c in q['contacts']),
        net_xy_m=float(np.linalg.norm(delta[:2])),xy_delta_m=delta[:2].tolist(),yaw_delta_deg=float(np.degrees(delta[2])),
        path_length_m=float(np.linalg.norm(np.diff(segment[:,:2],axis=0),axis=1).sum()),
        commanded_pulses=dict(Counter(p['profile_key'] for p in pulse))),
      trajectory=cells,support=support,updates=pred['updates'],windows=windows,
      reconverged_t=valid[0]['t'] if valid else None,
      reconverged_error_m=float(np.linalg.norm(error(valid[0])[:2])) if valid else None,
      carry_end_error_m=float(np.linalg.norm(error(endpose)[:2])),
      recovery=dict(updates=len(rr),injected=sum(q['injected'] for q in rr),injection_events=sum(q['injected']>0 for q in rr),
        max_probability=max((q['injection_probability'] for q in rr),default=0)),
      inputs={k:sha(RAW/k) for k in ('student_record.json','eval_only/trajectory.jsonl','eval_only/wall-contacts.jsonl')},
      prediction_sha=sha(out/option/'prediction.json'),max_delta=pred['max_delta'])
    dest=out/f'{option}-audit.json';dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('support','updates','inputs')}))
    return result

def compare(out):
    criteria=read(Path(__file__).with_name('tracking-recovery-criteria.json'))
    baseline=read(out/'baseline'/'prediction.json');off=read(out/'off'/'prediction.json');on=read(out/'on'/'prediction.json')
    assert not any(r['partial'] for r in (baseline,off,on))
    a=read(out/'off-audit.json');b=read(out/'on-audit.json')
    gates=dict(baseline_reproduced=baseline['max_delta']<=1e-9,
        off_particle_bytes_identical=baseline['cloud_sha256']==off['cloud_sha256'],
        off_pose_bytes_identical=json.dumps(baseline['poses']).encode()==json.dumps(off['poses']).encode(),
        postcontact_reconverged=b['reconverged_t'] is not None,
        carry_end_xy=b['carry_end_error_m']<=criteria['recovery_xy_m'],
        postcontact_rmse_improved=b['windows']['post_contact']['rmse_m']<a['windows']['post_contact']['rmse_m'],
        carry_rmse_nonincrease=b['windows']['carry']['rmse_m']<=a['windows']['carry']['rmse_m'])
    result=dict(schema='ugrp.s2.tracking_recovery.result.v1',criteria=criteria,
        criteria_sha256=sha(Path(__file__).with_name('tracking-recovery-criteria.json')),
        source_sha='fe779a28',physics_runs=0,model_calls=0,gt_use='posthoc only',
        replay_script_sha256=sha(Path(__file__).with_name('replay_tracking_recovery.py')),
        options={'off':'off','on':'augmented_mcl_v1'},gates=gates,physical_admitted=all(gates.values()),
        runs={k:{n:v for n,v in x.items() if n not in ('support','updates')} for k,x in [('off',a),('on',b)]},
        hashes={str(p.relative_to(out)):sha(p) for p in [out/'baseline'/'prediction.json',out/'off'/'prediction.json',out/'on'/'prediction.json',out/'off-audit.json',out/'on-audit.json']},
        cohort_comparison=[dict(condition='v133 prior',success=6,trials=6),dict(condition='v139 no prior',success=2,trials=3),
            dict(condition='s2v55 tracking recovery offline',success=None,trials=0,reason='physical gated on replay')])
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(gates))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--option',choices=('baseline','off','on'));p.add_argument('--compare',action='store_true')
    a=p.parse_args()
    if a.compare:compare(a.output)
    elif a.option:audit(a.output,a.option)
    else:p.error('--option or --compare required')
