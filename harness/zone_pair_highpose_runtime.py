"""Instance-only pose adaptation of the existing v3 beam-relative student."""
from types import MethodType

import numpy as np

from harness import zone_final_pair_skill as previous
from harness import zone_pair_highpose as pose
from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_runtime import Runtime as PreviousRuntime
from harness.zone_final_pair_guards import CommandGuard as PreviousGuard
from harness.own_beam_edge import edge_line
from scripts import run_m2_pair as m2


class HighController:
    def set(self, state, now, **detail):
        if state == 'wait_carry' and getattr(self, '_checking_low_lift', False):
            # Do not emit a P03 relift receipt until HIGH is also observed.
            self.low_lift_confirmed = True
            return
        return super().set(state, now, **detail)

    def _queue_open_descent(self, now):
        self.high_raising, self.high_ready = False, False
        self.low_lift_confirmed = False
        return super()._queue_open_descent(now)

    def _lift(self, now, arm_idle):
        if not getattr(self, 'high_raising', False):
            # Keep the existing floor -> low lift RGB co-motion decision.
            self._checking_low_lift = True
            try:
                super()._lift(now, arm_idle)
            finally:
                self._checking_low_lift = False
            if getattr(self, 'low_lift_confirmed', False):
                self.high_raising, self.high_ready = True, False
                pose.queue_path(self.arm, now, pose.raise_path())
                self.set('lift', now, subphase='raise_to_high', pose_id=pose.POSE_ID)
            return
        if not arm_idle:
            return
        obs = self.look(now)
        rgb = m2.study.ob.decode(obs['image'])[..., ::-1]
        line = edge_line(np.ascontiguousarray(rgb))
        if not pose.at_high(self.pose_of(obs)) or line is None:
            return self.fail('HIGH_CARRY_EDGE_NOT_SEEN', now)
        # Pose change invalidates the low-view hold anchors. Establish a new
        # own-RGB anchor only after a visible HIGH edge; never reuse low IoU.
        self.anchor = m2.study.ob.held_signature(obs['image'])
        self.anchor_kind = 'lime_v1'
        self.anchor_full = m2.hv3.hold_view_mask(obs['image'])
        self.high_ready = True
        self.log(self.rid, 'high_carry_view', now, edge_columns=line[2], slope=line[0],
                 pose_id=pose.POSE_ID, physical_success=None)
        self.set('wait_carry', now)

    def _wait_carry(self, now, arm_idle):
        if not getattr(self, 'high_ready', False):
            return self.fail('HIGH_CARRY_VIEW_REQUIRED', now)
        # Let the same delayed own-camera BeamEdgeTracker acquire a reference
        # before advertising carry readiness. No new barrier/message fields.
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
        def go(t):
            self.high_ready = False
            pose.queue_path(self.arm, t, pose.lower_path())
        self._wait('lower', 'lower', now, go)


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
