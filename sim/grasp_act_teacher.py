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


def grasp_poses(target):
    """Existing pad IK for the entire Cartesian descent and lift."""
    x,y,z=target
    grip=solve_grip_site_ik(target)
    pitch=tool_pose(grip).pitch_deg
    hover=solve_grip_site_ik((x,y,.095),preferred_pitch_deg=pitch)
    descent=[solve_grip_site_ik((x,y,.095+(z-.095)*i/8),preferred_pitch_deg=pitch)
             for i in range(1,9)]
    return hover,descent


class IssuedArm:
    """ArmSequence sink: records commands without reading a robot."""
    def __init__(self, pwm):
        self.pwm = {int(k):int(v) for k,v in pwm.items()}
    def apply(self, action, now):
        sid = 6 if action['kind']=='look' else action['servo_id']
        self.pwm[sid] = action['pan_pulse'] if sid==6 else action['pulse']


class GraspTeacher:
    def __init__(self, rid, end, initial_pwm, *, bounds, rects=(), profile="legacy"):
        if profile not in ("legacy","pi_geometry_v1","observable_v2"):raise ValueError("unknown teacher profile")
        self.profile=profile;self.folded_ready=False
        self.last_seen=None;self.last_seen_t=None;self.search_since=None
        self.visibility_counts={'visible':0,'N':0};self.blind_s=0.;self.max_blind_s=0.
        self.observed_objects={};self.observed_peers={}
        self.align_integral=[0.,0.,0.];self.align_t=None
        self.ik_rejections=0;self.last_ik_error=None;self.planning_radius=.17
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
            # Height-aware configuration-space radius only for the opt-in
            # folded-arm teacher. The unchanged v3 geometry below 10 cm fits
            # within 0.123 m; use 0.130 m plus 5 mm low-cargo padding.
            # Tall walls, bounds, unknown/high objects and peers keep the old
            # 0.170 m clearance. No collision/physical parameter changes.
            fine=self.profile!='legacy' and self.folded_ready
            radius=.13 if fine else .17;extra=.17-radius
            self.planning_radius=radius
            peers=truth['robots'] if self.profile!='observable_v2' else self.observed_peers
            objects=truth.get('objects',{}) if self.profile!='observable_v2' else self.observed_objects
            discs=[PeerDisc((*v['pose'][:2],.17+extra)) for r,v in peers.items() if r!=self.rid]
            for iid,o in objects.items():
                if iid=='beam_1':continue
                padding=.005 if fine and o.get('top_z_bound_m',math.inf)<=.1 else .02+extra
                discs.append((*o['xy'],o['radius']+padding))
            bx,by,ba=truth['beam']['pose']
            discs += [(bx+x*math.cos(ba),by+x*math.sin(ba),.02) for x in (-.27,-.135,0,.135,.27)]
            bounds=self.bounds
            rects=self.rects
            if fine:
                x0,x1,y0,y1=bounds;bounds=(x0+extra,x1-extra,y0+extra,y1-extra)
                rects=[(x,y,hx+extra,hy+extra,a) for x,y,hx,hy,a in rects]
            self.path=plan_path(pose[:2],goal,bounds,discs,rects=rects,radius=radius) or []
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
        # Coarse path tracking loses authority at small errors on native v7.
        # Enter the existing higher-gain alignment law before the 3 cm stop
        # band, rather than requiring coarse tracking to reach that band first.
        if self.phase=='approach' and math.dist(pose[:2],goal)>.08:
            return self._route(truth,goal,heading,now),False
        if self.phase=='approach':self._set('align',now)
        gx,gy=local(pose,g);ex,ey,ea=gx-STATION_M,gy,wrap(heading-pose[2])
        # Stop the chassis within 3 cm; actual residual goes into v3 pad IK.
        # Reachability is checked before ready, not assumed from chassis error.
        reachable=True
        try:
            if self.profile!='legacy':grasp_poses((gx,gy,g[2]))
            else:
                solve_grip_site_ik((gx,gy,g[2]))
                solve_grip_site_ik((gx,gy,.095))
        except ValueError as error:
            reachable=False;self.ik_rejections+=1;self.last_ik_error=str(error)
        if abs(ea)<=YAW_TOL_RAD and math.dist(pose[:2],goal)<=XY_TOL_M and reachable:
            self.stable_since=now if self.stable_since is None else self.stable_since
            self.align_integral=[0.,0.,0.];self.align_t=now
            return self._hold(now),now-self.stable_since>=.3
        self.stable_since=None
        # Original zone_teacher._align proportional law; retain current v3 IK.
        clip=lambda v,lo,hi:max(lo,min(hi,v))
        if self.profile!='legacy':
            dt=0. if self.align_t is None else clip(now-self.align_t,0.,.2)
            self.align_t=now
            for i,(error,gain,limit) in enumerate(zip((ex,ey,ea),(.45,.45,.4),(.025,.025,.03))):
                self.align_integral[i]=clip(self.align_integral[i]+gain*error*dt,-limit,limit)
            return self._continuous(now,clip(.9*ex+self.align_integral[0],-.05,.08),
                clip(.9*ey+self.align_integral[1],-.06,.06),clip(.8*ea+self.align_integral[2],-.10,.10)),False
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

    def _observe(self,truth,now):
        """Look before translation; hidden target never chooses search direction."""
        from sim.grasp_act_gaze import gaze_pose,slew
        visibility=truth['visibility'][self.rid]
        visible=visibility['visible_probes']>=3
        self.visibility_counts['N']+=1;self.visibility_counts['visible']+=int(visible)
        self.blind_s=0. if visible else self.blind_s+.1
        self.max_blind_s=max(self.max_blind_s,self.blind_s)
        if visible:
            self.last_seen=deepcopy(truth['beam']['ends'][self.end]);self.last_seen_t=now;self.search_since=None
        for iid in visibility.get('objects',[]):
            self.observed_objects[iid]=deepcopy(truth['objects'][iid])
        for rid in visibility.get('peers',[]):
            self.observed_peers[rid]=deepcopy(truth['robots'][rid]);self.observed_peers[rid]['seen_t']=now
        self.observed_peers={r:v for r,v in self.observed_peers.items() if now-v['seen_t']<=8.}
        if self.last_seen_t is not None and now-self.last_seen_t<=1.:
            pose=truth['robots'][self.rid]['pose'];x,y=local(pose,self.last_seen)
            target=gaze_pose((x,y,self.last_seen[2]+.009),self.sink.pwm)
        else:
            # Deterministic observation search, independent of hidden end pose.
            self.search_since=now if self.search_since is None else self.search_since
            target={**FOLDED,3:820,6:round(1500+1000*math.sin((now-self.search_since)*.7))}
        self.sink.pwm.update(slew(self.sink.pwm,target));self.arm.commanded.update(self.sink.pwm)
        if visible:return None
        # A recently seen end may be reacquired by the arm while chassis holds.
        if self.last_seen_t is not None and now-self.last_seen_t<=1.:return self._hold(now)
        return self._continuous(now,0.,0.,.12)

    def step(self,truth,now,*,permit_pick=True):
        if not self.started:
            self.started=True;self.phase_t=now
            self.arm.queue({**FOLDED,6:self.sink.pwm[6] if self.profile=='observable_v2' else 1500},now,duration=.5)
        arms_done=self.arm.tick(now)
        self.folded_ready=arms_done and all(self.sink.pwm[k]==FOLDED[k] for k in (3,4,5))
        if self.profile=='observable_v2':
            self.folded_ready=arms_done and 500<=self.sink.pwm[3]<=960 and 2320<=self.sink.pwm[4]<=2500 and self.sink.pwm[5]==1320
        if self.outcome:return self._hold(now),self.outcome=='success'
        if now-self.phase_t>60:
            self.outcome='phase_timeout';return self._hold(now),False
        if self.phase in ('approach','align'):
            if self.profile=='observable_v2':
                if not arms_done:return self._hold(now),False
                search=self._observe(truth,now)
                if search is not None:return search,False
            action,ready=self._approach(truth,now)
            if ready:
                self._set('ready',now)
            return action,False
        if self.phase=='ready':
            if self.profile=='observable_v2':
                search=self._observe(truth,now)
                if search is not None:return search,False
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
        return {'profile':self.profile,'planning_radius_m':self.planning_radius,
                'visibility_counts':self.visibility_counts,'max_unseen_before_pick_s':self.max_blind_s,
                'ik_rejections':self.ik_rejections,'last_ik_error':self.last_ik_error,
                'alignment_integral':list(self.align_integral),'phase':self.phase,'outcome':self.outcome,'events':deepcopy(self.events),
                'staging_distance_m':self.staging_distance,'phase_sim_s':self.phase_durations,
                'planner_calls':self.planner_calls,'no_path_calls':self.no_path_calls,
                'scope':'privileged_teacher_only; single-end lift is not whole-beam lift'}
