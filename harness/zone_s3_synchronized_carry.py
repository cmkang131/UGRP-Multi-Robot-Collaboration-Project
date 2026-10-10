"""Opt-in command-space virtual-leader pulse train; no simulator input.

Both endpoints derive one identical clock from consumed carry GO and the static
leg. Opposed body signs give the same object translation. No loaded individual
pose correction, heading turn or force/GT feedback is introduced.
"""
import copy
import math
import numpy as np
from harness import zone_s3_coarse_fine as cf
from harness.zone_pair_executor import carry_role_sign

OPTION='synchronized_pulses_v1'
PLAN_OPTION='joint_pan_v1'
PARAMS=dict(pulse_source='configs/s2_v133_full_template.json loaded pulse calibration',
    axial_u=.35,axial_s=.10,axial_period_s=.20,lateral_u=.65,lateral_s=.65,
    lateral_period_s=.80,leader='static object route; same consumed two-party GO',
    go_ack_settle_s=.20,goal_tolerance_m=.02,runtime_gt=False,force_feedback=False,heading_turns=False)


def joint_plan(grip,heading,rid):
    """Enumerate discrete pan under the SAME simultaneous acceptance bounds.

    A feasible candidate takes priority over minimising one residual to zero.
    The centre-only legacy plan is retained for cyan and when no feasible pan
    exists; coarse decisions can still improve the full envelope.
    """
    old=cf.plan(grip,heading,rid)
    if rid=='r3' or old['ready']:return old
    x,y=grip;tol=old['halfwidths'];good=[]
    for pan in range(cf.PARAMS['pan_pwm_min'],cf.PARAMS['pan_pwm_max']+1,4):
        a=cf.angle(pan);c,s=math.cos(a),math.sin(a)
        errors=[c*(x-cf.arm.MOUNT_X_M)+s*y-old['radius_m'],
                -s*(x-cf.arm.MOUNT_X_M)+c*y-cf.PARAMS['dy_center_m'],
                math.atan2(math.sin(heading-a),math.cos(heading-a))]
        if not all(abs(e)<=t for e,t in zip(errors,tol)):continue
        q={**old,'pan':pan,'errors':errors,'ready':True}
        try:cf.postures(q)
        except ValueError:continue
        good.append((max(abs(e)/t for e,t in zip(errors,tol)),abs(pan-old['pan']),pan,q))
    return min(good,key=lambda x:x[:3])[-1] if good else old


def pulse_schedule(ctl,t0,profiles):
    a,b=ctl.v3_plan['route'][ctl.seg:ctl.seg+2]
    delta=np.asarray(b,float)-a;distance=float(np.linalg.norm(delta))
    if distance<=0 or abs(delta[0])>1e-8 and abs(delta[1])>1e-8:
        raise ValueError('registered cardinal carry leg required')
    axis='left' if abs(delta[1])>1e-8 else 'forward'
    sign=carry_role_sign(ctl.rid)*math.copysign(1.,delta[1 if axis=='left' else 0])
    u,duration,period=(.65,.65,.80) if axis=='left' else (.35,.10,.20)
    choices=[p for p in profiles.values() if p['loaded'] and p['axis']==axis
             and p['u']==sign*u and p['duration_s']==duration]
    if len(choices)!=1:raise ValueError('missing calibrated coupled pulse')
    p=choices[0];step=abs(p['mean_delta'][1 if axis=='left' else 0])
    if not math.isfinite(step) or step<=0:raise ValueError('invalid registered response')
    # Mirrored profiles may have slight lateral asymmetry; both endpoints use
    # the smaller calibrated magnitude so count/clock are EXACTLY the same.
    steps=[abs(v['mean_delta'][1 if axis=='left' else 0]) for v in profiles.values()
           if v['loaded'] and v['axis']==axis and abs(v['u'])==u and v['duration_s']==duration]
    step=min(steps);count=math.ceil(distance/step)
    command=dict(forward=0.,left=0.,turn=0.);command[axis]=sign*u
    start=t0+PARAMS['go_ack_settle_s']
    schedule=[(start+i*period,start+i*period+duration,dict(command)) for i in range(count)]
    # Final settle is a zero interval; the old carry monitor/barrier remains.
    schedule.append((start+count*period,start+count*period+.1,dict(forward=0.,left=0.,turn=0.)))
    ctl.claims.setdefault('segments',[]).append(dict(seg=ctl.seg,axis=axis,distance_m=distance,
        static_from_xy=list(a),static_to_xy=list(b),cmd=command,pulses=count,
        calibrated_step_m=step,nominal_distance_m=count*step,option=OPTION))
    ctl.log(ctl.rid,'synchronized_carry_plan',t0,seg=ctl.seg,cmd=command,duration_s=duration,
        period_s=period,pulses=count,distance_m=distance,calibrated_step_m=step,
        common_clock='consumed carry GO + two control ticks for carry heartbeat',go_ack_settle_s=PARAMS['go_ack_settle_s'],runtime_gt=False)
    return schedule,duration


def attach(ep,option='off'):
    if option=='off':return ep
    if option!=OPTION:raise ValueError('unknown synchronized carry option')
    ctl=ep.controller;profiles=ep.own.pose.localizer.pulse_profiles
    apply=ctl.port.apply
    def schedule(t0):
        value,ctl.s3_carry_pulse_s=pulse_schedule(ctl,t0,profiles)
        return value
    def issue(action,now):
        if ctl.state=='carry' and action.get('kind')=='mecanum' and any(action.get(k,0.) for k in ('forward','left','turn')):
            action={**action,'duration_s':ctl.s3_carry_pulse_s}
        return apply(action,now)
    ctl.door_schedule=schedule;ctl.port.apply=issue
    ctl.s3_synchronized_carry=dict(option=option,params=copy.deepcopy(PARAMS))
    return ep
