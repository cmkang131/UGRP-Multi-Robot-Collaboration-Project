"""Frozen train/holdout system identification, Oracle post-run only."""
import argparse,hashlib,json,platform
from pathlib import Path
import numpy as np
from harness.zone_solo_cyan_pulse_cal import profile_key


def fit(runs,template):
    groups={};sources=[];abnormal=0
    for raw in runs:
        result=json.loads((raw/'result.json').read_text())
        if result['status']!='COLLECTED_UNQUALIFIED' or result['host']!='oracle-x86':raise ValueError('completed x86 measurements required')
        condition=result['condition']
        path=raw/'pulse-responses.jsonl';sources.append(dict(condition=condition,path=str(raw),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        for line in path.read_text().splitlines():
            row=json.loads(line);row['condition']=condition
            groups.setdefault(profile_key(row['action'],False),[]).append(row)
        for line in (raw/'eval_only/contacts.jsonl').read_text().splitlines():
            for c in json.loads(line)['contacts']:
                a,b=c['geom1'],c['geom2']
                if any(r+'__' in a for r in ('r1','r2')) and ('cargo_' in b or 'wall' in b):abnormal+=1
                if any(r+'__' in b for r in ('r1','r2')) and ('cargo_' in a or 'wall' in a):abnormal+=1
                if any(r+'__' in a and q+'__' in b for r,q in (('r1','r2'),('r2','r1'))):abnormal+=1
    if sorted(s['condition'] for s in sources)!=list(range(6)):raise ValueError('all six frozen conditions required')
    profiles={};scores={}
    for key,rows in sorted(groups.items()):
        train=[r for r in rows if r['condition']<3];test=[r for r in rows if r['condition']>=3]
        if len(train)!=12 or len(test)!=12:raise ValueError('fixed two robots/two repeats split required')
        curves=np.array([r['curve'] for r in train]);mean=curves.mean(0)
        err=np.array([r['curve'][-1] for r in test])-mean[-1]
        var=np.mean((curves[:,-1]-mean[-1])**2,axis=0)
        action=rows[0]['action'];axis=next(a for a in ('forward','left','turn') if action[a]);u=action[axis]
        old=[p for p in template.values() if not p['loaded'] and p['axis']==axis and p['u']==u]
        floor=np.max([p['prediction_variance'] for p in old],axis=0)
        variance=np.maximum(var,floor)
        movement=2 if axis=='turn' else 0 if axis=='forward' else 1
        direction=all(r['curve'][-1][movement]*u>0 for r in rows)
        xy=float(np.linalg.norm(err[:,:2],axis=1).max());yaw=float(abs(err[:,2]).max())
        scores[key]=dict(train_n=len(train),holdout_n=len(test),max_xy_error_m=xy,max_yaw_error_rad=yaw,
            direction_consistent=direction,qualified=bool(xy<=.003 and yaw<=.035 and direction and abnormal==0))
        profiles[key]=dict(loaded=False,axis=axis,u=u,duration_s=action['duration_s'],
            times=rows[0]['times'],mean_curve=mean.tolist(),mean_delta=mean[-1].tolist(),
            prediction_variance=variance.tolist(),prediction_covariance=np.diag(variance).tolist(),
            residual_variance=var.tolist(),settle_s=.5-action['duration_s'],n=len(train),transfer=None,
            s3_trim_measured=True,source_conditions=[0,1,2])
    return dict(option='measured_pose_mpc_v1',qualified=len(profiles)==18 and all(s['qualified'] for s in scores.values()),
        host='oracle-x86',profiles=profiles,holdout=scores,abnormal_contacts=abnormal,sources=sources,
        runtime_gt=False,train_conditions=[0,1,2],holdout_conditions=[3,4,5],
        qualification='development simulator calibration; no real-robot qualification')


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',action='append',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('Oracle x86 post-run only')
    template=json.loads(Path('configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']
    model=fit(a.raw,template)
    with a.output.open('x') as f:json.dump(model,f,indent=2,allow_nan=False)
    print(json.dumps(dict(qualified=model['qualified'],profiles=len(model['profiles']),abnormal_contacts=model['abnormal_contacts'])))


if __name__=='__main__':main()
