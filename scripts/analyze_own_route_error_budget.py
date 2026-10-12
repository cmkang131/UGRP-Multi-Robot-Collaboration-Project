"""egomap69: post-hoc saved-data audit. No simulator, controller or fitting.

GT enters only this evaluator. Motion is replayed by the frozen command model;
posterior-minus-prior includes sample selection, Manhattan, CSM and route edits.
It is not labelled a measured wheel-slip signal or a pure CSM correction.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import numpy as np


def read(p):
    return json.loads(p.read_text())


def rows(p):
    return [json.loads(s) for s in p.open() if s.strip()]


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def wrap(x):
    return (np.asarray(x)+math.pi) % (2*math.pi)-math.pi


def compose(a, b):
    c, s = np.cos(a[2]), np.sin(a[2])
    return np.array([a[0]+c*b[0]-s*b[1], a[1]+s*b[0]+c*b[1], float(wrap(a[2]+b[2]))])


def between(a, b):
    c, s = np.cos(a[2]), np.sin(a[2])
    x, y = np.asarray(b[:2])-a[:2]
    return np.array([c*x+s*y, -s*x+c*y, float(wrap(b[2]-a[2]))])


def distribution(a):
    a = np.asarray(a, float)
    return dict(n=len(a), median=float(np.median(a)), p90=float(np.quantile(a,.9)),
                max=float(np.max(a)), mean=float(np.mean(a))) if len(a) else dict(n=0)


def kind(cmd):
    if cmd.get('turn', 0): return 'left_turn' if cmd['turn'] > 0 else 'right_turn'
    if cmd.get('forward', 0): return 'forward' if cmd['forward'] > 0 else 'backward'
    if cmd.get('left', 0): return 'lateral'
    return 'hold'


def recorded_B(result, events):
    # Physical-failure result has no declared_B field. Preserve that run and
    # use its retained causal event log, rather than dropping it from N.
    return bool(result.get('declared_B', any(e.get('reason')=='goal_reached' and e.get('entity')=='B' for e in events)))


def motion_poses(commands, times):
    from harness.self_pulse_rotation import RotationPulseOdometry
    model = RotationPulseOdometry(min(float(commands[0]['t']), times[0]))
    result=[]; index=0
    for t in times:
        # Image is acquired before the command issued at its timestamp.
        while index < len(commands) and commands[index]['t'] < t-1e-8:
            model.command(commands[index]); index += 1
        model.advance(t); result.append(model.pose)
    return np.asarray(result)


def interval_audit(own, truth, dr):
    """Exact SE2 one-step prediction and post-update error bookkeeping."""
    pred=[]; actual=[]; innovations=[]; before=[]; after=[]
    for i in range(1,len(own)):
        d=between(dr[i-1],dr[i]); g=between(truth[i-1],truth[i])
        prior=compose(own[i-1],d)
        pred.append(d);actual.append(g);innovations.append(between(prior,own[i]))
        before.append(np.linalg.norm(prior[:2]-truth[i,:2]));after.append(np.linalg.norm(own[i,:2]-truth[i,:2]))
    return np.asarray(pred),np.asarray(actual),np.asarray(innovations),np.asarray(before),np.asarray(after)


def evaluate(p, out, features=True):
    result=read(p/'result.json');start=result['start_sim_s']
    ts=rows(p/'eval_only/trajectory.jsonl');tb={round(r['t'],6):r for r in ts}
    rr=[r for r in rows(p/'own-controller.jsonl') if round(r['t'],6) in tb]
    times=np.array([r['t'] for r in rr]); origin=np.r_[ts[0]['robot_xyz_m'][:2],ts[0]['robot_yaw_rad']]
    gt=np.array([between(origin,np.r_[tb[round(t,6)]['robot_xyz_m'][:2],tb[round(t,6)]['robot_yaw_rad']]) for t in times])
    own=np.array([r['local_pose'] for r in rr]);dr=motion_poses(rows(p/'robots/r3/commands.jsonl'),times)
    # Comparison after checkpoint resets DR to GT ONCE, evaluation only.
    cut=int(np.searchsorted(times,start-1e-8));rr=rr[cut:];times=times[cut:];gt=gt[cut:];own=own[cut:];dr=dr[cut:]
    reset_dr=np.array([compose(gt[0],between(dr[0],x)) for x in dr])
    perfect_yaw=[gt[0].copy()]
    for i in range(1,len(gt)):
        d=between(dr[i-1],dr[i]); q=compose(np.r_[perfect_yaw[-1][:2],gt[i-1,2]],d)
        q[2]=gt[i,2];perfect_yaw.append(q)
    perfect_yaw=np.array(perfect_yaw)
    pred,actual,innovation,prior_err,post_err=interval_audit(own,gt,dr)
    e=np.linalg.norm(own[:,:2]-gt[:,:2],axis=1); ye=np.degrees(wrap(own[:,2]-gt[:,2]))
    de=np.linalg.norm(reset_dr[:,:2]-gt[:,:2],axis=1);dy=np.degrees(wrap(reset_dr[:,2]-gt[:,2]))
    ce=np.linalg.norm(perfect_yaw[:,:2]-gt[:,:2],axis=1)
    sigma=np.array([r['sigma_xy'] for r in rr]);groups={}
    kinds=[kind(r['command']) for r in rr[:-1]]
    for k in sorted(set(kinds)):
        m=np.array([v==k for v in kinds]); n=int(m.sum())
        groups[k]=dict(intervals=n,sim_s=float(np.diff(times)[m].sum()),
            predicted_xy_path_m=float(np.linalg.norm(pred[m,:2],axis=1).sum()),
            actual_xy_path_m=float(np.linalg.norm(actual[m,:2],axis=1).sum()),
            predicted_forward_m=float(pred[m,0].sum()),actual_forward_m=float(actual[m,0].sum()),
            predicted_lateral_m=float(pred[m,1].sum()),actual_lateral_m=float(actual[m,1].sum()),
            predicted_yaw_deg=float(np.degrees(pred[m,2].sum())),actual_yaw_deg=float(np.degrees(actual[m,2].sum())),
            increment_xy_error_mm=distribution(1000*np.linalg.norm(pred[m,:2]-actual[m,:2],axis=1)),
            increment_yaw_error_deg=distribution(np.degrees(pred[m,2]-actual[m,2])),
            posterior_xy_error_m=distribution(e[1:][m]),posterior_abs_yaw_deg=distribution(abs(ye[1:][m])),
            correction_jump_m=distribution(np.linalg.norm(innovation[m,:2],axis=1)),
            correction_jump_gt_improved=int((post_err[m]<prior_err[m]-1e-9).sum()),
            motion_squared_error_change=float(((prior_err**2-e[:-1]**2)[m]).sum()),
            update_squared_error_change=float(((post_err**2-prior_err**2)[m]).sum()))
    events=read(p/'utility-events.json');ret=next((x['t'] for x in events if x['reason']=='registered_return_stage_started' and x['t']>=start),times[-1]+.1)
    gates=[g for g in read(p/'arrival-gates.json') if start<=g['t']<ret]
    B=read(p/'inputs/static_map.json')['regions']['zone_B']
    ag=[tb[round(t,6)] for t in times if t<ret]
    bd=[float(np.linalg.norm(np.maximum(np.abs(np.asarray(t['robot_xyz_m'][:2])-B['center_m'])-B['half_extents_m'],0))) for t in ag]
    near=[g for g in gates if g['near']];route=read(p/'route-map.json');matches=[x for x in route['matches'] if x['t']>=start]
    decisions=[x for x in read(p/'decisions.json') if x['t']>=start]
    decision_by_t={round(x['t'],6):x for x in decisions}
    update_groups=defaultdict(list)
    for i in range(1,len(rr)):
        d=decision_by_t.get(round(times[i],6),{})
        update_groups[d.get('reason','missing')].append(i-1)
    update_summary={}
    for key, ids in update_groups.items():
        ix=np.asarray(ids); jump=np.linalg.norm(innovation[ix,:2],axis=1)
        update_summary[key]=dict(n=len(ids),jump_m=distribution(jump),gt_improved=int((post_err[ix]<prior_err[ix]-1e-9).sum()),
            gt_worsened=int((post_err[ix]>prior_err[ix]+1e-9).sum()),delta_error_m_sum=float((post_err[ix]-prior_err[ix]).sum()))
    series=[]
    for i,t in enumerate(times):
        series.append(dict(t=float(t),elapsed=float(t-start),kind=kind(rr[i]['command']),stage=rr[i]['stage'],
            error_m=float(e[i]),yaw_error_deg=float(ye[i]),sigma_m=float(sigma[i]),
            dr_reset_error_m=float(de[i]),dr_reset_yaw_error_deg=float(dy[i]),oracle_yaw_dr_error_m=float(ce[i])))
    seed=result['seed'];(out/f'time-{seed}.json').write_text(json.dumps(series,separators=(',',':')))
    checkpoints=[]
    for dt in [0,60,120,180,240,270,360,480,540]:
        if start+dt>times[-1]+1e-7:continue
        checkpoints.append(series[min(int(np.searchsorted(times,start+dt)),len(times)-1)])
    sensor=[r for r in rows(p/'robots/r3/inputs/range.jsonl') if 't' in r and start<=r['t']<=times[-1]]
    valid=[r['range_m'] for r in sensor if r.get('valid')]
    bsummary=dict(arrived=recorded_B(result,events),approach_sim_s=float(min(ret,times[-1])-start),
        nearest_GT_B_boundary_m=min(bd),frames_inside_GT_B=sum(d<1e-9 for d in bd),
        gate_frames=len(gates),estimated_near_frames=len(near),gate_reasons=dict(Counter(g['reason'] for g in gates)),
        near_reasons=dict(Counter(g['reason'] for g in near)),
        near_patch_present=sum(g['patches']>0 for g in near),near_fresh_confirmed=sum(g['fresh_confirmed'] for g in near),
        near_hold=sum(kind(r['command'])=='hold' for r in rr if any(abs(g['t']-r['t'])<1e-6 for g in near)),
        patches_present=sum(g['patches']>0 for g in gates),fresh_confirmed=sum(g['fresh_confirmed'] for g in gates),
        max_streak=max((g['streak'] for g in gates),default=0),final_GT_B_boundary_m=bd[-1],
        last_near_time=max((g['t'] for g in near),default=None),
        entity=route['entities'].get('B'),status=result['status'])
    final=dict(estimate_error_m=float(e[-1]),estimate_yaw_deg=float(ye[-1]),sigma_m=float(sigma[-1]),
        over_3sigma_frames=int((e>3*sigma).sum()),samples=len(e),
        reset_DR_error_m=float(de[-1]),reset_DR_yaw_deg=float(dy[-1]),oracle_yaw_DR_error_m=float(ce[-1]),
        estimate_RMSE_m=float(np.sqrt(np.mean(e**2))),reset_DR_RMSE_m=float(np.sqrt(np.mean(de**2))),
        oracle_yaw_DR_RMSE_m=float(np.sqrt(np.mean(ce**2))))
    allhash={}
    for name in ['result.json','bundle.json','own-controller.jsonl','eval_only/trajectory.jsonl','robots/r3/commands.jsonl',
                 'robots/r3/frames.jsonl','robots/r3/inputs/range.jsonl','arrival-gates.json','route-map.json','decisions.json']:
        allhash[name]=sha(p/name)
    report=dict(seed=seed,source=str(p),source_sha=result['source_sha'],inputs_sha256=allhash,final=final,
        checkpoints=checkpoints,by_command=groups,B=bsummary,
        CSM_frame_reasons=dict(Counter(d['reason'] for d in decisions)),updates=update_summary,
        route_match_reasons=dict(Counter(m['reason'] for m in matches)),route_match_n=len(matches),
        route_match_accepted=sum(m['status']=='accepted' for m in matches),
        sonar=dict(samples=len(sensor),valid=len(valid),range_m=distribution(valid),statuses=dict(Counter(r['status'] for r in sensor))))
    if features:report['features']=feature_audit(p,rr,out)
    return report


def feature_audit(p,own,out):
    import cv2
    from harness.own_rgb_homing import Memory,matches
    cv2.setNumThreads(1);cv2.setRNGSeed(69001)
    memory=Memory();manifest={r['frame_id']:r for r in rows(p/'robots/r3/frames.jsonl')}
    # Fixed systematic sample every 25 saved observations (5 SIM s), no outcome selection.
    evidence=[]
    for i in range(0,len(own),25):
        r=own[i];fs=[]
        for j in [max(0,i-1),i]:
            row=own[j];f=manifest[row['frame_id']];path=p/f['path']
            if sha(path)!=f['sha256']:raise ValueError('RGB_HASH '+str(path))
            rgb=cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2RGB)
            fs.append(memory.extract(rgb,{int(k):v for k,v in f['commanded_servo'].items()},row['local_pose'],row['t'],row['frame_id'],f['sha256']))
        a,b=fs;mm=matches(a.descriptors,b.descriptors);inliers=0
        if len(mm)>=5 and i:
            ix,jx=np.asarray(mm).T
            _,mask=cv2.findEssentialMat(a.uv[ix],b.uv[jx],memory.K,method=cv2.RANSAC,prob=.99,threshold=1.)
            inliers=int(mask.sum()) if mask is not None else 0
        evidence.append(dict(frame_id=r['frame_id'],t=r['t'],sha256=manifest[r['frame_id']]['sha256'],features=len(b.uv),
            upper_third_features=int((b.uv[:,1]<160).sum()),lower_two_thirds_features=int((b.uv[:,1]>=160).sum()),
            consecutive_matches=len(mm) if i else None,essential_inliers=inliers if i else None,kind=kind(r['command'])))
    seed=read(p/'result.json')['seed'];(out/f'features-{seed}.json').write_text(json.dumps(evidence))
    return dict(samples=len(evidence),eligible_frames=len(own),stride=25,features=distribution([r['features'] for r in evidence]),
        below_50=sum(r['features']<50 for r in evidence),upper_third=distribution([r['upper_third_features'] for r in evidence]),
        matches=distribution([r['consecutive_matches'] for r in evidence if r['consecutive_matches'] is not None]),
        essential_inliers=distribution([r['essential_inliers'] for r in evidence if r['essential_inliers'] is not None]),
        qualification='Saved JPEG, egomap68 rectification/body mask/ORB parameters; E inliers are not metric pose or reliable parallax.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report=dict(schema='egomap69.error_budget.v1',host='oracle-x86',scope='posthoc same six DEV baseline recordings; no physics/model calls',
        method='Original-start GT alignment for posterior; one GT reset at checkpoint for standalone DR; oracle yaw is diagnostic only. Updates include particle selection, Manhattan/CSM and route corrections, not pure visual innovations.',runs=[])
    for seed in range(63001,63007):
        report['runs'].append(evaluate(args.root/f'egomap68-{seed}-baseline',args.output))
        (args.output/'audit.json').write_text(json.dumps(report,indent=2));print('completed',seed,flush=True)
    report['artifacts_sha256']={p.name:sha(p) for p in args.output.glob('*.json') if p.name!='audit.json'}
    report['script_sha256']=sha(Path(__file__))
    (args.output/'audit.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
