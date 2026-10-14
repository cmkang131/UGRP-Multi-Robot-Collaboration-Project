"""Observable local teacher with issued-command completion and real wheel pulses.

Truth is a demonstration-only label source. Navigation is explicitly outside
ACT. Once handed off, a lost target is propagated from issued wheels only;
the actual base pose cannot steer the gaze until the target is seen again.
"""
import math
from copy import deepcopy
from harness.grasp_act_contract import command,SERVOS,MEMORY_S
from sim.grasp_act_teacher import GraspTeacher,local,wrap,grasp_poses,STATION_M,XY_TOL_M,YAW_TOL_RAD
from sim.grasp_act_port import duty_wheels
from scripts.zone_teacher import FOLDED


def propagate_owned(point,issued,dt):
    # Nominal 65 mm wheel / 150 rpm kinematics; not calibrated odometry.
    # Only the preceding issued pulse is integrated, never measured motion.
    wheel=[w*min(dt,d) for w,d in zip(issued['wheels'],issued['duration_s'])]
    a,b,c,d=wheel;gain=.0325*150*2*math.pi/60
    dx= gain*(a+b+c+d)/4;dy=gain*(-a+b+c-d)/4
    yaw=gain*(-a+b-c+d)/(4*.1255)
    x,y,z=point;x-=dx;y-=dy;co,si=math.cos(yaw),math.sin(yaw)
    return [co*x+si*y,-si*x+co*y,z]


class VisibleOnlyGraspTeacher(GraspTeacher):
    def __init__(self,*args,**kwargs):
        self.teacher_stability=kwargs.pop('teacher_stability','off')
        if self.teacher_stability not in ('off','align_relook_v1'):
            raise ValueError('unknown teacher stability mode')
        kwargs.pop('profile',None)
        super().__init__(*args,profile='observable_v2',**kwargs)
        self.phase='approach';self.handoff=False;self.local_seen=None
        self.last_command=None;self.last_tick=None;self.command_complete=False
        self.ready_revocations=0;self.skill_started=None
        self.path_goal=None;self.blocked_goal_calls=0
        self.align_relooks=0;self.initial_search_pan=self.sink.pwm[6]
        self._reset_alignment()


    def _reset_alignment(self):
        self.align_integral=[0.,0.,0.];self.align_t=None
        self.align_active=[False]*3;self.align_sign=[0]*3
        self.align_flips=[0]*3;self.align_best=None;self.align_progress_t=None

    def _begin_relook(self,now,reason):
        self.align_relooks+=1
        self.events.append({'t':now,'alignment_recovery':reason})
        self._reset_alignment();self.path=[];self.path_goal=None
        self.local_seen=None;self.last_seen_t=None;self.search_since=now
        if self.align_relooks>2:
            self.outcome='alignment_no_progress'
        else:
            self._set('relook',now)
        return self._hold(now),False

    def _approach(self,truth,now):
        if self.teacher_stability=='off':return super()._approach(truth,now)
        # Only the currently visible measurement frame reaches this law.
        if truth['beam'] is None or truth['visibility'][self.rid]['visible_probes']<5:
            return self._hold(now),False
        pose,g,heading,goal=self._geometry(truth)
        if self.phase=='approach' and math.dist(pose[:2],goal)>.08:
            return self._route(truth,goal,heading,now),False
        if self.phase=='approach':self._set('align',now);self._reset_alignment()
        gx,gy=local(pose,g);errors=(gx-STATION_M,gy,wrap(heading-pose[2]))
        if self.ready_geometry(truth):
            self.stable_since=now if self.stable_since is None else self.stable_since
            self._reset_alignment()
            return self._hold(now),now-self.stable_since>=.3
        self.stable_since=None
        # Schmitt deadbands: stop within inner, restart beyond outer. The
        # residual still goes to the same pad IK; readiness is never relaxed.
        inner=(.002,.012,.02);outer=(.004,.018,.04)
        merit=max(abs(e)/b for e,b in zip(errors,inner))
        if self.align_best is None or merit<self.align_best-.25:
            self.align_best=merit;self.align_progress_t=now
        elif now-self.align_progress_t>=3.:
            return self._begin_relook(now,'no_visible_error_progress_3s')
        for i,error in enumerate(errors):
            if abs(error)<=inner[i]:self.align_active[i]=False
            elif abs(error)>=outer[i]:self.align_active[i]=True
            if not self.align_active[i]:self.align_integral[i]=0.
        # IK may reject an x residual inside the wider restart band. Avoid
        # accepting it as ready or accumulating tiny lateral/yaw commands.
        try:grasp_poses((gx,gy,g[2]));reachable=True
        except ValueError:reachable=False
        if not reachable and abs(errors[0])>.0005:self.align_active[0]=True
        axis=next((i for i in (2,1,0) if self.align_active[i]),None)
        if axis is None:return self._hold(now),False
        sign=1 if errors[axis]>0 else -1
        old=self.align_sign[axis]
        self.align_flips[axis]=self.align_flips[axis]+1 if old and sign!=old else 0
        self.align_sign[axis]=sign
        if self.align_flips[axis]>=4:return self._begin_relook(now,'alternating_error_sign_4')
        if old and sign!=old:self.align_integral[axis]=0.
        dt=0. if self.align_t is None else max(0.,min(.2,now-self.align_t))
        self.align_t=now
        for i in range(3):
            if i!=axis:self.align_integral[i]=0.
        limits=(.025,.025,.03);gains=(.45,.45,.4)
        self.align_integral[axis]=max(-limits[axis],min(limits[axis],
            self.align_integral[axis]+gains[axis]*errors[axis]*dt))
        effort=(.9,.9,.8)[axis]*errors[axis]+self.align_integral[axis]
        lo,hi=((- .05,.08),(-.06,.06),(-.10,.10))[axis]
        drive=[0.,0.,0.];drive[axis]=max(lo,min(hi,effort))
        # One axis per command keeps the four-wheel ratios intact when the
        # bounded minimum width is applied. No new grasp motion/IK path.
        return self._continuous(now,*drive),False

    def _observe_stable(self,truth,now):
        from sim.grasp_act_gaze import slew
        from sim.grasp_act_visible_gaze import gaze_pose
        visible=truth['visibility'][self.rid]['visible_probes']>=5
        self.visibility_counts['N']+=1;self.visibility_counts['visible']+=int(visible)
        self.blind_s=0. if visible else self.blind_s+.1
        self.max_blind_s=max(self.max_blind_s,self.blind_s)
        if visible:
            g=truth['beam']['ends'][self.end];pose=truth['robots'][self.rid]['pose']
            self.local_seen=[*local(pose,g),g[2]+.009];self.last_seen_t=now
            self.search_since=None
            occluders=[{'xy':local(pose,v['pose']),'radius':v.get('radius',.17),
                'top_z_bound_m':v.get('top_z_bound_m',.32)}
                for r,v in truth['robots'].items() if r!=self.rid]
            occluders += [{'xy':local(pose,v['xy']),'radius':v['radius'],
                'top_z_bound_m':v['top_z_bound_m']} for k,v in truth['objects'].items() if k!='beam_1']
            target=gaze_pose(self.local_seen,self.sink.pwm,occluders,visible=True)
            if self.phase=='search':self._set('approach',now);self._reset_alignment()
        else:
            self.search_since=now if self.search_since is None else self.search_since
            age=now-self.search_since
            if self.phase!='relook' and self.phase!='search':self._set('search',now)
            # Full stationary pan/pitch sweep before turning the chassis.
            # All targets depend on issued scan age, never a hidden pose.
            pans=(self.initial_search_pan,1500,1000,2000,500,2500)
            slot=int(age/.6)%(2*len(pans));near=slot%2==0
            target={**FOLDED,3:500 if near else 820,4:2500 if near else 2320,6:pans[slot//2]}
        self.sink.pwm.update(slew(self.sink.pwm,target));self.arm.commanded.update(self.sink.pwm)
        if visible:return None
        if age<7.2:return self._hold(now)
        return self._continuous(now,0.,0.,.25)

    def _geometry(self,world):
        pose=world['robots'][self.rid]['pose'];g=world['beam']['ends'][self.end]
        heading=world['beam']['pose'][2]+(math.pi if self.end=='blue' else 0.)
        goal=(g[0]-STATION_M*math.cos(heading),g[1]-STATION_M*math.sin(heading))
        return pose,g,heading,goal

    def _route(self,world,goal,heading,now):
        from sim.grasp_act_visible_route import constraints,free,segment_free,waypoint,drive
        from scripts.zone_teacher import plan_path
        pose=world['robots'][self.rid]['pose']
        radius,discs,rects=constraints(world,self.rid,self.folded_ready)
        self.planning_radius=radius
        # A newly observed target may disagree with dead reckoning. Cached
        # odometry-frame waypoints must then be rebuilt from the new view.
        changed=self.path_goal is None or math.dist(goal,self.path_goal)>.025
        target=waypoint(pose[:2],self.path,discs,rects,radius) if self.path else None
        if changed or now>=self.next_plan or (self.path and target is None):
            self.planner_calls+=1;self.path_goal=tuple(goal);self.next_plan=now+1.
            if not free(goal,discs,rects,radius):
                self.blocked_goal_calls+=1;self.path=[]
            else:
                self.path=plan_path(pose[:2],goal,self.bounds,discs,rects=rects,radius=radius) or []
            self.no_path_calls+=int(not self.path)
            target=waypoint(pose[:2],self.path,discs,rects,radius) if self.path else None
        if target is None:return self._hold(now)
        # Mecanum translation and gaze yaw are independent. Keep the observed
        # end in front while moving around a peer, until fine alignment starts.
        end=world['beam']['ends'][self.end]
        return self._continuous(now,**drive(pose,goal,target,end))

    def _hold(self,now):
        return command({'t':now,'wheels':[0.]*4,'duration_s':[0.]*4,
                        'pwm':{str(s):self.sink.pwm[s] for s in SERVOS}})

    def _continuous(self,now,forward,left,turn):
        wheels,widths=duty_wheels([3.*forward,3.*left,.65*turn])
        if self.teacher_stability!='off' and self.phase in ('align','search'):
            # Candidate 40 ms floor; real-wheel response remains unmeasured.
            widths=[max(.04,d) if w else 0. for w,d in zip(wheels,widths)]
        value=self._hold(now);value.update(wheels=wheels,duration_s=widths)
        return command(value)

    def _observe(self,truth,now):
        if self.teacher_stability!='off':return self._observe_stable(truth,now)
        from sim.grasp_act_gaze import slew
        from sim.grasp_act_visible_gaze import gaze_pose
        vis=truth['visibility'][self.rid];visible=vis['visible_probes']>=5
        self.visibility_counts['N']+=1;self.visibility_counts['visible']+=int(visible)
        self.blind_s=0. if visible else self.blind_s+.1;self.max_blind_s=max(self.max_blind_s,self.blind_s)
        if visible:
            g=truth['beam']['ends'][self.end]
            self.local_seen=[*local(truth['robots'][self.rid]['pose'],g),g[2]+.009]
            self.last_seen_t=now
        for iid in vis.get('objects',[]):self.observed_objects[iid]=deepcopy(truth['objects'][iid])
        for rid in vis.get('peers',[]):
            self.observed_peers[rid]=deepcopy(truth['robots'][rid]);self.observed_peers[rid]['seen_t']=now
        self.observed_peers={r:v for r,v in self.observed_peers.items() if now-v['seen_t']<=8.}
        if self.local_seen is not None and now-self.last_seen_t<=MEMORY_S:
            pose=truth['robots'][self.rid]['pose']
            occluders=[{'xy':local(pose,v['pose']),'radius':v.get('radius',.17),
                        'top_z_bound_m':v.get('top_z_bound_m',.32)}
                       for rid,v in truth['robots'].items() if rid!=self.rid]
            occluders += [{'xy':local(pose,v['xy']),'radius':v['radius'],
                          'top_z_bound_m':v['top_z_bound_m']}
                         for key,v in truth['objects'].items() if key!='beam_1']
            target=gaze_pose(self.local_seen,self.sink.pwm,occluders,visible=visible)
        else:
            # Clock starts at the issued local-skill instruction, not hidden
            # visibility events. Exactly the same elapsed scalar goes to ACT.
            age=now-self.skill_started
            near=age<2. or (age>=3.2 and int((age-3.2)/1.2)%2==0)
            target={**FOLDED,3:500 if near else 820,4:2500 if near else 2320,6:1500}
        self.sink.pwm.update(slew(self.sink.pwm,target));self.arm.commanded.update(self.sink.pwm)
        if visible:return None
        if self.last_seen_t is not None and now-self.last_seen_t<=MEMORY_S:return self._hold(now)
        if now-self.skill_started<3.2:return self._hold(now)
        return self._continuous(now,0.,0.,.45)

    def ready_geometry(self,truth):
        if truth['beam'] is None or truth['visibility'][self.rid]['visible_probes']<5:return False
        pose,g,heading,goal=self._geometry(truth)
        x,y=local(pose,g)
        try:grasp_poses((x,y,g[2]))
        except ValueError:return False
        return math.dist(pose[:2],goal)<=XY_TOL_M and abs(wrap(heading-pose[2]))<=YAW_TOL_RAD

    def prepare_signal(self,truth,now):
        """Own teacher readiness; only a binary READY crosses the protocol."""
        if self.phase=='ready' and not self.ready_geometry(truth):
            self.ready_revocations+=1;self._set('align',now)
        return self.phase in ('ready','pick','complete')

    def step(self,truth,now,*,permit_pick=False):
        if self.local_seen is not None and self.last_command is not None and self.last_tick is not None:
            self.local_seen=propagate_owned(self.local_seen,self.last_command,min(.1,now-self.last_tick))
        value,done=self._step(truth,now,permit_pick=permit_pick)
        self.last_command=deepcopy(value);self.last_tick=now
        return value,done

    def remember_applied(self,value):
        # DART may alter the label command before it is sent. The observer
        # integrates what was actually issued, which is also in student input.
        self.last_command=deepcopy(command(value))

    def _step(self,truth,now,*,permit_pick):
        if not self.started:
            self.started=True;self.phase_t=now;self.skill_started=now
            self.arm.queue({**FOLDED,6:self.sink.pwm[6]},now,duration=.5)
        arms_done=self.arm.tick(now)
        self.folded_ready=arms_done and 500<=self.sink.pwm[3]<=960 and 2320<=self.sink.pwm[4]<=2500 and self.sink.pwm[5]==1320
        if self.command_complete:return self._hold(now),True
        if now-self.phase_t>60:
            self.outcome='phase_timeout';return self._hold(now),False
        self.rects=truth.get('walls',[])
        self.observed_objects=deepcopy(truth.get('objects',{}))
        self.observed_peers={r:{**deepcopy(v),'seen_t':now} for r,v in truth['robots'].items() if r!=self.rid}
        if self.teacher_stability!='off' and self.phase=='relook':
            search=self._observe(truth,now)
            if search is not None:return search,False
            if now-self.phase_t>=.4:self._set('approach',now)
            return self._hold(now),False
        if self.phase in ('approach','align','ready','search'):
            if not arms_done:return self._hold(now),False
            search=self._observe(truth,now)
            if search is not None:
                if self.phase=='ready':self._set('align',now)
                return search,False
            if not arms_done:return self._hold(now),False
            pose=truth['robots'][self.rid]['pose'];g=truth['beam']['ends'][self.end]
            if not self.handoff and math.dist(pose[:2],g[:2])<=.8:
                self.handoff=True;self.skill_started=now
            self.prepare_signal(truth,now)
            if self.phase!='ready':
                value,ready=self._approach(truth,now)
                if ready:self._set('ready',now)
                return value,False
            if permit_pick:
                # Revalidate immediately before committing the fixed motion.
                if not self.ready_geometry(truth):self._set('align',now)
                else:self._queue_pick(truth,now)
            return self._hold(now),False
        if self.phase=='pick' and arms_done:
            self.command_complete=True;self._set('complete',now)
            # No contact, object height, GT timer or success field decides done.
            return self._hold(now),True
        return self._hold(now),False

    def diagnostic(self):
        return {**super().diagnostic(),'profile':'visible_only','command_complete':self.command_complete,
                'ready_revocations':self.ready_revocations,'handoff':self.handoff,
                'blocked_goal_calls':self.blocked_goal_calls,
                'teacher_stability':self.teacher_stability,'alignment_relooks':self.align_relooks,
                'done_semantics':'own issued arm sequence complete; physical evaluation separate'}
