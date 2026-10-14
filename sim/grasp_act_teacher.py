"""Privileged demonstration-only local grasp teacher, normal physics, no weld.

Reuses v3 pad IK, the existing arm interpolator and static-map A*. The only
output is an issued command. Truth is supplied by the simulation owner and
must never enter an ACT observation or LLM request.
"""
from __future__ import annotations
import math
from copy import deepcopy

from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose
from harness.grasp_act_contract import command, SERVOS
from scripts.zone_teacher import ArmSequence, FOLDED, plan_path, PeerDisc

ROLE = {'teal': 'end_neg', 'blue': 'end_pos'}
STATION_M = .203
XY_TOL_M = .004
YAW_TOL_RAD = math.radians(1.)


def wrap(x):
    return math.atan2(math.sin(x), math.cos(x))


def local(pose, point):
    dx,dy=point[0]-pose[0],point[1]-pose[1]
    c,s=math.cos(pose[2]),math.sin(pose[2])
    return c*dx+s*dy,-s*dx+c*dy


class IssuedArm:
    """ArmSequence sink: records commands without reading a robot."""
    def __init__(self, pwm):
        self.pwm = {int(k):int(v) for k,v in pwm.items()}
    def apply(self, action, now):
        sid = 6 if action['kind']=='look' else action['servo_id']
        self.pwm[sid] = action['pan_pulse'] if sid==6 else action['pulse']


class GraspTeacher:
    def __init__(self, rid, end, initial_pwm, *, bounds, rects=()):
        if rid not in ('r1','r2') or end not in ROLE:
            raise ValueError('explicit demo assignment required')
        self.rid, self.end = rid,end
        self.sink=IssuedArm(initial_pwm)
        self.arm=ArmSequence(self.sink,self.sink.pwm)
        self.bounds,self.rects=bounds,rects
        self.phase='approach';self.phase_t=0.
        self.next_drive=0.;self.stable_since=None
        self.outcome=None;self.events=[];self.path=[];self.next_plan=0.
        self.grasp_xyz=None;self.initial_end_z=None;self.started=False

    def _set(self,phase,now):
        self.events.append({'t':now,'from':self.phase,'to':phase})
        self.phase,self.phase_t=phase,now
        self.stable_since=None

    def _hold(self,now):
        return command({'t':now,'drive':[0.,0.,0.],'duration_s':0.,
                        'pwm':{str(s):self.sink.pwm[s] for s in SERVOS}})

    def _pulse(self,now,axis,error,*,coarse=False):
        value=self._hold(now)
        if now+1e-8 < self.next_drive:return value
        value['drive'][axis]=math.copysign(.35,error)
        value['duration_s']=.15 if coarse and axis!=1 else .06
        self.next_drive=now+value['duration_s']+.20  # allow passive settle
        return command(value)

    def _route(self,truth,goal,now):
        pose=truth['robots'][self.rid]['pose']
        if now>=self.next_plan or not self.path:
            discs=[PeerDisc((*v['pose'][:2],.17)) for r,v in truth['robots'].items() if r!=self.rid]
            discs += [(*o['xy'],o['radius']+.02) for iid,o in truth.get('objects',{}).items() if iid!='beam_1']
            # A line of discs covers the known beam; this is teacher-only geometry.
            bx,by,ba=truth['beam']['pose']
            discs += [(bx+x*math.cos(ba),by+x*math.sin(ba),.04) for x in (-.27,-.135,0,.135,.27)]
            self.path=plan_path(pose[:2],goal,self.bounds,discs,rects=self.rects) or []
            self.next_plan=now+1.
        while self.path and math.dist(pose[:2],self.path[0])<.07:self.path.pop(0)
        if not self.path:return self._hold(now)
        dx,dy=local(pose,self.path[0]);heading=math.atan2(dy,dx)
        if abs(heading)>.10:return self._pulse(now,2,heading,coarse=abs(heading)>.35)
        return self._pulse(now,0,dx,coarse=abs(dx)>.08)

    def _approach(self,truth,now):
        pose=truth['robots'][self.rid]['pose'];g=truth['beam']['ends'][self.end]
        heading=truth['beam']['pose'][2]+(math.pi if self.end=='blue' else 0.)
        goal=(g[0]-.50*math.cos(heading),g[1]-.50*math.sin(heading))
        gx,gy=local(pose,g)
        if self.phase=='approach' and math.dist(pose[:2],goal)>.09:
            return self._route(truth,goal,now),False
        if self.phase=='approach':self._set('align',now)
        ex,ey,ea=gx-STATION_M,gy,wrap(heading-pose[2])
        if abs(ea)>YAW_TOL_RAD or abs(ey)>XY_TOL_M or abs(ex)>XY_TOL_M:
            self.stable_since=None
        if abs(ea)>YAW_TOL_RAD:return self._pulse(now,2,ea,coarse=abs(ea)>.3),False
        if abs(ey)>XY_TOL_M:return self._pulse(now,1,ey),False
        if abs(ex)>XY_TOL_M:return self._pulse(now,0,ex,coarse=abs(ex)>.06),False
        if now < self.next_drive:return self._hold(now),False
        self.stable_since = now if self.stable_since is None else self.stable_since
        return self._hold(now),now-self.stable_since>=.3

    def _queue_pick(self,truth,now):
        pose=truth['robots'][self.rid]['pose'];g=truth['beam']['ends'][self.end]
        x,y=local(pose,g);self.grasp_xyz=(x,y,g[2]);self.initial_end_z=g[2]
        grip=solve_grip_site_ik(self.grasp_xyz)
        pitch=tool_pose(grip).pitch_deg
        hover=solve_grip_site_ik((x,y,.095),preferred_pitch_deg=pitch)
        self.arm.queue({**hover,1:2000},now,duration=1.)
        for i in range(1,9):
            z=.095+(g[2]-.095)*i/8
            self.arm.queue(solve_grip_site_ik((x,y,z),preferred_pitch_deg=pitch),now,duration=.15,settle=.04)
        self.arm.queue({1:1500},now,duration=.8,settle=.5)
        lift=solve_grip_site_ik((x,y,.095),preferred_pitch_deg=pitch)
        self.arm.queue(lift,now,duration=1.2,settle=.5)
        self._set('pick',now)

    def step(self,truth,now,*,permit_pick=True):
        if not self.started:
            self.started=True;self.phase_t=now
            self.arm.queue({**FOLDED,6:1500},now,duration=.5)
        arms_done=self.arm.tick(now)
        if self.outcome:return self._hold(now),self.outcome=='success'
        if now-self.phase_t>90:
            self.outcome='phase_timeout';return self._hold(now),False
        if self.phase in ('approach','align'):
            action,ready=self._approach(truth,now)
            if ready:
                self._set('ready',now)
            return action,False
        if self.phase=='ready':
            if permit_pick:
                try:self._queue_pick(truth,now)
                except ValueError:
                    self.outcome='ik_unreachable'
            return self._hold(now),False
        if self.phase=='pick' and arms_done:self._set('verify',now)
        if self.phase=='verify':
            end=truth['beam']['ends'][self.end]
            bilateral=min(truth['contacts'][self.rid])>=.5
            lifted=end[2]>=self.initial_end_z+.012
            self.stable_since=(self.stable_since if self.stable_since is not None else now) if bilateral and lifted else None
            if self.stable_since is not None and now-self.stable_since>=1.:
                self.outcome='success';self._set('done',now)
                return self._hold(now),True
            if now-self.phase_t>5.:self.outcome='no_bilateral_end_lift'
        return self._hold(now),False

    def diagnostic(self):
        return {'phase':self.phase,'outcome':self.outcome,'events':deepcopy(self.events),
                'scope':'privileged_teacher_only; single-end lift is not whole-beam lift'}
