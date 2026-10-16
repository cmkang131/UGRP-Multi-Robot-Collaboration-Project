"""Nav2 SimpleGoalChecker stateful XY latch + rotate-to-goal-heading.

Installed only inside look_before_move's opt-in branch. Existing S2 XY
tolerance and .06 rad yaw tolerance, fixed measured turn pulses, no GT input.
"""
import copy
import math
from harness.zone_solo_cyan_pulse_cal import action_of,profile_key

YAW_TOLERANCE=.06

def install(runtime,audit):
    previous=runtime.drive
    state=dict(goal=None,phase='position',xy_tolerance_m=.03,yaw_tolerance_rad=YAW_TOLERANCE,rows=[])
    runtime.goal_heading=state;audit['goal_heading']=state

    def drive(xy,now,*,tolerance=.03):
        token=(runtime.state,*map(float,xy))
        if state['goal']!=token:
            state.update(goal=token,phase='position',xy_tolerance_m=tolerance)
        r=runtime.last_report
        distance=math.dist((r.x_m,r.y_m),xy)
        yaw=math.atan2(math.sin(r.yaw_rad),math.cos(r.yaw_rad))
        if state['phase']=='position':
            if not r.initialized or distance>tolerance:
                return previous(xy,now,tolerance=tolerance)
            state['phase']='heading'
            state['rows'].append(dict(t=now,event='xy_latched',state=runtime.state,
                goal=list(xy),distance_m=distance,xy_tolerance_m=tolerance,yaw_rad=yaw))
        # Nav2 stateful: never re-enter XY checking for this goal while rotating.
        if abs(yaw)<=YAW_TOLERANCE:
            if state['phase']!='reached':
                state['rows'].append(dict(t=now,event='goal_reached',state=runtime.state,
                    distance_m=distance,yaw_rad=yaw,xy_rechecked=False))
            state['phase']='reached';runtime.path=[];runtime.path_goal=None
            return [dict(kind='hold')],True
        if r.std_xy_m>.05 or r.std_yaw_rad>math.radians(5) or r.last_fix_t is None:
            runtime.soft('POSE_UNCERTAIN',now)
        loaded=runtime.pose.provider.loc._pf.load.loaded
        pool=[p for p in runtime.pulse_profiles.values() if p['axis']=='turn' and
              p['loaded']==loaded and p['duration_s']==.10]
        residual=lambda p:math.atan2(math.sin(yaw+p['mean_delta'][2]),math.cos(yaw+p['mean_delta'][2]))
        # Goal-heading stage optimizes yaw only; penalizing tiny translational
        # drift here would veto a needed turn just outside yaw tolerance.
        p=min(pool,key=lambda p:abs(residual(p))) if pool else None
        if p is not None and abs(residual(p))>=abs(yaw):p=None
        if p is None:
            runtime.soft('PULSE_RESOLUTION_LIMIT',now)
            return [dict(kind='hold')],False
        action=action_of(p)
        score=dict(before=yaw*yaw,after=residual(p)**2,yaw_rad=yaw,objective='final_yaw_only')
        runtime.cal_rows.append(dict(t=now,state=runtime.state,waypoint=list(xy),issued=action,
            profile_key=profile_key(action,loaded),predicted_delta=p['mean_delta'],
            prediction_variance=p['prediction_variance'],transfer=p['transfer'],score=score,
            goal_heading_only=True))
        state['rows'].append(dict(t=now,event='rotate',state=runtime.state,distance_m=distance,
            yaw_rad=yaw,xy_rechecked=False,action=copy.deepcopy(action)))
        return [action],False

    runtime.drive=drive
