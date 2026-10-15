"""GCP saved-run diagnosis only. Evaluator poses never enter runtime code."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scripts.analyze_reloc11_selfmap import rows, obj
from scripts.analyze_reloc13 import analyze as funnel, distribution
from harness.natural_floor_slam import compose, wrap
from harness.selfmap4_geometry import inverse


def error(p, truth):
    return float(np.linalg.norm(np.asarray(p[:2])-truth[:2])), abs(math.degrees(wrap(p[2]-truth[2])))


def summary(es):
    return dict(N=len(es), xy_bad_N=sum(e['xy_m']>.1 for e in es), yaw_bad_N=sum(e['yaw_deg']>5 for e in es),
        both_bad_N=sum(e['xy_m']>.1 and e['yaw_deg']>5 for e in es),
        xy_m=distribution([e['xy_m'] for e in es]), yaw_deg=distribution([e['yaw_deg'] for e in es]),
        pf_xy_m=distribution([e['pf_xy_m'] for e in es]), pf_yaw_deg=distribution([e['pf_yaw_deg'] for e in es]))


def selfmap(folder):
    base=funnel(folder); raw=folder/'raw'; trace=rows(raw/'trace.jsonl')
    truth={round(r['t'],6):r for r in rows(raw/'eval_only/trajectory.jsonl')}
    epochs=[]; es=[]; fixes=[]; increments=[]; previous=None; registered=False
    for r in trace:
        s=r.get('static_registration',{}); packet=s.get('reloc12',{}); gt=truth.get(round(r['t'],6))
        if not s.get('registered') or not gt or packet.get('registered_world_pose') is None:continue
        anchor=packet['map_from_execution'] if packet.get('execution_frame_v1') else compose(packet['registered_world_pose'],inverse(packet['replay']['own_odometry_pose']))
        p=compose(anchor,r['pose'])
        actual=np.array([*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']])
        own=np.asarray(packet['replay']['own_odometry_pose'])
        fix=(not registered or r.get('pose_source')=='visual_relocalized' and r.get('visual_reason')=='selfmap4_static_lines')
        if fix:
            epoch=dict(t=r['t'],command_distance_m=0.,command_turn_deg=0.,actual_distance_m=0.,actual_turn_deg=0.)
            epochs.append(epoch)
        elif previous:
            epoch['command_distance_m']+=float(np.linalg.norm(own[:2]-previous['own'][:2]))
            epoch['command_turn_deg']+=abs(math.degrees(wrap(own[2]-previous['own'][2])))
            epoch['actual_distance_m']+=float(np.linalg.norm(actual[:2]-previous['actual'][:2]))
            epoch['actual_turn_deg']+=abs(math.degrees(wrap(actual[2]-previous['actual'][2])))
        xy,yaw=error(p,actual); px,pa=error(s['world_pose'],actual)
        e=dict(t=r['t'],xy_m=xy,yaw_deg=yaw,pf_xy_m=px,pf_yaw_deg=pa,
            since_fix_s=r['t']-epoch['t'],fix=fix,initial_fix=not registered,
            stage=r.get('stage'),source=r.get('pose_source'),R7=s.get('execution_r7_admitted'),
            **{k:v for k,v in epoch.items() if k!='t'})
        es.append(e)
        if fix:fixes.append(e)
        if previous:
            da=wrap(actual[2]-previous['actual'][2]); dc=wrap(own[2]-previous['own'][2]); dp=wrap(p[2]-previous['p'][2])
            increments.append(dict(t=r['t'],actual_yaw_rad=da,command_yaw_rad=dc,control_yaw_rad=dp,
                yaw_error_growth_deg=yaw-previous['yaw'],stage=r.get('stage'),static_fix=fix))
        previous=dict(actual=actual,own=own,p=p,yaw=yaw);registered=True
    # Explicit diagnostic bins, not new runtime admission constants.
    bins={}
    for name,bounds in [('since_fix_s',[0,.2,1,3,10,30,float('inf')]),
            ('command_distance_m',[0,.01,.1,.25,.5,1,float('inf')]),
            ('command_turn_deg',[0,1,5,15,45,90,180,float('inf')])]:
        bins[name]=[dict(lo=lo,hi=None if math.isinf(hi) else hi,**summary([e for e in es if lo<=e[name]<hi]))
            for lo,hi in zip(bounds,bounds[1:])]
    turning=[e for e in increments if abs(e['command_yaw_rad'])>1e-6 and not e['static_fix']]
    return dict(**base, drift=dict(all=summary(es),fixes=summary(fixes),first_registration=summary([e for e in es if e['initial_fix']]),
        bins=bins,epochs=epochs,fix_frames=fixes,frames=es,
        increment_regression=dict(N=len(turning),actual_per_command=(sum(e['actual_yaw_rad']*e['command_yaw_rad'] for e in turning)/sum(e['command_yaw_rad']**2 for e in turning)) if turning else None,
            yaw_error_growth_turning_deg=distribution([e['yaw_error_growth_deg'] for e in turning])),increments=increments))


def carry(folder):
    raw=folder/'raw';truth={round(r['t'],5):r for r in rows(raw/'eval-only.jsonl')};es=[]
    for r in rows(raw/'teacher-commands.jsonl'):
        m=r.get('map_pose',{}); gt=truth.get(round(r['t'],5),{})
        if gt.get('map_pose_error_yaw_rad') is None or not m:continue
        partial=m.get('partial_budget_epoch',[0.,0.])
        d=max(0.,m['issued_distance_since_fix_m']-partial[0]);a=max(0.,m['issued_turn_since_fix_rad']-partial[1])
        es.append(dict(t=r['t'],xy_m=gt['map_pose_error_xy_m'],yaw_deg=abs(math.degrees(gt['map_pose_error_yaw_rad'])),
            d=d,a=a,age_s=m.get('rgb_fix_age_s') if m.get('rgb_fix_age_s') is not None else r['t']-1.3,
            phase=r['phase'],run=folder.name,partial=bool(partial!=[0.,0.]),
            old_sigma=m.get('sigma_m_m_rad')))
    return dict(run=folder.name,frames=es,source_sha=obj(raw/'result.json').get('source_sha'),
        sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (raw/'teacher-commands.jsonl.zst',raw/'eval-only.jsonl.zst') if p.exists()})


def fit_carry(runs):
    train=[e for r in runs if '93266' in r['run'] for e in r['frames']]
    X=np.array([[1,e['d'],e['a'],e['age_s']] for e in train]); fits={}
    for name in ('xy_m','yaw_deg'):
        y=np.array([e[name] for e in train])
        fit=linprog(X.sum(0),A_ub=-X,b_ub=-y,bounds=[(0,None)]*4,method='highs')
        if not fit.success:raise RuntimeError(fit.message)
        coeff=fit.x.tolist(); scores=[]
        for r in runs:
            positive=[e for e in r['frames'] if e[name]>=(.5 if name=='xy_m' else 20)]
            def pred(e):return float(np.array([1,e['d'],e['a'],e['age_s']])@fit.x)
            scores.append(dict(run=r['run'],N=len(r['frames']),covered_N=sum(pred(e)+1e-8>=e[name] for e in r['frames']),
                positive_N=len(positive),trigger_recall=sum(pred(e)>=(.5 if name=='xy_m' else 20) for e in positive)/len(positive) if positive else None))
        fits[name]=dict(coefficients=coeff,features=['intercept','issued_distance_m','issued_turn_rad','since_rgb_fix_s'],scores=scores)
    return dict(basis='nonnegative linear upper envelope, all recorded phases including partial epochs; fit seed93266; seed93315 holdout; scoring-only truth',fits=fits)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/home/ugrp/ugrp-sim/runs'));p.add_argument('--pattern',default='reloc13-*selfmap-texture*');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    ss=[selfmap(f) for f in sorted(a.root.glob(a.pattern))]
    cs=[carry(f) for f in sorted(a.root.glob('reloc13-*carry*retry1'))]
    result=dict(schema='ugrp.reloc14.drift.v1',analysis_host='gcp1',selfmap=ss,carry_fit=fit_carry(cs),carry=cs,
        reproduce='PYTHONPATH=. .venv-sim/bin/python /tmp/analyze_reloc14.py --output /tmp/reloc14-baseline.json')
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    for r in ss:print(json.dumps(dict(run=r['run'],all=r['drift']['all'],first=r['drift']['first_registration'],fixes=r['drift']['fixes'],turn=r['drift']['increment_regression'])))
    print(json.dumps(result['carry_fit']))


if __name__=='__main__':main()
