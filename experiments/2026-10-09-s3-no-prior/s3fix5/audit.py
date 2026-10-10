"""Post-run error accounting only. GT never enters a controller or calibration."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from harness.zone_solo_cyan_pulse_cal import install, profile_key, response


def rows(p):
    return [json.loads(s) for s in p.read_text().splitlines()]


def rotation(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, -s], [s, c]])


def wrap(yaw):
    return (yaw + np.pi) % (2*np.pi) - np.pi


class ZeroNoise:
    def normal(self, *, size): return np.zeros(size)
    def multivariate_normal(self, mean, cov, *, size): return np.zeros((size, 3))


def integrate(commands, times, model):
    """Run the actual finite-pulse predictor, with deterministic zero noise."""
    pf = SimpleNamespace(t=0., initialized=True, n=1, px=np.zeros((1, 3)),
        logw=np.zeros(1), load=SimpleNamespace(loaded=False), rng=ZeroNoise(),
        _map_logprior=lambda p: np.zeros(len(p)))
    def command(row):
        pf.predict_to(row['t'])
        if row['kind']=='initial_servo_command':
            pf.load.loaded=int(row['pulses'].get('1', row['pulses'].get(1, 2000)))<=1600
        if row['kind']=='arm' and row['servo_id']==1:
            pf.load.loaded=row['pulse']<=1600
    pf.command=command
    install(pf, model)
    out=[]; i=0
    for t in times:
        while i<len(commands) and commands[i]['t']<t-1e-8:
            pf.command(commands[i]); i+=1
        pf.predict_to(t); out.append(pf.px[0].copy())
    return np.asarray(out)


def audit(raw):
    commands=rows(raw/'robots/r2/commands.jsonl')
    loc=json.loads((raw/'student_record.json').read_text())['localizers']['r2']
    model=loc['pulse_motion_model']['model']
    gt=rows(raw/'eval_only/r2/trajectory.jsonl')
    ts=np.array([r['t'] for r in gt]); xy=np.array([r['robot_xyz_m'][:2] for r in gt])
    yaw=np.unwrap([r['robot_yaw_rad'] for r in gt])
    def truth(t): return np.r_[[np.interp(t,ts,xy[:,i]) for i in range(2)],np.interp(t,ts,yaw)]
    pulses=[c for c in commands if c['kind'] in ('drive','mecanum') and any(c.get(k,0) for k in ('forward','left','turn'))]
    pulse_rows=[]
    for i,c in enumerate(pulses):
        key=profile_key(c,False); p=model['profiles'][key]
        end=min(c['t']+p['times'][-1],pulses[i+1]['t'] if i+1<len(pulses) else ts[-1],ts[-1])
        a,b=truth(c['t']),truth(end)
        pred=response(p,end-c['t']); actual=np.r_[rotation(a[2]).T@(b[:2]-a[:2]),wrap(b[2]-a[2])]
        pulse_rows.append(dict(t=c['t'],end=end,key=key,axis=p['axis'],pred=pred.tolist(),actual=actual.tolist()))
    table=[]
    for axis in ('turn','forward','left'):
        rr=[r for r in pulse_rows if r['axis']==axis]
        pred=np.array([r['pred'] for r in rr]).reshape(-1,3);actual=np.array([r['actual'] for r in rr]).reshape(-1,3)
        table.append(dict(axis=axis,n=len(rr),predicted_xy_length_m=float(np.linalg.norm(pred[:,:2],axis=1).sum()),
            actual_xy_length_m=float(np.linalg.norm(actual[:,:2],axis=1).sum()),
            predicted_body_sum=pred.sum(0).tolist(),actual_body_sum=actual.sum(0).tolist(),
            residual_body_sum=(pred-actual).sum(0).tolist()))
    poses=[r for r in loc['poses'] if r['t_est']>=13.34-1e-8]
    times=[r['t_est'] for r in poses]; dr=integrate(commands,times,model)
    est=np.array([[r[k] for k in ('x','y','yaw')] for r in poses]); actual=np.array([truth(t) for t in times])
    contributions=defaultdict(lambda:np.zeros(2)); counts=defaultdict(int); intervals=[]
    for j in range(1,len(times)):
        body=rotation(dr[j-1,2]).T@(dr[j,:2]-dr[j-1,:2])
        predicted=rotation(est[j-1,2])@body
        actual_delta=actual[j,:2]-actual[j-1,:2]
        correction=est[j,:2]-est[j-1,:2]-predicted
        # Tags include the stopping tail; zero-motion gaps are kept separately.
        prior=[p for p in pulse_rows if p['t']<times[j]-1e-8 and p['end']>times[j-1]+1e-8]
        tag=prior[-1]['axis'] if prior else 'idle'
        contributions[tag]+=predicted-actual_delta;contributions['posterior_correction']+=correction;counts[tag]+=1
        intervals.append(dict(t=times[j],axis=tag,model_minus_actual=(predicted-actual_delta).tolist(),correction=correction.tolist()))
    initial=est[0,:2]-actual[0,:2];final=est[-1,:2]-actual[-1,:2]
    closure=initial+sum(contributions.values())
    assert np.allclose(closure,final,atol=1e-10)
    sig=np.array([r['std_xy_m'] for r in poses]);errors=np.linalg.norm(est[:,:2]-actual[:,:2],axis=1)
    return dict(source=str(raw),scope='evaluation only; body sums are not endpoint errors',
        input_hashes={str(p.relative_to(raw)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [raw/'robots/r2/commands.jsonl',raw/'student_record.json',raw/'eval_only/r2/trajectory.jsonl']},
        command_table=table,initial_error_vector=initial.tolist(),final_error_vector=final.tolist(),
        additive_error_vectors={k:v.tolist() for k,v in contributions.items()},interval_counts=dict(counts),
        final_error_m=float(errors[-1]),final_sigma_m=float(sig[-1]),over_3sigma=int(sum(errors>3*sig)),frames=len(poses),
        closure_residual_m=float(np.linalg.norm(closure-final))),pulse_rows,intervals


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report,pulses,intervals=audit(a.raw);a.output.mkdir(parents=True,exist_ok=False)
    for name,value in [('audit.json',report),('pulses.json',pulses),('intervals.json',intervals)]:
        (a.output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report,indent=2))
