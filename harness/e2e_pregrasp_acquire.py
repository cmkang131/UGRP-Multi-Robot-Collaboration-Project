"""Bounded own-camera acquisition before a pregrasp station is available.

Remembered geometry proposes a search direction; only current RGB may satisfy
the existing fine alignment and grasp gates. No peer or world state is read.
"""
import math
import numpy as np
from harness.e2e_rpp_path import command as rpp_command
from harness.e2e_carrier_axes import station
from harness.owncam_pair_beam_v2 import pose_of

OPTION='remember_scan_v1'
QUEUES='per_robot_v1'
MAPPING='interleaved_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v235.json'
VIEWS=(('search',1500),('p45',1500),('inspect',1500),('search',1250),('search',1750))


def busy(tr,rid,now):
    if getattr(tr,'arm_clearance',None) is not None and tr.arm_clearance.busy(rid):return True
    return (getattr(tr,'align_queues','off')==QUEUES and
            (now<tr.robot_queue_until.get(rid,-1.)-1e-8 or any(r==rid for _,r,_ in tr.queue)))


def acquire(tr,rid,now,state,target):
    if getattr(tr,'pregrasp_acquire','off')!=OPTION:return None
    r=tr.robots[rid];last=getattr(r,'last_beam',None)
    age=now-last['rgb']['t_sim'] if last else math.inf
    if last and target and 0<=age<=8.:
        end,grip,basis=station(last,target['center_m'],getattr(tr,'task_roles',{}).get(rid,rid))
        state.update(station=end,grip=grip,basis=basis,last_seen=last['rgb']['t_sim'])
        tr.event(now,'own_recent_beam_station_hypothesis',robot_id=rid,rgb=last['rgb'],age_s=age)
        return None
    pose=np.asarray(r.goal.explorer.local_pose)
    from harness import e2e_approach_efficiency as efficient
    if 'acquisition' not in state:
        point=np.asarray(last['pose_own_m'][:2]) if last and 0<=age<=120. else None
        yaw=math.atan2(*(point-pose[:2])[::-1]) if point is not None else float(pose[2])
        state['acquisition']=dict(phase='turn',started=now,yaw=yaw,cycles=0,view=-1)
        efficient.search_memory(tr,rid,state['acquisition'],pose,last,now)
        tr.event(now,'own_pregrasp_acquisition_begin',robot_id=rid,
                 source='last_own_rgb_search_hypothesis' if point is not None else 'own_camera_scan',age_s=age if math.isfinite(age) else None,
                 rgb=last['rgb'] if point is not None else None,execution_phase=tr.state)
    if target is not None and getattr(tr,'beam_lost_standoff','off')!='off':
        from harness.e2e_acquire_standoff import advance as standoff_advance
        stood=standoff_advance(tr,rid,now,state['acquisition'],last,age,pose)
        if stood is not None:return stood
    a=state['acquisition'];phase=a['phase'];elapsed=now-a['started']
    from harness.e2e_acquire_standoff import scan_timing
    view_period,turn_cap=scan_timing(tr)
    r.carrier_approach=dict(t=now,status='acquire_'+phase,own_beam_age_s=age if math.isfinite(age) else None,B_candidate_available=target is not None,cycle=a['cycles'])
    if phase=='turn':
        command,_=rpp_command(dict(coordinate_frame=rid+'/own_odom',path_m=[pose[:2].tolist()],status='goal_approach',heading_rad=a['yaw']),pose,tr.profiles,robot_id=rid)
        if command['kind']=='hold' or elapsed>=turn_cap:
            a.update(phase='scan',started=now,view=-1)
            return False,[dict(kind='hold')]
        return False,[command]
    if phase=='explore':
        from harness.e2e_acquisition_mobility import explore
        recovered=explore(tr,rid,now,a)
        if recovered is not None:return recovered
        if elapsed<5.:return False,[{k:v for k,v in r.nav_command.items() if k!='t'}]
        a.update(phase='turn',started=now,yaw=efficient.next_yaw(tr,rid,a,pose))
        return False,[dict(kind='hold')]
    sequence=efficient.views(tr,rid,a,pose,VIEWS)
    index=int(elapsed//view_period)
    if efficient.enabled(tr):
        # Advance only after an accepted image from the commanded view. Existing
        # queue and camera-settling barriers still own the .8+.6 s trajectory.
        frame=(r.last_obs or {}).get('frame_id')
        observed=(a.get('view_frame')!=frame and not busy(tr,rid,now)
                  and now>=getattr(r,'camera_settle_until',-1.)
                  and all(r.servo.get(k)==v for k,v in a.get('view_pose',{}).items()))
        index=a['view']+(1 if observed else 0)
        if a['view']<0:index=0
    if index>=len(sequence):
        a['cycles']+=1
        phase='explore' if a['cycles']%2==0 else 'turn'
        yaw=a['yaw'] if efficient.enabled(tr) and phase=='explore' else efficient.next_yaw(tr,rid,a,pose)
        a.update(phase=phase,started=now,yaw=yaw)
        return False,[dict(kind='hold')]
    if index!=a['view']:
        a['view']=index
        tag,pan=sequence[index];posture=pose_of(tag);posture[6]=pan
        if efficient.enabled(tr):
            a.update(view_frame=(r.last_obs or {}).get('frame_id'),view_pose=dict(posture))
        tr._poses(rid,now,[(posture,.3,.6)])
        tr.event(now,'own_pregrasp_acquisition_view',robot_id=rid,camera=tag,pan_pulse=pan)
    return False,[dict(kind='hold')]


def mapping_commands(tr,now):
    out=[]
    for rid,r in tr.robots.items():
        if rid=='r3' or r.packet is not None:continue
        baseline=lambda:out.append((rid,r.nav_command))
        if rid!='r1' or getattr(tr,'mapping_acquire','off')!=MAPPING:
            baseline();continue
        if busy(tr,rid,now):
            out.append((rid,dict(kind='hold')));continue
        state=tr.mapping_acquisitions.setdefault(rid,{})
        ref=r.goal.e2e_gate.references.get('B')
        if r.beam is not None or not ref:
            state.clear();baseline();continue
        if 'until' in state and now>=state['until']:
            state.clear();state['next']=now+30.
        if 'until' not in state:
            if now<max(ref['ref']['t_sim']+15.,state.get('next',-1.)):
                baseline();continue
            state.update(until=now+12.,search={})
            tr.event(now,'own_mapping_beam_scan',robot_id=rid,until=now+12.,B_rgb=ref['ref'])
        if busy(tr,rid,now):actions=[dict(kind='hold')]
        else:_,actions=acquire(tr,rid,now,state['search'],None)
        out.extend((rid,a) for a in actions)
    return out


def compose(bundle,acquisition,queues,decode,mapping):
    if acquisition=='off' and queues=='off' and decode=='off' and mapping=='off':return ()
    if acquisition!=OPTION or queues!=QUEUES or decode!='once_v1' or mapping!=MAPPING or bundle['execution_bundle_id']!='e2e18-v234':
        raise ValueError('PREGRASP_ACQUIRE_REQUIRES_V234')
    bundle['e2e_options'].update(pregrasp_acquire=acquisition,align_queues=queues,beam_decode=decode,mapping_acquire=mapping)
    bundle.update(schema='ugrp.e2e_ownmap_live.v235',execution_bundle_id='e2e18-v235',workflow_version='7.128.0')
    return (WORKFLOW,)
