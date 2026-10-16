"""Opt-in shared carry plan from leader's own static-floor RGB registration.

The local bus carries a command plan and pixel provenance, not images, PF truth,
contacts or simulator coordinates. The existing mutual GO remains mandatory.
"""
import copy
import math
import numpy as np
from harness import zone_s3_checkpoint_visual as visual
from harness.zone_solo_cyan_pulse_cal import profile_key
from harness.zone_s3_integer_carry import PulseWindows, tick, ZERO
from harness.zone_pair_executor import carry_role_sign


def finite_profile(base, duration, u, motion):
    """Fixed first-order pulse/stop model; explicit duration transfer, not new fit."""
    p=copy.deepcopy(base);tau=motion['tau_axis_s'][1];stop=motion['tau_stop_s']
    def area(t,d):
        b=min(t,d);a=b-tau*(1-math.exp(-b/tau))
        if t>d:a+=(1-math.exp(-d/tau))*stop*(1-math.exp(-(t-d)/stop))
        return a
    denom=area(base['times'][-1],base['duration_s'])
    times=np.arange(0,duration+.55,.05)
    curve=np.array([np.asarray(base['mean_delta'])*(u/base['u'])*area(float(t),duration)/denom for t in times])
    p.update(u=u,duration_s=duration,times=times.tolist(),mean_curve=curve.tolist(),mean_delta=curve[-1].tolist(),
        prediction_variance=(np.asarray(base['prediction_variance'])+np.array([.005**2,.005**2,.01**2])).tolist(),
        transfer='fixed v7 first-order duration/stop transfer; physical response unverified until this batch')
    p.pop('prediction_covariance',None)
    return p


def corrective_schedule(ctl,now,center,profiles,motion):
    goal=np.asarray(ctl.v3_plan['route'][ctl.seg+1]);delta=goal-np.asarray(center)
    nominal=np.asarray(ctl.v3_plan['route'][ctl.seg+1])-ctl.v3_plan['route'][ctl.seg]
    if np.linalg.norm(delta-nominal)>.08:return None
    sign=carry_role_sign(ctl.rid);schedule=[];durations=[];receipt=[];start=tick(now+.2)
    # Planned leg first; remaining coordinate second. One axis at a time.
    primary=1 if abs(nominal[1])>1e-8 else 0
    for i in (primary,1-primary):
        axis=('forward','left')[i];wanted=float(delta[i]);remaining=abs(wanted)
        if remaining<.006:continue
        direction=math.copysign(1.,wanted)*sign
        pool=[p for p in profiles.values() if p['loaded'] and p['axis']==axis
            and p['u']*direction>0 and p['duration_s']>=.1]
        if axis=='left':
            original=next(p for p in pool if abs(p['u'])==.65 and p['duration_s']==.65)
            for u in (.35,.65):
                for n in range(2,17):
                    duration=round(n*.05,2)
                    action=dict(forward=0.,left=direction*u,turn=0.,duration_s=duration)
                    key=profile_key(action,True)
                    if key not in profiles:profiles[key]=finite_profile(original,duration,direction*u,motion)
            pool=[p for p in profiles.values() if p['loaded'] and p['axis']==axis
                and p['u']*direction>0 and p['duration_s']>=.1]
        # Closest finite response that improves error, never a sub-contract tick.
        for _ in range(30):
            p=min(pool,key=lambda p:abs(remaining-abs(p['mean_delta'][i])))
            step=abs(p['mean_delta'][i])
            if abs(remaining-step)>=remaining-1e-9:break
            cmd=dict(ZERO);cmd[axis]=p['u'];d=float(p['duration_s'])
            n=max(2,tick(d));schedule.append((start/20,(start+n)/20,cmd));durations.append(d)
            receipt.append(dict(axis=axis,u=p['u'],duration_s=d,predicted_m=step,transfer=p['transfer']))
            # Direction reversal after overshoot is prohibited; residual logged.
            remaining-=step
            start+=n+max(2,tick(.20))
            if remaining<=.006:break
    if not schedule:return None
    schedule.append((start/20,(start+2)/20,dict(ZERO)));durations.append(.1)
    return schedule,durations,dict(center_m=list(center),goal_m=goal.tolist(),delta_m=delta.tolist(),pulses=receipt)


def attach(ep,enabled=False,*,bus=None,motion=None):
    if not enabled:return ep
    if bus is None or motion is None:raise ValueError('explicit command bus and fixed calibration required')
    ctl=ep.controller;own=ep.own.pose.localizer;reference=None;audit=[]
    ctl.s3_checkpoint_correction=dict(audit=audit,runtime_gt=False,leader='r1',input='own RGB floor registration; no PF pose')
    old_log=ctl.log
    def log(rid,event,now,**detail):
        nonlocal reference
        if rid==ctl.rid and event=='coarse_fine_aligned' and rid=='r1':
            ref=ctl.s3_pregrasp_reference;obs=ep.own.last_obs
            beam=ref['beam']
            try:
                current=visual.snapshot(obs,dict(ep.own.servo),ep.vision.calibration,beam)
                if ctl.seg==0:
                    reference=current
                    audit.append(dict(t=now,seg=0,phase='initial_own_rgb_reference',frame_id=obs['frame_id'],sha256=obs['sha256'],features=len(current['points'])))
                elif reference is not None:
                    displacement,fit=visual.register(reference,current)
                    if displacement is not None:
                        center=np.asarray(ctl.v3_plan['route'][0])+displacement
                        correction=center-np.asarray(ctl.v3_plan['route'][ctl.seg])
                        if np.linalg.norm(correction)<=visual.PARAMS['max_correction_m']:
                            bus[ctl.seg]=dict(center_m=center.tolist(),fit=fit,source='r1 own RGB static floor; explicit shared command plan')
                        else:fit.update(accepted=False,reason='bounded_visual_correction',correction_m=correction.tolist())
                    audit.append(dict(t=now,seg=ctl.seg,phase='visual_registration',**fit))
            except (ValueError,KeyError,cv_error()) as exc:
                audit.append(dict(t=now,seg=ctl.seg,phase='registration_unavailable',reason=type(exc).__name__+': '+str(exc)))
        return old_log(rid,event,now,**detail)
    ctl.log=log
    old_schedule,old_carry=ctl.door_schedule,ctl._carry
    def schedule(now):
        message=bus.get(ctl.seg)
        if message:
            value=corrective_schedule(ctl,now,message['center_m'],own.pulse_profiles,motion)
            if value is not None:
                windows,durations,receipt=value
                ctl.s3_corrective_durations=durations
                ctl.s3_integer_windows=PulseWindows(windows)
                ctl.log(ctl.rid,'checkpoint_carry_command_plan',now,seg=ctl.seg,**receipt,provenance=message,gt_inputs=False)
                audit.append(dict(t=now,seg=ctl.seg,phase='shared_command_plan',**receipt,source=message['source']))
                return windows
        ctl.s3_corrective_durations=None
        return old_schedule(now)
    def carry(now,idle):
        durations=getattr(ctl,'s3_corrective_durations',None)
        if durations is not None:
            n=tick(now)
            for i,(a,b,_) in enumerate(ctl.s3_integer_windows.windows):
                if a<=n<b and i not in ctl.s3_integer_windows.issued:
                    ctl.s3_carry_pulse_s=durations[i];break
        return old_carry(now,idle)
    ctl.door_schedule,ctl._carry=schedule,carry
    return ep


def cv_error():
    import cv2
    return cv2.error
