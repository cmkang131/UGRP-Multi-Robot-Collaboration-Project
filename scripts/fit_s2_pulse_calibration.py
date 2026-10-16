"""Batch system identification from saved S2 pulse responses; no simulator.

Empirical finite-pulse impulse response and Gaussian residuals. Fit unloaded
using s1042/43/45, hold out s1044; fit loaded s1045 t<400, hold out t>=400.
These are retrospective development splits, never independent confirmation.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.optimize import nnls


def interpolate(row, times):
    values=np.asarray(row['curve'])
    return np.array([np.interp(times,row['times'],values[:,j]) for j in range(3)]).T


def training(row):
    return row['t']<400 if row['loaded'] else row['seed']!=1044


def fit(rows):
    profiles={};heldout={}
    for key in sorted({r['key'] for r in rows}):
        group=[r for r in rows if r['key']==key and training(r)]
        if not group:continue
        duration=group[0]['duration_s']
        # All saved coarse cycles contain >=100 ms coast; fine >=140 ms.
        coast=.10 if duration>=.10 else .14
        ts=np.round(np.linspace(0,duration+coast,round((duration+coast)/.01)+1),8)
        curves=np.array([interpolate(r,ts) for r in group])
        mean=curves.mean(0);residual=curves[:,-1]-mean[-1]
        var=(residual**2).mean(0)
        profiles[key]=dict(loaded=group[0]['loaded'],axis=group[0]['axis'],u=group[0]['u'],
            duration_s=duration,settle_s=coast,times=ts.tolist(),mean_curve=mean.tolist(),
            mean_delta=mean[-1].tolist(),residual_variance=var.tolist(),n=len(group),
            source_seeds=sorted({r['seed'] for r in group}),transfer=None)
        test=[r for r in rows if r['key']==key and not training(r)]
        if test:
            err=np.array([interpolate(r,[ts[-1]])[0]-mean[-1] for r in test])
            heldout[key]=dict(n=len(test),mean_error=err.mean(0).tolist(),
                rmse=np.sqrt((err**2).mean(0)).tolist(),max_abs=np.max(abs(err),axis=0).tolist())
    # Missing states are explicitly transferred, never presented as measured.
    # Minimum 35-speed fine strafe was recorded unloaded only. Apply each
    # output's loaded/unloaded *coarse strafe* ratio; retain a large floor.
    for sign in (-1,1):
        key=f'1:left:{sign*.35:.2f}:0.06';source=f'0:left:{sign*.35:.2f}:0.06'
        profile=copy.deepcopy(profiles[source])
        a=np.array(profiles[f'0:left:{sign*.65:.2f}:0.65']['mean_delta'])
        b=np.array(profiles[f'1:left:{sign*.65:.2f}:0.65']['mean_delta'])
        scale=np.array([1.,b[1]/a[1],b[2]/a[2]])
        profile.update(loaded=True,mean_curve=(np.array(profile['mean_curve'])*scale).tolist(),
            mean_delta=(np.array(profile['mean_delta'])*scale).tolist(),n=0,
            transfer=dict(source=source,scale=scale.tolist(),qualification='UNQUALIFIED loaded fine transfer; fresh DEV only'))
        profile['residual_variance']=(np.maximum(np.array(profile['residual_variance'])*scale**2,[.005**2,.005**2,np.deg2rad(1.)**2])).tolist()
        profiles[key]=profile
    # Reverse straight pulses are absent from TRAINING, not necessarily from
    # saved evidence. Keep the split: mirror positive and score reverse holdout.
    for key,source in [('0:forward:-0.35:0.06','0:forward:0.35:0.06'),
                       ('0:forward:-0.35:0.10','0:forward:0.35:0.10'),
                       ('1:forward:-0.35:0.10','1:forward:0.35:0.10')]:
        if key in profiles:continue
        profile=copy.deepcopy(profiles[source])
        profile.update(u=-.35,n=0,mean_curve=(-np.array(profile['mean_curve'])).tolist(),
            mean_delta=(-np.array(profile['mean_delta'])).tolist(),
            transfer=dict(source=source,qualification='UNQUALIFIED sign symmetry; no reverse training rows'))
        profile['residual_variance']=np.maximum(profile['residual_variance'],[.002**2,.002**2,.01**2]).tolist()
        profiles[key]=profile
    for key,p in profiles.items():
        test=[r for r in rows if r['key']==key and not training(r)]
        if test:
            err=np.array([interpolate(r,[p['times'][-1]])[0]-p['mean_delta'] for r in test])
            heldout[key]=dict(n=len(test),mean_error=err.mean(0).tolist(),
                rmse=np.sqrt((err**2).mean(0)).tolist(),max_abs=np.max(abs(err),axis=0).tolist())
    # Thrun-style nonnegative squared-motion noise coefficients, generalized
    # to holonomic body dx/dy/dyaw. This is not the differential-drive formula.
    alpha={}
    for loaded in (False,True):
        observed=[r for r in rows if r['loaded']==loaded and training(r)]
        x=[];y=[]
        for row in observed:
            p=profiles[row['key']];d=np.array(p['mean_delta'])
            x.append([d[0]**2+d[1]**2,d[2]**2])
            y.append((interpolate(row,[p['times'][-1]])[0]-d)**2)
        alpha[str(int(loaded))]=np.array([nnls(np.array(x),np.array(y)[:,j])[0] for j in range(3)]).tolist()
        for p in profiles.values():
            if p['loaded']!=loaded:continue
            d=np.array(p['mean_delta']);v=np.array(alpha[str(int(loaded))])@np.array([d[:2]@d[:2],d[2]**2])
            p['prediction_variance']=np.maximum.reduce([v,np.array(p['residual_variance']),np.array([.0005**2,.0005**2,.001**2])]).tolist()
    return dict(id='s2-v7-pulse-cal-v1',option='v7_pulse_cal_v1',profiles=profiles,
        noise_alpha_xy_yaw_by_trans2_rot2=alpha,train_rule='unloaded seed!=1044; loaded s1045 t<400s',
        holdout_rule='unloaded s1044; loaded s1045 t>=400s; retrospective only',
        heldout=heldout,qualified=False,
        runtime_inputs='own issued commands, elapsed time, own commanded-grasp state only; no live eval',
        method='batch least-squares response curves; Gaussian MLE per-primitive residual variance; NNLS holonomic squared-motion variance; conservative max with per-primitive variance and floors',
        measurement_limit='20Hz trajectory, 10ms interpolation grid is not 100Hz evidence; coast after 100/140ms not independently identified',
        navigation=dict(position_tolerance_m=.03,waypoint_tolerance_m=.035,yaw_tolerance_rad=.06,
            post_stop_fresh_pose=True,short_lateral_speed=.35,short_lateral_duration_s=.06,
            coarse_lateral_speed=.65,coarse_lateral_duration_s=.65,
            forward_speed=.35,forward_duration_s=.10,turn_speed=.35,turn_duration_s=.10))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();rows=[json.loads(s) for s in a.input.read_text().splitlines()]
    result=fit(rows);result['input']=dict(path=str(a.input),sha256=hashlib.sha256(a.input.read_bytes()).hexdigest())
    with a.output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(profiles=len(result['profiles']),heldout=result['heldout'],alpha=result['noise_alpha_xy_yaw_by_trans2_rot2']),indent=2))


if __name__=='__main__':main()
