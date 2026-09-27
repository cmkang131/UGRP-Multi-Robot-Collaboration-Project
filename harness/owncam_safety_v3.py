"""Common v3 safety for matched memory-look ON/OFF. No condition branches.

Uses only own estimates, issued commands and the existing static collision API.
Successful looks cannot erase the separate no-progress budget.
"""
from __future__ import annotations

import math

from harness.owncam_drive import LOOK_IF_STD_XY_M, LOOK_IF_STD_YAW_RAD
from harness.owncam_drive_mem import ARRIVAL_OK_YAW_RAD
from harness.owncam_drive_v2 import LOADED_UNCERTAIN_STD_XY_M, LOADED_UNCERTAIN_STD_YAW_RAD
from harness.owncam_sweep_collision import OwnPose, commands_clear, plan_safe_sweep

SCHEMA = 'ugrp.owncam_safety.v3'
MAX_UNVERIFIED_LOOKS = 2
# Leave room for prediction during posture restoration; recheck the unchanged
# drive/arrival ceilings at dispatch. Both full and short fixes use this target.
FIX_ACCEPT_XY_M = {False: .04, True: .05}
FIX_ACCEPT_YAW_RAD = math.radians(2.)
ARRIVAL_FIX_ACCEPT_YAW_RAD = math.radians(1.3)
MAX_LOOKS_WITHOUT_PROGRESS = 4
MAX_LOOK_STAGNATION_S = 60.
MIN_GOAL_PROGRESS_M = .10
INIT_RECOVERY_S = 8.  # cumulative stationary time; paused only during a guarded sweep
INIT_MAX_CAPTURES = 20
INIT_CAPTURE_INTERVAL_S = .2
INIT_TIMEOUT_S = 30.  # includes sweeps; never paused/reset (rationale in the v3 design)


class LegSafetyV3:
    def _init_safety(self):
        self.verification_since = None
        self.unverified_looks = 0
        self.arrival_verifications = 0
        self.looks_without_progress = 0
        self.progress_goal_distance = None
        self.progress_drive_issued = False
        self.progress_since = None

    def on_command(self, row):
        super().on_command(row)
        if row['kind'] in ('mecanum', 'drive') and any(
                abs(row.get(k, 0.)) > 0 for k in ('forward', 'left')):
            self.progress_drive_issued = True
        elif row['kind'] in ('hold', 'stop'):
            self.progress_drive_issued = False

    def _look_stalled(self, now, *, starting=False):
        est = self.loc.estimate()
        if est.get('initialized') and self._current_uncertainty_ok(est) and self.memory.guard.consistent(now):
            distance = math.dist((est['x'], est['y']), self.goal)
            if self.progress_goal_distance is None:
                self.progress_goal_distance = distance
            elif (self.state == 'drive' and self.progress_drive_issued
                  and self.progress_goal_distance - distance >= MIN_GOAL_PROGRESS_M):
                # Estimate + issued motion is progress evidence, never physical success.
                self.progress_goal_distance = distance
                self.looks_without_progress = 0
                self.progress_since = None
                self.progress_drive_issued = False
                self._mem_event(now, 'look_progress', remaining_m=distance)
        stalled = (self.progress_since is not None
                   and now - self.progress_since >= MAX_LOOK_STAGNATION_S)
        if starting:
            stalled |= self.looks_without_progress >= MAX_LOOKS_WITHOUT_PROGRESS
            if not stalled:
                self.looks_without_progress += 1
                if self.progress_since is None:
                    self.progress_since = float(now)
        if stalled:
            self._mem_event(now, 'look_stagnation', looks=self.looks_without_progress,
                            since=self.progress_since)
        return stalled

    def tick(self, now):
        if self.outcome:
            return []
        self.loc.predict_to(now)
        if self._look_stalled(now):
            return self._finish(now, 'look_stagnation')
        commands = super().tick(now)
        return [{'kind': 'hold'}] if self.outcome else commands

    def _current_uncertainty_ok(self, est, *, arrival=False):
        # A remembered fix or the v2 minimum-travel hysteresis cannot grant
        # permission to move/arrive when the current estimate exceeds limits.
        if not est.get('initialized'):
            return False
        xy_limit = self._fix_std_xy_m() if arrival else (
            LOADED_UNCERTAIN_STD_XY_M if self.loaded else LOOK_IF_STD_XY_M)
        yaw_limit = ARRIVAL_OK_YAW_RAD if arrival else (
            LOADED_UNCERTAIN_STD_YAW_RAD if self.loaded else LOOK_IF_STD_YAW_RAD)
        return (math.isfinite(est['std_xy_m']) and 0 <= est['std_xy_m'] <= xy_limit
                and math.isfinite(est['std_yaw_rad']) and 0 <= est['std_yaw_rad'] <= yaw_limit)

    def _needs_look(self, est, now):
        if est.get('initialized') and not self.memory.guard.consistent(now):
            return 'pose_inconsistent'
        if est.get('initialized') and not self._current_uncertainty_ok(est):
            return 'uncertain'
        return super()._needs_look(est, now)

    def _start_look(self, now, reason):
        self.loc.predict_to(now)
        if self._look_stalled(now, starting=True):
            return self._finish(now, 'look_stagnation')
        if reason == 'arrival_check':
            if self.arrival_verifications >= MAX_UNVERIFIED_LOOKS:
                return self._finish(now, 'arrival_unverified')
            self.arrival_verifications += 1
            self.verification_since = float(now)
            # v2's skip branch must never execute at a v3 arrival boundary.
            reason = 'arrival_reverify'
        if reason != 'refix':
            self.current_look_since = float(now)
        commands = super()._start_look(now, reason)
        if self.outcome:
            return commands
        plan = plan_safe_sweep(self.map, self.servo, self.arm_target, self.look_queue,
                               OwnPose.from_estimate(self.loc.estimate()), loaded=self.loaded,
                               restore=self.drive_pose)
        self.look_queue = plan['pans']
        self._mem_event(now, 'sweep_collision_check', **plan)
        if not self.look_queue:
            self.arm_target = {}
            return self._finish(now, 'look_collision_unverified')
        return commands

    def _arm_step(self):
        commands = super()._arm_step()
        if not commands_clear(self.map, self.servo, commands,
                              OwnPose.from_estimate(self.loc.estimate()), loaded=self.loaded):
            return self._finish(self.loc.t, 'look_collision_unverified')
        return commands

    def _should_refix(self, fixed):
        est = self.loc.estimate()
        xy_limit = FIX_ACCEPT_XY_M[bool(self.loaded)]
        yaw_limit = ARRIVAL_FIX_ACCEPT_YAW_RAD if self.verification_since is not None else FIX_ACCEPT_YAW_RAD
        # The inherited `fixed` flag only checks xy. Loaded driving hysteresis
        # also cannot certify a fix: zero travel must not excuse uncertain yaw.
        good = (fixed and math.isfinite(est['std_xy_m']) and math.isfinite(est['std_yaw_rad'])
                and 0 <= est['std_xy_m'] <= xy_limit
                and 0 <= est['std_yaw_rad'] <= yaw_limit
                and self.memory.look_fix_since(self.current_look_since)
                and self.memory.look_fix_fresh(self.loc.t, (est['x'], est['y']))) if est.get('initialized') else False
        if not good:
            self.unverified_looks += 1
            self._mem_event(self.loc.t, 'fix_unverified', attempts=self.unverified_looks,
                            **self._sig(est), xy_limit_m=xy_limit, yaw_limit_rad=yaw_limit)
            if self.look_mode == 'short':
                self.look_counts['escalated'] += 1
            if self.unverified_looks >= MAX_UNVERIFIED_LOOKS:
                self._finish(self.loc.t, 'pose_unverified')
                return False
            return True
        self.unverified_looks = 0
        self.memory.reset_view_checks()
        return False

    def _arrive(self, now):
        self.loc.predict_to(now)
        est = self.loc.estimate()
        if (not self._current_uncertainty_ok(est, arrival=True)
                or self.verification_since is None or not self.memory.look_fix_since(self.verification_since)
                or not self.memory.look_fix_fresh(now, (est['x'], est['y']))):
            if self.unverified_looks >= MAX_UNVERIFIED_LOOKS:
                return self._finish(now, 'arrival_unverified')
            self.unverified_looks += 1
            return self._start_look(now, 'arrival_check')
        return super()._arrive(now)


class ControllerSafetyV3:
    """Shared collision and finite stationary initialization recovery."""
    def _init_controller_safety(self):
        self.init_started = None
        self.init_recovery = None

    def _defer_initial_sweep(self, now, reason):
        if self.init_recovery is None:
            self.init_recovery = {'since': float(now), 'deadline': float(now) + INIT_RECOVERY_S,
                                  'remaining_s': INIT_RECOVERY_S,
                                  'captures': 0, 'next_capture': float(now),
                                  'last_frame': self.last_frame_id}
        else:
            self._resume_init_recovery(now)
        self._event(now, 'init_sweep_deferred', reason=reason, recovery=dict(self.init_recovery))

    def _resume_init_recovery(self, now):
        recovery = self.init_recovery
        if recovery is not None and recovery['deadline'] is None:
            # After completion or command rejection, use only the unspent
            # stationary time. Repeated rejections/captures never refill it.
            recovery['deadline'] = float(now) + recovery['remaining_s']

    def _init_failed(self, now, reason):
        self.outcome, self.sweep = 'NOT_INITIALIZED', None
        self._event(now, 'init_recovery_exhausted', reason=reason, recovery=self.init_recovery)
        return {'mode': 'done', 'outcome': self.outcome}

    def decide(self, now):
        if self.phase == 'init' and self.skill is None and self.slot_inspection is None and not self.outcome:
            if self.init_started is None:
                self.init_started = float(now)
            if now - self.init_started >= INIT_TIMEOUT_S:
                return self._init_failed(now, 'initialization_deadline')
            if (self.init_recovery is not None and self.init_recovery['deadline'] is not None
                    and now >= self.init_recovery['deadline']):
                return self._init_failed(now, 'stationary_deadline')
        result = super().decide(now)
        if self.phase == 'init' and self.sweep is None and not self.outcome:
            self._resume_init_recovery(now)
        return result

    def _init(self, now):
        recovery = self.init_recovery
        if recovery is not None:
            # A capture is not a time step. Alternate with hold until the next
            # sampling time; neither old nor simultaneous frames unlock retries.
            obs = self.last_obs
            fresh = (obs is not None and self.last_frame_id != recovery['last_frame']
                     and 0 <= now - float(obs['sim_time']) <= .25
                     and float(obs['sim_time']) > recovery['since'])
            if not fresh:
                if now < recovery['next_capture']:
                    return self._hold()
                if recovery['captures'] >= INIT_MAX_CAPTURES:
                    return self._init_failed(now, 'capture_budget')
                recovery['captures'] += 1
                recovery['next_capture'] = float(now) + INIT_CAPTURE_INTERVAL_S
                return {'mode': 'capture'}
            recovery['last_frame'] = self.last_frame_id
        result = super()._init(now)
        if self.phase != 'init':
            self.init_recovery = None
        return result

    def _sweep_collision_failure(self, now, reason):
        if self.phase == 'init' and self.skill is None:
            self.sweep = None
            self._defer_initial_sweep(now, reason)
            return
        if self.slot_inspection is not None:
            self._slot_fail(now, 'look_collision_' + reason)
        else:
            self.outcome = 'LOOK_COLLISION_UNVERIFIED'
            self._event(now, 'look_collision_unverified', reason=reason)

    def _start_sweep(self, now, purpose, pose, pans, restore, reason):
        loaded = bool(self.skill is not None and self.skill.box.held)
        plan = plan_safe_sweep(self.map, self.servo, pose, pans,
                               OwnPose.from_report(self.pose.report(now)), loaded=loaded, restore=restore)
        self._event(now, 'sweep_collision_check', purpose=purpose, **plan)
        if not plan['pans']:
            self.sweep = None
            if self.phase == 'init' and reason == 'init':
                self.init_looks = max(0, self.init_looks - 1)  # only actual sweeps consume this budget
            self._sweep_collision_failure(now, plan['reason'])
            return
        # Pan belongs to the pan stage; interpolate other servos first.
        super()._start_sweep(now, purpose, {k: v for k, v in pose.items() if int(k) != 6},
                             plan['pans'], restore, reason)
        recovery = self.init_recovery
        if self.phase == 'init' and recovery is not None and recovery['deadline'] is not None:
            # A safe sweep has its own execution time under INIT_TIMEOUT_S;
            # do not charge it to the stopped-camera recovery budget.
            recovery['remaining_s'] = max(0., recovery['deadline'] - float(now))
            recovery['deadline'] = None
            self._event(now, 'init_sweep_resumed', recovery=dict(recovery))

    def _arm_steps(self, target):
        commands = super()._arm_steps(dict(sorted(target.items())))
        now = self.pose.loc.t if self.pose.loc.t is not None else 0.
        if not commands_clear(self.map, self.servo, commands,
                              OwnPose.from_report(self.pose.report(now)),
                              loaded=bool(self.skill is not None and self.skill.box.held)):
            self._sweep_collision_failure(now, 'command_transition')
            return [{'kind': 'hold'}]
        return commands
