"""Separate gcp5 evaluator: sealed same-frame chassis SE2 OFF/ON comparison."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import sys


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ONLY')
    root=Path(__file__).resolve().parents[1];sys.path[:0]=[str(root),str(root/'scripts')]
    import numpy as np
    from scripts.mapbuild6_evaluate import relative_trajectory,errors
    from harness.e2e_rgb_vo import between
    def read(p):return json.loads(p.read_text())
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    seal=read(a.prediction/'prediction-seal.json')
    for p,h in seal['input_sha256'].items():
        if sha(Path(p))!=h:raise ValueError('INPUT_SEAL_CHANGED:'+p)
    for p,h in seal['prediction_sha256'].items():
        if sha(a.prediction/p)!=h:raise ValueError('PREDICTION_SEAL_CHANGED:'+p)
    a.output.mkdir(parents=True,exist_ok=False)
    rows=read(a.prediction/'trajectory.json');events=read(a.prediction/'events.json');truth=read(a.input/'eval-only.json')['frames'];route=read(a.input/'events.json')
    if [r['frame_id'] for r in rows]!=[r['frame_id'] for r in truth]:raise ValueError('EXACT_FRAMES_REQUIRED')
    world=np.array([r['pose'] for r in truth]);gt=relative_trajectory(world);req=read(a.requirements)
    dist=np.r_[0,np.cumsum(np.linalg.norm(np.diff(gt[:,:2],axis=0),axis=1))]
    arrays={};methods={};phases={};points=[]
    carry_start=next((e['t'] for e in route if e['event']=='own_rgb_pickup_hold_confirmed'),math.inf)
    carry_end=next((e['t'] for e in route if e['event']=='estimated_zone_arrival'),math.inf)
    masks=dict(all=np.ones(len(rows),bool),commanded_closed=np.array([int(r['servo']['1'])<=1600 for r in rows]),
               actual_transport_command_interval=np.array([carry_start<=r['t']<=carry_end for r in rows]))
    for method in ('lk','off','on','rbpf'):
        pred=np.array([r[method+'_pose'] for r in rows]);xy,yaw=errors(pred,gt);arrays[method]=(xy,yaw)
        coupled=yaw+np.arctan2(xy,req['handoff']['nominal_target_range_m']-xy)
        def metric(mask):
            indices=np.flatnonzero(mask)
            if not len(indices):return dict(frames=0,status='not_recorded')
            k=indices[-1];length=dist[k]-dist[indices[0]]
            return dict(frames=len(indices),path_m=float(length),xy_rmse_m=float(np.sqrt(np.mean(xy[indices]**2))),
                final_xy_m=float(xy[k]),final_yaw_deg=float(np.degrees(yaw[k])),maximum_xy_m=float(xy[indices].max()),
                maximum_yaw_deg=float(np.degrees(yaw[indices].max())),final_drift_percent=float(100*xy[k]/length) if length>0 else None,
                final_handoff_pass=bool(xy[k]<=req['handoff']['position_error_m'] and coupled[k]<=req['handoff']['yaw_error_rad']),
                final_direction_coupled_deg=float(np.degrees(coupled[k])),slot_pass=bool(xy[k]<=req['arrival']['slot_center_error_m']))
        methods[method]=metric(masks['all']);phases[method]={name:metric(mask) for name,mask in masks.items() if name!='all'}
    for e in route:
        k=min(range(len(rows)),key=lambda k:abs(rows[k]['t']-e['t']));values={}
        for method,(xy,yaw) in arrays.items():
            coupled=float(yaw[k]+math.atan2(xy[k],req['handoff']['nominal_target_range_m']-xy[k]))
            values[method]=dict(xy_m=float(xy[k]),yaw_deg=float(np.degrees(yaw[k])),direction_coupled_deg=float(np.degrees(coupled)),
                handoff_pass=bool(xy[k]<=req['handoff']['position_error_m'] and coupled<=req['handoff']['yaw_error_rad']),slot_pass=bool(xy[k]<=req['arrival']['slot_center_error_m']))
        points.append(dict(t=e['t'],event=e['event'],methods=values))
    corrections=[];registrations=[]
    for k,e in enumerate(events):
        reg=e.get('registration')
        if reg and reg.get('status')=='accepted':
            from harness.e2e_rgb_vo import compose
            absolute=compose(reg['static_from_own'],rows[k]['on_pose']);xy,yaw=errors([absolute],[world[k]])
            coupled=float(yaw[0]+math.atan2(xy[0],req['handoff']['nominal_target_range_m']-xy[0]))
            registrations.append(dict(t=e['t'],absolute_body_pose=absolute.tolist(),xy_m=float(xy[0]),yaw_deg=float(np.degrees(yaw[0])),
                direction_coupled_deg=float(np.degrees(coupled)),within_handoff_budget=bool(xy[0]<=req['handoff']['position_error_m'] and coupled<=req['handoff']['yaw_error_rad'])))
        e=e['correction']
        if not e['accepted']:continue
        before_xy,before_yaw=errors([e['prior_pose']],[gt[k]]);after_xy,after_yaw=errors([e['pose']],[gt[k]])
        corrections.append(dict(t=e['t'],selected=e['selected'],before_xy_m=float(before_xy[0]),after_xy_m=float(after_xy[0]),
            before_yaw_deg=float(np.degrees(before_yaw[0])),after_yaw_deg=float(np.degrees(after_yaw[0])),
            xy_worsened=bool(after_xy[0]>before_xy[0]),yaw_worsened=bool(after_yaw[0]>before_yaw[0])))
    intervals=[]
    frames=read(a.input/'own.json')['frames']
    for k in range(1,len(rows)):
        d=between(world[k-1],world[k]);estimate=np.asarray(rows[k]['motion_delta']);r=estimate-d;r[2]=math.atan2(math.sin(r[2]),math.cos(r[2]))
        cause=('servo_change' if frames[k]['servo']!=frames[k-1]['servo'] else 'measured_rotation' if rows[k]['lk']['status']=='measured' and frames[k]['command_delta'][2]!=0 else
               'measured_translation_or_rest' if rows[k]['lk']['status']=='measured' else 'command_prediction_'+rows[k]['lk']['status'])
        intervals.append(dict(t=rows[k]['t'],category=cause,xy_increment_residual_m=float(np.linalg.norm(r[:2])),yaw_increment_residual_deg=float(np.degrees(abs(r[2]))),
            motion_covariance=rows[k]['motion_covariance'],blocked_object='own_floor_projection_or_command_model',minimum_gap_m=None,gap_status='not_measured'))
    distribution=[]
    for cause,n in Counter(r['category'] for r in intervals).items():
        rs=[r for r in intervals if r['category']==cause]
        distribution.append(dict(category=cause,n=n,xy_increment_residual_sum_m=sum(r['xy_increment_residual_m'] for r in rs),
            xy_increment_residual_p95_m=float(np.percentile([r['xy_increment_residual_m'] for r in rs],95)),
            blocked_object='own_floor_projection_or_command_model',minimum_gap_m=None,gap_status='not_measured'))
    distribution.sort(key=lambda r:-r['xy_increment_residual_sum_m'])
    static=read(a.input/'static-map.json');crossings=[]
    for p in static['passages']:
        axis=0 if p['axis']=='x' else 1;other=1-axis;c=np.asarray(p['center_m'])
        ks=np.flatnonzero((world[:-1,axis]-c[axis])*(world[1:,axis]-c[axis])<=0)+1
        for k in ks:
            if world[k-1,axis]==world[k,axis] or abs(world[k,other]-c[other])>p['width_m']/2:continue
            values={}
            for method,(xy,yaw) in arrays.items():
                pred=np.asarray(rows[k][method+'_pose']);lateral=abs(pred[other]-gt[k,other])
                # GT and own gauge may be rotated. Conservatively report radial
                # error as a bound separately; do not call it lateral error.
                support=req['passage']['robot_half_length_m']*abs(np.sin(yaw[k]))+req['passage']['robot_half_width_m']*abs(np.cos(yaw[k]))
                values[method]=dict(xy_error_bound_m=float(xy[k]),yaw_deg=float(np.degrees(yaw[k])),chassis_bound_pass=bool(xy[k]+support<=p['width_m']/2),held_footprint_pass=None)
            crossings.append(dict(t=rows[k]['t'],passage=p['id'],methods=values))
    names={e['event'] for e in route};missing=[]
    for key,name in [('estimated_zone_arrival','zone_arrival'),('estimated_return_arrival','return'),('post_setdown_lookaround_end','setdown_lookaround')]:
        if key not in names:missing.append(name)
    if not crossings:missing.append('door_crossing')
    if not any(e['event']=='map_to_teacher_handoff' and e.get('navigation_before_handoff') for e in route):missing.append('map_to_ACT_handoff_after_navigation')
    # A visible-only demonstration is not a learned ACT or LLM execution.
    result=dict(status='NOT_READY' if missing else 'route_recorded_requires_physical_recount',decision='no default adoption until all actual-route requirements pass',
        raw=str(a.input),prediction=str(a.prediction),frames=len(rows),sim_s=rows[-1]['t'],path_m=float(dist[-1]),reference='chassis SE2; start-only alignment; scale=1',
        methods=methods,phases=phases,checkpoints=points,door_crossings=crossings,missing=missing,
        correction_counts=dict(attempts=sum(e['correction']['attempted'] for e in events),accepted=len(corrections),xy_worsened=sum(e['xy_worsened'] for e in corrections),yaw_worsened=sum(e['yaw_worsened'] for e in corrections)),
        correction_evaluation=corrections,rejection_distribution=distribution,truth_to_control=0,scale_fitting=0,
        accepted_global_registration_evaluation=registrations,wrong_global_accepts=sum(not r['within_handoff_budget'] for r in registrations),
        phase_scope='closed grip is a command label, not proof of load; actual transport starts at own-RGB hold confirmation; physical lift independently evaluated',
        requirements_sha256=sha(a.requirements),prediction_seal_sha256=sha(a.prediction/'prediction-seal.json'),reproduction=sys.argv)
    dump(a.output/'summary.json',result);dump(a.output/'intervals.json',intervals)
    dump(a.output/'frame-errors.json',[dict(t=r['t'],methods={m:dict(xy_m=float(xy[k]),yaw_deg=float(np.degrees(yaw[k]))) for m,(xy,yaw) in arrays.items()}) for k,r in enumerate(rows)])
    print(json.dumps({k:v for k,v in result.items() if k not in ('checkpoints','correction_evaluation','rejection_distribution')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('input','prediction','requirements','output'):p.add_argument('--'+k,type=Path,required=True)
    main(p.parse_args())
