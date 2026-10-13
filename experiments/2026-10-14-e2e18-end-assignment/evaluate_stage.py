"""Evaluation only. No result is read by a robot/controller."""
import json,math,sys,collections
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read

def evaluate(p):
    result=read(p/'raw/result.json');plan=read(p/'STAGE_PLAN.json')
    cp=read(ROOT/plan['checkpoint']);beam=cp['setup_only']['beam']
    center=np.array([beam['x'],beam['y']]);u=np.array([math.cos(beam['yaw']),math.sin(beam['yaw'])])
    if (np.array([4.6,-2.1])-center)@u<0:u=-u
    stations=np.array([center-.4732*u,center+.4732*u]);robots={};trajectories={}
    trace=read(p/'raw/transport-trace.json')
    for rid in ('r1','r2'):
        gt=read(p/f'raw/eval_only/{rid}/trajectory.jsonl',True);trajectories[rid]=gt
        if not gt:robots[rid]=dict(reached_end=None);continue
        pos=np.array([x['robot_xyz_m'][:2] for x in gt]);dist=np.linalg.norm(pos[:,None,:]-stations[None,:,:],axis=2)
        end=int(dist.min(axis=0).argmin());ready=[x['t'] for x in trace if x.get('event')=='s3_coarse_fine' and x.get('phase')=='ready' and x.get('robot_id')==rid]
        close=[x['t'] for x in trace if x.get('event')=='phase' and x.get('state') in ('grasp_close','grasp_lift')]
        end_time=cp['cutoff_s']+result.get('sim_s',0)
        wait=max(0,min(close+[end_time])-ready[0]) if ready else None
        robots[rid]=dict(reached_end=end if dist.min()<.25 else None,min_stance_distance_m=dist.min(axis=0).tolist(),ready_t=ready[0]-cp['cutoff_s'] if ready else None,ready_wait_sim_s=wait,
            assignment_choices=dict(collections.Counter(x['choice'] for x in trace if x.get('event')=='end_assignment' and x.get('robot_id')==rid)),
            occupied_events=sum(x.get('event')=='end_occupancy_rgb' and x.get('robot_id')==rid for x in trace))
    a,b=[robots[r]['reached_end'] for r in ('r1','r2')];relation='unreached' if a is None or b is None else 'same' if a==b else 'opposite'
    simultaneous=False
    if all(trajectories.values()):
        a=trajectories['r1'];b=trajectories['r2'];ta=np.array([x['t'] for x in a]);tb=np.array([x['t'] for x in b]);pa=np.array([x['robot_xyz_m'][:2] for x in a]);pb=np.array([x['robot_xyz_m'][:2] for x in b]);ib=np.column_stack([np.interp(ta,tb,pb[:,k]) for k in range(2)])
        da=np.linalg.norm(pa[:,None,:]-stations[None,:,:],axis=2);db=np.linalg.norm(ib[:,None,:]-stations[None,:,:],axis=2)
        simultaneous=bool(np.any(((da[:,0]<.25)&(db[:,1]<.25))|((da[:,1]<.25)&(db[:,0]<.25))))
    return dict(name=p.name,condition=result['condition'],source_run=result['source_run'],sim_s=result.get('sim_s'),status=result['status'],first_attempt_success=result.get('first_attempt_success',False),relation=relation,simultaneous_opposite=simultaneous,robots=robots)

if __name__=='__main__':
    rows=[evaluate(p) for p in sorted((ROOT/'outputs/azure3-runs').glob(sys.argv[1]))]
    groups={}
    for c in sorted({r['condition'] for r in rows}):
        rs=[r for r in rows if r['condition']==c];groups[c]=dict(N=len(rs),relations=dict(collections.Counter(r['relation'] for r in rs)),first_attempt_success=sum(r['first_attempt_success'] for r in rs),simultaneous_opposite=sum(r['simultaneous_opposite'] for r in rs),ready_wait_sim_s=[v['ready_wait_sim_s'] for r in rs for v in r['robots'].values() if v.get('ready_wait_sim_s') is not None])
    out=dict(evaluation_only=True,stance_offset_m=.4732,threshold_m=.25,metric='nearest over entire run for comparison to historical 5/12; simultaneous reported separately',groups=groups,runs=rows)
    Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(groups))
