"""Diagnostic-only nonmutating likelihood instrumentation; no production edit."""
import argparse,copy,importlib.util,json,math
from pathlib import Path
import numpy as np
from harness.zone_solo_cyan_bias_tempering import attach,SCALE,TEMPER,closure,replace_cell
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_landmarks import MapFeatures,landmark_likelihood,wall_likelihood
from scripts.audit_s2_formal_stops import RUNS,OUTPUTS,read,rows
HERE=Path('experiments/2026-10-06-s2-realism')
spec=importlib.util.spec_from_file_location('replay_old',HERE/'replay_rotation_left.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)

def posterior(w,loglik):
    q=w*np.exp(loglik-loglik.max());return q/q.sum()

def shapley(px,w,logs):
    n=len(logs);means={}
    for mask in range(1<<n):
        ll=sum((logs[j] for j in range(n) if mask>>j&1),start=np.zeros(len(w)))
        means[mask]=posterior(w,ll)@px[:,:2]
    result=[]
    for i in range(n):
        value=np.zeros(2)
        for mask in range(1<<n):
            if mask>>i&1:continue
            size=mask.bit_count();factor=math.factorial(size)*math.factorial(n-size-1)/math.factorial(n)
            value+=factor*(means[mask|1<<i]-means[mask])
        result.append(value.tolist())
    np.testing.assert_allclose(np.sum(result,axis=0),means[(1<<n)-1]-means[0],atol=1e-12)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True);a=p.parse_args();seed=a.seed
    root=OUTPUTS/'s2-innovation-v46-20261008';out=root/'diagnosis';out.mkdir(parents=True,exist_ok=True)
    raw=OUTPUTS/RUNS[seed];record=read(raw/'student_record.json');frames=rows(raw/'robots/r3/frames.jsonl')
    end=next(e['t'] for e in record['events'] if e.get('state')=='carry');n=sum(f['sim_time']<end for f in frames)
    holder={};audit=[];table=read(OUTPUTS/'s2-bias-tempering-v45-20261008/fit'/f's{seed}-calibration.json')
    def selected(runtime,**_):
        runtime=attach(runtime,forward_scale=SCALE,likelihood_tempering=TEMPER,calibration=table,servo_stiffness='real_v1',audit=True)
        pf=runtime.pose.provider.loc._pf;wrapper=pf.update_obs;update=closure(wrapper)['selected'];previous=update.__globals__['likelihood']
        mapped=closure(previous)['mapped'];holder['runtime']=runtime
        def likelihood(field,px,packet):
            value=previous(field,px,packet);w=pf._weights();wall=wall_likelihood(field,px,packet.wall)
            scores=[wall]+[landmark_likelihood(mapped,px,[f]) for f in packet.features]
            logs=[.5*np.log(s) for s in scores];contrib=shapley(px,w,logs)
            # Joint score is captured exactly; component arithmetic is audit-only.
            np.testing.assert_allclose(np.prod(scores,axis=0)**.5,value,rtol=1e-12,atol=1e-300)
            index=len(audit);path=out/f's{seed}-update{index:02d}.npz'
            np.savez_compressed(path,px=px.copy(),w=w.copy(),wall=packet.wall.copy(),log_components=np.array(logs))
            audit.append(dict(t=pf.t,servo=dict(runtime.pose.provider.servo),features=copy.deepcopy(packet.features),wall_points=packet.wall.tolist(),shapley_xy=contrib,particles=str(path)))
            return value
        pf.update_obs=replace_cell(wrapper,'selected',bind(update,likelihood=likelihood))
        return runtime
    replay=bind(old.replay,attach=selected,CRITERIA=HERE/'bias-tempering-criteria.json')
    replay(seed,'combined',out,n)
    previous=read(OUTPUTS/'s2-bias-tempering-v45-20261008/replay'/f's{seed}-combined.json');now=read(out/f's{seed}-combined.json')
    assert json.dumps(now['poses']).encode()==json.dumps(previous['poses'][:n]).encode()
    result=dict(seed=seed,observations=audit,measurements=holder['runtime'].measurement_consistency_audit,
        off_pose_bytes_identical=True,frames=n,scope='approach only, unchanged v45 combined; own RGB and commands; GT0')
    with (out/f's{seed}-audit.json').open('x') as f:json.dump(result,f);f.write('\n')
    print('AUDIT SEALED',seed,len(audit),flush=True)
if __name__=='__main__':main()
