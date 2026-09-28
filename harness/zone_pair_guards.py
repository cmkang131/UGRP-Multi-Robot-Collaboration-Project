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
        self.monitor = ProgressMonitor()
        self.segment = None
        self.last_evidence = None
        self.stationary_pose = None
        self.motion_until = -math.inf
        self.recheck = _PairRecheck()
        if isinstance(execution.controller.driver, GuardedPairApproach):
            execution.controller.driver.sweep_recheck = self.recheck
        self._pose(execution.own.now)

    @property
    def approach(self):
        return self.ep.controller.state in ('approach', 'reapproach', 'wait_approach')

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
        ok = self.beam_track.observe_standoff(obs, own.servo, self.ep.controller.seg)
        self.ep.log(own.robot_id, 'beam_standoff', now, accepted=ok,
                    frame_id=obs['frame_id'], sha256=obs['sha256'],
                    beam=copy.deepcopy(self.beam_track.beam) if ok else None)
        return ok

    def _pose(self, now):
        report = self.ep.own.last_report
        pose = OwnPose.from_report(report)
        fresh = pose_report_fresh(report, now)
        # Cache only a bounded own estimate AFTER the last base command ended.
        # A reset localizer has no pose yet, but cannot move a stationary base.
        if fresh and pose is not None:
            if (now >= self.motion_until and (self.motion_until == -math.inf or report_at_or_after(report, self.motion_until))
                    and not self._high(pose)):
                self.stationary_pose = pose
            return pose
        if (fresh and not report.initialized and self.reobserving
                and now >= self.motion_until):
            return self.stationary_pose
        return None

    def _high(self, pose):
        p = self.ep.own.gate.profile
        return pose.std_xy > p.high_xy_m or pose.std_yaw > p.high_yaw_rad

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
        if self.recheck.check_gate(now, ready=not self._high(pose)) == 'blocked':
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
                self.recheck.check_gate(now, ready=pose is not None and not self._high(pose))
            return commands
        pose, report = self._pose(now), own.last_report
        if self.reobserving and not self._stationary_reobserve(now, pose):
            return [{'kind': 'hold'}]
        reason = None
        if pose is None:
            reason = 'POSE_UNCERTAIN'
        elif not self.reobserving and (self._high(pose) or (loaded and not own.gate.ok)):
            reason = 'POSE_UNCERTAIN'
        if reason is None and self.reobserving and (now < self.motion_until or any(
                c['kind'] not in ('hold', 'arm', 'look') for c in commands)):
            reason = 'POSE_UNCERTAIN'
        if reason is None and loaded and not self.reobserving:
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
        guard = PairSweepGuard(own.guard, ep.plan['beam_geometry'], ep.arguments['role'])
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
                if not own.gate.ok and getattr(ep.controller.driver, 'state', None) != 'guard_backoff':
                    reason = 'POSE_UNCERTAIN'
                    break
                if not guard.motion_clear(servo, pose, cmd, loaded=self.carrying_beam):
                    reason = 'PAIR_COLLISION_GUARD'
                    break
        if reason:
            ep.abort(now, reason)
            return [{'kind': 'hold'}]
        return commands
