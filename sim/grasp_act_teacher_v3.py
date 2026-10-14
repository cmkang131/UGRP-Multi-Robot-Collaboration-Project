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
        # search_body_scan_v1: pan sweep + in-place 8-direction body scan only.
        self.teacher_search=kwargs.pop('teacher_search','off')
        if self.teacher_search not in ('off','search_body_scan_v1','search_body_scan_v2'):
            raise ValueError('unknown teacher search mode')
        if self.teacher_search!='off' and self.teacher_stability=='off':
            raise ValueError('teacher search requires align_relook_v1')
        self.approach_goal_set=kwargs.pop('approach_goal_set','off')
        if self.approach_goal_set not in ('off','approach_goal_set_v1'):
            raise ValueError('unknown approach goal set mode')
        if self.approach_goal_set!='off' and self.teacher_stability=='off':
            raise ValueError('approach goal set requires align_relook_v1')
        self.nominal_blocked_handoff=kwargs.pop('nominal_blocked_handoff','off')
        if self.nominal_blocked_handoff not in ('off','nominal_blocked_handoff_v1'):
            raise ValueError('unknown nominal blocked handoff mode')
        if self.nominal_blocked_handoff!='off' and self.teacher_stability=='off':
            raise ValueError('nominal blocked handoff requires align_relook_v1')
        self.approach_progress=kwargs.pop('approach_progress','off')
        if self.approach_progress not in ('off','approach_progress_v1'):
            raise ValueError('unknown approach progress mode')
        if self.approach_progress!='off' and self.teacher_stability=='off':
            raise ValueError('approach progress requires align_relook_v1')
        from sim.grasp_act_progress import ApproachProgress
        self.progress=ApproachProgress();self.progress_log=[]
        self.nominal_handoff_log=[]
        self.approach_choice=(0.,STATION_M);self.goal_set_log=[]
        self.approach_blocked_since=None;self.approach_plan_valid=False
        self.sc=None;self.search_log=[];self.ever_seen=False
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
        if self._nominal_handoff(truth,now):return self._hold(now),False
        use_goals=self._uses_goal_set(truth)
        if use_goals:
            from sim.grasp_act_visible_route import constraints,free
            pose,g,heading,goal=self._geometry(truth)
            radius,discs,rects=constraints(truth,self.rid,self.folded_ready)
            if self.phase in ('align','ready') and (not self.approach_plan_valid or not free(goal,discs,rects,radius)):
                self._set('approach',now);self._reset_alignment();self.next_plan=now
            if self.phase=='approach' and not self._plan_approach(truth,now):
                return self._hold(now),False
        pose,g,heading,goal=self._geometry(truth)
        if self.phase=='approach' and math.dist(pose[:2],goal)>.08:
            return self._route(truth,goal,heading,now),False
        if self.phase=='approach':self._set('align',now);self._reset_alignment()
        gx,gy=local(pose,g);errors=(gx-self.staging_distance,gy,wrap(heading-pose[2]))
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
            self.search_since=None;self.sc=None;self.ever_seen=True
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
            if self.teacher_search!='off' and self.phase=='search' and not self.ever_seen:
                # Never-seen target (ever_seen, not local_seen: a relook clears local_seen).
                target,value=(self._search_step_v2(now,age) if self.teacher_search=='search_body_scan_v2'
                              else self._search_step(now,age))
                self.sink.pwm.update(slew(self.sink.pwm,target));self.arm.commanded.update(self.sink.pwm)
                if self.teacher_search=='search_body_scan_v2':
                    # The returned command must contain this tick's slewed pose,
                    # not the pre-slew snapshot made by _hold/_continuous.
                    value['pwm']={str(s):self.sink.pwm[s] for s in SERVOS}
                return value
            # Full stationary pan/pitch sweep before turning the chassis.
            # All targets depend on issued scan age, never a hidden pose.
            pans=(self.initial_search_pan,1500,1000,2000,500,2500)
            slot=int(age/.6)%(2*len(pans));near=slot%2==0
            target={**FOLDED,3:500 if near else 820,4:2500 if near else 2320,6:pans[slot//2]}
        self.sink.pwm.update(slew(self.sink.pwm,target));self.arm.commanded.update(self.sink.pwm)
        if visible:return None
        if age<7.2:return self._hold(now)
        return self._continuous(now,0.,0.,.25)

    SEARCH_LIMIT_S=33.      # backstop; one full scan normally ends at ~24 SIM s
    SWEEP_PANS=(1000,1500,2000)
    SLOT_S=.6
    SCAN_STEPS=8            # 45 deg body directions, in place, same command ACT can issue
    # Real/nominal yaw of this turn command (width ~0.05 s): 0.73 on seed 76015's
    # search rotation (300 ticks); 0.69-0.78 over 9 GCP gate episodes. Pulse
    # widths differ: full-width 0.1 s yaw ticks measured 1.75 (see search-body-scan.md).
    TURN_GAIN=.73

    # v2 covers the close peer stance (203 mm) as well as middle/far targets.
    # Each pitch gets a continuous revolution: a close target's horizontal
    # cone is narrower than 45 deg because the camera is ahead of the axle.
    SEARCH_V2_LIMIT_S=58.
    SEARCH_V2_PITCHES=((500,2500),(700,2440),(820,2320))
    SEARCH_V2_CIRCLE_PITCHES=tuple(reversed(SEARCH_V2_PITCHES))
    SEARCH_V2_TURN_RAD=math.radians(390.)  # >=360 at measured gains .69..78
    SEARCH_V2_SETTLE_S=.3

    def _search_step_v2(self,now,age):
        """Issued pan/tilt settle, then three in-place pitch-specific circles.

        No target, spawn, map or measured pose input. Visibility is still
        evaluated on every tick, including turns, by the unchanged >=5 gate.
        """
        from harness.grasp_act_visible_world import command_delta
        if self.outcome is not None:return dict(self.sink.pwm),self._hold(now)
        sweep=[(pan,w,e) for pan in (1500,1000,2000) for w,e in self.SEARCH_V2_PITCHES]
        if self.sc is None:
            self.sc={'stage':'sweep','k':0,'view':0,'turned':0.,'settled_t':None}
        sc=self.sc
        if sc['stage']=='turn' and self.last_command is not None and self.last_tick is not None:
            sc['turned']+=abs(command_delta(self.last_command,min(.1,now-self.last_tick))[2])*self.TURN_GAIN
        def log(stage):
            row={'t':round(now,2),'stage':stage,'k':sc['k'],
                 'command_estimated_yaw_deg':round(math.degrees(sc['turned']),2)}
            self.search_log.append(row);self.events.append({**row,'search':stage})
        def handoff(reason):
            self.outcome='search_timeout_handoff';log(reason)
            return dict(self.sink.pwm),self._hold(now)
        if age>=self.SEARCH_V2_LIMIT_S:return handoff('scan_deadline_handoff')
        if sc['stage']=='turn' and sc['turned']>=self.SEARCH_V2_TURN_RAD:
            log('circle_complete');sc['k']+=1
            if sc['k']==len(self.SEARCH_V2_CIRCLE_PITCHES):return handoff('handoff')
            sc.update(stage='settle',settled_t=None,turned=0.)
        if sc['stage']=='sweep':pan,w,e=sweep[sc['view']]
        else:pan=1500;w,e=self.SEARCH_V2_CIRCLE_PITCHES[sc['k']]
        target={**FOLDED,3:w,4:e,6:pan}
        if sc['stage']=='turn':return target,self._continuous(now,0.,0.,.25)
        # Dwell starts only once the target has actually been issued. This
        # handles extreme initial pans and does not read measured joints.
        reached=self.last_command is not None and all(self.last_command['pwm'][str(s)]==v for s,v in target.items())
        sc['settled_t']=(now if sc['settled_t'] is None else sc['settled_t']) if reached else None
        if sc['settled_t'] is not None and now-sc['settled_t']>=self.SEARCH_V2_SETTLE_S-1e-8:
            if sc['stage']=='sweep':
                log('view_complete');sc['view']+=1
                if sc['view']==len(sweep):sc['stage']='settle'
            else:sc['stage']='turn';log('circle_start')
            sc['settled_t']=None
        return target,self._hold(now)

    def _scan_target(self,age,pans):
        slot=int(age/self.SLOT_S);near=slot%2==0
        # 700/2440 sees 0.26-0.92 m ahead, 820/2320 0.45 m to the horizon (camera FK).
        return {**FOLDED,3:700 if near else 820,4:2440 if near else 2320,6:pans[min(slot//2,len(pans)-1)]}

    def _search_step(self,now,age):
        """search_body_scan_v1. Only own issued commands drive it: a pan/tilt sweep,
        then seven 45 deg in-place turns with a short dwell each, then hand off.
        No map, no pose, no object or peer position. Map moves are not ACT's job."""
        from harness.grasp_act_visible_world import command_delta
        look={**FOLDED,3:820,4:2320,6:1500}
        if self.sc is None:
            self.sc={'stage':'sweep','t0':now,'k':0,'turned':0.}
        sc=self.sc
        if self.last_command is not None and self.last_tick is not None and sc['stage']=='turn':
            sc['turned']+=abs(command_delta(self.last_command,min(.1,now-self.last_tick))[2])*self.TURN_GAIN
        def log(stage):
            self.search_log.append({'t':round(now,2),'stage':stage,'k':sc['k']})
            self.events.append({'t':now,'search':stage,'k':sc['k']})
        def handoff():
            if self.outcome is None:
                self.outcome='search_timeout_handoff';log('handoff')
            return look,self._hold(now)
        if age>self.SEARCH_LIMIT_S:return handoff()
        if sc['stage']=='sweep':
            span=len(self.SWEEP_PANS)*2*self.SLOT_S
            if now-sc['t0']<span:return self._scan_target(now-sc['t0'],self.SWEEP_PANS),self._hold(now)
        elif sc['stage']=='dwell':
            if now-sc['t0']<2*self.SLOT_S:return self._scan_target(now-sc['t0'],(1500,)),self._hold(now)
        elif sc['stage']=='turn':
            if sc['turned']<math.pi/4 and now-sc['t0']<6.:
                return look,self._continuous(now,0.,0.,.25)
            sc['k']+=1;sc.update(stage='dwell',t0=now,turned=0.);log('dwell')
            return self._scan_target(0.,(1500,)),self._hold(now)
        # sweep or dwell finished
        log('swept' if sc['stage']=='sweep' else 'dwelled')
        if sc['k']>=self.SCAN_STEPS-1:return handoff()
        sc.update(stage='turn',t0=now,turned=0.)
        return look,self._hold(now)

    def _geometry(self,world):
        if self.approach_goal_set!='off':
            from sim.grasp_act_goal_set import geometry
            return geometry(world,self.rid,self.end,self.approach_choice)
        pose=world['robots'][self.rid]['pose'];g=world['beam']['ends'][self.end]
        heading=world['beam']['pose'][2]+(math.pi if self.end=='blue' else 0.)
        goal=(g[0]-STATION_M*math.cos(heading),g[1]-STATION_M*math.sin(heading))
        return pose,g,heading,goal

    APPROACH_BLOCKED_LIMIT_S=3.

    def _nominal_handoff(self,world,now):
        if self.nominal_blocked_handoff=='off' or self.outcome is not None:return False
        if world['beam'] is None or world['visibility'][self.rid]['visible_probes']<5:return False
        from sim.grasp_act_goal_set import nominal_goal_blocked,geometry
        if not nominal_goal_blocked(world,self.rid,self.end,self.bounds,self.folded_ready,static_map_only=True):return False
        self.outcome='approach_blocked_handoff';self.path=[];self.approach_plan_valid=False
        row={'t':now,'approach':'nominal_blocked_handoff','goal':geometry(world,self.rid,self.end,(0.,STATION_M))[3],
             'reason':'approach_blocked_handoff','criterion':'static_map_only',
             'alternative_candidates_used':False,'input':'visible assigned band + visible/remembered walls; issued pose'}
        self.nominal_handoff_log.append(row);self.events.append(row)
        return True

    def _uses_goal_set(self,world):
        # Keep the alternative implementation for the OFF comparison. With
        # map handoff enabled, every clear nominal case uses the original law.
        if self.nominal_blocked_handoff!='off':return False
        if self.approach_goal_set=='off':return False
        # A failed set stays active until a full collision/path check succeeds.
        # A static obstacle disappearing does not prove a peer-occupied goal safe.
        if self.approach_blocked_since is not None:return True
        # Once selected, retain the end-relative stance through alignment/READY.
        # Until then the exact original planner, cadence and readiness law run.
        if self.approach_choice!=(0.,STATION_M):return True
        from sim.grasp_act_goal_set import nominal_goal_blocked
        return nominal_goal_blocked(world,self.rid,self.end,self.bounds,self.folded_ready)

    def _approach_handoff(self,now):
        self.outcome='approach_blocked_handoff';self.path=[];self.approach_plan_valid=False
        self.events.append({'t':now,'approach':'all_goals_blocked_handoff',
                            'blocked_s':now-self.approach_blocked_since})

    def _plan_approach(self,world,now):
        if self.nominal_blocked_handoff!='off':
            self._nominal_handoff(world,now)
            return False
        from sim.grasp_act_goal_set import select_goal
        from sim.grasp_act_visible_route import constraints,free,waypoint
        pose,g,heading,goal=self._geometry(world)
        radius,discs,rects=constraints(world,self.rid,self.folded_ready)
        self.planning_radius=radius
        changed=self.path_goal is None or math.dist(goal,self.path_goal)>.025
        blocked=not free(goal,discs,rects,radius)
        unusable=self.path and math.dist(pose[:2],goal)>.08 and waypoint(pose[:2],self.path,discs,rects,radius) is None
        entering=not self.approach_plan_valid and self.approach_blocked_since is None
        if entering or changed or now>=self.next_plan or (self.approach_plan_valid and (blocked or unusable)):
            selected,checked=select_goal(world,self.rid,self.end,self.bounds,self.folded_ready,self.approach_choice)
            self.planner_calls+=1;self.next_plan=now+1.;self.path_goal=tuple(goal)
            self.blocked_goal_calls+=int(blocked)
            self.approach_plan_valid=selected is not None
            self.no_path_calls+=int(selected is None)
            row={'t':now,'candidates':checked,'selected':None}
            if selected is None:
                self.path=[]
                if self.approach_blocked_since is None:self.approach_blocked_since=now
            else:
                self.approach_choice=selected['choice'];self.staging_distance=self.approach_choice[1]
                self.path=selected['path'];self.path_goal=tuple(selected['goal'])
                self.approach_blocked_since=None
                row['selected']={k:v for k,v in selected.items() if k!='path'}
            self.goal_set_log.append(row)
        if self.approach_blocked_since is not None and now-self.approach_blocked_since>=self.APPROACH_BLOCKED_LIMIT_S-1e-8:
            self._approach_handoff(now)
        return self.approach_plan_valid

    def _route(self,world,goal,heading,now):
        from sim.grasp_act_visible_route import constraints,free,segment_free,waypoint,drive
        from scripts.zone_teacher import plan_path
        pose=world['robots'][self.rid]['pose']
        if self.approach_progress!='off':
            recovery=self.progress.observe(pose[:2],now)
            if recovery is not None:
                row={'t':now,'approach_progress':recovery,'phase':self.phase,
                     'required_movement_m':self.progress.required_movement_m,
                     'allowance_s':self.progress.allowance_s,
                     'planner_calls':self.planner_calls,'no_path_calls':self.no_path_calls,
                     'blocked_goal_calls':self.blocked_goal_calls,
                     'reason':'no_issued_pose_progress','input':'issued-command pose only'}
                self.progress_log.append(row);self.events.append(row)
                self.path=[];self.path_goal=None;self.next_plan=now
                self.approach_plan_valid=False
                if recovery=='handoff':
                    self.outcome='approach_blocked_handoff'
                    return self._hold(now)
        if self._uses_goal_set(world):
            if not self._plan_approach(world,now):return self._hold(now)
            pose,g,heading,goal=self._geometry(world)
            radius,discs,rects=constraints(world,self.rid,self.folded_ready)
            target=waypoint(pose[:2],self.path,discs,rects,radius)
            if target is None:return self._hold(now)
            return self._continuous(now,**drive(pose,goal,target,g))
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
        if self.nominal_blocked_handoff!='off':
            from sim.grasp_act_goal_set import nominal_goal_blocked
            if nominal_goal_blocked(truth,self.rid,self.end,self.bounds,self.folded_ready,static_map_only=True):return False
        pose,g,heading,goal=self._geometry(truth)
        if self._uses_goal_set(truth):
            if not self.approach_plan_valid or self.approach_blocked_since is not None:return False
            from sim.grasp_act_visible_route import constraints,free
            radius,discs,rects=constraints(truth,self.rid,self.folded_ready)
            if not free(goal,discs,rects,radius):return False
        x,y=local(pose,g)
        try:grasp_poses((x,y,g[2]))
        except ValueError:return False
        return math.dist(pose[:2],goal)<=XY_TOL_M and abs(wrap(heading-pose[2]))<=YAW_TOL_RAD

    def prepare_signal(self,truth,now):
        """Own teacher readiness; only a binary READY crosses the protocol."""
        if self.outcome is not None:return False
        if self.phase in ('approach','align','ready','search','relook') and self._nominal_handoff(truth,now):return False
        if self.phase=='ready' and not self.ready_geometry(truth):
            self.ready_revocations+=1;self._set('align',now)
        return self.phase in ('ready','pick','complete')

    def step(self,truth,now,*,permit_pick=False):
        if self.local_seen is not None and self.last_command is not None and self.last_tick is not None:
            self.local_seen=propagate_owned(self.local_seen,self.last_command,min(.1,now-self.last_tick))
        value,done=self._step(truth,now,permit_pick=permit_pick)
        # READY waiting belongs to GO/ACK, and fine alignment has its own
        # error-progress checker. A search detour does not erase route debt.
        if self.phase in ('align','ready','pick','complete'):self.progress.reset()
        self.last_command=deepcopy(value);self.last_tick=now
        return value,done

    def remember_applied(self,value):
        # DART may alter the label command before it is sent. The observer
        # integrates what was actually issued, which is also in student input.
        self.last_command=deepcopy(command(value))

    def _step(self,truth,now,*,permit_pick):
        if self.outcome is not None:return self._hold(now),False
        if (self.approach_blocked_since is not None and truth['beam'] is not None
                and truth['visibility'][self.rid]['visible_probes']>=5):
            # A fresh view may recover before the deadline, but only after the
            # complete candidate check (static obstacles, peers and route).
            self._plan_approach(truth,now)
            if self.outcome is not None:return self._hold(now),False
        # Losing sight cannot reset a blocked approach's finite deadline.
        if self.approach_blocked_since is not None and now-self.approach_blocked_since>=self.APPROACH_BLOCKED_LIMIT_S-1e-8:
            self._approach_handoff(now);return self._hold(now),False
        if not self.started:
            self.started=True;self.phase_t=now;self.skill_started=now
            self.arm.queue({**FOLDED,6:self.sink.pwm[6]},now,duration=.5)
        arms_done=self.arm.tick(now)
        self.folded_ready=arms_done and 500<=self.sink.pwm[3]<=960 and 2320<=self.sink.pwm[4]<=2500 and self.sink.pwm[5]==1320
        if self.phase in ('approach','align','ready','search','relook') and self._nominal_handoff(truth,now):return self._hold(now),False
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
                'teacher_search':self.teacher_search,'search_log':self.search_log,
                'approach_goal_set':self.approach_goal_set,'goal_set_log':self.goal_set_log,
                'nominal_blocked_handoff':self.nominal_blocked_handoff,'nominal_handoff_log':self.nominal_handoff_log,
                'approach_progress':self.approach_progress,'approach_progress_log':self.progress_log,
                'alternative_goal_path_enabled':self.approach_goal_set!='off' and self.nominal_blocked_handoff=='off',
                'done_semantics':'own issued arm sequence complete; physical evaluation separate'}
