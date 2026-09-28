"""Own executor guards around the frozen M2 approach and command stream.

Unloaded approach reuses the merged guarded driver's bounded look/back-off
recovery. After joint grasp, an unsafe or stalled robot aborts through STATUS;
it must not drag its peer into a unilateral navigation recovery.
"""
from __future__ import annotations

import copy
import math

from harness.pair_owncam_approach import PairApproachDriverV2
from harness.zone_own_contract import pose_report_fresh
from harness.owncam_time import report_at_or_after
from harness.zone_own_driver import GuardedDriver
from harness.zone_own_guards import (GATE_LOADED, GATE_UNLOADED,
                                     TRUSTED_FIX_AGE_S, OwnPose, ProgressMonitor, commanded_step_m)
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_own_sweep import SweepRecheck


class _PairRecheck(SweepRecheck):
    """One cumulative budget for HIGH estimates and blocked stationary sweeps.

    A geometrically clear arm step may run while HIGH, but must not stop the
    uncertainty clock. Overlapping gate/geometry waits count only once.
    """
    def __init__(self):
        super().__init__()
        self.uncertain = False
        self.sweep_waiting = False
        # Review 3: a planned safety look (envelope growth by issued motion)
        # is expected work, charged to its own registered per-look/total
        # budget. Only the excess over that allowance spends HIGH recovery.
        self.scheduled = None
        self.scheduled_count = 0
        self.scheduled_total_s = 0.

    def begin_scheduled(self):
        from harness.zone_pair_global import SCHEDULED_REOBSERVE as budget
        if self.scheduled is not None:
            return True  # the active planned look continues; no second count
        if (self.scheduled_count >= budget['max_count']
                or self.scheduled_total_s >= budget['total_s'] - 1e-9):
            return False
        self.scheduled_count += 1
        self.scheduled = {'index': self.scheduled_count, 'waited_s': 0.}
        return True

    def end_scheduled(self, now):
        self._account_wait(now)
        self.scheduled = None

    def _account_wait(self, now):
        if self.last_wait is None:
            return
        from harness.zone_pair_global import SCHEDULED_REOBSERVE as budget
        dt = max(0., now - self.last_wait)
        self.last_wait = None
        if self.scheduled is not None:
            room = max(0., min(budget['per_look_s'] - self.scheduled['waited_s'],
                               budget['total_s'] - self.scheduled_total_s))
            used = min(dt, room)
            self.scheduled['waited_s'] += used
            self.scheduled_total_s += used
            dt -= used
        self.waited_s += dt

    def check_gate(self, now, *, ready):
        self.uncertain = not ready
        return super().check_gate(now, ready=ready and not self.sweep_waiting)

    def check(self, now, *args, **kwargs):
        result = super().check(now, *args, **kwargs)
        self.sweep_waiting = result == 'wait'
        if result == 'clear' and self.uncertain and self._wait(now) == 'blocked':
            return 'blocked'
        return result


class GuardedPairApproach(GuardedDriver, PairApproachDriverV2):
    """GuardedDriver hooks with the frozen M2 heading/pursuit/relocalization policy.

    Exactly one own pose source receives frames and commands. The loc property
    also keeps the frozen controller's explicit relocalization assignments local
    to that same source. observe() consumes an already processed own frame.
    """
    def __init__(self, own, params, **kwargs):
        self._shared_pose = None
        super().__init__(own.pose.loc, own.map, params, gate=own.gate, guard=own.guard, **kwargs)
        self._shared_pose = own.pose

    @property
    def loc(self):
        return self._shared_pose.loc if self._shared_pose is not None else self._initial_loc

    @loc.setter
    def loc(self, value):
        if self._shared_pose is None:
            self._initial_loc = value
        else:
            self._shared_pose.loc = value

    def observe(self, now, rgb):
        self.frames_seen += 1
        self.loc.predict_to(now)
        self.last_estimate = self.loc.estimate()
        return self.last_estimate

    def _look_step(self, now):
        # OwnCamDriver resets the counter before emitting look_done. Preserve
        # the prior value before requiring an accepted observation fix.
        self._looks_before_step = self.looks_without_fix
        verify = getattr(self, 'verified_global_fix', None)
        if verify is not None:
            ready = verify(now, self.look_t0)
            if ready:
                self.look_queue.clear()  # the requested new fix is complete
            elif (ready is False and not self.look_queue
                  and all(self.servo.get(k)==v for k,v in self.arm_target.items())):
                from harness.zone_pair_global import SCHEDULED_REOBSERVE
                # Final review P2-1: this dwell is bounded by the registered
                # per-look allowance; afterwards the frozen look_done path
                # (no fix -> GATE_MAX_LOOKS / relocalize) takes over.
                if self.look_t0 is None or now-self.look_t0 < SCHEDULED_REOBSERVE['per_look_s']-1e-9:
                    return [{'kind':'hold'}]  # allow the three-receipt check to finish
        # Bypass the frozen V2 post-hook: its receipt is provider-specific.
        # _event below applies the same rule using the common report contract.
        return super(PairApproachDriverV2, self).tick(now)

    def _start_look(self, now, reason, **kwargs):
        budget = self.sweep_recheck
        commands = super()._start_look(now, reason, **kwargs)
        # Pair recovery is cumulative for the job, including repeated M2 looks.
        self.sweep_recheck = budget
        return commands

    def _event(self, now, kind, **detail):
        # A low sigma alone is not a new observation fix.
        report = (self._shared_pose.report(now)
                  if kind == 'look_done' and detail.get('fixed') and self._shared_pose is not None else None)
        fixed_at = None if report is None else report.last_fix_t
        missing_fix = (kind == 'look_done' and detail.get('fixed')
                       and not (fixed_at is not None and self.look_t0 is not None
                                and fixed_at >= self.look_t0))
        if missing_fix:
            detail['fixed'] = False
            self.looks_without_fix = self._looks_before_step + 1
        super()._event(now, kind, **detail)
        if missing_fix:
            super()._event(now, 'look_no_fix', looks_without_fix=self.looks_without_fix)

    def _relocalize(self, now):
        self.relocalizations += 1
        self._shared_pose.begin_relocalization(now, self.servo)
        self.looks_without_fix = 0
        self.turn_ref = None
        self.path = None
        self._event(now, 'relocalize', count=self.relocalizations)
        return self._start_look(now, 'relocalize')



class PairCommandGuard:
    def __init__(self, execution):
        from harness.zone_pair_beam_track import RestingBeamTrack

        self.ep = execution
        self.beam_track = RestingBeamTrack()
        from harness.zone_pair_global import GlobalEnvelope
        from harness.zone_pair_relative import RelativeBeamTrack
        self.relative_track = RelativeBeamTrack()
        self.global_envelope = GlobalEnvelope()
        self.object_anchor = None
        self.anchor_motion = None
        self.monitor = ProgressMonitor()
        self.segment = None
        self.last_evidence = None
        self.stationary_pose = None
        self.motion_until = -math.inf
        self.recheck = _PairRecheck()
        if isinstance(execution.controller.driver, GuardedPairApproach):
            execution.controller.driver.sweep_recheck = self.recheck
            execution.controller.driver.verified_global_fix = self.approach_fix_ready
        self._pose(execution.own.now)

    @property
    def approach(self):
        return self.ep.controller.state in ('approach', 'reapproach', 'wait_approach')

    def approach_fix_ready(self, now, started):
        if not self.relative_enabled:
            return None
        from harness.owncam_time import accepted_fix_checks
        from harness.zone_pair_v6_policy import informative_fix
        report = self.ep.own.last_report
        return (started is not None and all(accepted_fix_checks(report,now,started).values())
                and informative_fix(report) and self.ep.own.gate.ok
                and self.global_certificate(now)['clear'])

    @property
    def relative_enabled(self):
        return bool(getattr(getattr(self.ep, 'policy', None), 'beam_relative', False))

    @property
    def relative_manipulation(self):
        return self.relative_enabled and self.ep.controller.state in (
            'align', 'pregrasp_standoff', 'pregrasp_descend', 'wait_close', 'grasp')

    def sweep_guard(self):
        from harness.zone_pair_global import GlobalPairSweepGuard
        cls = GlobalPairSweepGuard if self.relative_enabled else PairSweepGuard
        return cls(self.ep.own.guard, self.ep.plan['beam_geometry'], self.ep.arguments['role'])

    def relative_report(self, now, obs):
        mode = 'attached_hypothesis' if self.carrying_beam else 'resting_hypothesis'
        result = self.relative_track.observe(obs, self.ep.own.servo, self.ep.controller.seg, now=now, mode=mode)
        self.ep.log(self.ep.own.robot_id, 'beam_relative', now, report=result.as_dict())
        self._anchor_object(now, result)
        return result

    # ---- object-anchored align safety (review 3 + literature recipe) ----------
    # During a+b align/pre-close the PF is a reference, not a stop condition.
    # The resting beam is static: one entry fix places it in the world; later
    # own relative views then bound the robot pose without dead-reckoning
    # growth. Wall/arm clearance is still certified on that bound.

    def _anchor_object(self, now, report):
        if not self.relative_manipulation or self.carrying_beam:
            return
        a = self.object_anchor
        if a is not None and a['segment'] == self.ep.controller.seg and self.relative_track.beam is not None:
            return
        self.object_anchor = None
        if not report.ready(now) or self._partner_grasping():
            return  # a loose far-range bound would make a loose world anchor
        entry = self.global_envelope.pose(self.ep.own.last_report, now)
        if entry is None or self._high(entry):
            return
        g = report.grip_base_m
        c, s_ = math.cos(entry.yaw), math.sin(entry.yaw)
        bound = report.std_xy_m+report.bias_bound_m
        # Final review P1-3: own issued base motion since the anchor, with the
        # same half-gain centre / [0, 1.6] gain reach as the global envelope,
        # in the anchor-time robot frame. The static-beam premise is checked
        # against it on every use (cumulative association, not frame-to-frame).
        from harness.zone_pair_global import GlobalEnvelope
        motion = GlobalEnvelope()
        motion.anchor, motion.fix_t, motion.t = OwnPose(0., 0., 0., 0., 0.), now, now
        motion.motion, motion.until = self.global_envelope.motion, self.global_envelope.until
        self.anchor_motion = motion
        self.object_anchor = {
            'segment': self.ep.controller.seg, 't': now, 'entry_fix_t': self.global_envelope.fix_t,
            'grip_world': (entry.x+c*g[0]-s_*g[1], entry.y+s_*g[0]+c*g[1]),
            'heading_world': entry.yaw+report.axis_heading_rad,
            'std_xy': entry.std_xy+entry.std_yaw*math.hypot(*g)+bound,
            'std_yaw': entry.std_yaw+report.std_yaw_rad,
            'frame_id': report.frame_id, 'sha256': report.sha256,
            'rel_grip': tuple(g), 'rel_heading': report.axis_heading_rad,
            'rel_bound': bound, 'rel_std_yaw': report.std_yaw_rad}
        self.ep.log(self.ep.own.robot_id, 'object_anchor', now, anchor=dict(self.object_anchor),
                    source='entry global envelope + own relative beam view; PF reference only afterwards')

    @property
    def object_anchor_active(self):
        from harness.zone_pair_align import RELOOK_STATES
        return self.relative_manipulation or (self.relative_enabled and self.ep.controller.state in RELOOK_STATES)

    def object_pose(self, now):
        a = self.object_anchor
        if (a is None or not self.object_anchor_active or self.carrying_beam
                or a['segment'] != self.ep.controller.seg):
            return None
        track = self.relative_track
        track.advance(now)
        b = track.beam
        if b is None or track.segment != a['segment']:
            self.object_anchor = None
            return None
        why = self._anchor_invalid(now, a, b)
        if why is not None:
            self.object_anchor = None
            self.ep.log(self.ep.own.robot_id, 'object_anchor_invalidated', now, reason=why)
            return None
        g = b['grip_base_m']
        yaw = a['heading_world']-b['axis_heading_rad']
        std_yaw = a['std_yaw']+b['std_yaw_rad']
        c, s_ = math.cos(yaw), math.sin(yaw)
        x = a['grip_world'][0]-(c*g[0]-s_*g[1])
        y = a['grip_world'][1]-(s_*g[0]+c*g[1])
        std_xy = a['std_xy']+b['std_xy_m']+b['bias_bound_m']+std_yaw*math.hypot(*g)
        return OwnPose(x, y, (yaw+math.pi) % (2*math.pi)-math.pi, std_xy, std_yaw)

    PARTNER_GRASP_STATES = ('ready', 'lift', 'carry', 'put_down')

    def _partner_grasping(self):
        # Messaged peer phase only (no peer pose): its closing/holding fingers
        # may move the beam, so the static-beam premise no longer holds.
        channel = self.ep.controller.status[0]
        me = self.ep.own.robot_id
        for rid, msg in channel.latest.items():
            state = msg.get('state') or ''
            if rid != me and (state in self.PARTNER_GRASP_STATES
                              or any(state.startswith(f'{p}_') for p in ('close', 'lift', 'carry', 'lower', 'open'))):
                return True
        return False

    def _anchor_invalid(self, now, a, b):
        """Final review P1-3: verify the static-beam premise of the object anchor."""
        from harness.zone_own_guards import K_SIGMA
        from harness.zone_pair_global import heading_spread, _wrap
        if self._partner_grasping():
            return 'PARTNER_HOLDING_PHASE'
        m = getattr(self, 'anchor_motion', None)
        if m is None:
            return 'ANCHOR_MOTION_UNKNOWN'
        m.advance(now)
        cx, cy = m.centre_offset
        th, yaw_tol = m.centre_turn, m.turn_bound/2
        d = (a['rel_grip'][0]-cx, a['rel_grip'][1]-cy)
        expected = (math.cos(th)*d[0]+math.sin(th)*d[1], -math.sin(th)*d[0]+math.cos(th)*d[1])
        tol_xy = (m.travel_bound*heading_spread(yaw_tol)+yaw_tol*math.hypot(*d)
                  + K_SIGMA*(a['rel_bound']+b['std_xy_m']+b['bias_bound_m']))
        tol_yaw = yaw_tol+K_SIGMA*(a['rel_std_yaw']+b['std_yaw_rad'])
        if (math.dist(b['grip_base_m'], expected) > tol_xy
                or abs(_wrap(b['axis_heading_rad']-(a['rel_heading']-th))) > tol_yaw):
            return 'BEAM_MOVED_SINCE_ANCHOR'
        return None

    def safety_pose(self, now, envelope=None):
        """Componentwise tighter of two independent enclosing bounds."""
        envelope = self.global_envelope.pose(self.ep.own.last_report, now) if envelope is None else envelope
        anchored = self.object_pose(now)
        if anchored is None:
            return envelope
        if envelope is None:
            return anchored
        from harness.zone_own_guards import K_SIGMA
        from harness.zone_pair_global import _wrap
        if (math.dist((envelope.x, envelope.y), (anchored.x, anchored.y)) > K_SIGMA*(envelope.std_xy+anchored.std_xy)
                or abs(_wrap(envelope.yaw-anchored.yaw)) > K_SIGMA*(envelope.std_yaw+anchored.std_yaw)):
            # Final review P1-3: two enclosing bounds that do not overlap mean
            # one premise failed (moved beam or bad fix). Drop the anchor;
            # the envelope path (and its relook/abort rules) decides.
            self.object_anchor = None
            self.ep.log(self.ep.own.robot_id, 'object_anchor_invalidated', now, reason='GLOBAL_ANCHOR_DISAGREE',
                        envelope=[envelope.x, envelope.y, envelope.yaw, envelope.std_xy, envelope.std_yaw],
                        anchored=[anchored.x, anchored.y, anchored.yaw, anchored.std_xy, anchored.std_yaw])
            return envelope
        xy = envelope if envelope.std_xy <= anchored.std_xy else anchored
        yaw = envelope if envelope.std_yaw <= anchored.std_yaw else anchored
        return OwnPose(xy.x, xy.y, yaw.yaw, xy.std_xy, yaw.std_yaw)

    def global_certificate(self, now, beam=None):
        envelope = self.global_envelope.pose(self.ep.own.last_report, now)
        anchored = self.object_pose(now) is not None
        pose = self.safety_pose(now, envelope)
        certificate = self.sweep_guard().certificate(self.ep.own.servo, pose, beam, loaded=self.carrying_beam,
                                                      reducible=self.envelope_reducible(pose))
        if anchored:
            # No PF-convergence (HIGH) stop while object-anchored; only the
            # safety bound's own reserve before its supported range stops.
            certificate['relook_reserve_low'] = self.sigma_reserve(pose)
        certificate['pose_source'] = 'object_anchored' if anchored else 'global_envelope'
        candidate = self.global_envelope.reacquisition
        certificate['reacquisition_count'] = 0 if candidate is None else candidate[3]
        self.ep.log(self.ep.own.robot_id, 'global_safety', now, certificate=certificate,
                    absolute_fix_t=self.global_envelope.fix_t,
                    pf_reference=None if envelope is None else [envelope.x, envelope.y, envelope.yaw,
                                                                envelope.std_xy, envelope.std_yaw])
        return certificate

    @property
    def reobserving(self):
        ctl = self.ep.controller
        from harness.zone_pair_align import RELOOK_STATES
        return (ctl.state in ('pregrasp_look', *RELOOK_STATES)
                or (ctl.state in ('approach', 'reapproach')
                    and getattr(ctl.driver, 'state', None) in ('look_arm', 'look_pan')))

    @property
    def carrying_beam(self):
        # Phase names and a closed PWM are not evidence of a held object.
        return bool(getattr(self.ep.controller, 'beam_grasp_confirmed', False))

    def preclose_check(self, now, obs):
        """Unattached stationary beam gate, shared by READY and each close PWM.

        A clipped band can constrain a segment-local standoff hypothesis.
        Commands/time grow its uncertainty; absent evidence still fails closed.
        """
        from harness.zone_pair_grasp import FIX_STD_XY_M, FIX_STD_YAW_RAD, stationary_beam_estimate
        from harness.zone_pair_vision import valid_frame

        own = self.ep.own
        if self.relative_enabled:
            if (now < self.motion_until or not valid_frame(obs, own.robot_id, now)
                    or not self._same_camera_commands(obs)):
                return False
            relative = self.relative_report(now, obs)
            return relative.ready(now) and self.global_certificate(now, relative.beam())['clear']
        pose = OwnPose.from_report(own.last_report)
        if (not pose_report_fresh(own.last_report, now) or pose is None or not own.gate.ok
                or not 0 <= pose.std_xy <= FIX_STD_XY_M or not 0 <= pose.std_yaw <= FIX_STD_YAW_RAD
                or now < self.motion_until or not valid_frame(obs, own.robot_id, now)
                or not self._same_camera_commands(obs)):
            return False
        beam = stationary_beam_estimate(obs, own.servo)
        if beam is None:
            beam = self.beam_track.estimate(now, obs, own.servo, self.ep.controller.seg)
        if beam is None:
            self.ep.log(own.robot_id, 'preclose_beam_guard', now, clear=False, reason='BEAM_UNCERTAIN')
            return False
        guard = PairSweepGuard(own.guard, self.ep.plan['beam_geometry'], self.ep.arguments['role'])
        clearance, wall = guard.stationary_beam_clearance(beam, pose)
        clear = clearance >= 0.  # margin() already includes the unchanged 35 mm
        self.ep.log(own.robot_id, 'preclose_beam_guard', now, clear=clear,
                    clearance_after_margin_m=clearance, wall_id=wall,
                    frame_id=obs['frame_id'], sha256=obs['sha256'], beam=beam)
        return clear

    def _same_camera_commands(self, obs):
        # A recent frame can still precede an arm command. Do not project it
        # with a different commanded camera FK. Finger PWM does not move it.
        try:
            image_servo = {int(k): v for k, v in obs['actuator_state']['servo_pulses'].items()}
            return all(image_servo[k] == self.ep.own.servo[k] for k in (3, 4, 5, 6))
        except (KeyError, TypeError, ValueError):
            return False

    def observe_standoff(self, now, obs):
        from harness.zone_pair_vision import valid_frame

        own = self.ep.own
        if (now < self.motion_until or own.servo.get(1) != 2000
                or not valid_frame(obs, own.robot_id, now) or not self._same_camera_commands(obs)):
            return False
        if self.relative_enabled:
            return self.relative_report(now, obs).ready(now)
        ok = self.beam_track.observe_standoff(obs, own.servo, self.ep.controller.seg)
        self.ep.log(own.robot_id, 'beam_standoff', now, accepted=ok,
                    frame_id=obs['frame_id'], sha256=obs['sha256'],
                    beam=copy.deepcopy(self.beam_track.beam) if ok else None)
        return ok

    def _pose(self, now):
        report = self.ep.own.last_report
        pose = OwnPose.from_report(report)
        fresh = pose_report_fresh(report, now)
        if self.relative_enabled:
            # The driver may plan toward a PF-mean goal, but EVERY command
            # (including approach/back-off and arm sweeps) uses this envelope.
            pose = self.global_envelope.pose(report, now)
            if self.object_anchor_active:
                # A stationary relook keeps the same static-beam bound.
                pose = self.safety_pose(now, pose)
            if pose is None and self.reobserving:
                pose = self.global_envelope.recovery_pose(report, now)
        # Cache only a bounded own estimate AFTER the last base command ended.
        # A reset localizer has no pose yet, but cannot move a stationary base.
        if fresh and pose is not None:
            if (now >= self.motion_until and (self.motion_until == -math.inf or report_at_or_after(report, self.motion_until))
                    and (not self._high(pose) or self.relative_enabled)):
                self.stationary_pose = pose
            return pose
        if (not self.relative_enabled and fresh and not report.initialized and self.reobserving
                and now >= self.motion_until):
            return self.stationary_pose
        return None

    def begin_scheduled_reobserve(self, now):
        ok = self.recheck.begin_scheduled()
        if ok:
            self.ep.log(self.ep.own.robot_id, 'scheduled_reobserve', now, index=self.recheck.scheduled['index'],
                        total_s=self.recheck.scheduled_total_s, reason='global_safety_reserve')
        else:
            self.ep.log(self.ep.own.robot_id, 'scheduled_reobserve_limit', now,
                        count=self.recheck.scheduled_count, total_s=self.recheck.scheduled_total_s)
        return ok

    def reset_phase_budget(self, now, phase):
        """HIGH recovery budget (SWEEP_REOBSERVE_S) is per phase entry (final review P2-2)."""
        r = self.recheck
        self.ep.log(self.ep.own.robot_id, 'phase_budget_reset', now, phase=phase,
                    previous_high_waited_s=r.waited_s, scheduled_count=r.scheduled_count)
        r.waited_s, r.last_wait, r.sweep_waiting, r.uncertain = 0., None, False, False
        r.scheduled = None

    @staticmethod
    def sigma_reserve(pose):
        # Same reserve as GlobalPairSweepGuard.certificate, before its .15/.20 support caps.
        return pose is None or pose.std_xy >= .10 or pose.std_yaw >= .15

    def envelope_reducible(self, pose):
        """A new fix can shrink the envelope only after it has grown (review 3).

        Without this, a thin static gap re-triggers looks forever with no drive.
        """
        from harness.zone_pair_global import SCHEDULED_REOBSERVE as budget
        dxy, dyaw = self.global_envelope.inflation(pose)
        return dxy >= budget['reducible_sigma_m'] or dyaw >= budget['reducible_sigma_rad']

    def _high(self, pose):
        p = self.ep.own.gate.profile
        return pose.std_xy > p.high_xy_m or pose.std_yaw > p.high_yaw_rad

    def _reobserve_ready(self, now, pose):
        return (pose is not None and not self._high(pose) and (not self.relative_enabled
                or self.global_envelope.pose(self.ep.own.last_report,now) is not None))

    def align_stop_ready(self, now, stopped_at):
        """Retain a valid post-hold own estimate before replacing its PF.

        A delayed report can be fresh yet still precede the hold. In that case
        leave the PF running; an old stationary cache alone is insufficient.
        The controller's existing per-look/total deadlines bound this wait.
        """
        own = self.ep.own
        pose = self._pose(now)
        report = own.last_report
        checks = {
            'after_stop': now > stopped_at,
            'initialized': report is not None and report.initialized,
            'report_fresh': pose_report_fresh(report, now),
            'report_after_stop': report_at_or_after(report, stopped_at),
            # Both are raw SIM times: only quantized REPORT comparisons above
            # have the existing 1e-4 s tolerance. Never soften raw fix bounds.
            'motion_ended_at_stop': stopped_at >= self.motion_until,
            'gate_ok': own.gate.ok,
            'pose_present': pose is not None,
            'pose_bounded': pose is not None and not self._high(pose),
            'stationary_pose_current': pose is not None and self.stationary_pose is pose,
        }
        if self.relative_enabled:
            checks.update(gate_ok=True, pose_bounded=pose is not None,
                          global_stationary_clear=self.sweep_guard().certificate(own.servo, pose)['clear'])
        ready = all(checks.values())
        if not ready:
            self.ep.log(own.robot_id, 'align_relook_stop_wait', now, checks=checks,
                        failed_checks=[k for k, ok in checks.items() if not ok],
                        stopped_at_s=stopped_at,
                        motion_until_s=self.motion_until if math.isfinite(self.motion_until) else None,
                        report_t=None if report is None else report.t_est)
        return ready

    def on_command(self, row):
        self.beam_track.command(row, self.ep.own.servo)
        if self.relative_enabled:
            self.relative_track.command(row, self.ep.own.servo)
            self.global_envelope.command(row)
            if getattr(self, 'anchor_motion', None) is not None:
                self.anchor_motion.command(row)
        if row['kind'] in ('drive', 'mecanum') and any(row.get(k, 0.) for k in ('forward', 'left', 'turn')):
            self.stationary_pose = None
            self.motion_until = row['t'] + row['duration_s']
        elif row['kind'] == 'hold' and self.motion_until > row['t']:
            self.motion_until = row['t']
        if not self.approach:
            self.monitor.drove(commanded_step_m(row))

    def before_control(self, now):
        own = self.ep.own
        expired = getattr(self.ep.controller, 'align_relook_expired', lambda t: False)
        if expired(now):
            self.ep.abort(now, 'ALIGN_RELOOK_TIMEOUT')
            return False
        own.gate.set_profile(GATE_UNLOADED if self.approach else GATE_LOADED)
        pose = self._pose(now)
        if self.reobserving:
            return self._stationary_reobserve(now, pose)
        if self.recheck.scheduled is not None:
            # Final review P1-1: a planned look ends as soon as its relook
            # (approach look or align relook) has returned, on every branch,
            # including the relative_manipulation early return below. Each
            # new planned look then gets its own per-look allowance and count.
            self.recheck.sweep_waiting = False
            self.recheck.end_scheduled(now)
        if self.relative_enabled and self.ep.controller.state in ('approach', 'reapproach', 'align'):
            # HIGH is a scheduling trigger, not a collision. Never let the
            # nominal PF's small sigma bypass the independent envelope.
            safety = pose or self.global_envelope.recovery_pose(own.last_report, now)
            cert = self.sweep_guard().certificate(own.servo, safety, reducible=self.envelope_reducible(pose))
            anchored = self.ep.controller.state == 'align' and self.object_pose(now) is not None
            if not cert['clear'] and not anchored:
                self.ep.abort(now, cert['reason'])
                return False
            if anchored and cert['clear'] and not self.sigma_reserve(safety):
                pass  # PF convergence is not an align stop condition while object-anchored
            elif pose is None or self._high(pose) or cert.get('relook_reserve_low') or not cert['clear']:
                # Anchored but no longer certifiable: stop and look (stationary,
                # same object bound) instead of aborting; re-anchor afterwards.
                ctl = self.ep.controller
                if not self.begin_scheduled_reobserve(now):
                    self.ep.abort(now, 'PAIR_SCHEDULED_REOBSERVE_LIMIT')
                    return False
                if ctl.state == 'align':
                    ctl._begin_align_relook(now, 'global_safety_reserve')
                else:
                    commands = ctl.driver._start_look(now, 'global_safety_reserve', allow_backoff=False)
                    self.ep.port.commands.extend(commands)
                return False  # endpoint issues the stop before any look commands
        if self.relative_manipulation:
            if not self.global_certificate(now)['clear']:
                self.ep.abort(now, 'GLOBAL_ENVELOPE_BLOCKED')
                return False
            return True
        self.recheck.sweep_waiting = False
        self.recheck.check_gate(now, ready=True)  # account prior wait; never refill
        if self.ep.controller.state not in ('approach', 'reapproach'):
            if not own.gate.ok or pose is None or self._high(pose):
                self.ep.abort(now, 'POSE_UNCERTAIN')
                return False
        return True

    def _stationary_reobserve(self, now, pose):
        if getattr(self.ep.controller, 'align_relook_expired', lambda t: False)(now):
            self.ep.abort(now, 'ALIGN_RELOOK_TIMEOUT')
            return False
        if self.carrying_beam:
            self.ep.abort(now, 'PAIR_RELOOK_WHILE_GRIPPED')
            return False
        if pose is None or now < self.motion_until:
            self.ep.abort(now, 'POSE_UNCERTAIN')
            return False
        if self.relative_enabled and not self.sweep_guard().certificate(self.ep.own.servo, pose)['clear']:
            self.ep.abort(now, 'GLOBAL_ENVELOPE_BLOCKED')
            return False
        if self.recheck.check_gate(now, ready=self._reobserve_ready(now,pose)) == 'blocked':
            self.ep.log(self.ep.own.robot_id, 'reobserve_timeout', now, waited_s=self.recheck.waited_s)
            self.ep.abort(now, 'PAIR_REOBSERVE_TIMEOUT')
            return False
        return True  # only checked stationary arm/camera commands, never base motion

    def check(self, now, commands):
        ep, own = self.ep, self.ep.own
        loaded = not self.approach
        own.gate.set_profile(GATE_LOADED if loaded else GATE_UNLOADED)
        # The drive -> look transition must apply its hold before testing that
        # the previous base command has ended. Arm/motion batches still need it.
        if not any(c['kind'] in ('arm', 'look', 'mecanum', 'drive') for c in commands):
            if self.reobserving:
                # Keep the HIGH budget's start time, but never veto a stop.
                # before_control() and arm/motion checks enforce exhaustion.
                pose = self._pose(now)
                self.recheck.check_gate(now, ready=self._reobserve_ready(now,pose))
            return commands
        pose, report = self._pose(now), own.last_report
        if self.reobserving and not self._stationary_reobserve(now, pose):
            return [{'kind': 'hold'}]
        reason = None
        if pose is None:
            reason = 'POSE_UNCERTAIN'
        elif not self.reobserving and not self.relative_manipulation and (self._high(pose) or (loaded and not own.gate.ok)):
            if self.relative_enabled and self.approach and self.before_control(now) is False:
                return [{'kind': 'hold'}]
            reason = 'POSE_UNCERTAIN'
        if reason is None and self.relative_enabled and not self.sweep_guard().certificate(
                own.servo, pose, loaded=self.carrying_beam)['clear']:
            reason = 'GLOBAL_ENVELOPE_BLOCKED'
        if reason is None and self.reobserving and (now < self.motion_until or any(
                c['kind'] not in ('hold', 'arm', 'look') for c in commands)):
            reason = 'POSE_UNCERTAIN'
        if reason is None and loaded and not self.reobserving and not self.relative_manipulation:
            # A new segment has its own movement baseline. Heartbeats and
            # repeated reads of one frame never count as a fresh stall check.
            if self.segment != ep.controller.seg:
                self.monitor.reset()
                self.segment, self.last_evidence = ep.controller.seg, None
            evidence = (own.last_obs['frame_id'], report.t_est)
            if (evidence != self.last_evidence and report.fix_age_s is not None
                    and report.fix_age_s <= TRUSTED_FIX_AGE_S and report.std_xy_m <= own.gate.profile.low_xy_m):
                target = ep.plan['route'][min(ep.controller.seg + 1, len(ep.plan['route']) - 1)]
                self.monitor.trusted((pose.x, pose.y), math.dist((pose.x, pose.y), target))
                self.last_evidence = evidence
            if self.monitor.stalled():
                reason = 'PAIR_blocked'
            elif self.monitor.needs_check():
                # A loaded pair cannot execute the single-robot back-off/look
                # recovery safely. Stop both; a new independent rendezvous is required.
                reason = 'POSE_UNCERTAIN_PROGRESS'
        servo = dict(own.servo)
        guard = self.sweep_guard()
        for cmd in commands if reason is None else ():
            if cmd['kind'] in ('arm', 'look'):
                sid = 6 if cmd['kind'] == 'look' else int(cmd['servo_id'])
                target = {**servo, sid: cmd['pan_pulse'] if sid == 6 and cmd['kind'] == 'look' else cmd['pulse']}
                if (sid == 1 and target[1] < servo.get(1, 2000) and not self.carrying_beam
                        and not self.preclose_check(now, own.last_obs)):
                    reason = 'PREGRASP_BEAM_UNSAFE'
                    break
                if self.reobserving:
                    result = self.recheck.check(now, guard, servo, target, pose, loaded=self.carrying_beam)
                    if result == 'wait':
                        return [{'kind': 'hold'}]
                    if result == 'blocked':
                        reason = 'PAIR_COLLISION_GUARD'
                        break
                plan = guard.plan(servo, target, [target[6]], pose, loaded=self.carrying_beam, allow_backoff=False)
                if plan['reason'] != 'clear' or not plan.get('transition_clear', False):
                    reason = 'PAIR_COLLISION_GUARD'
                    break
                servo = target
            elif cmd['kind'] in ('mecanum', 'drive'):
                # Bounded guarded approach back-offs are the only motion
                # permitted while the gate is uncertain (same as GuardedDriver).
                if (not own.gate.ok and not self.relative_manipulation
                        and getattr(ep.controller.driver, 'state', None) != 'guard_backoff'):
                    reason = 'POSE_UNCERTAIN'
                    break
                if not guard.motion_clear(servo, pose, cmd, loaded=self.carrying_beam):
                    reason = 'PAIR_COLLISION_GUARD'
                    break
        if reason:
            ep.abort(now, reason)
            return [{'kind': 'hold'}]
        return commands
