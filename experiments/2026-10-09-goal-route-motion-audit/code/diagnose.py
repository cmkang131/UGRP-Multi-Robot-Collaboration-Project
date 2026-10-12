"""egomap59 saved-command audit. Truth is consumed here only, never by policy.

Replay the exact admitted commands, not controller proposals. Compare at RGB
timestamps with real GT samples (no extrapolation past a HOST_ERROR). Norms of
posterior corrections are not distances driven and are not additive scalars.
"""
from pathlib import Path
import argparse, hashlib, json, math, sys
from collections import defaultdict
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from harness.self_pulse_rotation import RotationPulseOdometry
from harness.self_pulse_odom import profile_key, response
from harness.self_map_prob import wrap
from harness.active_wall_mapping import compose, inverse
EXP=ROOT/'experiments/2026-10-09-goal-route-motion-audit'
BASE=Path('/Users/changmin/projects/ugrp/outputs/goal-route-preflight-v1')


def rows(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def replay(commands,times):
    od=RotationPulseOdometry(commands[0]['t']); i=0; poses=[]
    for t in times:
        # RGB is acquired before the command with the same timestamp.
        while i<len(commands) and commands[i]['t']<t-1e-8:
            od.command(commands[i]);i+=1
        poses.append(od.advance(t))
    return np.asarray(poses)


def audit(seed):
    ep=BASE/f'seed{seed}'
    names=['robots/r3/commands.jsonl','own-controller.jsonl','eval_only/trajectory.jsonl',
           'decisions.json','utility-events.json','frontend-covariances.jsonl']
    hashes={n:hashlib.sha256((ep/n).read_bytes()).hexdigest() for n in names}
    commands=rows(ep/names[0]);trace=rows(ep/names[1]);gt=rows(ep/names[2])
    by_t={round(r['t'],6):r for r in gt}
    trace=[r for r in trace if round(r['t'],6) in by_t]
    times=[r['t'] for r in trace];dr=replay(commands,times)
    poses=np.array([r['local_pose'] for r in trace])
    actual=np.array([by_t[round(t,6)]['robot_xyz_m'][:2] for t in times])
    # Evaluate relative command increments in the preceding posterior frame.
    prior=np.array([compose(a,compose(inverse(b),c)) for a,b,c in zip(poses[:-1],dr[:-1],dr[1:])])
    residual=poses[1:]-prior;residual[:,2]=wrap(residual[:,2])
    decisions={round(r['t'],6):r for r in json.loads((ep/'decisions.json').read_text())}
    corrections=defaultdict(lambda:dict(frames=0,xy_sum_m=0.,yaw_abs_sum_deg=0.))
    for t,d in zip(times[1:],residual):
        reason=decisions.get(round(t,6),{}).get('reason','no_scan')
        row=corrections[reason];row['frames']+=1
        row['xy_sum_m']+=float(np.linalg.norm(d[:2]));row['yaw_abs_sum_deg']+=float(abs(np.rad2deg(d[2])))
    ts=np.array([r['t'] for r in gt]);xy=np.array([r['robot_xyz_m'][:2] for r in gt])
    yaw=np.unwrap([r['robot_yaw_rad'] for r in gt]);profiles=RotationPulseOdometry().profiles
    pulse_rows=[]
    for i,c in enumerate(commands):
        if c['kind']!='mecanum':continue
        end=min(commands[i+1]['t'] if i+1<len(commands) else ts[-1],ts[-1])
        dt=end-c['t']
        if dt<=1e-8:continue  # final command has no following GT observation
        p=profiles[profile_key(c,False)];pred=response(p,dt)
        start_xy=np.array([np.interp(c['t'],ts,xy[:,j]) for j in range(2)])
        end_xy=np.array([np.interp(end,ts,xy[:,j]) for j in range(2)])
        a=np.interp(c['t'],ts,yaw);b=np.interp(end,ts,yaw)
        rot=np.array([[math.cos(a),math.sin(a)],[-math.sin(a),math.cos(a)]])
        body=rot@(end_xy-start_xy)
        pulse_rows.append(dict(t=c['t'],axis=p['axis'],u=p['u'],duration_s=c['duration_s'],
            observed_interval_s=dt,predicted_body=pred.tolist(),actual_body=[*body.tolist(),float(b-a)],
            predicted_xy_m=float(np.linalg.norm(pred[:2])),actual_xy_m=float(np.linalg.norm(body))))
    groups=defaultdict(list)
    for r in pulse_rows:groups[(r['axis'],r['u'],r['duration_s'],round(r['observed_interval_s'],6))].append(r)
    table=[]
    for (axis,u,duration,dt),rr in sorted(groups.items()):
        pred=np.array([r['predicted_body'] for r in rr]);truth=np.array([r['actual_body'] for r in rr])
        table.append(dict(axis=axis,u=u,duration_s=duration,observed_interval_s=dt,n=len(rr),
            predicted_xy_sum_m=sum(r['predicted_xy_m'] for r in rr),actual_xy_sum_m=sum(r['actual_xy_m'] for r in rr),
            predicted_body_mean=pred.mean(0).tolist(),actual_body_mean=truth.mean(0).tolist(),
            actual_body_std=truth.std(0).tolist(),predicted_yaw_sum_deg=float(np.rad2deg(pred[:,2].sum())),
            actual_yaw_sum_deg=float(np.rad2deg(truth[:,2].sum()))))
    origin=np.r_[gt[0]['robot_xyz_m'][:2],gt[0]['robot_yaw_rad']]
    world=np.array([compose(origin,p) for p in poses]);error=np.linalg.norm(world[:,:2]-actual,axis=1)
    sigma=np.array([r['sigma_xy'] for r in trace]);ratio=error/np.maximum(sigma,1e-12)
    length=lambda x:float(np.linalg.norm(np.diff(x[:,:2],axis=0),axis=1).sum())
    expected={round(r['t'],6) for r in commands if r['kind']=='mecanum'}
    rejected=[r['command'] for r in rows(ep/'own-controller.jsonl')
              if r['command']['kind']=='mecanum' and round(r['t'],6) not in expected]
    result=dict(seed=seed,source=str(ep),hashes=hashes,frames=len(trace),pulse_groups=table,
        rejected_proposals=rejected,unobserved_terminal_commands=int(sum(c['kind']=='mecanum' and c['t']>=ts[-1]-1e-8 for c in commands)),
        dr_path_m=length(dr),posterior_path_m=length(poses),actual_path_m=length(actual),
        dr_to_actual=length(dr)/length(actual),posterior_to_actual=length(poses)/length(actual),
        correction_norm_sum_m=float(np.linalg.norm(residual[:,:2],axis=1).sum()),corrections=dict(corrections),
        final_error_m=float(error[-1]),final_sigma_m=float(sigma[-1]),final_error_sigma=float(ratio[-1]),
        over_3sigma_frames=int((ratio>3).sum()),over_3sigma_fraction=float((ratio>3).mean()),
        command_replay_sha256=hashlib.sha256(dr.tobytes()).hexdigest(),
        hypothesis='No startup deadband loss: all admitted pulses .10s; forward gain matches. Rotation XY cross coupling and posterior jumps remain.')
    return result,pulse_rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);a=p.parse_args()
    out=EXP/'results';out.mkdir(exist_ok=True)
    records=[audit(s)[0] for s in range(55001,55006)]
    (out/f'audit-{a.label}.json').write_text(json.dumps(records,indent=2)+'\n')
    for r in records:print({k:r[k] for k in ('seed','frames','dr_path_m','posterior_path_m','actual_path_m','correction_norm_sum_m','over_3sigma_frames')})


if __name__=='__main__':main()
