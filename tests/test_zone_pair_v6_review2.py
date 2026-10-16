"""Command-response scenarios through the real endpoint, driver, guard and align.

The response model supplies synthetic own sensor reports / analytic wrist JPEGs.
It has no MuJoCo world, no contact/success oracle and no model/network calls.
"""
import base64
from dataclasses import replace
import hashlib
import math

import cv2
import numpy as np
import pytest

from harness.owncam_drive import LOOK_P20
from harness.owncam_pair_beam_v2 import pose_of
from harness.owncam_recovery_v6 import enable_provider
from harness.owncam_view import base_rays
from harness.zone_pair_v6_policy import pair_policy
from tests.test_zone_pair_grasp import real_pair
from tests.test_zone_pair_executor import pair_obs
from tests.test_zone_pair_v6 import good
from tests.test_zone_pair_v6_review1 import box_pixels, image_at


def raster(servo, intervals, *, fid=0, face_at=None):
    x, y, top, end = box_pixels(servo, intervals, face_at=face_at)
    frame = np.full((480,640,3),100,np.uint8)
    frame[y[top],x[top]] = [0,220,120]
    frame[y[end],x[end]] = [0,160,88]
    frame[0,0] = [fid % 255,100,100]  # capture noise outside valid optics
    return frame


class Scenario:
    def __init__(self, *, state='approach', goal=(1.,-1.,0.), yaw=0., beam_grip=None, fixes=True,
                 fix_delay_s=0., fail_every=0, fail_s=0., partner_state='aligning'):
        _,_,self.eps = real_pair()
        self.ep = ep = self.eps['r1']; self.own = ep.own; self.ctl = ep.controller
        ep.policy = pair_policy('a+b'); enable_provider(self.own.pose)
        self.ctl.state = state; self.ctl.state_t = 0.
        self.ctl.look_name = 'search'; self.ctl.next_look = 0.
        self.ctl.align_started_at = 0.
        self.own.servo = pose_of('search'); self.ctl.arm.commanded = dict(self.own.servo)
        self.ctl.driver.servo = dict(self.own.servo)
        self.ctl.driver.state = 'drive'; self.ctl.driver.state_since = 0.
        self.ctl.driver.goal = list(goal[:2]); self.ctl.driver.goal_yaw = goal[2]
        self.pose = np.array([.6,-1.,yaw]); self.t = 0.; self.last_arm = -1.
        self.last_fix = 0.; self.fixes = fixes; self.motion = (0.,0.,0.); self.until = 0.
        self.commands = []; self.trace = []; self.beam_x = None if beam_grip is None else .6+beam_grip
        self.sensor_yaw_offset = 0.
        self.partner_state = partner_state
        # Review 3: realistic sensor latency. A look posture yields its first
        # informative fix only after fix_delay_s; every fail_every-th look
        # episode yields none for an extra fail_s (occluded/blurred pans).
        self.fix_delay_s, self.fail_every, self.fail_s = fix_delay_s, fail_every, fail_s
        self.ready_since = None; self.episodes = 0
        self.capture(0.)
        ep.command_guard.global_envelope.pose(self.own.last_report,0.)

    def capture(self, now):
        dt = max(0., min(now,self.until)-self.t)
        f,l,w = self.motion; yaw = self.pose[2]
        self.pose += [dt*(math.cos(yaw)*f-math.sin(yaw)*l),dt*(math.sin(yaw)*f+math.cos(yaw)*l),dt*w]
        self.t = now
        own = self.own; own.now = now
        camera_ready = all(own.servo.get(k) == v for k,v in LOOK_P20.items()) and now-self.last_arm >= .3
        if not camera_ready:
            self.ready_since = None
        elif self.ready_since is None:
            self.ready_since = now; self.episodes += 1
        delay = self.fix_delay_s+(self.fail_s if self.fail_every and self.episodes % self.fail_every == 0 else 0.)
        if (self.fixes and camera_ready and now >= self.until+.2
                and now-self.ready_since >= delay-1e-9):
            self.last_fix = now
        x,y,yaw = self.pose; yaw += self.sensor_yaw_offset
        r = replace(good(now),x_m=x,y_m=y,yaw_rad=yaw,last_fix_t=self.last_fix,fix_age_s=now-self.last_fix)
        if now != self.last_fix:
            r = replace(r,observation_quality={'accepted':False,'informative':False,'settled':True,'ambiguous':True,
                'last_fix_quality':{**good().observation_quality,'t':self.last_fix}})
        # Deterministic sensor posterior supplied to the shared real recovery
        # provider. Tests exercise its begin_observation/reset semantics too.
        loc = own.pose.loc; loc.t = now; loc.initialized = True
        loc.px[:] = (x,y,yaw); loc.logw[:] = -math.log(loc.n)
        loc.last_tag_t = loc.last_informative_t = self.last_fix
        loc.last_fix_quality = {**good().observation_quality,'t':self.last_fix}
        loc.quality = r.observation_quality
        own.last_report = r
        own._update_gate(now,r)
        fid = own.last_obs['frame_id']+1
        obs = pair_obs(own.robot_id,fid,now,own.servo)
        if self.beam_x is not None:
            grip = self.beam_x-x
            frame = raster(own.servo,[(grip-.03,grip+.57)],fid=fid,face_at=grip-.03)
            background = np.all(frame == 100,axis=2)
            texture = 100+12*np.sin(np.indices(frame.shape[:2])[1]/20.)
            frame[background] = np.repeat(texture[...,None],3,axis=2)[background]
            data = cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,100])[1].tobytes()
            obs.update(image=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest())
        own.last_obs = obs
        for ep in self.eps.values():
            ep.status.tick('aligning' if ep is self.ep else self.partner_state, now)

    def issue(self, commands, now):
        for command in commands:
            row = {**command,'t':now}; self.commands.append(row)
            self.own.on_command(row)
            if row['kind'] in ('mecanum','drive'):
                self.motion = tuple(row.get(k,0.) for k in ('forward','left','turn'))
                self.until = now+row['duration_s']
            elif row['kind'] == 'hold':
                self.until = min(self.until,now)
            elif row['kind'] in ('arm','look'):
                self.last_arm = now

    def tick(self, now):
        self.capture(now)
        result = self.ep.step(now)
        assert result['mode'] == 'tick'
        self.issue(result['commands'],now)
        self.issue(self.ep.arm_step(now),now)
        self.trace.append((now,self.ctl.state,self.ctl.driver.state,self.ep.command_guard.global_envelope.fix_t))
        assert not self.ep.terminal, (self.trace[-8:],self.own.jobs_done[-1:],self.ep.events[-8:])

    def run_until(self, condition, limit=60.):
        for i in range(1,int(limit/.05)+1):
            self.tick(round(i*.05,6))
            if condition():
                return
        pytest.fail(f'scenario deadline: {self.trace[-10:]}')


@pytest.mark.parametrize('turn',[False,True])
def test_actual_endpoint_normal_approach_and_rotation_reobserve_then_arrive(turn):
    s = Scenario(goal=(.6,-1.,.5) if turn else (1.,-1.,0.))
    s.run_until(lambda:s.ctl.state=='wait_approach')
    assert s.ctl.driver.outcome == 'arrived'
    looks = [r for r in s.ctl.driver.log if r.get('reason')=='global_safety_reserve']
    assert looks
    assert math.dist(s.pose[:2],s.ctl.driver.goal) <= .03
    from harness.pair_owncam_approach import ARRIVE_TOL_YAW_RAD
    assert abs(s.pose[2]-s.ctl.driver.goal_yaw) <= ARRIVE_TOL_YAW_RAD
    assert any(r['kind']=='hold' for r in s.commands)
    assert any(r['kind'] in ('look','arm') for r in s.commands)


def test_actual_endpoint_align_yaw_reacquires_three_fixes_then_returns():
    s = Scenario(state='align',beam_grip=.36)
    s.sensor_yaw_offset = .2
    # Start with a new compact sensor candidate at the same XY, no turn command.
    s.last_fix = .05
    s.run_until(lambda:any(t[1]=='align_relook_return' for t in s.trace) and s.ctl.state=='align',limit=9.)
    env = s.ep.command_guard.global_envelope
    assert env.anchor.yaw == pytest.approx(.2) and env.fix_t > .05
    assert sum(t[1] in ('align_relook_stop','align_relook') for t in s.trace) >= 3
    assert not any(r['kind'] in ('drive','mecanum') for r in s.commands)
    assert s.own.pose.loc.recovery_requests == 0  # routine look preserved PF


def test_actual_endpoint_partial_view_forward_reaches_pregrasp():
    s = Scenario(state='align',beam_grip=.36)
    s.run_until(lambda:s.ctl.state=='pregrasp_descend',limit=30.)
    reports = [e['report'] for e in s.ep.events if e['event']=='beam_relative']
    assert any('PARTIAL_SUPPORT_ONLY' in r['reasons'] for r in reports)
    assert any('STATIONARY_MULTIVIEW_COMPLETE_SHAPE' in r['reasons'] for r in reports)
    from harness.owncam_pair_beam import ALIGN_TOL_X_M
    final = reports[-1]
    # The mid-height end-face estimate may leave the true grip up to its bound
    # beyond the unchanged align tolerance; it must stay in the 14.5-18 cm IK band.
    assert abs((s.beam_x-s.pose[0])-.162) <= ALIGN_TOL_X_M+final['std_xy_m']+final['bias_bound_m']
    assert .145 <= s.beam_x-s.pose[0] <= .18
    assert 'aligned' in s.ctl.claims


def test_occluded_partial_boundary_does_not_update_axis_or_contract_bound():
    from harness.zone_pair_relative import RelativeBeamTrack
    tr=RelativeBeamTrack();o,servo=image_at(.36)
    assert tr.observe(o,servo,0,now=0.).ready(0.)
    tr.command(dict(kind='drive',t=0.,forward=.08,duration_s=.3),servo)
    tr.advance(.3);before=dict(tr.beam)
    servo=pose_of('p45');frame=raster(servo,[(.41,.906)])  # near end hidden: no face
    obs=dict(frame_id=2,sha256='occlusion',sim_time=.3,image=frame,actuator_state={'servo_pulses':servo})
    r=tr.observe(obs,servo,0,now=.3)
    assert r.grip_base_m == tuple(before['grip_base_m'])
    assert r.std_xy_m+r.bias_bound_m >= before['std_xy_m']+before['bias_bound_m']
    assert not r.ready(.3) and r.anchor_time_s==0.


def test_two_piece_obstacle_stays_yes_in_actual_status_judge():
    from harness.zone_own_perception import judge_route_blockage
    from harness.zone_pair_obstruction import target_context
    _,_,eps=real_pair();ep=eps['r1'];servo={**pose_of('search'),**LOOK_P20}
    frame=raster(servo,[(.37,.80),(.84,.97)])
    target=dict(order_id='cargoX',grip_base_m=[.40,0.],axis_heading_rad=0.,xy_slack_m=.05,
                yaw_slack_rad=.05,source='static coarse order',allow_shape_identity=True)
    kw=dict(static_map=ep.own.map,pose_belief={'x_m':.6,'y_m':-1.,'yaw_rad':0.,'confidence':'high'})
    before=judge_route_blockage(frame,servo,**kw)
    after=judge_route_blockage(frame,servo,expected_target=target,**kw)
    assert before['answer']==after['answer']=='yes'
    assert len(before['candidates'])==len(after['candidates'])==1
    assert not after['expected_target_occupancy'] and after['flat_features']==1
    # Then exercise the real active-job context and status caller, not a
    # hand-authored expected target. The coarse order locates this grip at .4 m.
    ep.policy=pair_policy('a+b');own=ep.own;own.servo=servo
    own.last_report=replace(good(),x_m=.33,y_m=0.)
    assert target_context(own,own.last_report,0.)['grip_base_m']==pytest.approx([.4,0.])
    data=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,100])[1].tobytes()
    own.last_obs=pair_obs(own.robot_id,3,0.,servo)
    own.last_obs.update(image=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest())
    assert own._judge(0.,own.last_obs,cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),own.last_report)
    assert own.judgment_log[-1]['answer']=='yes'
    assert not own.judgment_log[-1]['expected_target_occupancy']


def test_missing_fixes_stop_then_exhaust_existing_reobserve_budget():
    from harness.zone_pair_global import SCHEDULED_REOBSERVE
    s=Scenario(fixes=False)
    for i in range(1,1200):
        try:
            s.tick(round(i*.05,6))
        except AssertionError:
            assert s.ep.terminal
            break
    # Final review P2-1: each look's fix-confirm dwell ends after its 6 s
    # allowance and the frozen no-fix path starts the next look. Without any
    # fix the job ends at the latest when the 30 s global anchor expires.
    assert s.ep.terminal and s.own.jobs_done[-1]['outcome'] in ('PAIR_REOBSERVE_TIMEOUT','POSE_UNCERTAIN')
    assert s.t <= 30.1
    stopped=next(r['t'] for r in s.commands if r['kind']=='hold')
    assert not any(r['kind'] in ('drive','mecanum') and r['t']>stopped for r in s.commands)
    assert s.ep.command_guard.global_envelope.fix_t==0.
    recheck=s.ep.command_guard.recheck
    assert recheck.scheduled_count>=2
    assert recheck.scheduled_total_s<=recheck.scheduled_count*SCHEDULED_REOBSERVE['per_look_s']+1e-9
    assert recheck.waited_s<=10.+1e-9


def test_recovery_envelope_keeps_posterior_hypotheses_and_invalidity():
    from harness.zone_pair_global import GlobalEnvelope
    env=GlobalEnvelope();env.pose(good(),0.)
    report=replace(good(1.),yaw_rad=.2,observation_quality={**good().observation_quality,
        'posterior_envelope':{'xy_radius_m':.4,'yaw_radius_rad':.5}})
    recovery=env.recovery_pose(report,1.)
    assert recovery.std_xy >= .2 and recovery.std_yaw >= .35
    bad=replace(report,observation_quality={'posterior_envelope':{'xy_radius_m':float('nan'),'yaw_radius_rad':.2}})
    assert env.recovery_pose(bad,1.) is None


def test_two_fragments_cannot_initialize_relative_shape_either():
    from harness.zone_pair_relative import shape_fit
    servo={**pose_of('search'),**LOOK_P20}
    fitted,reasons=shape_fit(raster(servo,[(.37,.80),(.84,.97)]),servo)
    assert fitted is None and 'DISCONNECTED_SHAPE_OR_OCCLUSION' in reasons


def test_partial_multiview_cache_cannot_cross_base_command_or_expired_view():
    from harness.zone_pair_relative import RelativeBeamTrack
    for fault in ('motion','old_view'):
        tr=RelativeBeamTrack();o,s=image_at(.36);tr.observe(o,s,0,now=0.)
        tr.command(dict(kind='drive',t=0.,forward=.08,duration_s=.3),s)
        o,s=image_at(.336,fid=2,t=.3);tr.observe(o,s,0,now=.3)
        if fault=='motion':
            tr.command(dict(kind='drive',t=.4,forward=.01,duration_s=.1),s)
        t=5. if fault=='old_view' else 1.
        o,s=image_at(.336,'p45',fid=3,t=t)
        r=tr.observe(o,s,0,now=t)
        assert not r.ready(t) and r.anchor_time_s==0.
        assert 'STATIONARY_MULTIVIEW_COMPLETE_SHAPE' not in r.reasons


def test_multiview_report_cannot_outlive_identity_on_duplicate_read():
    from harness.zone_pair_relative import RelativeBeamTrack
    tr=RelativeBeamTrack();o,s=image_at(.36);tr.observe(o,s,0,now=0.)
    a,s=image_at(.336,fid=2,t=29.);tr.observe(a,s,0,now=29.)
    b,s=image_at(.336,'p45',fid=3,t=29.9)
    r=tr.observe(b,s,0,now=29.9)
    assert r.ready(29.9) and r.anchor_time_s==29.9 and r.identity_time_s==0.
    assert not tr.observe(b,s,0,now=30.1).ready(30.1)


def test_last_approach_pan_is_reachable_while_global_fix_is_pending():
    s=Scenario(fixes=False);drv=s.ctl.driver
    drv.state='look_pan';drv.look_t0=0.;drv.arm_target={6:1230};drv.look_queue=[]
    s.tick(.05)
    assert any(c['kind']=='look' and c['pan_pulse']<1500 for c in s.commands)
    assert not s.ep.terminal and not any(c['kind'] in ('drive','mecanum') for c in s.commands)
