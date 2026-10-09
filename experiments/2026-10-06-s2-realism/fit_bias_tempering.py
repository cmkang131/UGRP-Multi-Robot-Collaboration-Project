"""Calibration-only GT, two training recordings; no held-out GT loaded to fit."""
import argparse,json,math
from pathlib import Path
import numpy as np
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,rows,sha,wrap
from harness.zone_solo_cyan_bias_tempering import BASE,group
HERE=Path(__file__).resolve().parent


def samples(seed):
    raw=OUTPUTS/RUNS[seed];r=read(raw/'student_record.json');tr=rows(raw/'eval_only/trajectory.jsonl')
    tt=[q['t'] for q in tr];xyz=np.array([q['robot_xyz_m'][:2]+[q['robot_yaw_rad']] for q in tr]);xyz[:,2]=np.unwrap(xyz[:,2])
    actual=lambda t:np.array([np.interp(t,tt,xyz[:,j]) for j in range(3)])
    contacts=rows(raw/'eval_only/wall-contacts.jsonl');cmds=r['commands'];result=[]
    for q in r['pulse_motion_model']['transformations']:
        key=q['profile_key'];p=r['pulse_motion_model']['model']['profiles'][key]
        if p['axis']!='forward' or p['u']<=0:continue
        t=q['t'];end=t+p['times'][-1];servo={}
        for c in cmds:
            if c['t']>t:break
            if c['kind']=='initial_servo_command':servo.update({int(k):v for k,v in c['pulses'].items()})
            if c['kind']=='arm':servo[c['servo_id']]=c['pulse']
        bad=[]
        for c in cmds:
            if not t+1e-8<c['t']<end-1e-8:continue
            if c['kind']=='arm':bad.append('arm')
            if c['kind'] in ('drive','mecanum') and any(c.get(k,0) for k in ('forward','left','turn')):bad.append('overlap')
        if any(t<=c['t']<=end and c['contacts'] for c in contacts):bad.append('wall_contact')
        a,b=actual(t),actual(end);d=b-a;c,s=math.cos(a[2]),math.sin(a[2]);d[:2]=np.array([[c,s],[-s,c]])@d[:2];d[2]=wrap(d[2])
        result.append(dict(seed=seed,t=t,group=group(servo,key),state=q['state'],predicted=p['mean_delta'],actual=d.tolist(),exclude=sorted(set(bad))))
    return result


def fit(data,fit_seeds):
    groups={}
    for g in sorted({q['group'] for q in data}):
        qs=[q for q in data if q['group']==g and not q['exclude']]
        if len(qs)<20 or set(q['seed'] for q in qs)!=set(fit_seeds):continue
        x=np.array([q['predicted'][0] for q in qs]);y=np.array([q['actual'][0] for q in qs]);gain=float(x@y/(x@x))
        groups[g]=dict(gain=gain,n=len(qs),seeds=sorted(set(q['seed'] for q in qs)),
            mean_error_before_m=float((x-y).mean()),mean_error_after_m=float((gain*x-y).mean()),residual_std_m=float((gain*x-y).std()))
    return groups


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    for holdout in RUNS:
        train=[s for s in RUNS if s!=holdout];data=[q for s in train for q in samples(s)]
        table=dict(option='forward_scale_v1',holdout=holdout,fit_seeds=train,base_sha256=sha(BASE),fit_gt_inputs=True,
            gt_use='offline physical calibration only; authorization s2v45/supervisor06:05',groups=fit(data,train),
            criteria_sha256=sha(HERE/'bias-tempering-criteria.json'),input_hashes={str(OUTPUTS/RUNS[s]/f):sha(OUTPUTS/RUNS[s]/f) for s in train for f in ('student_record.json','eval_only/trajectory.jsonl','eval_only/wall-contacts.jsonl')})
        with (a.output/f's{holdout}-calibration.json').open('x') as f:json.dump(table,f,indent=2);f.write('\n')
        with (a.output/f's{holdout}-training-samples.json').open('x') as f:json.dump(data,f);f.write('\n')
        print(holdout,json.dumps(table['groups']),flush=True)
if __name__=='__main__':main()
