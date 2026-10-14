"""Opt-in own-RGB object memory, gaze and bounded return/coverage skills.

Object detection and all tracking are code. Gemma chooses a offered SKILL only.
Memory is never a grasp observation. No peer/physics/evaluator state is read.
"""
import copy
import math
import numpy as np
from harness.active_wall_mapping import compose, inverse, wrap
from harness.self_odom_grid import transform

OPTIONS=('view_return_v1','object_return_v1')
PARAMS=dict(memory_s=300.,lost_after_s=2.,return_cap_s=20.,scan_view_s=2.4,
            pan_limit_deg=60.,gaze_deadband_deg=8.,gaze_period_s=1.2,
            stand_off_m=.65,decision_period_s=20.,no_progress_choices=3)
SYSTEM='''You select a robot SKILL, not image recognition, beam coordinates or motor commands.
Code detects and tracks the beam and supplies private own-RGB memory and feasible candidates.
Choose return_memory to revisit the last view then look and sweep, turn_memory to face a target
outside pan range, scan to inspect ordered sectors, explore if remembered routes failed, or
wait briefly. Minimize time to reacquire the beam. Never infer that memory permits grasping.
Use only offered candidates and own information. The image is audit context; do not output
object detections. Return JSON {"choice":"candidate id","message":"","reason":"brief"}.
In no_comm message must be empty. Other channels, if enabled, allow only delivered text;
fixed_signal message is empty, CLAIM, YIELD or WAIT. No shared coordinates are assumed.'''


def enabled(r):return getattr(r,'beam_tracking','off') in OPTIONS


def partial_band_point(r,b):
    """Code-only ray/known-top-plane estimate; never supplies an end pose."""
    patches=b.get('color_components',[])
    if not b.get('band_visible') or len(patches)!=1:return None
    from harness.active_camera import transform as camera_transform
    from harness.owncam_view import _pixel_rays
    from harness.owncam_pair_beam import BEAM_TOP_Z_M
    origin,rotation=camera_transform(r.servo);xs,ys,normal,valid=_pixel_rays(4)
    uv=patches[0]['center_px'];i=int(np.argmin((xs-uv[0])**2+(ys-uv[1])**2))
    direction=np.r_[normal[i],1.]@rotation.T
    if not valid[i] or direction[2]>=-1e-6:return None
    scale=(BEAM_TOP_Z_M-origin[2])/direction[2]
    if scale<=0:return None
    point=origin[:2]+scale*direction[:2]
    return point.tolist() if .08<=np.linalg.norm(point)<=2.5 else None


def observe(r,now):
    if not enabled(r):return
    ob=getattr(r,'beam_observation',None) or {};b=ob.get('result',{});ref=ob.get('rgb',{})
    if not 0<=now-ref.get('t_sim',-math.inf)<=.45:return
    point=(b.get('grip_base_m') or b.get('near_end_base_m')) if b.get('visible') else partial_band_point(r,b)
    if point is None or len(point)!=2 or not np.isfinite(point).all():return
    if (b.get('visible') and b.get('points',0)<25) or not .08<=np.linalg.norm(point)<=2.5:return
    # Broad object-body support is intentionally independent of end/color gates.
    if b.get('lateral_spread_m',0)>.15:return
    pose=np.asarray(r.goal.explorer.local_pose,float)
    target=transform([point],pose)[0]
    old=getattr(r,'beam_memory',None)
    if old and old['rgb']==ref:return
    r.beam_memory=dict(point_own_m=target.tolist(),observer_own_m=pose.tolist(),
        point_map_m=transform([target],r.goal.explorer.map_to_odom)[0].tolist(),
        rgb=copy.deepcopy(ref),seen=now,kind='observed_body_point_not_grasp' if b.get('visible') else 'partial_band_point_not_grasp',
        end_qualified=bool(b.get('end_visible')),source='own_RGB+issued_camera+own_command_odometry')


def memory(r,now):
    m=getattr(r,'beam_memory',None)
    return m if enabled(r) and m and 0<=now-m['seen']<=PARAMS['memory_s'] else None


def gaze_target(tr,rid,now):
    m=memory(tr.robots[rid],now)
    return np.asarray(m['point_own_m']) if m else None


def pan_geometry(r,point):
    from harness.visual_arm import PULSE_PER_DEGREE
    pose=r.goal.explorer.local_pose;d=np.asarray(point)-pose[:2]
    error=math.degrees(wrap(math.atan2(d[1],d[0])-pose[2]))
    clipped=max(-PARAMS['pan_limit_deg'],min(PARAMS['pan_limit_deg'],error))
    return dict(bearing_deg=error,reachable=abs(error)<=PARAMS['pan_limit_deg'],
                target_pwm=round(1500+clipped*PULSE_PER_DEGREE))


def decorate_gaze(tr,now,commands):
    """Bounded pan pursuit also during base turns; never override fine/grasp/scan."""
    if getattr(tr,'beam_tracking','off')=='off' or tr.state not in ('align','mapping'):return commands
    out=list(commands)
    for rid in ('r1','r2'):
        r=tr.robots[rid];m=memory(r,now)
        if not m:continue
        state=tr.beam_search[rid];ap=tr.approach.get(rid,{})
        if ap.get('fine') or state.get('phase')=='scan':continue
        from harness.e2e_pregrasp_acquire import busy
        if busy(tr,rid,now) or now<state.get('next_gaze',-1.):continue
        geom=pan_geometry(r,m['point_own_m']);current=r.servo[6]
        from harness.visual_arm import PULSE_PER_DEGREE
        err=abs(current-geom['target_pwm'])/PULSE_PER_DEGREE
        tr.event(now,'beam_tracking_gaze',robot_id=rid,**geom,current_pwm=current,
                 error_deg=err,memory_rgb=m['rgb'],age_s=now-m['seen'])
        state['next_gaze']=now+PARAMS['gaze_period_s']
        if err<PARAMS['gaze_deadband_deg']:continue
        # Use existing gaze settle barrier; do not concurrently issue body movement.
        out=[(who,a) for who,a in out if who!=rid or a['kind'] not in ('mecanum','drive','hold','look')]
        out.extend([(rid,dict(kind='look',pan_pulse=geom['target_pwm'])),(rid,dict(kind='hold'))])
        ap['gaze_settle_until']=now+.8
    return out


def install(tr,option='off',relay_url=None):
    if option=='off':return
    if option not in OPTIONS:raise ValueError('UNKNOWN_BEAM_TRACKING')
    if relay_url is None:raise ValueError('BEAM_SKILL_GEMMA_RELAY_REQUIRED')
    from harness.e2e_end_model import Client
    tr.beam_tracking=option;tr.beam_search={rid:dict(blocked=set(),failures={},coverage=[]) for rid in ('r1','r2')}
    tr.beam_clients={rid:Client(relay_url) for rid in ('r1','r2')}
    for rid in ('r1','r2'):tr.robots[rid].beam_tracking=option


def path_to(r,point):
    from harness.public_navigation_unknown import from_observed_grid
    ex=r.goal.explorer;tf=ex.map_to_odom;pose=np.asarray(ex.local_pose);mp=compose(tf,pose)
    cm=from_observed_grid(ex.grid,mp,ex.latest,set());goal=transform([point],tf)[0]
    path=ex.navigator.plan_to(cm,mp,goal)
    return cm,mp,path,tf


def candidates(tr,rid,now,state):
    r=tr.robots[rid];pose=np.asarray(r.goal.explorer.local_pose);m=memory(r,now);out=[]
    if m:
        goal=np.asarray(m['observer_own_m'][:2])
        if tr.beam_tracking=='object_return_v1':
            point=np.asarray(m['point_own_m']);delta=goal-point;n=np.linalg.norm(delta)
            if n>.001:goal=point+delta/n*PARAMS['stand_off_m']
        _,_,path,_=path_to(r,goal)
        distance=sum(math.dist(a,b) for a,b in zip(path,path[1:])) if path else None
        if path:out.append(dict(id='return_memory',goal_own_m=goal.tolist(),distance_m=distance,
                                expected_s=distance/.08+8.,description='return then face last object point and sweep'))
        out.append(dict(id='turn_memory',distance_m=0.,expected_s=8.,description='face remembered beam, then sweep'))
    out += [dict(id='scan',distance_m=0.,expected_s=14.4,description='ordered camera sectors, accepted-frame coverage'),
            dict(id='explore',distance_m=None,expected_s=5.,description='existing own-map exploration'),
            dict(id='wait',distance_m=0.,expected_s=2.,description='brief wait')]
    return [c for c in out if c['id'] not in state['blocked']]


def finish(tr,rid,now,state,reason):
    r=tr.robots[rid];start=state.get('start_pose',r.goal.explorer.local_pose);pose=r.goal.explorer.local_pose
    progress=math.dist(start[:2],pose[:2])>.05 or (not state.get('start_visible',True) and bool((r.beam_observation or {}).get('result',{}).get('visible')))
    choice=state.get('choice')
    if choice:
        state['failures'][choice]=0 if progress else state['failures'].get(choice,0)+1
        if state['failures'][choice]>=PARAMS['no_progress_choices']:state['blocked'].add(choice)
    tr.event(now,'beam_tracking_skill_end',robot_id=rid,choice=choice,reason=reason,
             progress=bool(progress),blocked=sorted(state['blocked']),coverage=state['coverage'])
    for key in ('phase','choice','view','view_frame'):state.pop(key,None)


def step(tr,rid,now,approach):
    if getattr(tr,'beam_tracking','off')=='off':return None
    r=tr.robots[rid];state=tr.beam_search[rid];m=memory(r,now);client=tr.beam_clients[rid]
    fresh=r.beam is not None and 0<=now-r.beam['rgb']['t_sim']<=.45
    response=client.poll()
    if response is not None:
        tr.event(now,'beam_tracking_model_receipt',robot_id=rid,response=response)
        if response.get('error')=='END_MODEL_BUDGET_EXHAUSTED':raise RuntimeError('BEAM_MODEL_BUDGET_EXHAUSTED')
        choices={c['id']:c for c in state['offered']};reply=response.get('decision',{})
        valid=(set(reply)=={'choice','message','reason'} and all(isinstance(v,str) for v in reply.values())
               and reply['choice'] in choices and reply['message']=='')
        # Explicit fixed fallback; never silently count provider failure as LLM success.
        choice=reply['choice'] if valid else next((c for c in ('return_memory','turn_memory','scan','explore','wait') if c in choices),None)
        if choice is None:raise RuntimeError('BEAM_NO_PROGRESS_CANDIDATE')
        state.update(choice=choice,selected=choices[choice],phase='return' if choice=='return_memory' else 'turn' if choice=='turn_memory' else choice,
                     started=now,phase_started=now,start_pose=list(r.goal.explorer.local_pose),start_visible=bool((r.beam_observation or {}).get('result',{}).get('visible')),view=-1,coverage=[])
        tr.event(now,'beam_tracking_skill',robot_id=rid,choice=choice,source='judgment_model' if valid else 'fixed_fallback',message=reply.get('message','') if valid else '')
    if fresh:
        state['episode_active']=False
        if state.get('phase'):finish(tr,rid,now,state,'fresh_grasp_observation')
        return None
    if 'station' in approach and now-approach.get('last_seen',-math.inf)<=PARAMS['lost_after_s']:return None
    from harness.e2e_pregrasp_acquire import busy
    if busy(tr,rid,now):return False,[dict(kind='hold')]
    if not state.get('phase') and client.future is None:
        offered=candidates(tr,rid,now,state)
        if not offered:
            raise RuntimeError('BEAM_ALL_SKILLS_EXHAUSTED_AFTER_NO_PROGRESS')
        context=dict(schema='ugrp.beam_tracking_skill.v1',robot_id=rid,condition='no_comm',
            memory=copy.deepcopy(m),own_pose=list(r.goal.explorer.local_pose),candidates=offered,
            delivered_text=[],blocked=sorted(state['blocked']))
        state['offered']=offered;client.start(context,r.frame)
        if not state.get('episode_active'):
            state['episode_active']=True
            tr.event(now,'beam_tracking_reacquire_begin',robot_id=rid)
        tr.event(now,'beam_tracking_model_request',robot_id=rid,context=context,rgb_sha256=r.frame.sha256)
    if client.future is not None:
        r.carrier_approach=dict(t=now,status='beam_skill_pending')
        return False,[dict(kind='hold')]
    phase=state['phase'];r.carrier_approach=dict(t=now,status='beam_'+phase,memory_age_s=now-m['seen'] if m else None)
    pose=np.asarray(r.goal.explorer.local_pose)
    from harness.e2e_rpp_path import command
    if phase in ('return','turn'):
        if m is None:state.update(phase='scan',phase_started=now,view=-1);return False,[dict(kind='hold')]
        point=np.asarray(m['point_own_m']);yaw=math.atan2(*(point-pose[:2])[::-1]);cm=None
        if phase=='return':
            goal=state['selected']['goal_own_m'];cm,mp,path,tf=path_to(r,goal)
            if not path or now-state['phase_started']>PARAMS['return_cap_s'] or math.dist(pose[:2],goal)<.12:
                state.update(phase='turn',phase_started=now);return False,[dict(kind='hold')]
            path=transform(path,inverse(tf)).tolist()
        else:path=[pose[:2].tolist()]
        action,diag=command(dict(coordinate_frame=rid+'/own_odom',path_m=path,status='goal_approach',heading_rad=yaw),pose,tr.profiles,robot_id=rid)
        if phase=='turn' and (action['kind']=='hold' or now-state['phase_started']>=8.):
            state.update(phase='scan',phase_started=now,view=-1);return False,[dict(kind='hold')]
        if cm is not None:
            from harness.public_navigation.follower import projected_clear
            from harness.public_navigation_recovery import issued_twist
            if not projected_clear(cm,mp,issued_twist(action)):
                state.update(phase='scan',phase_started=now,view=-1)
                tr.event(now,'beam_tracking_path_blocked',robot_id=rid,alternative='ordered_scan')
                return False,[dict(kind='hold')]
        return False,[action]
    if phase=='scan':
        views=(('search',1500),('search',1200),('search',1800),('p45',1500),('inspect',1500),('search',1500))
        frame=r.last_obs['frame_id'];index=state.get('view',-1)
        if index>=0 and now-state['phase_started']>=PARAMS['scan_view_s'] and frame!=state.get('view_frame'):
            state['coverage'].append(dict(index=index,frame_id=frame,t=now,servo=dict(r.servo),body_visible=bool((r.beam_observation or {}).get('result',{}).get('visible'))))
            tr.event(now,'beam_tracking_coverage',robot_id=rid,**{k:v for k,v in state['coverage'][-1].items() if k!='t'});index+=1
        elif index<0:index=0
        if index>=len(views):finish(tr,rid,now,state,'ordered_sweep_complete');return False,[dict(kind='hold')]
        if index!=state.get('view'):
            from harness.owncam_pair_beam_v2 import pose_of
            tag,pan=views[index];pwm=pose_of(tag);pwm[6]=pan;tr._poses(rid,now,[(pwm,.3,.6)])
            state.update(view=index,view_frame=frame,phase_started=now)
        return False,[dict(kind='hold')]
    cap=2. if phase=='wait' else 5.
    if now-state['phase_started']>=cap:finish(tr,rid,now,state,'bounded_skill_complete');return False,[dict(kind='hold')]
    return False,[dict(kind='hold') if phase=='wait' else copy.deepcopy(r.nav_command)]
