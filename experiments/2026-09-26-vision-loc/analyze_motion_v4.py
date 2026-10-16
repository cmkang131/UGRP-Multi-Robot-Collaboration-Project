#!/usr/bin/env python3
"""DEV teacher motion residual decomposition, independent of PF scoring."""
import json
from pathlib import Path

import numpy as np

import diagnose_v4 as d
import vision_loc_io as vio


def summary(pred, truth, dt):
    if not len(pred): return {'n':0}
    error = pred-truth
    return {'n':len(pred), 'duration_s':float(dt.sum()),
            'mean_velocity_error':np.mean(error, axis=0).tolist(),
            'abs_velocity_error_p90':np.percentile(np.abs(error),90,axis=0).tolist(),
            'body_displacement_error_sum_m_m_rad':np.sum(error*dt[:,None],axis=0).tolist(),
            'target_mean_abs_velocity':np.mean(np.abs(truth),axis=0).tolist()}


def wheel_phases(commands, times):
    ci, cmd, expiry, before, last_change = 0, np.zeros(3), -1., False, -1e9
    names, active = [], []
    for t in times:
        while ci < len(commands) and commands[ci]['t'] <= t:
            row=commands[ci]; ci+=1
            if row['kind'] in ('mecanum','drive'):
                cmd=np.array([row['forward'],row.get('left',0.),row['turn']]); expiry=row['t']+row['duration_s']
            elif row['kind'] not in ('arm','look','initial_servo_command'):
                cmd=np.zeros(3); expiry=-1.
        on=bool(np.any(cmd)) and t < expiry
        if on != before: last_change=t; before=on
        names.append(('start' if on else 'stop') if t-last_change < 1. else ('steady' if on else 'rest'))
        active.append(on)
    return np.array(names), np.array(active)


def main():
    plan=vio.load_json(d.PLAN)
    fitted=vio.load_json(d.OUT/'motion_fit_final.json')
    original,_=d.vl.mp.load_m1_calibration()
    eps=plan['fit_episodes']+plan['validation_episodes']; d.require_dev(eps)
    report={'episodes':{},'scope':'offline teacher displacement targets; these errors are not PF pose errors',
            'units':['m/s','m/s','rad/s'],'plan_sha256':vio.sha_file(d.PLAN)}
    for ep in eps:
        row=d.targets(ep); mid=.5*(row['t'][1:]+row['t'][:-1]); dt=np.diff(row['t'])
        phases,active=wheel_phases(row['commands'],mid)
        moving=(np.linalg.norm(row['body'][:,:2],axis=1)>.005)|(np.abs(row['body'][:,2])>.02)
        rep={}
        for state,loaded,key in (('unloaded',False,'motion'),('loaded',True,'motion_loaded')):
            mask=np.array([s==(loaded,None) for s in row['states']]) & (row['age']>1.5)
            by_model={}
            for name,params,delay in (('M1',original['params'],0.),('dev_fit',fitted['params'],fitted['motion_v4']['delay_s'][state])):
                mp=params[key]
                pred=d.command_response(row['t'],row['commands'],mp['gain'],mp['tau_s'],mp.get('tau_stop_s',mp['tau_s']),delay)
                groups={'all':mask,'moving':mask&moving,'commanded_stationary':mask&active&~moving}
                groups.update({phase:mask&(phases==phase) for phase in ('start','stop','steady','rest')})
                by_model[name]={g:summary(pred[m],row['body'][m],dt[m]) for g,m in groups.items()}
            rep[state]=by_model
        wheels=[c for c in row['commands'] if c['kind'] not in ('arm','look','initial_servo_command')]
        opportunities=sum(c['kind'] in ('drive','mecanum') and c['t']+c['duration_s'] < n['t']-1e-9
                          for c,n in zip(wheels,wheels[1:]))
        report['episodes'][ep]={'split':'fit' if ep in plan['fit_episodes'] else 'validation',
                              'wheel_events':len(wheels),'expiry_before_next_command':opportunities,'states':rep}
    d.save(d.OUT/'motion_residuals.json',report)
    for state in ('unloaded','loaded'):
        for split in ('fit','validation'):
            for model in ('M1','dev_fit'):
                groups=[e['states'][state][model]['moving'] for e in report['episodes'].values() if e['split']==split]
                groups=[g for g in groups if g['n']]
                print(state,split,model,'episode_mean_error',np.mean([g['mean_velocity_error'] for g in groups],axis=0).tolist())


if __name__=='__main__': main()
