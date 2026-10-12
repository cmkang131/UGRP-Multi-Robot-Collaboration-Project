"""Own-input S3 command executive using the frozen calibrated S3 primitives.

No authored Runtime shell, fixture entrance, teacher pose or automatic claim.
Every movement is issued only after the received OwnRoute approval. A route
which cannot be represented in the calibrated carrier axes is rejected.
"""
import copy
import math
from types import SimpleNamespace
from harness import e2e_own_inputs as own
from harness.e2e_goal_route import provider_plan
from harness.e2e_pulse_budget import pulse_schedule
from harness.e2e_setdown_relook import boundary_reasons
from harness.zone_s3_coarse_fine import Servo, postures
from harness.zone_s3_synchronized_carry import joint_plan
from harness.zone_s3_alignment_ownership import ALL
from harness.zone_pair_highpose import raise_path, lower_path

PAIR=('r1','r2')


class AgreementView:
    """Adapter to existing provider-plan checks; never manufactures a receipt."""
    def __init__(self,dialogue):self.dialogue=dialogue
    @property
    def approved(self):return self.dialogue.approved
    @property
    def proposal(self):
        p=self.dialogue.proposal
        return (p['route']['route_hash'],p['message_id']) if p else None


class Transport:
    def __init__(self,robots,dialogue,profiles,*,pulse_budget='off',setdown_only_when_relook='off',dev_light=False,carrier_approach='off',align_progress='off',pregrasp_recovery='off',pregrasp_gaze='off',search_bearing='off',pregrasp_progress='off'):
        self.robots,self.dialogue,self.profiles=robots,dialogue,profiles
        self.pulse_budget=pulse_budget;self.relook_option=setdown_only_when_relook
        self.state='mapping';self.stage_t=0.;self.seg=0;self.first_seg=0;self.epoch=0
        self.plan=None;self.events=[];self.failure=None;self.done=False;self.setdowns=0
        self.align={r:Servo(r,profiles,ALL,joint_plan) for r in PAIR}
        self.aligned={};self.queue=[];self.queue_until=0.;self.permit=None
        self.authorizations={};self.used=set();self.last_route_error=None
        self.final_correction=False
        self.dev_light=dev_light;self.would_stops=set()
        if carrier_approach not in ('off','standoff_v1'):raise ValueError('UNKNOWN_CARRIER_APPROACH')
        self.carrier_approach=carrier_approach;self.approach={}
        if align_progress not in ('off','dev_continue_v1') or pregrasp_recovery not in ('off','bounded_search_v1'):raise ValueError('UNKNOWN_ALIGN_RECOVERY')
        self.align_progress=align_progress;self.pregrasp_recovery=pregrasp_recovery
        if pregrasp_gaze not in ('off','own_bearing_v1') or search_bearing not in ('off','last_seen_v1'):raise ValueError('UNKNOWN_PREGRASP_GAZE')
        self.pregrasp_gaze=pregrasp_gaze;self.search_bearing=search_bearing
        if pregrasp_progress not in ('off','backup_replan_v1'):raise ValueError('UNKNOWN_PREGRASP_PROGRESS')
        self.pregrasp_progress=pregrasp_progress

    def event(self,t,kind,**data):self.events.append(dict(t=t,event=kind,**data))
    def set(self,state,t):self.state=state;self.stage_t=t;self.event(t,'phase',state=state,seg=self.seg,epoch=self.epoch)
    def fail(self,reason,t):
        self.failure=reason;self.queue.clear();self.permit=None
        self.set('failed',t)
        return [(r,dict(kind='hold')) for r in PAIR]

    def observation_timeout(self,reason,t):
        if not self.dev_light:return self.fail(reason,t)
        key=(self.state,self.epoch,self.seg,reason)
        if key not in self.would_stops:
            self.event(t,'would_stop',reason=reason,state=self.state,dev_light=True)
            self.would_stops.add(key)
        return []

    def _poses(self,rid,now,path):
        # Fixed command-space trajectory, one common start, no servo measurements.
        start=now
        for pose,duration,settle in path:
            original=self.robots[rid].servo if start==now else previous
            n=max(1,round(duration/.05))
            for i in range(1,n+1):
                at=start+i*duration/n
                for sid,value in pose.items():
                    command=dict(kind='look',pan_pulse=round(original.get(sid,value)+(value-original.get(sid,value))*i/n)) if sid==6 else dict(
                        kind='arm',servo_id=sid,pulse=round(original.get(sid,value)+(value-original.get(sid,value))*i/n))
                    self.queue.append((round(at,8),rid,command))
            previous={**original,**pose};start+=duration+settle
        self.queue_until=max(self.queue_until,start)
        self.queue.sort(key=lambda row:(row[0],row[1]))

    def _drain(self,now):
        out=[]
        while self.queue and self.queue[0][0]<=now+1e-8:
            _,rid,command=self.queue.pop(0);out.append((rid,command))
        return out

    def _route(self,now):
        r1=self.robots['r1']
        if r1.packet is None:
            try:packet=r1.route(self.profiles,self.pulse_budget)
            except own.ContractViolation as exc:
                reason=str(exc)
                if reason!=self.last_route_error:self.event(now,'own_route_wait',reason=reason)
                self.last_route_error=reason
                return
            if packet is not None:
                r1.packet=packet
                self.event(now,'own_map_B_route_generated',route_hash=packet['route']['route_hash'],
                    B_rgb_sources=packet['route']['B_rgb_sources'],length_m=packet['compiled']['length_m'],
                    observed_coverage_complete=packet.get('observed_coverage_complete',True))
        if r1.packet is not None and self.dialogue.approved and self.dialogue.claims==set(PAIR):
            self.plan=provider_plan(r1.packet,agreement=AgreementView(self.dialogue),now=now,
                observed=r1.goal.e2e_observed,profiles=self.profiles)
            self.set('align',now)

    def _align(self,now):
        out=[]
        for rid in PAIR:
            r=self.robots[rid];b=r.beam
            if rid in self.aligned:continue
            if self.carrier_approach!='off':
                from harness.e2e_carrier_approach import advance
                fine,actions=advance(self,rid,now)
                out.extend((rid,a) for a in actions)
                if not fine:continue
            if b is None or now-b['rgb']['t_sim']>.25:continue
            # Require the actual common carrier orientation. A same-facing pair
            # cannot be sent opposite body commands simply because roles differ.
            from harness.active_wall_mapping import wrap
            yaw=r.goal.explorer.local_pose[2]
            required=0. if rid=='r1' else math.pi
            if self.carrier_approach=='off' and abs(wrap(yaw-required))>math.radians(5):
                self.event(now,'own_carrier_axes_unavailable',robot_id=rid)
                continue
            phase,value=self.align[rid].observe(now,r.last_obs,r.servo,b['grip_base_m'],b['axis_heading_rad'])
            self.event(now,'s3_coarse_fine',robot_id=rid,phase=phase)
            if phase=='base':out.append((rid,value))
            elif phase=='pan':out.append((rid,dict(kind='look',pan_pulse=value)))
            elif phase=='ready':self.aligned[rid]=value
        if len(self.aligned)==2:
            self.epoch+=1
            for rid in PAIR:
                hover,descent=postures(self.aligned[rid])
                self._poses(rid,now,[(dict(hover)|{1:2000},.8,.6),
                    *[(dict(p)|{1:2000},.25,.1) for p in descent],({1:1500},.5,.4),
                    (dict(hover)|{1:1500},.8,.4),
                    *[(dict(p)|{1:1500},d,s) for p,d,s in raise_path()]])
            self.set('grasp_lift',now)
        elif now-self.stage_t>75:
            stopped=self.observation_timeout('OWN_RGB_ALIGNMENT_TIMEOUT',now)
            if not (self.dev_light and self.align_progress=='dev_continue_v1'):return stopped
            out+=stopped
        return out

    def _open_epoch(self,now):
        self.dialogue.begin_epoch(order_id='order-5',route_hash=self.plan['agreement_route_hash'],
                                  grip_epoch=self.epoch,seg=self.seg,now=now)
        self.set('wait_go_ack',now)

    def _carry(self,now):
        if not self.dialogue.allowed(self.dialogue.key,now):return False
        if any(self.robots[r].servo.get(1)!=1500 for r in PAIR):
            raise own.ContractViolation('OWN_ISSUED_GRIP_LOST')
        self.permit=tuple(self.dialogue.key)
        for rid in PAIR:
            ctl=SimpleNamespace(rid=rid,seg=self.seg,v3_plan=self.plan,claims={},log=lambda *a,**k:None)
            schedule,duration=pulse_schedule(ctl,now,self.profiles,option=self.pulse_budget)
            for i,(start,end,action) in enumerate(schedule):
                if not any(action.values()):continue
                dur=ctl.claims['segments'][-1].get('pulse_durations_s',[duration]*len(schedule))[i]
                command=dict(kind='mecanum',**action,duration_s=dur)
                self.queue.append((start,rid,command))
                self.authorizations[(rid,round(start,8))]=(self.permit,copy.deepcopy(command))
            self.queue_until=max(self.queue_until,schedule[-1][1])
        self.queue.sort(key=lambda row:(row[0],row[1]))
        self.set('carry',now)
        self.event(now,'s3_synchronized_segment',key=list(self.permit),source='received_own_route',
                   pulse_budget=self.pulse_budget,planned_m=self.plan['own_route']['legs'][self.seg]['distance_m'])
        return True

    def authorize(self,rid,command,now):
        identity=(rid,round(now,8));row=self.authorizations.get(identity)
        if row is None or identity in self.used or self.state!='carry' or row!=(self.permit,command):return False
        if self.permit!=self.dialogue.key or self.robots[rid].servo.get(1)!=1500:return False
        self.used.add(identity);return True

    def _after_carry(self,now):
        compiled=self.plan['own_route'];final=self.seg==len(compiled['legs'])-1
        reasons=boundary_reasons(compiled,self.first_seg,self.seg,self.robots['r1'].goal.pose_covariance()) if self.relook_option!='off' else ['legacy_segment']
        if not reasons and not final:
            self.seg+=1;self._open_epoch(now);return
        self.event(now,'setdown_relook_boundary',reasons=reasons)
        if final:
            self.set('final_rgb_wait',now);return
        self._lower(now)

    def _lower(self,now):
        for rid in PAIR:
            self._poses(rid,now,[*[(dict(p)|{1:1500},d,s) for p,d,s in lower_path()],({1:2000},.5,1.2)])
        self.set('lower_open',now)

    def _final_reobserve(self,now):
        robot=self.robots['r1'];goal=robot.goal;b=robot.beam
        if b is None:return
        beam={k:b[k] for k in ('rgb','pose_own_m')}
        changed=goal.reobserve_setdown(robot.packet,beam,now=now,profiles=self.profiles,
                                      agreement=self.dialogue,pulse_budget=self.pulse_budget)
        if changed['status']!='REAPPROVAL_REQUIRED':return
        robot.packet=changed['pending_route'];self.dialogue.claims=set()
        self.final_correction=math.dist(b['pose_own_m'][:2],goal.e2e_pending_setdown['boundary_center'])>.02
        self.event(now,'final_B_RGB_reobserved',rgb=b['rgb'],
            revised_route_hash=robot.packet['route']['route_hash'],endpoint_correction_required=self.final_correction)
        self.set('final_route_approval',now)

    def step(self,now):
        if self.failure or self.done:return []
        out=self._drain(now)
        if self.queue or now<self.queue_until-1e-8:return out
        if self.state=='mapping':self._route(now)
        elif self.state=='align':out+=self._align(now)
        elif self.state=='grasp_lift':self._open_epoch(now)
        elif self.state=='wait_go_ack':
            if not self._carry(now) and now-self.stage_t>15:out+=self.fail('CURRENT_GO_ACK_TIMEOUT',now)
        elif self.state=='carry':self._after_carry(now)
        elif self.state=='final_rgb_wait':
            if now-self.stage_t>15:out+=self.observation_timeout('FINAL_OWN_RGB_REOBSERVATION_TIMEOUT',now)
            if not self.failure:self._final_reobserve(now)
        elif self.state=='final_route_approval':
            if self.dialogue.approved and self.dialogue.claims==set(PAIR):
                robot=self.robots['r1']
                self.plan=provider_plan(robot.packet,agreement=AgreementView(self.dialogue),now=now,
                    observed=robot.goal.e2e_observed,profiles=self.profiles)
                self.epoch+=1;self.seg=0 if self.final_correction else len(self.plan['own_route']['legs'])-1
                self.first_seg=self.seg;self._open_epoch(now)
                if not self.final_correction:self.set('final_lower_go_ack',now)
            elif now-self.stage_t>20:out+=self.fail('FINAL_ROUTE_REAPPROVAL_TIMEOUT',now)
        elif self.state=='final_lower_go_ack':
            robot=self.robots['r1'];b=robot.beam
            if b is not None and self.dialogue.allowed(self.dialogue.key,now):
                from harness.self_odom_grid import transform
                corners=transform([[-.30,-.025],[-.30,.025],[.30,.025],[.30,-.025]],b['pose_own_m']).tolist()
                gate=SimpleNamespace(ready=True,key=self.dialogue.key)
                if robot.goal.setdown_ready(dict(rgb=b['rgb'],polygon_own_m=corners),now=now,agreement=gate,
                        order_id='order-5',grip_epoch=self.epoch,seg=self.seg):self._lower(now)
            if self.state=='final_lower_go_ack' and now-self.stage_t>20:
                out+=self.fail('FINAL_LOWER_RGB_OR_GO_ACK_TIMEOUT',now)
        elif self.state=='lower_open':
            from harness.active_camera import SEARCH
            self.setdowns+=1
            for rid in PAIR:self._poses(rid,now,[(SEARCH,.8,.7)])
            self.set('relook_camera',now)
        elif self.state=='relook_camera':
            for rid in PAIR:self.robots[rid].goal.e2e_relook.request(now,seg=self.seg,epoch=self.epoch)
            self.set('relook',now)
        elif self.state=='relook':
            if all(self.robots[r].goal.e2e_relook.receipt is not None for r in PAIR):
                self.event(now,'e2e_pose_corrections_applied',receipts={r:self.robots[r].goal.e2e_relook.receipt for r in PAIR})
                if self.seg==len(self.plan['own_route']['legs'])-1:
                    self.done=True;self.set('done',now)
                else:
                    # A corrected endpoint requires a newly computed, delivered,
                    # approved route; the old claim/GO never survives regrasp.
                    r1=self.robots['r1'];r1.packet=None
                    if self.relook_option!='off' and r1.beam is not None:
                        r1.packet=r1.goal.route_after_relook({k:r1.beam[k] for k in ('rgb','pose_own_m')},
                            now=now,profiles=self.profiles,agreement=self.dialogue,pulse_budget=self.pulse_budget)
                    self.dialogue.approved=False;self.dialogue.proposal=None
                    self.dialogue.claims=set();self.dialogue.key=None;self.dialogue.votes={}
                    self.aligned={};self.approach={};self.seg=0;self.first_seg=0;self.plan=None
                    self.set('mapping',now)
            elif now-self.stage_t>15:out+=self.observation_timeout('OWN_RGB_METRIC_CORRECTION_TIMEOUT',now)
        return out
