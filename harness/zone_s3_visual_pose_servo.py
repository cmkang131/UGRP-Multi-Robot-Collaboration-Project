"""Opt-in finite-pulse position-based visual servo; original RGB verdict retained.

PBVS target coordinates transform with the FULL rigid body motion, including
rotation of the station lever arm. Enumerate bounded existing command sequences
and issue the first pulse, then observe again (finite-horizon receding control).
No new motor primitive, likelihood, success threshold, or ground truth input.
"""
import itertools
import math
from types import SimpleNamespace,MethodType
import numpy as np
from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_vision import GRASP_RADIUS_M,ALIGN_TOL_X_M,ALIGN_TOL_Y_M
from harness.owncam_pair_beam import ALIGN_TOL_RAD
from harness.zone_s3_pair_alignment import project as previous
from harness.zone_solo_cyan_path_heading import command_reason
from harness.zone_solo_cyan_pulse_cal import action_of

OPTION='visual_pose_mpc_v1'
HORIZON=6

def transform(grip, angle, motion):
    x,y=np.asarray(grip)-np.asarray(motion[:2]);c,s=math.cos(motion[2]),math.sin(motion[2])
    return np.array([c*x+s*y,-s*x+c*y]),math.atan2(math.sin(angle-motion[2]),math.cos(angle-motion[2]))

class Selector:
    def __init__(self,profiles,*,angle_required=True):
        self.angle_required=angle_required
        self.profiles=profiles
        self.pool=[p for p in profiles.values() if not p['loaded'] and p['axis'] in ('forward','turn')
            and p['duration_s']==.1 and command_reason(action_of(p)) is None]
        if len(self.pool)!=4:raise ValueError('requires existing forward/backward and left/right turn .10s profiles')
        poses=[];first=[];lengths=[]
        for n in range(1,HORIZON+1):
            for seq in itertools.product(range(4),repeat=n):
                q=np.zeros(3)
                for j in seq:
                    d=self.pool[j]['mean_delta'];c,s=math.cos(q[2]),math.sin(q[2])
                    q+=np.array([c*d[0]-s*d[1],s*d[0]+c*d[1],d[2]])
                poses.append(q);first.append(seq[0]);lengths.append(n)
        self.poses=np.array(poses);self.first=np.array(first);self.lengths=np.array(lengths)
    def __call__(self,profiles,errors):
        ex,ey,ea=map(float,errors);distance=math.hypot(ex,ey)
        if distance>.10:return previous(profiles,errors)
        if not all(math.isfinite(v) for v in errors):raise ValueError('finite own RGB fit required')
        q=self.poses;dx,dy=(GRASP_RADIUS_M+ex)-q[:,0],ey-q[:,1];c,s=np.cos(q[:,2]),np.sin(q[:,2])
        terminal=np.column_stack((c*dx+s*dy-GRASP_RADIUS_M,-s*dx+c*dy,np.arctan2(np.sin(ea-q[:,2]),np.cos(ea-q[:,2]))))
        scale=np.array([ALIGN_TOL_X_M,ALIGN_TOL_Y_M,ALIGN_TOL_RAD])
        def cost(e):
            value=np.maximum(np.abs(e)/scale-1.,0.)**2
            if not self.angle_required:value[...,2]=0.
            return np.sum(value,axis=-1)
        before=float(cost(np.array(errors)));costs=cost(terminal)+.01*self.lengths
        best=int(np.argmin(costs));p=self.pool[self.first[best]] if costs[best]<before else None
        action=dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=.1) if p is None else action_of(p)
        return action,p,dict(phase='visual_pose_mpc',goal_distance_m=distance,before=before,after=float(costs[best]),
            horizon=HORIZON,selected_length=int(self.lengths[best]),terminal_errors=terminal[best].tolist(),
            error_source='own RGB fit',thresholds_changed=False)

def attach_endpoint(ep,option='off'):
    if option=='off':return ep
    if option!=OPTION:raise ValueError('unknown visual servo option')
    ctl=ep.controller;old=ctl._align.__func__;ob=old.__globals__['ob']
    # Existing instance wrapper retains its audit, settle clock and apply proof.
    selector=Selector(ep.own.pose.localizer.pulse_profiles)
    replacement=bind(ob.align_command,project=selector)
    private=SimpleNamespace(**{**vars(ob),'align_command':replacement})
    ctl._align=MethodType(bind(old,ob=private),ctl)
    ctl.s3_visual_pose_servo=OPTION
    return ep

def attach_solo(own,option='off'):
    if option=='off':return own
    if option!=OPTION:raise ValueError('unknown visual servo option')
    selector=Selector(own.pulse_profiles,angle_required=False);step=own.step;record=own.record;audit=[]
    def selected(now):
        rows=step(now)
        if own.state!='align' or own.target is None:return rows
        # Only a NEW RGB-based motion proposal invokes the replacement. Arm
        # waits, repeated frames, aligned receipts, and hidden views remain holds.
        if not own.fine_rows or own.fine_rows[-1]['t']!=now:return rows
        errors=[own.target[0]-GRASP_RADIUS_M,own.target[1],0.]
        action,p,score=selector(own.pulse_profiles,errors)
        if math.hypot(*errors[:2])>.10:return rows
        own.fine_until=None
        if p is not None:
            own.heading_align_until=now+p['duration_s'];own.heading_align_settled=now+p['times'][-1]
            own.fine_observe_after=own.heading_align_settled
        audit.append(dict(t=now,frame_id=own.last_obs['frame_id'],errors=errors,issued=action,**score))
        return [(rid,action if row['kind'] in ('mecanum','drive','hold') else row) for rid,row in rows]
    own.step=selected
    own.record=lambda:{**record(),'visual_pose_servo':dict(option=option,decisions=audit)}
    return own
