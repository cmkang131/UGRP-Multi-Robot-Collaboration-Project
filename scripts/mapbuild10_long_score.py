"""Original-GCP5 post-seal long diagnostic evaluation; no control imports."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import numpy as np


def main(a):
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('SOURCE_VM_ONLY')
    def read(p):return json.loads(p.read_text())
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
    sys.path.insert(0,str(a.source))
    from harness.e2e_rgb_vo import compose,between
    b=a.input;a.output.mkdir(exist_ok=False)
    inputs=['own.json','online-trajectory.json','map-correction.json','scans.json','commands.json','static-map.json','public-start-zone.json','summary.json','events.json']
    seal={n:sha(b/n) for n in inputs};dump(a.output/'prediction-seal.json',seal)
    rows=read(b/'online-trajectory.json');own=read(b/'own.json')['frames'];rgb_bad=[]
    for f in own:
        if sha(b/f['rgb'])!=f['sha256']:rgb_bad.append(f['frame_id'])
    if rgb_bad:raise ValueError('RGB_CHANGED')
    # Only now open evaluation labels. OFF receives ONE starting SE2 gauge,
    # no scale fit; AMCL remains an absolute static-map estimate.
    truth=read(b/'eval-only.json')['frames']
    if len(rows)!=len(truth) or len(rows)!=len(own):raise ValueError('FRAME_JOIN_REQUIRED')
    req=read(a.requirements)['handoff'];off=np.zeros(3);data=[];distance=0.;route_distance=0.;turn=0.;last=None
    for r,g in zip(rows,truth):
        if r['t']!=g['t'] or r['frame_id']!=g['frame_id']:raise ValueError('TIME_JOIN_REQUIRED')
        gt=np.array(g['pose']);off=compose(off,r['motion_delta']);aligned=compose(truth[0]['pose'],off)
        if last is not None:
            d=float(np.linalg.norm(gt[:2]-last[:2]));distance+=d
            if r['stage'] in ('diagnostic_route','carry','return'):route_distance+=d;turn+=abs(float(between(last,gt)[2]))
        last=gt
        p=r['map_event'].get('absolute_proposal') if r['map_event'] else None
        result=dict(t=r['t'],stage=r['stage'],actual_path_m=distance,route_path_m=route_distance,
            off_xy_m=float(np.linalg.norm(aligned[:2]-gt[:2])),off_yaw_rad=abs(float(between(gt,aligned)[2])),
            amcl_xy_m=None,amcl_yaw_rad=None,amcl_requirement_pass=False,
            attempted=bool(r['map_event'] and r['map_event']['attempted']),converged=bool(r['map_event'] and r['map_event']['converged']))
        if p is not None:
            xy=float(np.linalg.norm(np.asarray(p[:2])-gt[:2]));yaw=abs(float(between(gt,p)[2]));coupled=yaw+math.atan2(xy,req['nominal_target_range_m']-xy)
            result.update(amcl_xy_m=xy,amcl_yaw_rad=yaw,amcl_coupled_rad=coupled,
                amcl_requirement_pass=bool(xy<=req['position_error_m'] and coupled<=req['yaw_error_rad']))
        data.append(result)
    dump(a.output/'frame-errors.json',data)
    def metric(rs,prefix):
        rs=[r for r in rs if r[prefix+'_xy_m'] is not None]
        if not rs:return None
        x=np.array([r[prefix+'_xy_m'] for r in rs]);y=np.array([r[prefix+'_yaw_rad'] for r in rs])
        return dict(frames=len(rs),end_xy_m=float(x[-1]),max_xy_m=float(x.max()),xy_rmse_m=float(np.sqrt(np.mean(x*x))),
            end_yaw_deg=float(np.degrees(y[-1])),max_yaw_deg=float(np.degrees(y.max())))
    phases=[]
    for stage in dict.fromkeys(r['stage'] for r in data):
        rs=[r for r in data if r['stage']==stage];phases.append(dict(stage=stage,off=metric(rs,'off'),amcl=metric(rs,'amcl')))
    # .5m bins are evaluation plot/report bins only, never an admission constant.
    bins=[]
    for k in range(int(distance/.5)+1):
        rs=[r for r in data if k*.5<=r['actual_path_m']<(k+1)*.5]
        if rs:bins.append(dict(start_path_m=k*.5,off=metric(rs,'off'),amcl=metric(rs,'amcl')))
    ready=[r for r in data if r['converged']];wrong=[r for r in ready if not r['amcl_requirement_pass']]
    route=[r for r in data if r['stage'] in ('diagnostic_route','carry','return')]
    amcl=metric(route,'amcl');off=metric(route,'off')
    # The authored route reverses tangent by pi. Its actual turn must cover
    # that geometry minus the frozen handoff yaw tolerance, not tiny yaw noise.
    turn_required=math.pi-req['yaw_error_rad']
    physical_status=read(b/'summary.json')['status']
    checks=[('record_command_complete',physical_status=='ROUTE_COMMAND_COMPLETE'),
        ('at_least_3m_route_and_authored_turn',route_distance>=3 and turn>=turn_required),
        ('distribution_converged',bool(ready)),('no_wrong_convergence',not wrong),
        ('all_route_frames_in_requirement',bool(route) and all(r['amcl_requirement_pass'] for r in route)),
        ('end_and_max_xy_improve_off',bool(amcl and off and amcl['end_xy_m']<off['end_xy_m'] and amcl['max_xy_m']<off['max_xy_m']))]
    gates=[];previous=1
    for name,ok in checks:
        n=int(previous and ok);gates.append(dict(stage=name,cumulative_pass_n=n,rejected_n=previous-n,predicate=bool(ok)));previous=n
    passed=bool(previous)
    frame_gates=[];previous=len(data)
    subsets=[('recorded_frames',data),('amcl_pose_available',[r for r in data if r['amcl_xy_m'] is not None]),
        ('measurement_updates',[r for r in data if r['attempted']]),('converged_updates',ready),
        ('correctly_converged_updates',[r for r in ready if r['amcl_requirement_pass']])]
    for name,rs in subsets:
        frame_gates.append(dict(stage=name,cumulative_pass_n=len(rs),rejected_n=previous-len(rs)));previous=len(rs)
    summary=dict(status='OFFLINE_LONG_DIAGNOSTIC_PASS' if passed else 'NOT_READY',physics_status=physical_status,
        recorded_frames=len(rows),actual_total_path_m=distance,actual_route_path_m=route_distance,actual_route_absolute_turn_rad=turn,
        off=off,amcl=amcl,phases=phases,path_bins=bins,converged_updates=len(ready),wrong_converged_updates=len(wrong),
        first_converged_sim_s=ready[0]['t'] if ready else None,loaded_frames=sum(r['stage']=='carry' for r in rows),
        scope='one recorded native-v7 public-start-box MJWarp diagnostic; same-frame post-seal OFF/AMCL; not ACT/LLM or physical mission success',
        evaluator_truth_to_control=0,rgb_sha_checked=len(own),rgb_mismatch=rgb_bad,requirements_sha256=sha(a.requirements),
        truth_sha256=sha(b/'eval-only.json'),prediction_seal_sha256=sha(a.output/'prediction-seal.json'),raw=str(b),reproduction=sys.argv)
    dump(a.output/'summary.json',summary)
    dump(a.output/'rejection_table.json',dict(raw=str(b),reproduction=sys.argv,case_gates=gates,frame_gates=frame_gates,
        distribution=[dict(reason='long_route_requirement_or_improvement_not_met' if not passed else 'diagnostic_pass',category='long_diagnostic',n=1,
            blocked_object='own_observed_wall',minimum_gap_m=None,gap_status='not_measured')]))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(2,1,figsize=(9,6),sharex=True)
        for prefix in ('off','amcl'):
            rr=[r for r in data if r[prefix+'_xy_m'] is not None]
            ax[0].plot([r['t'] for r in rr],[1000*r[prefix+'_xy_m'] for r in rr],label=prefix.upper())
            ax[1].plot([r['t'] for r in rr],np.degrees([r[prefix+'_yaw_rad'] for r in rr]),label=prefix.upper())
        ax[0].axhline(req['position_error_m']*1000,color='k',ls='--',label='XY requirement')
        ax[0].set_ylabel('XY error [mm]');ax[1].set_ylabel('Yaw error [deg]');ax[1].set_xlabel('SIM time [s]')
        ax[0].legend();ax[1].legend();fig.tight_layout();fig.savefig(a.output/'error-curves.png',dpi=140);plt.close(fig)
    except ImportError:summary['plot']='matplotlib unavailable';dump(a.output/'summary.json',summary)
    if any(sha(b/n)!=h for n,h in seal.items()):raise ValueError('SEALED_INPUT_CHANGED')
    dump(a.output/'SHA256SUMS.json',{p.name:sha(p) for p in a.output.iterdir() if p.is_file()})
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','input','output','requirements'):p.add_argument('--'+n,type=Path,required=True)
    main(p.parse_args())
