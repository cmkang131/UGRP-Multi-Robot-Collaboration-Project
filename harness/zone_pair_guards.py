"""Own executor guards around the frozen M2 approach and command stream.

Unloaded approach reuses the merged guarded driver's bounded look/back-off
recovery. After joint grasp, an unsafe or stalled robot aborts through STATUS;
it must not drag its peer into a unilateral navigation recovery.
"""
from __future__ import annotations

import math
from dataclasses import replace

from harness.pair_owncam_approach import PairApproachDriverV2
from harness.zone_own_driver import GuardedDriver
from harness.zone_own_guards import (BACKOFF_GAIN_MAX, GATE_LOADED, GATE_UNLOADED,
                                     TRUSTED_TAG_AGE_S, OwnPose, ProgressMonitor, commanded_step_m)
from harness.zone_pair_status import CONTROL_S


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

    def _event(self, now, kind, **detail):
        # Pair v2 rejects low-sigma looks without an actual tag. Apply that rule
        # before GuardedDriver lets the progress monitor trust the look.
        if kind == 'look_done' and detail.get('fixed'):
            detail['fixed'] = (self.loc.last_tag_t is not None and self.look_t0 is not None
                               and self.loc.last_tag_t >= self.look_t0)
        return super()._event(now, kind, **detail)


class PairCommandGuard:
    def __init__(self, execution):
        self.ep = execution
        self.monitor = ProgressMonitor()
        self.segment = None
        self.last_evidence = None

    @property
    def approach(self):
        return self.ep.controller.state in ('approach', 'reapproach', 'wait_approach')

    def on_command(self, row):
        if not self.approach:
            self.monitor.drove(commanded_step_m(row))

    def before_control(self, now):
        own = self.ep.own
        own.gate.set_profile(GATE_UNLOADED if self.approach else GATE_LOADED)
        if self.ep.controller.state not in ('approach', 'reapproach'):
            report = own.last_report
            if (not own.gate.ok or OwnPose.from_report(report) is None
                    or not 0 <= now - report.t_est <= .3 + 1e-9):
                self.ep.abort(now, 'POSE_UNCERTAIN')
                return False
        return True

    def check(self, now, commands):
        ep, own = self.ep, self.ep.own
        loaded = not self.approach
        own.gate.set_profile(GATE_LOADED if loaded else GATE_UNLOADED)
        if not any(c['kind'] in ('arm', 'look', 'mecanum', 'drive') for c in commands):
            return commands
        pose, report = OwnPose.from_report(own.last_report), own.last_report
        reason = None
        if pose is None or not 0 <= now - report.t_est <= .3 + 1e-9:
            reason = 'POSE_UNCERTAIN'
        elif loaded and not own.gate.ok:
            reason = 'POSE_UNCERTAIN'
        if reason is None and loaded:
            # A new segment has its own movement baseline. Heartbeats and
            # repeated reads of one frame never count as a fresh stall check.
            if self.segment != ep.controller.seg:
                self.monitor.reset()
                self.segment, self.last_evidence = ep.controller.seg, None
            evidence = (own.last_obs['frame_id'], report.t_est)
            if (evidence != self.last_evidence and report.since_tag_s is not None
                    and report.since_tag_s <= TRUSTED_TAG_AGE_S and report.std_xy_m <= own.gate.profile.low_xy_m):
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
        for cmd in commands if reason is None else ():
            if cmd['kind'] in ('arm', 'look'):
                sid = 6 if cmd['kind'] == 'look' else int(cmd['servo_id'])
                target = {**servo, sid: cmd['pan_pulse'] if sid == 6 and cmd['kind'] == 'look' else cmd['pulse']}
                plan = own.guard.plan(servo, target, [target[6]], pose, loaded=loaded, allow_backoff=False)
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
                for u in (0., .5, 1.):
                    dt = CONTROL_S * BACKOFF_GAIN_MAX * u
                    moved = pose.moved(cmd.get('forward', 0.) * dt, cmd.get('left', 0.) * dt)
                    for sign in (-1., 1.):
                        swept = replace(moved, yaw=moved.yaw + sign * abs(cmd.get('turn', 0.)) * dt)
                        if (own.guard.chassis_clearance(swept)[0] < 0.
                                or own.guard.arm_clearance(servo, swept, loaded=loaded)[0] < 0.):
                            reason = 'PAIR_COLLISION_GUARD'
                            break
                    if reason:
                        break
        if reason:
            ep.abort(now, reason)
            return [{'kind': 'hold'}]
        return commands
