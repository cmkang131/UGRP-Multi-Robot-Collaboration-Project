"""Same-command saved-stream filter replay, GCP2; not a closed-loop claim."""
import collections,json,math,platform,subprocess
from pathlib import Path
import numpy as np
from harness.natural_floor_slam import compose,wrap,_motion_covariance
from harness.selfmap4_geometry import inverse
from harness.reloc18_innovation import InnovationGate
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def load(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def rows(p):return [json.loads(s) for s in load(p).splitlines()]
def stats(x):return dict(N=len(x),p50=float(np.percentile(x,50)),p95=float(np.percentile(x,95)),end=float(x[-1])) if x else dict(N=0)
def replay():
    assert platform.node().startswith('ugrp-sim-gcp2')
    out=[]
    for seed in (93584,93583):
        raw=RUNS/f'reloc17-r2-selfmap-{seed}-47670d14/raw';trace=rows(raw/'trace.jsonl');ev={round(x['t'],6):x for x in rows(raw/'eval_only/trajectory.jsonl')}
        gt=ev[round(trace[0]['t'],6)];origin=[*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']]
        x=np.zeros(3);P=np.zeros((3,3));oldodom=np.zeros(3);oldt=trace[0]['t'];gate=InnovationGate();scored=[];decisions=[]
        for r in trace:
            s=r.get('static_registration',{});od=s.get('reloc12',{}).get('replay',{}).get('own_odometry_pose')
            truth=ev.get(round(r['t'],6))
            if od is None or truth is None:continue
            od=np.asarray(od);dt=r['t']-oldt;delta=compose(inverse(oldodom),od)
            a=x[2];c,ss=math.cos(a),math.sin(a);rot=np.array([[c,ss,0],[-ss,c,0],[0,0,1]])
            Q=rot@np.asarray(gate.fit['command_covariance_per_sim_s'])@rot.T*dt
            P=_motion_covariance(x,delta,P,Q);x=compose(x,delta)
            h=r.get('pose_handoff')
            if h is not None and s.get('updated'):
                anchor=np.asarray(h['map_from_execution']);a=anchor[2];c,ss=math.cos(a),math.sin(a)
                gate.rotation=np.array([[c,ss,0],[-ss,c,0],[0,0,1]])
                z=compose(inverse(anchor),s['world_pose']);R=np.asarray(s['execution_covariance'])
                d=gate.consider(x,z,P,R,t=r['t'],source='static');decisions.append(dict(t=r['t'],**d))
                if d['accepted']:x=np.asarray(d['posterior_pose']);P=np.asarray(d['posterior_covariance'])
            actual=np.array([*truth['robot_xyz_m'][:2],truth['robot_yaw_rad']])
            def err(p):
                w=compose(origin,p);return float(np.linalg.norm(w[:2]-actual[:2])),abs(math.degrees(wrap(w[2]-actual[2])))
            scored.append(dict(t=r['t'],command=err(od),candidate=err(x),original_local=err(r['pose'])))
            oldodom,oldt=od,r['t']
        data=dict(seed=seed,raw=str(raw),scope='same saved commands and PF stream; initial truth alignment evaluation only; no changed navigation or physical execution',
            errors={k:dict(xy_m=stats([r[k][0] for r in scored]),yaw_deg=stats([r[k][1] for r in scored])) for k in ('command','candidate','original_local')},
            bins=[dict(sim_interval=[lo,hi],errors={k:stats([r[k][0] for r in scored if lo<=r['t']-trace[0]['t']<hi]) for k in ('command','candidate')}) for lo,hi in ((0,20),(20,40),(40,60))],
            rejection_reasons=dict(collections.Counter(d['reason'] for d in decisions)),decisions=decisions)
        out.append(data)
    p=RUNS/'reloc18-audit';(p/'replay-full.json').write_text(json.dumps(dict(runs=out),indent=2)+'\n')
    for d in out:del d['decisions']
    (p/'replay.json').write_text(json.dumps(dict(runs=out),indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':replay()
