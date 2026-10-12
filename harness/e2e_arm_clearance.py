"""Opt-in scan recovery using own sonar, RGB walls and commanded posture only.

Clearance is a navigation hypothesis, never a contact/success observation.
Candidate slots use a fixed task clock, not another robot's private state.
"""
import copy
import math
import numpy as np
from harness.active_wall_mapping import wrap
from harness.range_provider import RangeReport, source_label
from harness.ultrasonic_input import range_report
from harness.e2e_rpp_path import command as rpp_command
from harness.zone_solo_cyan_pulse_cal import action_of

OPTIONS = ('range_v1', 'range_wall_v1', 'range_wall_slots_v1')
VERSIONS = dict(zip(OPTIONS, (242, 243, 244)))
PARAMS = dict(range_m=.26, wall_base_m=.38, backup_m=.30,
              repeat_radius_m=.25, range_max_age_s=.15, rgb_max_age_s=1.,
              backup_cap_s=6., turn_cap_s=5., max_recoveries=3)


def stop():
    return dict(kind='mecanum', forward=0., left=0., turn=0., duration_s=0.)


def wall_distance(robot, now):
    if not 0 <= now-robot.now <= PARAMS['rgb_max_age_s']:
        return None
    distances=[]
    for a,b in robot.wall_segments:
        a,b=np.asarray(a,float),np.asarray(b,float)
        if a.shape!=(2,) or b.shape!=(2,) or not np.isfinite([a,b]).all():continue
        d=b-a;length=float(d@d)
        q=a+min(1.,max(0.,float(-a@d)/length))*d if length else a
        distances.append(float(np.linalg.norm(q)))
    return min(distances) if distances else None


def evidence(robot, now, option):
    report=range_report(robot,now);near=False;value=None;status='unavailable'
    if (isinstance(report,RangeReport) and report.source==source_label() and
            report.t_meas is not None and 0<=now-report.t_meas<=PARAMS['range_max_age_s']+1e-8):
        status=report.status
        if report.status=='blind':near=True
        elif report.valid and report.status=='ok' and math.isfinite(report.range_m):
            value=report.range_m;near=value<PARAMS['range_m']
    wall=wall_distance(robot,now) if option!='range_v1' else None
    return dict(near=bool(near or wall is not None and wall<PARAMS['wall_base_m']),
                range_m=value,range_status=status,wall_base_m=wall)


def scan_path(robot,path):
    from harness.owncam_pair_beam_v2 import pose_of
    if robot.servo.get(1,0)<1900:return False
    for pose,_,_ in path:
        if pose.get(1,2000)<1900:return False
        if not any(all(pose.get(k)==pose_of(tag)[k] for k in (3,4,5))
                   for tag in ('search','p45','inspect')):return False
    return any(any(robot.servo.get(k)!=v for k,v in p.items()) for p,_,_ in path)


class Clearance:
    def __init__(self,option='off',scan_guard='off'):
        from harness.e2e_scan_guard import OPTIONS as GUARDS
        if scan_guard not in ('off',*GUARDS):raise ValueError('UNKNOWN_SCAN_GUARD')
        if scan_guard!='off' and option!='range_wall_v1':raise ValueError('SCAN_GUARD_REQUIRES_RANGE_WALL')
        self.scan_guard=scan_guard;self.retreat_grants={}
        if option not in ('off',*OPTIONS):raise ValueError('UNKNOWN_ARM_CLEARANCE')
        self.option=option;self.pending={};self.excluded={};self.cooldown={}

    def evidence(self,robot,now):
        ev=evidence(robot,now,self.option)
        if self.scan_guard=='map_v1':
            from harness.e2e_scan_guard import mapped_wall_distance,PARAMS as GUARD_PARAMS
            distance=mapped_wall_distance(robot);ev['map_wall_m']=distance
            ev['near']=bool(ev['near'] or distance is not None and distance<GUARD_PARAMS['map_wall_radius_m'])
        return ev

    def busy(self,rid):return rid in self.pending

    def slot(self,rid,now):
        if self.option!='range_wall_slots_v1' and self.scan_guard!='retreat_slots_v1':return True
        # A complete 1.4 s scan fits; r1 and r2 have disjoint three-second slots.
        offset=0. if rid=='r1' else 3.
        return 0<=now%6.-offset<=1.5

    def defer(self,tr,rid,now,path):
        if self.option=='off' or tr.state not in ('mapping','align'):return False
        r=tr.robots[rid]
        if not scan_path(r,path):return False
        if rid in self.pending:return True
        if now<self.cooldown.get(rid,0.):return True
        pose=np.asarray(r.goal.explorer.local_pose,float)
        ev=self.evidence(r,now)
        from harness.e2e_scan_guard import forced
        retreat=forced(self,rid,now,pose)
        repeated=any(np.linalg.norm(pose[:2]-p)<PARAMS['repeat_radius_m'] for p in self.excluded.get(rid,[]))
        if not ev['near'] and not repeated and not retreat and self.slot(rid,now):return False
        phase='backup' if ev['near'] or repeated or retreat else 'slot'
        self.pending[rid]=dict(path=copy.deepcopy(path),phase=phase,since=now,
                               pose=pose.copy(),cycle=1,ev=ev)
        if phase=='backup':self.excluded.setdefault(rid,[]).append(pose[:2].copy())
        tr.event(now,'own_arm_clearance_deferred',robot_id=rid,phase=phase,
                 repeated_location=repeated,command_space_retreat=retreat,**ev)
        return True

    def filter(self,tr,now,commands):
        if self.option=='off':return commands
        if tr.state not in ('mapping','align') or tr.failure:
            self.pending.clear();return commands
        blocked=set(self.pending);out=[(rid,a) for rid,a in commands if rid not in blocked]
        for rid,s in list(self.pending.items()):
            r=tr.robots[rid];pose=np.asarray(r.goal.explorer.local_pose,float)
            phase=s['phase'];elapsed=now-s['since'];action=stop()
            if phase=='backup':
                if np.linalg.norm(pose[:2]-s['pose'][:2])>=PARAMS['backup_m'] or elapsed>=PARAMS['backup_cap_s']:
                    sign=1 if s['cycle']%2 else -1
                    s.update(phase='turn',since=now,yaw=float(pose[2]+sign*math.pi/3))
                else:
                    candidates=[p for p in tr.profiles.values() if not p['loaded'] and p['axis']=='forward' and -.35<=p['u']<0 and p['duration_s']==.1]
                    action=action_of(min(candidates,key=lambda p:abs(p['u'])))
            elif phase=='turn':
                action,_=rpp_command(dict(coordinate_frame=rid+'/own_odom',path_m=[pose[:2].tolist()],
                    status='goal_approach',heading_rad=s['yaw']),pose,tr.profiles,robot_id=rid)
                if action['kind']=='hold' or elapsed>=PARAMS['turn_cap_s']:
                    s.update(phase='verify',since=now);action=stop()
            elif phase in ('verify','slot'):
                ev=self.evidence(r,now)
                repeated=any(np.linalg.norm(pose[:2]-p)<PARAMS['repeat_radius_m'] for p in self.excluded.get(rid,[]))
                if phase=='verify' and elapsed<.7:pass
                elif ev['near'] or repeated:
                    if s['cycle']>=PARAMS['max_recoveries']:
                        self.pending.pop(rid);self.cooldown[rid]=now+12.
                        tr.event(now,'own_arm_clearance_scan_abandoned',robot_id=rid,**ev)
                    else:s.update(phase='backup',since=now,pose=pose.copy(),cycle=s['cycle']+1)
                elif self.slot(rid,now):
                    self.pending.pop(rid)
                    self.retreat_grants[rid]=(now,pose.copy())
                    tr._poses(rid,now,s['path'],_clearance_checked=True)
                    tr.event(now,'own_arm_clearance_released',robot_id=rid,cycles=s['cycle'],**ev)
            r.carrier_approach=dict(t=now,status='arm_clearance_'+s['phase'],cycle=s['cycle'])
            out.append((rid,action))
        return out


def compose(bundle,option):
    if option=='off':return ()
    if option not in OPTIONS or bundle['execution_bundle_id']!='e2e18-v241':
        raise ValueError('ARM_CLEARANCE_REQUIRES_V241')
    version=VERSIONS[option]
    bundle['e2e_options']['arm_clearance']=option
    bundle['arm_clearance_parameters']=dict(PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}',execution_bundle_id=f'e2e18-v{version}',workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)
