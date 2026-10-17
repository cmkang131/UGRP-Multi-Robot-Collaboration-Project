"""Same-recording three-way prediction, then sealed evaluation on original GCP5.

No evaluation labels are opened by predict(). OFF gets one initial SE2 gauge
only in score(); AMCL remains absolute. All candidates, including unready ones,
are scored and explicitly labelled. No endpoint/scale fitting.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import numpy as np


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False);f.write('\n')


def predict(a):
    from harness.mapbuild_amcl import StaticAMCL,OPTION
    from harness.e2e_rgb_vo import compose,between
    b=a.input;a.output.mkdir(exist_ok=False)
    names=['own.json','online-trajectory.json','scans.json','static-map.json','public-start-zone.json','commands.json']
    inputs={str(b/n):sha(b/n) for n in names}
    inputs.update({str(p):sha(p) for p in [a.calibration,a.requirements,Path(__file__),Path('harness/mapbuild_amcl.py'),Path('harness/mapbuild_amcl_vendor/algorithms.py')]})
    own=read(b/'own.json')['frames'];online=read(b/'online-trajectory.json');scans=read(b/'scans.json')
    if not len(own)==len(online)==len(scans):raise ValueError('FRAME_JOIN_REQUIRED')
    for f in own:
        if sha(b/f['rgb'])!=f['sha256']:raise ValueError('RGB_CHANGED')
    filters={p:StaticAMCL(read(b/'static-map.json'),read(a.calibration),read(a.requirements),option=OPTION,profile=p,
        seed=2026101700,initial_prior_option='start_zone_prior_v1',initial_prior=read(b/'public-start-zone.json'))
        for p in ('nav2_defaults_v1','nav2_rgb_field_v1')}
    rows=[];off=np.zeros(3);maps={p:[] for p in filters}
    for f,r,s in zip(own,online,scans):
        if not f['t']==r['t']==s['t']:raise ValueError('TIME_JOIN_REQUIRED')
        off=compose(off,r['motion_delta']);entry=dict(t=r['t'],frame_id=r['frame_id'],stage=r['stage'],off_own=off.tolist(),models={})
        for name,m in filters.items():
            e=m.step(f['t'],f['frame_id'],r['motion_delta'],s,servo=f['servo'])
            pose=compose(m.current['candidate_pose'],between(m.sensor_odom,m.odom)).tolist() if m.current else None
            entry['models'][name]=dict(candidate=pose,ready=bool(m.current and m.current['converged']),attempted=e['attempted'],
                reason=e['reason'],xy95=e.get('xy_p95_m'),yaw95=e.get('yaw_p95_rad'),ess=e.get('ess'),
                production_qualified=False)
            if m.local_map and m.local_map[-1]['frame_id']==f['frame_id']:
                maps[name].append(dict(t=f['t'],pose=pose,converged=bool(m.current and m.current['converged']),segments=s['segments'],
                    own_odom=m.odom.tolist(),used_for_localization=False))
        rows.append(entry)
    dump(a.output/'predictions.json',rows);dump(a.output/'own-maps.json',maps)
    dump(a.output/'prediction-seal.json',dict(inputs=inputs,prediction_sha256=sha(a.output/'predictions.json'),
        own_maps_sha256=sha(a.output/'own-maps.json'),truth_inputs=0,rgb_verified=len(own),reproduction=sys.argv))
    print(json.dumps(dict(stage='predictions_sealed',frames=len(rows),truth_inputs=0)),flush=True)


def score(a):
    from harness.e2e_rgb_vo import compose,between
    b=a.input;o=a.output;seal=read(o/'prediction-seal.json')
    for p,h in seal['inputs'].items():
        if sha(Path(p))!=h:raise ValueError('INPUT_CHANGED')
    if sha(o/'predictions.json')!=seal['prediction_sha256'] or sha(o/'own-maps.json')!=seal['own_maps_sha256']:raise ValueError('PREDICTION_CHANGED')
    pred=read(o/'predictions.json');truth=read(b/'eval-only.json')['frames']
    if len(pred)!=len(truth):raise ValueError('EVAL_JOIN_REQUIRED')
    req=read(a.requirements)['handoff'];rows=[];distance=0.;route_distance=0.;turn=0.;last=None
    for r,g in zip(pred,truth):
        if r['t']!=g['t']:raise ValueError('EVAL_TIME_JOIN_REQUIRED')
        gt=np.array(g['pose']);route=r['stage']=='diagnostic_route'
        if last is not None:
            d=float(np.linalg.norm(gt[:2]-last[:2]));distance+=d
            if route:route_distance+=d;turn+=abs(float(between(last,gt)[2]))
        last=gt
        entry=dict(t=r['t'],stage=r['stage'],path_m=distance,route_path_m=route_distance,models={})
        candidates={'off':dict(candidate=compose(truth[0]['pose'],r['off_own']).tolist(),ready=False,attempted=False),**r['models']}
        for name,v in candidates.items():
            p=v['candidate'];v=dict(v)
            if p is None:v.update(xy_m=None,yaw_deg=None,coupled_deg=None,requirement_pass=False)
            else:
                xy=float(np.linalg.norm(np.asarray(p[:2])-gt[:2]));yaw=abs(float(between(gt,p)[2]));coupled=yaw+math.atan2(xy,req['nominal_target_range_m']-xy)
                v.update(xy_m=xy,yaw_deg=math.degrees(yaw),coupled_deg=math.degrees(coupled),
                    requirement_pass=xy<=req['position_error_m'] and coupled<=req['yaw_error_rad'])
            entry['models'][name]=v
        rows.append(entry)
    dump(o/'frame-errors.json',rows)
    names=['off','nav2_defaults_v1','nav2_rgb_field_v1'];route=[r for r in rows if r['stage']=='diagnostic_route']
    def metric(rs,name):
        valid=[r for r in rs if r['models'][name]['xy_m'] is not None]
        if not valid:return None
        vs=[r['models'][name] for r in valid];xy=np.array([v['xy_m'] for v in vs])
        ready=[r for r in valid if r['models'][name]['ready'] and r['models'][name]['attempted']]
        return dict(frames=len(valid),end_xy_mm=float(xy[-1]*1000),max_xy_mm=float(xy.max()*1000),rmse_xy_mm=float(np.sqrt(np.mean(xy*xy))*1000),
            end_yaw_deg=vs[-1]['yaw_deg'],max_yaw_deg=max(v['yaw_deg'] for v in vs),end_coupled_deg=vs[-1]['coupled_deg'],
            requirement_frames=sum(v['requirement_pass'] for v in vs),end_requirement_pass=vs[-1]['requirement_pass'],
            first_converged_sim_s=ready[0]['t'] if ready else None,ready_updates=len(ready),wrong_ready_updates=sum(not r['models'][name]['requirement_pass'] for r in ready))
    bins=[]
    for k in range(math.floor(route_distance/.5)+1):
        rs=[r for r in route if k*.5<=r['route_path_m']<(k+1)*.5]
        if rs:bins.append(dict(start_m=k*.5,end_m=(k+1)*.5,models={n:metric(rs,n) for n in names}))
    events=read(b/'events.json');stops=[e for e in events if e['event']=='would_stop' or e.get('would_stop',False)]
    result=dict(status='OFFLINE_EVALUATION_ONLY',recording_status=read(b/'summary.json')['status'],actual_path_m=distance,route_path_m=route_distance,
        route_abs_turn_deg=math.degrees(turn),route={n:metric(route,n) for n in names},whole={n:metric(rows,n) for n in names},bins=bins,
        would_stop_count=len(stops),first_would_stop=stops[0] if stops else None,requirements=req,
        loaded_frames=0,student_success=False,llm_success=False,production_qualified=False,
        raw=str(b),truth_sha256=sha(b/'eval-only.json'),prediction_seal_sha256=sha(o/'prediction-seal.json'))
    dump(o/'summary.json',result)
    gates=[];left=1
    for name,passed in [('recording_finished',result['recording_status']=='ROUTE_COMMAND_COMPLETE'),
        ('route_at_least_3m',route_distance>=3),('authored_reversal',turn>=math.pi-req['yaw_error_rad'])]:
        nxt=left*bool(passed);gates.append(dict(stage=name,input_n=left,cumulative_pass_n=nxt,rejected_n=left-nxt));left=nxt
    funnel=dict(raw=str(b),reproduction=sys.argv,recording=gates,models={n:dict(route=result['route'][n],
        reasons=dict(Counter(r['models'][n].get('reason','off') for r in rows))) for n in names},
        rejection_fields=dict(blocked_object='not_measured',minimum_gap_m=None,gap_status='not_measured'),runtime_admission=False)
    dump(o/'rejection_table.json',funnel)
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True)
    for n in names:
        rs=[r for r in route if r['models'][n]['xy_m'] is not None]
        axes[0].plot([r['route_path_m'] for r in rs],[r['models'][n]['xy_m']*1000 for r in rs],label=n,lw=1)
        axes[1].plot([r['route_path_m'] for r in rs],[r['models'][n]['yaw_deg'] for r in rs],label=n,lw=1)
    axes[0].axhline(req['position_error_m']*1000,color='k',ls='--',label='handoff XY budget')
    axes[0].set_ylabel('XY error (mm)');axes[1].set_ylabel('yaw error (deg)');axes[1].set_xlabel('actual route travel (m), evaluation only')
    for ax in axes:ax.grid();ax.legend(fontsize=8);ax.set_xticks(np.arange(0,route_distance+.5,.5))
    fig.suptitle('Same recording; OFF initial gauge only; AMCL absolute/unqualified')
    fig.tight_layout();fig.savefig(o/'error-curves.png',dpi=140);plt.close(fig)
    print(json.dumps({k:v for k,v in result.items() if k not in ('bins','first_would_stop','requirements')}),flush=True)


if __name__=='__main__':
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('ORIGINAL_GCP5_ONLY')
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['predict','score'],required=True)
    for n in ('input','output','calibration','requirements'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();globals()[a.stage](a)
