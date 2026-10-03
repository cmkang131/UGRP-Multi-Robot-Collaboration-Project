"""Instance-only pose adaptation of the existing v3 beam-relative student."""
from types import MethodType

import numpy as np

from harness import zone_final_pair_skill as previous
from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_grip as grip
from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_runtime import Runtime as PreviousRuntime
from harness.zone_final_pair_guards import CommandGuard as PreviousGuard
from harness.own_beam_edge import edge_line
from scripts import run_m2_pair as m2


class HighController:
    def set(self, state, now, **detail):
        if state == 'wait_carry' and getattr(self, '_checking_low_lift', False):
            self.low_lift_confirmed = True
            return
        return super().set(state, now, **detail)

    def _issued(self):
        # ArmSequence.commanded is the future queue endpoint, NOT issued PWM.
        return dict(self.port.own.servo)

    def _queue_open_descent(self, now):
        self.high_raising, self.high_ready = False, False
        self.low_lift_confirmed = False
        self.grip_epoch = getattr(self, 'grip_epoch', 0)+1
        self.pose_anchors = {}
        self.transit = None
        self.floor_return_verified, self.floor_check_until = False, None
        return super()._queue_open_descent(now)

    def _anchor(self, name, obs, now):
        key = grip.pose_key(self.pose_of(obs))
        self.pose_anchors[name] = grip.Anchor(self.grip_epoch, key,
            m2.hv3.hold_view_mask(obs['image']).copy(), obs['frame_id'], now)
        self.log(self.rid, 'pose_anchor', now, pose=name, epoch=self.grip_epoch,
                 frame_id=obs['frame_id'], lifetime='same grasp epoch and exact posture; no refresh')

    def _grasp(self, now, arm_idle):
        super()._grasp(now, arm_idle)
        if self.state == 'wait_lift' and 'floor' not in self.pose_anchors:
            # The original floor grip check already passed. This image is not
            # recaptured/replaced at the end of lowering.
            self._anchor('floor', self.look(now), now)

    def _partner_transit_ok(self, now, phase):
        if self.status is None:
            return False
        peers = self.status[0].partner_view(self.rid, now)
        allowed = {'lift'} if phase == 'raise' else {'put_down'}
        # One actor is stepped before the other on the same tick. Only the
        # first 100 ms can see the phase just before GO; no long grace period.
        if now-self.transit.started_at <= .1+1e-8:
            allowed.add('ready' if phase == 'raise' else 'carry')
        return bool(peers) and all(p['alive'] and p['state'] in allowed for p in peers.values())

    def _transit_abort(self, reason, now):
        self.arm.events.clear()
        self.arm.until = now
        self.arm.commanded = self._issued()
        self.high_ready = self.floor_return_verified = False
        self.floor_check_until = None
        self.anchor_full = None
        self.pose_anchors = {}
        self.port.hold(now)
        return self.fail(reason, now)

    def _start_transit(self, phase, path, now):
        servo = self._issued()
        pose.queue_path(self.arm, now, path)
        self.transit = grip.TransitMonitor(phase, now, servo, self.arm.events,
                                           self.arm.until, self.grip_epoch)
        self.next_transit_look = now
        return self._monitor_transit(now)

    def _monitor_transit(self, now):
        if now < self.next_transit_look-1e-8:
            return True
        self.next_transit_look = now+grip.SAMPLE_S
        obs, servo = self.look(now), self._issued()
        ok = self.transit.observe(now, obs, servo,
                    self._partner_transit_ok(now, self.transit.phase))
        self.log(self.rid, 'transit_grip', now, phase=self.transit.phase,
                 ok=ok, reason=self.transit.failure, evidence=self.transit.last,
                 epoch=self.grip_epoch, frame_id=obs['frame_id'])
        if not ok:
            self._transit_abort(self.transit.failure, now)
        return ok

    def _lift(self, now, arm_idle):
        if not getattr(self, 'high_raising', False):
            self._checking_low_lift = True
            try:
                super()._lift(now, arm_idle)
            finally:
                self._checking_low_lift = False
            if getattr(self, 'low_lift_confirmed', False):
                self.high_raising, self.high_ready = True, False
                self.set('lift', now, subphase='raise_to_high', pose_id=pose.POSE_ID)
                self._start_transit('raise', pose.raise_path(), now)
            return
        if not self._monitor_transit(now) or not arm_idle:
            return
        if not self.transit.evidence_ok(now):
            return self._transit_abort('HIGH_TRANSIT_EVIDENCE_INCOMPLETE', now)
        if not self.transit.complete(now):
            return   # own HIGH view still moving; monitor bounds this wait
        obs = self.look(now)
        rgb = m2.study.ob.decode(obs['image'])[..., ::-1]
        line = edge_line(np.ascontiguousarray(rgb))
        if not pose.at_high(self._issued()) or line is None:
            return self._transit_abort('HIGH_CARRY_EDGE_NOT_SEEN', now)
        # Only a continuous validated held relation can mint the HIGH anchor.
        self._anchor('high', obs, now)
        self.anchor = m2.study.ob.held_signature(obs['image'])
        self.anchor_kind = 'lime_v1'
        self.anchor_full = self.pose_anchors['high'].mask.copy()
        self.high_ready = True
        self.log(self.rid, 'high_carry_view', now, edge_columns=line[2], slope=line[0],
                 pose_id=pose.POSE_ID, physical_success=None)
        self.set('wait_carry', now)

    def hold_state(self, obs):
        # Before raising, keep the original floor/low grip checks. After HIGH
        # admission, anchors live until release/abort, and only at their pose.
        if not getattr(self, 'high_raising', False):
            return super().hold_state(obs)
        servo = self.pose_of(obs)
        name = 'high' if pose.at_high(servo) else 'floor'
        anchor = self.pose_anchors.get(name)
        eligible = (anchor is not None and anchor.epoch == self.grip_epoch
                    and anchor.pose == grip.pose_key(servo)
                    and (self.high_ready if name == 'high' else self.floor_return_verified)
                    and servo.get(1) == 1500)
        iou = m2.hv3.hold_iou(anchor.mask, obs['image']) if eligible else 0.
        # HIGH: commanded-geometry held relation AND the HIGH anchor. Floor:
        # the original floor-grasp anchor only (the same pre-lift check type).
        relation = (grip.relation(obs['image'], servo) if name == 'high' else {'ok': True}) if eligible else {'ok': False}
        return {'ok': bool(eligible and relation['ok'] and iou >= m2.hv3.HOLD_MIN_IOU),
                'v1_ratio': 0., 'v3_iou': iou, 'decided_by': 'pose_epoch_anchor:'+name}

    def _wait_carry(self, now, arm_idle):
        if not getattr(self, 'high_ready', False):
            return self.fail('HIGH_CARRY_VIEW_REQUIRED', now)
        if getattr(self, 'checkpoint_fix_after', None) is not None:
            from harness.zone_own_contract import pose_report_fresh
            from harness.zone_pair_highpose_timing import CHECKPOINT_REOBSERVE_S
            report = self.port.own.last_report
            fresh = (report is not None and pose_report_fresh(report, now)
                     and report.initialized and report.last_fix_t is not None
                     and report.last_fix_t > self.checkpoint_fix_after
                     and report.std_xy_m <= .05 and report.std_yaw_rad <= np.deg2rad(3.))
            if now-self.checkpoint_started > 8.:
                return self._transit_abort('HIGH_CHECKPOINT_REOBSERVE_TIMEOUT', now)
            if now >= self.next_look:
                self.next_look = now+m2.study.LOOK_EVERY_S
                obs = self.look(now)
                if not self.hold_state(obs)['ok']:
                    return self._transit_abort('HIGH_CHECKPOINT_GRIP_CHANGED', now)
                self.report('carry', obs, now, ready=False, reason='HIGH stop/reobserve pending')
            if not fresh or now-self.checkpoint_started < CHECKPOINT_REOBSERVE_S:
                return
            self.grasp_estimate = [float(report.x_m), float(report.y_m), float(report.yaw_rad)]
            self.log(self.rid, 'checkpoint_high_reobserved', now, seg=self.seg,
                     fix_t=report.last_fix_t, high=True, opened=False, epoch=self.grip_epoch)
            self.checkpoint_fix_after = None
        provider = self.port.own.pose.provider
        if not provider.beam_edge.available(now):
            if now-self.state_t > m2.study.STATE_LIMIT_S['wait_carry']:
                return self.fail('HIGH_CARRY_EDGE_REFERENCE_TIMEOUT', now)
            if now >= self.next_look:
                self.next_look = now+m2.study.LOOK_EVERY_S
                self.report('carry', self.look(now), now, ready=False, reason='HIGH edge reference pending')
            return
        return super()._wait_carry(now, arm_idle)

    def _wait_lower(self, now, arm_idle):
        if self.seg+1 < len(self.segments):
            # Same end-of-leg lower barrier is a STOP rendezvous only. It never
            # queues lower/open/raise. Change segment keys after both stop.
            def checkpoint(t):
                self.seg += 1
                self.checkpoint_started = t
                self.checkpoint_fix_after = t
                self.grasp_estimate = None
                self.next_look = t
                self.port.own.pose.begin_relocalization(t, self._issued())
                self.log(self.rid, 'checkpoint_high_stop', t, seg=self.seg,
                         high=True, opened=False, epoch=self.grip_epoch)
            self._wait('lower', 'wait_carry', now, checkpoint)
            return
        def go(t):
            self.high_ready = False
            self.floor_return_verified = False
            self._start_transit('lower', pose.lower_path(), t)
        # Guard against the parent's unconditional set(nxt) after on_go when
        # the first lower observation already failed.
        self._wait('lower', 'lower', now, go)
        if self.transit is not None and self.transit.failure:
            self._transit_abort(self.transit.failure, now)

    def _lower(self, now, arm_idle):
        if getattr(self, 'floor_check_until', None) is None:
            if not self._monitor_transit(now) or not arm_idle:
                return
            if not self.transit.evidence_ok(now):
                return self._transit_abort('LOWER_TRANSIT_EVIDENCE_INCOMPLETE', now)
            # Anchor lifetime: the floor anchor was taken at this exact closed
            # floor pose in this grasp epoch, before any lift. A lagging partner
            # may still be lowering, so allow a bounded re-check; a slipped
            # beam never returns to the grasp-time view and is refused.
            self.floor_check_until = now+grip.SAMPLE_S+grip.FLOOR_CONFIRM_MAX_S
            return   # first floor view on the next control sample
        if now < self.next_transit_look-1e-8:
            return
        self.next_transit_look = now+grip.SAMPLE_S
        obs = self.look(now)
        anchor = self.pose_anchors.get('floor')
        valid = (anchor is not None and anchor.epoch == self.grip_epoch
                 and anchor.pose == grip.pose_key(self._issued()) and self._issued().get(1) == 1500)
        iou = m2.hv3.hold_iou(anchor.mask, obs['image']) if valid else 0.
        self.log(self.rid, 'floor_return_view', now, iou=iou, epoch=self.grip_epoch,
                 frame_id=obs['frame_id'], anchor_frame_id=None if anchor is None else anchor.frame_id)
        if valid and iou >= m2.hv3.HOLD_MIN_IOU:
            self.floor_check_until = None
            self.floor_return_verified = True
            return self.set('wait_open', now)
        if not valid or now >= self.floor_check_until-1e-8:
            self.floor_check_until = None
            return self._transit_abort('FLOOR_RETURN_GRIP_CHANGED', now)

    def _wait_open(self, now, arm_idle):
        if self.seg+1 < len(self.segments) or not self.floor_return_verified:
            return self._transit_abort('FINAL_VERIFIED_FLOOR_RELEASE_REQUIRED', now)
        return super()._wait_open(now, arm_idle)

class CommandGuard(PreviousGuard):
    def check(self, now, commands):
        moving = any(c['kind'] == 'mecanum' and any(c.get(k, 0.) != 0.
                     for k in ('forward', 'left', 'turn')) for c in commands)
        if moving and self.carrying_beam and not pose.at_high(self.ep.own.servo):
            self.ep.abort(now, 'LOADED_BASE_MOTION_REQUIRES_HIGH')
            return [{'kind': 'hold'}]
        return super().check(now, commands)


class Execution(previous.Execution):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ctl = self.controller
        ctl.__class__ = type('HighPairController', (HighController, type(ctl)), {})
        ctl.high_raising, ctl.high_ready = False, False
        ctl.grip_epoch, ctl.pose_anchors, ctl.transit = 0, {}, None
        ctl.floor_return_verified, ctl.floor_check_until = False, None
        self.command_guard = CommandGuard(self, self.vision)


class Team(previous.Team):
    def __init__(self, executors, calibration, static_task):
        super().__init__(executors, calibration, static_task)
        def make_execution(own, status, arguments, plan, params, factory, *, policy):
            return Execution(own, status, arguments, plan, params, calibration=calibration)
        self.start = MethodType(bind(previous.pair.PairTeam.start,
            make_plan=previous.make_plan, PairExecution=make_execution), self)

    def records(self):
        rows = super().records()
        for row in rows:
            row.update(pair_policy='b-v6h1-v3-highpose-opencv', high_pose=pose.record(),
                       previous_acceptance_inherited=False)
        return rows


class Runtime(PreviousRuntime):
    def __init__(self, static, calibration_path, calibration_sha, *, seed, provider_factory=None):
        from harness.vision_pose_source_highpose import build_provider
        initialize = bind(PreviousRuntime.__init__, Team=Team)
        initialize(self, static, calibration_path, calibration_sha, seed=seed,
                   provider_factory=provider_factory or build_provider)
