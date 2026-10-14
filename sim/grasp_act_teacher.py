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
from scripts.zone_teacher import ArmSequence, FOLDED, plan_path, PeerDisc, proportional_drive
from harness.static_keepouts import rect_distance

ROLE = {'teal': 'end_neg', 'blue': 'end_pos'}
STATION_M = .203
XY_TOL_M = .03
YAW_TOL_RAD = .06


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
        self.staging_distance=STATION_M
        self.planner_calls=0;self.no_path_calls=0;self.phase_durations={}

    def _set(self,phase,now):
        self.phase_durations[self.phase]=self.phase_durations.get(self.phase,0.)+now-self.phase_t
        self.events.append({'t':now,'from':self.phase,'to':phase})
        self.phase,self.phase_t=phase,now
        self.stable_since=None

    def _hold(self,now):
        return command({'t':now,'drive':[0.,0.,0.],'duration_s':0.,
                        'pwm':{str(s):self.sink.pwm[s] for s in SERVOS}})

    def _continuous(self,now,forward,left,turn):
        # Legacy body-wrench units -> native motor effort. The shared ACT
        # port handles the fixed v7 breakaway relay from issued commands only.
        drive=[3.*forward,3.*left,.65*turn]
        from harness.grasp_act_contract import wheel_mix
        scale=max(1.,max(map(abs,wheel_mix(drive))))
        value=self._hold(now);value['drive']=[v/scale for v in drive]
        value['duration_s']=.15 if any(drive) else 0.
        return command(value)

    def _route(self,truth,goal,heading,now):
        pose=truth['robots'][self.rid]['pose']
        # Empty paths are cached too. Previously "or not self.path" retried
        # a failed A* ten times per SIM second.
        if now>=self.next_plan:
            discs=[PeerDisc((*v['pose'][:2],.17)) for r,v in truth['robots'].items() if r!=self.rid]
            discs += [(*o['xy'],o['radius']+.02) for iid,o in truth.get('objects',{}).items() if iid!='beam_1']
            bx,by,ba=truth['beam']['pose']
            # Robot disc .17 + beam thickness .02 fits the .203 m station.
            discs += [(bx+x*math.cos(ba),by+x*math.sin(ba),.02) for x in (-.27,-.135,0,.135,.27)]
            self.path=plan_path(pose[:2],goal,self.bounds,discs,rects=self.rects) or []
            self.planner_calls+=1;self.no_path_calls+=int(not self.path)
            self.next_plan=now+1.
        while len(self.path)>1 and math.dist(pose[:2],self.path[0])<.12:self.path.pop(0)
        if not self.path:return self._hold(now)
        target=self.path[0] if len(self.path)>1 else goal
        return self._continuous(now,**proportional_drive(pose,goal,target,heading))

    def _approach(self,truth,now):
        pose=truth['robots'][self.rid]['pose'];g=truth['beam']['ends'][self.end]
        heading=truth['beam']['pose'][2]+(math.pi if self.end=='blue' else 0.)
        goal=(g[0]-STATION_M*math.cos(heading),g[1]-STATION_M*math.sin(heading))
        if self.phase=='approach' and math.dist(pose[:2],goal)>.03:
            return self._route(truth,goal,heading,now),False
        if self.phase=='approach':self._set('align',now)
        gx,gy=local(pose,g);ex,ey,ea=gx-STATION_M,gy,wrap(heading-pose[2])
        # Stop the chassis within 3 cm; actual residual goes into v3 pad IK.
        # Reachability is checked before ready, not assumed from chassis error.
        reachable=True
        try:
            solve_grip_site_ik((gx,gy,g[2]))
            solve_grip_site_ik((gx,gy,.095))
        except ValueError:reachable=False
        if abs(ea)<=YAW_TOL_RAD and math.dist(pose[:2],goal)<=XY_TOL_M and reachable:
            self.stable_since=now if self.stable_since is None else self.stable_since
            return self._hold(now),now-self.stable_since>=.3
        self.stable_since=None
        # Original zone_teacher._align proportional law; retain current v3 IK.
        clip=lambda v,lo,hi:max(lo,min(hi,v))
        return self._continuous(now,clip(.9*ex,-.05,.08),clip(.9*ey,-.06,.06),clip(.8*ea,-.10,.10)),False

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
                'staging_distance_m':self.staging_distance,'phase_sim_s':self.phase_durations,
                'planner_calls':self.planner_calls,'no_path_calls':self.no_path_calls,
                'scope':'privileged_teacher_only; single-end lift is not whole-beam lift'}
