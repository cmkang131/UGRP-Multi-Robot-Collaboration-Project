"""Offline S3 composition probe. Synthetic own state; real controllers and ports.

Only the physical world is replaced by a motor/servo sink. State-entry fixtures
are explicit; they test integration contracts, not perception or task success.
No MuJoCo, render, remote model, evaluation truth or physics is used.
"""
import copy
import json
import traceback
from dataclasses import replace
from types import SimpleNamespace

from harness import zone_s3_sweep_contract as contract
from harness.zone_s3_motion_runtime import Runtime
from sim.s3_motion_ports import PhysicsBackend, Previous, attach
from sim.final_pair_highpose_clock import IntegerClock
from sim.final_environment_checks import PhysicsBackend as BaseBackend
from sim.camera_robot_port import CameraRobotPort
from tests.test_solo_cyan_v106 import observation

ROBOTS = ('r1', 'r2', 'r3')
INITIAL = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


class Motor:
    def __init__(self):
        self.servo_command_pulses = dict(INITIAL)
        self.motors = (0.,)*4

    def set_motor_commands(self, values):
        self.motors = tuple(values)

    def set_servo_pulse(self, sid, pulse):
        self.servo_command_pulses[sid] = pulse

    def set_servo_pulses(self, pulses):
        self.servo_command_pulses.update(pulses)


class Probe:
    def __init__(self, out, monkeypatch):
        self.out, self.patch = out, monkeypatch
        self.rows, self.errors, self.issued = [], [], []
        self.fid = 0
        b = contract.bundle('0'*40)
        self.runtime = Runtime(contract.hp.resolve(b['map_id'])[0], contract.inputs()[2]['orders'],
            contract.ROOT/b['calibration'], b['calibration_sha256'], seed=b['seed'], config=b['controller_config'])
        self.robots = {r: Motor() for r in ROBOTS}
        host = self.host = PhysicsBackend.__new__(PhysicsBackend)
        host.world = SimpleNamespace(robot=lambda rid: self.robots[rid], data=SimpleNamespace(time=0.))
        host.dt, host.out, host.bundle = .00025, out, b
        host.commands = {r: dict(INITIAL) for r in ROBOTS}
        host.ports = {r: CameraRobotPort(host.world, r, allow_reverse=True, allow_mecanum=True) for r in ROBOTS}
        host._append = lambda p, row: self.issued.append(dict(path=p, **row))
        # Execute the real destructive port rebuild and the production S3 fix.
        monkeypatch.setattr(BaseBackend, 'reset', lambda self, cap: self.now)
        monkeypatch.setattr(Previous, 'reset', IntegerClock.reset)
        host.reset(5.)
        self.runtime.initial_commands(0., {r: dict(INITIAL) for r in ROBOTS})
        self.runtime.on_frames(.2, {r: observation(.2, 1, rid=r) for r in ROBOTS})
        self.runtime.boot_finished_at = .2  # synthetic post-start entry, not a convergence claim
        self.pair = self.runtime.pair.producer
        self.refresh(.2)
        for a, b in [('r1','r2'), ('r2','r1')]:
            ack = self.runtime.links[a].submit(a, 'cargoX', 'B', b, now=.2)
            assert ack['accepted'], ack
        self.eps = self.pair.team.sessions[0]['endpoints']

    def refresh(self, now, *, xy=(-.9, -.85), yaw=0.):
        now=round(now,9)
        self.host.world.data.time = now
        self.fid += 1
        for rid, loc in self.runtime.localizers.items():
            obs, rgb = observation(now, self.fid+10, rid=rid)
            obs['actuator_state'] = {'servo_pulses': dict(self.host.commands[rid])}
            loc.last_obs, loc.last_rgb = obs, rgb
            loc.last_report = replace(loc.last_report, t_est=now, initialized=True,
                x_m=xy[0], y_m=xy[1], yaw_rad=yaw, std_xy_m=.01, std_yaw_rad=.01,
                last_fix_t=now, fix_age_s=0.)
            if rid in self.pair.actors:
                own = self.pair.actors[rid]
                own.now, own.last_obs, own.last_report = now, obs, loc.last_report

    def issue(self, rid, action, now):
        self.host.world.data.time = now
        self.host.issue(rid, action)
        self.runtime.on_command(rid, now, action)
        # Drive the SAME issued-command predictor too (provider normally consumes
        # this queued history at the next capture).
        provider = self.runtime.localizers[rid].pose.provider
        if provider.failure:
            raise AssertionError(provider.failure)

    def drain(self, ep, now):
        rows, ep.port.commands = ep.port.commands, []
        for action in rows:
            self.issue(ep.own.robot_id, action, now)
        return rows

    def arm(self, ep, until):
        start = self.host.now
        steps = max(1, int(round((until-start)/.05)))
        for i in range(steps+1):
            now = round(start+(until-start)*i/steps, 9)
            self.refresh(now)
            ep.controller.arm.tick(now)
            self.drain(ep, now)
            for p in self.host.ports.values(): p.tick(now)

    def pair_arms(self, until, *, phase=None):
        start=self.host.now
        steps=max(1,int(round((until-start)/.05)))
        for i in range(steps+1):
            now=round(start+(until-start)*i/steps,9)
            self.refresh(now)
            for ep in self.eps.values():
                ep.status.tick(('lift' if phase=='raise' else 'put_down') if phase else ep.status.state,now)
            for ep in self.eps.values():
                ep.controller.arm.tick(now)
                self.drain(ep,now)
            for port in self.host.ports.values():port.tick(now)
            if phase:
                for ep in self.eps.values():
                    assert ep.controller._monitor_transit(now), ep.controller.failure
        for rid in ('r1','r2'):
            self.runtime.localizers[rid].pose.on_frame(until+.2,None)
        self.refresh(until+.21)
        if phase:
            for ep in self.eps.values():ep.status.tick('lift' if phase=='raise' else 'put_down',self.host.now)

    def solo_arm(self, until):
        own=self.runtime.localizers['r3'];start=self.host.now
        steps=max(1,int(round((until-start)/.05)))
        for i in range(steps+1):
            now=round(start+(until-start)*i/steps,9)
            self.refresh(now);own.arm.tick(now)
            rows,own.sink.rows=own.sink.rows,[]
            for action in rows:self.issue('r3',action,now)
            self.host.ports['r3'].tick(now)
        own.pose.on_frame(until+.2,None)
        self.refresh(until+.21)

    def case(self, name, rid, operation, *, expect=None):
        before = len(self.issued)
        try:
            detail = operation() or {}
            if not isinstance(detail,dict): detail=dict(returned=detail)
            if expect:
                raise AssertionError('expected rejection did not occur: '+expect)
            row = dict(case=name, robot=rid, result='pass', issued=len(self.issued)-before, **detail)
        except Exception as exc:
            message = type(exc).__name__+': '+str(exc)
            expected = expect and expect in str(exc)
            row = dict(case=name, robot=rid, result='expected_rejection' if expected else 'error',
                       error=message, traceback=traceback.format_exc(), issued=len(self.issued)-before)
            if not expected: self.errors.append(row)
        self.rows.append(row)
        self.out.mkdir(parents=True,exist_ok=True)
        (self.out/'progress.json').write_text(json.dumps(self.rows,indent=2)+'\n')

    def bus(self, now, phase):
        from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint
        channel=PairStatusChannel('synthetic-stage-entry')
        for rid,ep in self.eps.items():
            PairStatusEndpoint.__init__(ep.status,channel,rid)
            ep.controller.status=(channel,ep.status)
            ep.status.tick(phase,now)

    def entry(self, state, now, *, closed=False):
        self.refresh(now)
        self.bus(now,'lift' if closed else 'aligning')
        from harness.zone_final_pair_vision import grasp_postures
        for rid, ep in self.eps.items():
            ctl = ep.controller
            ctl.state, ctl.state_t, ctl.failure = state, now, None
            ctl.arm.events.clear(); ctl.arm.until = now
            ctl.next_look = float('inf')
            ctl.grasp_pose = dict(grasp_postures()[1][-1])
            ctl.hover = dict(grasp_postures()[0])
            for k, v in {**ctl.grasp_pose, 1:1500 if closed else 2000}.items():
                action = dict(kind='look', pan_pulse=v) if k==6 else dict(kind='arm', servo_id=k, pulse=v)
                self.issue(rid, action, now)
            ctl.arm.commanded.update(self.host.commands[rid])
            ctl.grip_closed_epoch = ctl.grip_epoch if closed else None
            # Own command history must activate load; never set the PF flag.
            loc = self.runtime.localizers[rid]
            loc.pose.on_frame(now+.3, None)
            assert loc.pose.provider.failure is None, loc.pose.provider.failure
        self.refresh(now+.31)

    def finish(self):
        value = dict(schema='ugrp.s3_offline_stage_sweep.v1', physics_runs=0, model_calls=0,
            fixture='synthetic own pose/state and recorded or fixed perception; no success evidence',
            rows=self.rows, errors=self.errors, error_count=len(self.errors),
            commands=len(self.issued), returns='not implemented by existing S3 delivery host')
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out/'sweep.json').write_text(json.dumps(value, indent=2)+'\n')
        (self.out/'commands.json').write_text(json.dumps(self.issued, indent=2)+'\n')
        self.runtime.close()
        return value


def sweep(out, monkeypatch, *, invalid_pose_cases=False):
    p = Probe(out, monkeypatch)
    from harness.zone_s3_pair_heading import approach_proposal
    from harness.zone_s3_coupled_motion import authorized
    from harness.zone_final_pair_vision import GRASP_RADIUS_M
    for rid in ROBOTS:
        def startup(rid=rid):
            own=p.runtime.localizers[rid]
            rows=own.step(.2)
            for robot,action in rows:p.issue(robot,action,.2)
            assert own.state=='scan'
            return dict(state=own.state,known_start_information=False)
        p.case('localization_start_scan',rid,startup)
        def pulse(rid=rid):
            action, _, _ = approach_proposal(p.runtime.localizers[rid].pulse_profiles,
                (0.,0.,0.), (1.,1.), (1.,1.), 0.)
            p.issue(rid, action, .3)
            p.host.ports[rid].tick(.40025)
            assert not any(p.robots[rid].motors)
        p.case('post_reset_heading_native_expiry', rid, pulse)
    p.refresh(.5)
    # All arm commands pass the real ArmSequence and host port, not a list of
    # manually manufactured valid servo actions.
    for rid, ep in p.eps.items():
        def align_start(ep=ep):
            ep.controller._align_start(p.host.now, True)
            p.arm(ep, ep.controller.arm.until+.05)
            assert ep.controller.state == 'align'
        p.case('approach_to_align_arm', rid, align_start)
    now = p.host.now+1.
    p.entry('align', now)
    for rid, ep in p.eps.items():
        def alignment(ep=ep):
            ob = ep.controller._align.__func__.__globals__['ob']
            cmd = ob.align_command(dict(grip_base_m=[GRASP_RADIUS_M,.04], axis_heading_rad=0.))
            ep.controller.drive(cmd, p.host.now)
            rows=p.drain(ep,p.host.now)
            assert len(rows)==1 and rows[0]['duration_s']>=.1
            return dict(state=ep.controller.state)
        p.case('final_rgb_alignment', rid, alignment)
    for error in (.01,.02):
        p.refresh(p.host.now+1.)
        for rid,ep in p.eps.items():
            def small_align(ep=ep,error=error):
                ob=ep.controller._align.__func__.__globals__['ob']
                cmd=ob.align_command(dict(grip_base_m=[GRASP_RADIUS_M,error],axis_heading_rad=0.))
                ep.controller.drive(cmd,p.host.now)
                rows=p.drain(ep,p.host.now)
                assert len(rows)==1 and rows[0]['turn'] and rows[0]['duration_s']==.1
                return dict(lateral_error_m=error,stalled=False)
            p.case('pair_final_alignment_'+str(error),rid,small_align)
    # The complete fixed open descent and close queue, with a synthetic valid
    # hover observation at the perception boundary only. The blind controller,
    # own-issued history, two-party barrier and arm sequencer are production.
    now=p.host.now+2.;p.entry('pregrasp_descend',now)
    for rid,ep in p.eps.items():
        def descend(ep=ep):
            ctl=ep.controller;ctl.grip_base=[GRASP_RADIUS_M,0.]
            ctl.pregrasp_done=True
            ctl._queue_open_descent(p.host.now)
            p.arm(ep,ctl.arm.until+.05)
            monkeypatch.setattr(ctl,'preclose_check',lambda t,o:True)
            def confirm(*a,**k):
                ctl.blind_track.blind_window=dict(drop_m=.071)
            monkeypatch.setattr(ctl.blind_track,'confirm',confirm)
            monkeypatch.setattr(ctl.blind_track,'window_record',lambda:dict(fixture='fixed hover perception'))
            monkeypatch.setattr(ctl.blind_track,'command',lambda *a:None)
            for _ in range(2):
                p.refresh(p.host.now+.1);ctl._pregrasp_descend(p.host.now,True)
            assert ctl.blind_phase=='descend', ctl.failure
            p.arm(ep,ctl.arm.until+.05)
            ctl._pregrasp_descend(p.host.now,True)
            assert ctl.state=='wait_close', (ctl.state,ctl.failure)
            return dict(state=ctl.state)
        p.case('hover_blind_descent_to_close',rid,descend)
    now=p.host.now+1.;p.entry('wait_close',now)
    def close_barrier():
        start=__import__('math').ceil(p.host.now*10)/10
        for i in range(20):
            p.refresh(round(start+i*.05,9))
            for ep in p.eps.values():ep.status.tick('ready',p.host.now)
            for ep in p.eps.values():
                if ep.controller.state=='wait_close' and i%2==0:ep.controller._wait_close(p.host.now,True)
                assert ep.controller.failure is None,ep.controller.failure
            if all(ep.controller.state=='grasp' for ep in p.eps.values()):break
        assert all(ep.controller.state=='grasp' for ep in p.eps.values())
        assert all(ep.status.grant[0]=='close_go_0' for ep in p.eps.values())
        p.pair_arms(max(ep.controller.arm.until for ep in p.eps.values())+.05)
        assert all(p.host.commands[r][1]==1500 for r in ('r1','r2'))
        return dict(grants={r:ep.status.grant for r,ep in p.eps.items()})
    p.case('mutual_close_GO_actual_arm_queue','r1+r2',close_barrier)
    # True GO protocol with live fixed enum heartbeats, both actor orders.
    now = p.host.now+2.
    p.entry('wait_carry', now, closed=True)
    now=p.host.now
    for rid, ep in p.eps.items():
        p.case('grasp_activates_own_load', rid,
            lambda ep=ep: {'loaded': bool(ep.own.pose.localizer.pose.provider.loc._pf.load.loaded)}
                if ep.own.pose.localizer.pose.provider.loc._pf.load.loaded else (_ for _ in ()).throw(AssertionError('own close did not load')))
    # Grasp receipt and HIGH transit from synthetic issued-close state.
    for rid,ep in p.eps.items():
        def grasp(ep=ep):
            ctl=ep.controller;ctl.state='grasp'
            ctl.close_started_at=now-.31;ctl.close_issued_at=now-.31
            ctl._grasp(p.host.now,True)
            assert ctl.state=='wait_lift', (ctl.state,ctl.failure)
            assert ctl.held_by_command()
        p.case('issued_close_to_grasp_receipt',rid,grasp)
    for ep in p.eps.values():ep.status.latched=None;ep.status.tick('lift',p.host.now,force=True)
    for rid,ep in p.eps.items():
        p.case('low_lift_to_HIGH_queue',rid,lambda ep=ep:ep.controller._low_lift(p.host.now,True))
    def high_transit():
        p.pair_arms(max(ep.controller.arm.until for ep in p.eps.values())+.1,phase='raise')
        for ep in p.eps.values():
            ep.controller._lift(p.host.now,True)
            assert ep.controller.state=='wait_carry', (ep.own.robot_id,ep.controller.state,ep.controller.failure)
        return dict(states={r:e.controller.state for r,e in p.eps.items()})
    p.case('HIGH_transit_complete','r1+r2',high_transit)
    now=p.host.now
    p.bus(now,'lift')
    for ep in p.eps.values():
        ep.status.tick('lift', now+.02)
        ep.controller.report('carry', ep.own.last_obs, now+.02, ready=True, reason='synthetic own held state')
    for offset in (.07,.12,.17):
        for ep in p.eps.values(): ep.status.tick('lift',now+offset)
    go = round(__import__('math').ceil((now+.22-1e-8)/.1)*.1, 9)
    for ep in p.eps.values(): ep.status.tick('lift',go)
    decisions={}
    for rid,ep in p.eps.items():
        decisions[rid]=ep.controller.sync_for('carry').authorize(go)
        assert decisions[rid]['phase']=='GO', decisions
        ep.controller.state='carry'
    p.refresh(go+.1)
    for rid, ep in p.eps.items():
        def carry_go(ep=ep):
            result=decisions[ep.own.robot_id]
            # First actor sees the partner's just-consumed carry GO (wire phase
            # 'lift') until that actor's next publisher tick. This is real order.
            ep.controller.schedule=[(go,go+1.,dict(forward=.005,left=.02,turn=.001))]
            ep.status.tick('carry',go+.1)
            ep.controller._carry(go+.1,True)
            rows=p.drain(ep,go+.1)
            assert rows and any(a.get('left') for a in rows)
            return dict(go=result, state=ep.controller.state, authorized=authorized(ep,go+.1))
        p.case('pair_GO_first_carry_motor',rid,carry_go)
    # A generic lift enum must not qualify for the exception, even with a local
    # grant; retain the strict endpoint missed-GO stop independently below.
    peer=p.eps['r2'];me=p.eps['r1']
    peer.status.tick('lift',go+.11,force=True)
    p.case('reject_unmatched_lift_enum','r1',lambda:me.port.apply(
        dict(kind='mecanum',forward=.005,left=.02,turn=.001,duration_s=.15),go+.11),
        expect='live pair carry GO')
    # Static plan's axial + lateral legs, including release / reload boundaries.
    for ep in p.eps.values(): ep.status.latched=None; ep.status.tick('carry',go+.15,force=True)
    p.refresh(go+.15)
    for rid,ep in p.eps.items():
        def carry(ep=ep):
            ep.controller.state='carry'; ep.controller._carry(go+.15,True)
            rows=p.drain(ep,go+.15)
            assert any(a.get('left') for a in rows)
        p.case('coupled_lateral_carry',rid,carry)
    # Every registered leg is produced by the actual door_schedule, then each
    # command goes through the heading exception, own history and native port.
    for rid,ep in p.eps.items():
        def legs(ep=ep):
            ctl=ep.controller;old_seg=ctl.seg;old_claims=copy.deepcopy(ctl.claims)
            try:
                for seg in range(len(ctl.segments)):
                    ctl.seg=seg;ctl.grasp_estimate=[1.,.05,0. if rid=='r1' else 3.141592653589793]
                    ctl.claims.setdefault('segments',[])
                    for _,_,cmd in ctl.door_schedule(p.host.now):
                        ep.port.apply(dict(kind='mecanum',**cmd,duration_s=.15),p.host.now)
                        p.drain(ep,p.host.now)
                return dict(legs=len(ctl.segments))
            finally:ctl.seg=old_seg;ctl.claims=old_claims
        p.case('all_axial_and_lateral_door_legs',rid,legs)
    # Lower uses the same real monitored arm schedule; no invented grip success.
    from harness import zone_pair_highpose as high
    p.refresh(p.host.now+1.)
    for ep in p.eps.values():
        ep.status.tick('put_down',p.host.now,force=True)
        ep.controller.state='lower'
    for rid,ep in p.eps.items():
        p.case('lower_queue',rid,lambda ep=ep:ep.controller._start_transit('lower',high.lower_path(),p.host.now))
    def lower():
        p.pair_arms(max(ep.controller.arm.until for ep in p.eps.values())+.1,phase='lower')
        for ep in p.eps.values():
            ep.controller._lower(p.host.now,True)
            assert ep.controller.state=='wait_open', (ep.controller.state,ep.controller.failure)
        return dict(states={r:e.controller.state for r,e in p.eps.items()})
    p.case('lower_to_release_barrier','r1+r2',lower)
    now=p.host.now+2.
    p.entry('released',now,closed=False)
    for rid,ep in p.eps.items():
        def released(ep=ep):
            ep.controller._released(p.host.now,True)
            rows=p.drain(ep,p.host.now)
            assert any(a.get('forward',0)<0 for a in rows)
        p.case('release_backoff',rid,released)
    now=p.host.now+2.
    p.entry('cp_backoff',now)
    for rid,ep in p.eps.items():
        def retry(ep=ep):
            ep.controller._cp_backoff(p.host.now,True)
            rows=p.drain(ep,p.host.now)
            assert any(a.get('forward',0)<0 for a in rows)
        p.case('checkpoint_retry_backoff',rid,retry)
    # Solo state-entry probes use the unchanged controller and real BlindCyan.
    from tests.test_solo_cyan_v106 import FakeVision
    from harness.zone_final_pair_vision import grasp_postures
    from harness.zone_solo_cyan_vision_v106 import BlindCyan
    solo=p.runtime.localizers['r3'];solo.vision=FakeVision(None)
    solo.detections=lambda:[dict(estimated_box_center_base_m=[GRASP_RADIUS_M,0.,.016])]
    solo.global_policy.active=False
    def solo_step(state, expected, *, setup=lambda:None, arm=True):
        p.refresh(p.host.now+1.)
        solo.state,solo.state_t,solo.failure=state,p.host.now,None
        solo.next_control=p.host.now;solo.arm.events.clear();solo.arm.until=p.host.now
        setup()
        for rid,action in solo.step(p.host.now):p.issue(rid,action,p.host.now)
        assert solo.state==expected,(solo.state,solo.failure)
        if arm:p.solo_arm(max(p.host.now,solo.arm.until)+.05)
        return dict(state=solo.state)
    p.case('solo_search_to_align','r3',lambda:solo_step('search','align'))
    for error in (.01,.02):
        def small_solo(error=error):
            from harness.owncam_pair_beam_v2 import pose_of
            p.refresh(p.host.now+1.)
            solo.state='align';solo.state_t=p.host.now;solo.next_control=p.host.now
            solo.arm.events.clear();solo.arm.until=p.host.now
            solo.heading_align_until=None;solo.heading_align_settled=-float('inf')
            solo.fine_until=None;solo.fine_observe_after=-float('inf')
            solo.detections=lambda:[dict(estimated_box_center_base_m=[GRASP_RADIUS_M,error,.016])]
            for k,v in pose_of('inspect').items():
                p.issue('r3',dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v),p.host.now)
            rows=solo.step(p.host.now)
            for rid,action in rows:p.issue(rid,action,p.host.now)
            assert any(a.get('turn') and a['duration_s']==.1 for _,a in rows),rows
            return dict(lateral_error_m=error,stalled=False)
        p.case('solo_final_alignment_'+str(error),'r3',small_solo)
    solo.detections=lambda:[dict(estimated_box_center_base_m=[GRASP_RADIUS_M,0.,.016])]
    solo.heading_align_until=None;solo.heading_align_settled=-float('inf')
    solo.fine_until=None;solo.fine_observe_after=-float('inf')
    def solo_blind_setup():
        solo.blind=BlindCyan();solo.target=[GRASP_RADIUS_M,0.];solo.target_t=p.host.now
        for k,v in {**grasp_postures()[0],1:2000}.items():
            p.issue('r3',dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v),p.host.now)
        for _ in range(2):
            p.refresh(p.host.now+.1)
            solo.blind.confirm(p.host.now,solo.last_obs,solo.servo,solo.target,True)
        for k,v in grasp_postures()[1][-1].items():
            p.issue('r3',dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v),p.host.now)
    p.case('solo_blind_descent_close','r3',lambda:solo_step('blind_descent','grasp',setup=solo_blind_setup))
    p.case('solo_grasp_to_lift','r3',lambda:solo_step('grasp','lift'))
    p.case('solo_lift_to_carry_posture','r3',lambda:solo_step('lift','real_carry_transition'))
    p.case('solo_carry_posture_to_drive','r3',lambda:solo_step('real_carry_transition','carry'))
    def solo_motion():
        p.refresh(p.host.now+1.)
        rows,arrived=solo.drive((1.,1.),p.host.now)
        for a in rows:p.issue('r3',a,p.host.now)
        assert not arrived and any(a.get('forward') or a.get('turn') for a in rows)
        return dict(state=solo.state)
    p.case('solo_loaded_heading_door_pass','r3',solo_motion)
    p.case('solo_lower_release','r3',lambda:solo_step('lower','released'))
    p.case('solo_release_done','r3',lambda:solo_step('released','done'))
    # Door arbitration and its actual gated producer reach real holds/motors.
    def door_wait():
        p.runtime.exchange(p.host.now);p.runtime.exchange(p.host.now)
        assert p.runtime.pair.allowed() and not p.runtime.solo.allowed()
        for rid,action in p.runtime.solo.step(p.host.now):p.issue(rid,action,p.host.now)
        assert not any(p.robots['r3'].motors)
    p.case('door_wait_pair_priority','r3',door_wait)
    def door_pass():
        p.refresh(p.host.now+1.,xy=(5.,0.))
        for own in p.pair.actors.values():own.jobs_done.append(dict(kind='pair_carry',confirmation='unconfirmed'))
        p.runtime.exchange(p.host.now);p.runtime.exchange(p.host.now)
        assert p.runtime.solo.allowed()
        for rid,action in p.runtime.solo.step(p.host.now):p.issue(rid,action,p.host.now)
        return dict(door={r:c.state for r,c in p.runtime.clients.items()})
    p.case('door_clear_solo_handoff','r1+r2+r3',door_pass)
    # v149 reached this time boundary with an alive, still-approaching peer.
    # Exercise the real inherited wait method, two renewed windows and native
    # hold. No readiness/GO is fabricated and the state must not advance.
    from scripts.run_m2_pair import APPROACH_WAIT_S
    for rid,ep in p.eps.items():
        def pre_go_wait(ep=ep):
            for repeat in range(2):
                now=p.host.now+APPROACH_WAIT_S+.1
                p.refresh(now);p.bus(now,'aligning')
                ctl=ep.controller;ctl.state='wait_approach'
                ctl.state_t=now-APPROACH_WAIT_S-.1;ctl.next_look=now+1.
                ctl._wait_approach(now,True)
                rows=p.drain(ep,now)
                assert rows and all(a['kind']=='hold' for a in rows)
                assert ctl.state=='wait_approach' and ctl.failure is None
                assert ep.status.grant is None and not ep.terminal
                assert ctl.sync_for('approach').authorize(now)['phase']=='WAIT'
            return dict(repeated_windows=2,advanced_without_GO=False)
        p.case('alive_peer_pre_GO_wait_timeout_continues',rid,pre_go_wait)
    # Actual endpoint failure path, not merely an authorization predicate.
    def missed_go():
        p.bus(p.host.now,'start_ready')
        ep=p.eps['r1'];ep.status.grant=('carry_go_0',p.host.now)
        ep.controller.state='carry'
        ep.check(p.host.now+.05)
        assert ep.terminal
        assert ep.own.jobs_done[-1]['outcome']=='PARTNER_MISSED_GO', ep.own.jobs_done[-1]
        p.issue('r1',dict(kind='hold'),p.host.now+.05)
        return dict(hard_stop='PARTNER_MISSED_GO')
    p.case('missed_GO_stays_hard_stop','r1',missed_go)
    def consumed_go_timeout():
        p.bus(p.host.now,'aligning')
        ep=p.eps['r2'];ep.status.grant=('approach_go_0',p.host.now)
        ep.controller.state='wait_approach'
        ep.controller.fail('BARRIER_APPROACH_TIMEOUT',p.host.now)
        assert ep.controller.failure=='BARRIER_APPROACH_TIMEOUT'
        p.drain(ep,p.host.now)
        return dict(hard_stop='BARRIER_APPROACH_TIMEOUT',already_consumed_GO=True)
    p.case('consumed_GO_timeout_stays_hard','r2',consumed_go_timeout)
    # Reset on a used port must remove active expiry and restore ALL capabilities.
    p.host.world.data.time=round(p.host.now+2.,4)
    p.host.reset(5.)
    for rid in ROBOTS:
        def reset(rid=rid):
            port=p.host.ports[rid]
            assert port._drive_expires_at is None
            p.host.issue(rid,dict(kind='mecanum',forward=0.,left=0.,turn=.35,duration_s=.1))
        p.case('reset_retry_heading',rid,reset)
    def serialize():
        value=p.runtime.record()
        json.dumps(value,allow_nan=False)
        assert all(o.s3_exact_cache['option']=='posterior_content_v2' for o in p.runtime.localizers.values())
        return dict(cache='posterior_content_v2',nonfinite=False)
    p.case('final_record_serialization','r1+r2+r3',serialize)
    if invalid_pose_cases:
        from harness.zone_own_guards import OwnPose
        from harness.zone_own_sweep import SweepRecheck
        from harness.zone_s3_pose_validity import finite_record
        now=max(p.host.now,*(o.pose.provider.loc._pf.t for o in p.runtime.localizers.values()))+20.
        for rid in ROBOTS:
            now += 50.
            for label,pose in [('none',None),('nan',OwnPose(float('nan'),0.,0.,.01,.01))]:
                now += 11.
                def missing_pose(rid=rid,pose=pose):
                    own=p.runtime.localizers[rid]
                    recheck=(type(p.eps[rid].command_guard.recheck)() if rid in p.eps else SweepRecheck())
                    assert recheck.check(now,own.guard,own.servo,{6:1500},pose,loaded=False)=='wait'
                    p.issue(rid,dict(kind='hold'),now)
                    assert recheck.check(now+10.,own.guard,own.servo,{6:1500},pose,loaded=False)=='blocked'
                    p.issue(rid,dict(kind='hold'),now+10.)
                    return dict(no_motion=True,expected='bounded wait; no pose dereference')
                p.case('invalid_pose_'+label,rid,missing_pose)
            def unmeasured_camera(rid=rid):
                own=p.runtime.localizers[rid]
                t=now+20.
                # Exact recorded v150 failure posture, through production
                # issue/on_command/port and delayed own-input provider.
                for sid,pulse in {3:1072,4:2400,5:1482,6:1630}.items():
                    p.issue(rid,dict(kind='look',pan_pulse=pulse) if sid==6 else
                        dict(kind='arm',servo_id=sid,pulse=pulse),t)
                old_fix=own.pose.provider.loc._pf.last_scan_t
                own.pose.on_frame(t+2.,observation(t+2.,p.fid+100,rid=rid)[1])
                report=own.pose.report(t+2.2)
                assert own.pose.provider.failure is None
                assert report.initialized and all(__import__('math').isfinite(v) for v in
                    (report.x_m,report.y_m,report.yaw_rad,report.std_xy_m,report.std_yaw_rad))
                assert own.pose_validity_audit['count']>0
                assert own.pose.provider.loc._pf.last_scan_t==old_fix
                p.issue(rid,dict(kind='hold'),t+2.2)
                return dict(prediction_only=True,new_visual_fix=False)
            p.case('unmeasured_posture_prediction',rid,unmeasured_camera)
        def invalid_record():
            original=dict(pose=[float('nan'),float('inf'),None])
            value=finite_record(original)
            json.dumps(value,allow_nan=False)
            assert value['nonfinite_record_fields']==['$.pose[0]','$.pose[1]']
            return dict(explicit_invalid_fields=2)
        p.case('invalid_report_strict_serialization','r1+r2+r3',invalid_record)
    return p.finish()
