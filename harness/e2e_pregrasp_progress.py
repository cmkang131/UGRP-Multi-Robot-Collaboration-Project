"""Own-visual progress checker, calibrated backup/turn, then fresh-map replan.

Nav2 SimpleProgressChecker/recovery structure, scaled to the slow finite pulse
port. No contact IDs, actual joint/robot pose, or evaluation input is read.
"""
import math
import numpy as np
from harness.active_wall_mapping import wrap
from harness.e2e_rpp_path import command as rpp_command
from harness.zone_solo_cyan_pulse_cal import action_of

OPTION='backup_replan_v1'


def step(tr,rid,now,state,distance):
    if getattr(tr,'pregrasp_progress','off')!=OPTION:return None
    r=tr.robots[rid];pose=np.asarray(r.goal.explorer.local_pose);count=r.translation_commands
    watch=state.setdefault('progress_watch',dict(pose=pose.copy(),since=now,count=count,issued=0,last_issue=now,cycle=0))
    if watch.get('phase'):
        elapsed=now-watch['phase_t'];start=watch['phase_pose']
        if watch['phase']=='backup':
            if np.linalg.norm(pose[:2]-start[:2])>=.12 or elapsed>=6.:
                watch.update(phase='turn',phase_t=now,phase_pose=pose.copy(),yaw=float(pose[2]+(1 if watch['cycle']%2 else -1)*math.pi/3))
                return False,[dict(kind='hold')]
            candidates=[p for p in tr.profiles.values() if not p['loaded'] and p['axis']=='forward' and -.35<=p['u']<0 and p['duration_s']==.1]
            action=action_of(min(candidates,key=lambda p:abs(p['u'])))
        else:
            action,_=rpp_command(dict(coordinate_frame=rid+'/own_odom',path_m=[pose[:2].tolist()],status='goal_approach',heading_rad=watch['yaw']),pose,tr.profiles,robot_id=rid)
            if action['kind']=='hold' or elapsed>=6.:
                watch.update(phase=None,pose=pose.copy(),since=now,count=count,issued=0,last_issue=now)
                state.pop('search_started',None);state.pop('search_step',None);state['lost_nav_until']=now+5.
                tr.event(now,'own_pregrasp_replan',robot_id=rid,cycle=watch['cycle'])
                return False,[dict(kind='hold')]
        r.carrier_approach.update(status='recover_'+watch['phase'],progress_recovery=True)
        return False,[action]
    delta=count-watch['count'];watch['count']=count
    if delta>0:watch['issued']+=delta;watch['last_issue']=now
    progressed=np.linalg.norm(pose[:2]-watch['pose'][:2])>.03 or abs(wrap(pose[2]-watch['pose'][2]))>.15
    if progressed or distance<=.20 or now-watch['last_issue']>1.:
        watch.update(pose=pose.copy(),since=now,issued=0)
    elif now-watch['since']>=8. and watch['issued']>=4:
        watch.update(phase='backup',phase_t=now,phase_pose=pose.copy(),cycle=watch['cycle']+1)
        tr.event(now,'own_pregrasp_no_progress',robot_id=rid,issued=watch['issued'],elapsed=now-watch['since'],source='own_rgb_odometry_and_issued_commands')
        return step(tr,rid,now,state,distance)
    return None
