"""Additional post-hoc counterfactuals motivated by egomap69 raw audit.

Not calibration, control, or a measured candidate improvement. Replace one
motion component with GT to bound its influence along the SAME saved commands.
"""
import argparse,json,math
from pathlib import Path
from collections import Counter
import numpy as np
from scripts.analyze_own_route_error_budget import read,rows,sha,compose,between,motion_poses,kind,distribution


def counterfactual(dr,gt,kinds,mode):
    estimates=[gt[0].copy()]
    for i in range(1,len(gt)):
        d=between(dr[i-1],dr[i]);g=between(gt[i-1],gt[i])
        if mode=='all_lateral':d[1]=g[1]
        elif mode=='turn_xy' and kinds[i-1].endswith('turn'):d[:2]=g[:2]
        elif mode=='all_xy':d[:2]=g[:2]
        elif mode!='turn_xy':raise ValueError(mode)
        estimates.append(compose(estimates[-1],d))
    errors=np.linalg.norm(np.asarray(estimates)[:,:2]-gt[:,:2],axis=1)
    return dict(end_m=float(errors[-1]),RMSE_m=float(np.sqrt(np.mean(errors**2))))


def boundary(xy,B):
    return float(np.linalg.norm(np.maximum(np.abs(np.asarray(xy)-B['center_m'])-B['half_extents_m'],0)))


def analyze(p):
    res=read(p/'result.json');start=res['start_sim_s']
    truth=rows(p/'eval_only/trajectory.jsonl');tb={round(r['t'],6):r for r in truth}
    origin=np.r_[truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    own=[r for r in rows(p/'own-controller.jsonl') if round(r['t'],6) in tb]
    dr=motion_poses(rows(p/'robots/r3/commands.jsonl'),[r['t'] for r in own])
    cut=next(i for i,r in enumerate(own) if r['t']>=start-1e-8);dr=dr[cut:];own=own[cut:]
    gt=np.array([between(origin,np.r_[tb[round(r['t'],6)]['robot_xyz_m'][:2],tb[round(r['t'],6)]['robot_yaw_rad']]) for r in own])
    actual=Counter();commands=Counter()
    for i,r in enumerate(own[:-1]):
        c=r['command'];commands[f'{kind(c)}:{c.get("duration_s",0)}']+=1
    motion={m:counterfactual(dr,gt,[kind(r['command']) for r in own],m) for m in ['turn_xy','all_lateral','all_xy']}
    B=read(p/'inputs/static_map.json')['regions']['zone_B'];positions=[]
    for index in [0,len(own)-1]:
        r=own[index];entity=r['remembered_entities'].get('B')
        if entity:
            target=np.r_[entity['center_m'],0.]
            world=compose(origin,target)
            relative=between(r['local_pose'],target);oracle=compose(compose(origin,gt[index]),relative)
            positions.append(dict(t=r['t'],target_world_m=world[:2].tolist(),target_GT_B_boundary_m=boundary(world[:2],B),
                target_if_current_GT_pose_m=oracle[:2].tolist(),target_if_current_GT_pose_B_boundary_m=boundary(oracle[:2],B),
                interpretation='Stored target transported by current pose error; not a fresh detector measurement unless last_t equals t.',last_t=entity['last_t']))
    gates=read(p/'arrival-gates.json');rb={round(r['t'],6):r for r in own}
    near_states=Counter();near_details=[]
    for g in gates:
        r=rb.get(round(g['t'],6))
        if r is None or not g['near']:continue
        near_states[(r['stage'],r['status'],kind(r['command']))]+=1
        if len(near_details)<1:near_details.append(dict(gate=g,own_pose=r['local_pose'],B=r['remembered_entities'].get('B')))
    ranges=[r for r in rows(p/'robots/r3/inputs/range.jsonl') if 't' in r and r['t']>=start and r.get('valid')]
    bins=Counter('<=0.10m' if r['range_m']<=.1 else '>0.10m' for r in ranges)
    decisions=read(p/'decisions.json');prior_axes=[]
    for d in decisions:
        y=d.get('yaw_prior',{})
        if d['t']<start or not y.get('observation'):continue
        prior_axes.append(dict(t=d['t'],reason=d['reason'],status=y['status'],angle=y['observation']['angle_rad'],
            correction_deg=y.get('max_abs_correction_deg'),nonnearest=y.get('nonnearest_modes')))
    return dict(seed=res['seed'],command_profiles=dict(commands),counterfactuals=motion,remembered_B_positions=positions,
        near_states=[dict(stage=k[0],status=k[1],command=k[2],n=n) for k,n in near_states.items()],first_near=near_details,
        sonar_range_bins=dict(bins),manhattan=dict(n=len(prior_axes),nonnearest_modes=sum(r['nonnearest'] or 0 for r in prior_axes),
        max_correction_deg=distribution([r['correction_deg'] for r in prior_axes if r['correction_deg'] is not None])))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();result=dict(scope='post-hoc, oracle component replacements are evaluation-only, no model refit',runs=[])
    for seed in range(63001,63007):result['runs'].append(analyze(a.root/f'egomap68-{seed}-baseline'))
    result['script_sha256']=sha(Path(__file__));a.output.write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
