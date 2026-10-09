"""Unloaded own-RGB pair alignment using the shared heading pulse vocabulary."""
import copy
import math
from types import MethodType, SimpleNamespace
import numpy as np

from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_path_heading import select
from harness.zone_solo_cyan_pulse_cal import action_of, profile_key
from harness.zone_s3_pair_heading import moving, validate_pulse
from harness.zone_final_pair_vision import ALIGN_TOL_X_M, ALIGN_TOL_Y_M


def project(profiles, errors):
    ex,ey,ea=map(float,errors)
    distance=math.hypot(ex,ey)
    p,score=select(profiles,False,np.array([ex,ey]),-ea,distance,
        position_tolerance_m=min(ALIGN_TOL_X_M,ALIGN_TOL_Y_M))
    action=(dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=.1)
        if p is None else action_of(p))
    validate_pulse(action,profiles,loaded=False,goal_distance=distance,alignment=True)
    return action,p,score


def attach(ep):
    ctl=ep.controller;own=ep.own.pose.localizer;profiles=own.pulse_profiles
    original_align=ctl._align.__func__
    previous_ob=original_align.__globals__['ob']
    raw_align=previous_ob.align_command
    until=None;settled=-math.inf;decisions=[]
    def align(beam):
        raw=raw_align(beam)
        if raw is None:
            return None  # only the original RGB tolerances declare aligned
        errors=previous_ob.align_errors(beam)
        action,p,score=project(profiles,errors)
        decisions.append(dict(t=ep.own.now,state='align',errors=list(errors),
            original=raw,issued=action,**score))
        return dict(forward=action['forward'],left=action['left'],turn=action['turn'],duration=action['duration_s'])
    ob=SimpleNamespace(**{**vars(previous_ob),'align_command':align})
    ctl._align=MethodType(bind(original_align,ob=ob),ctl)
    old_apply=ep.port.apply
    def apply(action,now):
        nonlocal until,settled
        if not moving(action) or ctl.state=='approach':
            return old_apply(action,now)
        pf=own.pose.provider.loc._pf
        if pf.load.loaded:
            from harness.zone_s3_coupled_motion import authorized
            if not authorized(ep, now):
                raise ValueError('coupled motion requires own grasp and live pair carry GO')
            return old_apply(action,now)  # preserve the approved paired schedule bytes
        if action.get('left',0.):
            proof=decisions[-1] if decisions else {}
            if (proof.get('state')!='align' or abs(proof.get('t',-math.inf)-now)>1e-8
                    or proof.get('issued')!=action or proof.get('goal_distance_m',math.inf)>.10):
                raise ValueError('lateral proposal lacks final own-RGB alignment proof')
        try:
            key=profile_key(action,False)
        except ValueError:
            raise ValueError('unhandled unloaded pair mixture before actuator issue') from None
        if key not in profiles:
            # Existing no-view search and checkpoint backoff are pure turn or
            # longitudinal proposals. Never turn an unobserved lateral proposal
            # into an admissible final-alignment command.
            axis=next(k for k in ('forward','left','turn') if action.get(k,0.))
            if axis=='left':
                raise ValueError('lateral proposal lacks final own-RGB alignment proof')
            pool=[p for p in profiles.values() if not p['loaded'] and p['axis']==axis
                and p['duration_s']==.1 and p['u']*action[axis]>0 and abs(p['u'])<=.35]
            if not pool:
                raise ValueError('no calibrated unloaded recovery pulse')
            p=min(pool,key=lambda p:abs(p['u']))
            replacement=action_of(p)
            decisions.append(dict(t=now,state=ctl.state,original=copy.deepcopy(action),issued=replacement,
                phase='unloaded_search_or_backoff',goal_distance_m=None))
            action=replacement
        else:
            p=profiles[key]
        until=now+p['duration_s'];settled=now+p['times'][-1]
        return old_apply(action,now)
    ep.port.apply=apply
    old_tick=ctl.tick
    def tick(now):
        nonlocal until
        # Endpoint heartbeat/GO/abort checks live outside this controller tick.
        if ctl.state!='approach':
            if until is not None:
                if now<until-1e-8:
                    return
                until=None;ep.port.hold(now)
                return
            if now<settled-1e-8 or own.last_report.t_est<settled-1e-8:
                return
        return old_tick(now)
    ctl.tick=tick
    ep.s3_alignment_audit=decisions
    return ep
