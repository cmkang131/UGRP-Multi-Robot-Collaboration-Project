"""Package F guarded loop driver (issue #221): ``OwnCamDriverV2`` + the own-input guards of
``harness.zone_own_guards`` (uncertainty gate, look-sweep collision guard, progress monitor with
bounded recovery). Loop v2 pursuit, planner, postures and look policy are unchanged.

Split from ``zone_own_guards`` (600-line rule). Nothing here imports the simulator.
"""
from __future__ import annotations

import math

from harness.owncam_drive import LOOK_P20, SETTLE_S, WIDE_LOOK_PANS
from harness.owncam_drive_v2 import OwnCamDriverV2
from harness.owncam_drive_shared import SharedPoseDriver
from harness.zone_own_sweep import SweepRecheck, reachable_pan
from harness.zone_own_guards import (GATE_LOADED, GATE_UNLOADED, MAX_LOOK_BACKOFFS, MAX_RECOVERIES,
                                     RECOVERY_BACKOFF_M, STALL_KEEPOUT_AHEAD_M, STALL_KEEPOUT_HALF_M,
                                     STALL_KEEPOUT_MIN_DOOR_M, STALL_KEEPOUT_MIN_GOAL_M, TRUSTED_FIX_AGE_S, OwnPose,
                                     ProgressMonitor, SweepGuard, UncertaintyGate, backoff_commands, commanded_step_m)

SCHEMA = 'ugrp.zone_own_driver.v1'

GATE_MAX_LOOKS = 3                  # consecutive looks without the gate reaching ok -> 'pose_uncertain'
ARRIVAL_FIX_MAX_AGE_S = 5.
ARRIVAL_MAX_RECHECKS = 2
LOOK_IF_NO_FIX_S = 3.             # unchanged frozen unloaded recency trigger


class GuardedDriver(OwnCamDriverV2, SharedPoseDriver):
    """Loop driver v2 on a shared localizer with the uncertainty gate, sweep guard and progress monitor.

    Commands and frames reach the shared localizer once (through the executor / pose source); this
    driver only does servo bookkeeping. New outcomes: ``pose_uncertain`` (gate never reached ok in
    ``GATE_MAX_LOOKS`` looks), ``arrival_unconfirmed`` (at the goal without a fresh fixed own look and
    an ok gate) and ``blocked`` (no progress after ``MAX_RECOVERIES`` back-off recoveries).
    """

    def __init__(self, shared_loc, *args, gate: UncertaintyGate, guard: SweepGuard, **kwargs):
        self.loc = shared_loc
        super().__init__(*args, **kwargs)
        self.gate, self.guard = gate, guard
        self.gate.set_profile(GATE_LOADED if self.loaded else GATE_UNLOADED)
        self.monitor = ProgressMonitor()
        self.gate_looks = 0
        self.recoveries = 0
        self.arrival_rechecks = 0
        self.last_look: dict | None = None
        self.backoff: dict | None = None
        self.guard_log: list[dict] = []
        self.stall_keepouts: list[dict] = []
        self.sweep_recheck = SweepRecheck()
        self.sweep_failure = None

    def on_command(self, row):
        kind = row['kind']
        if kind == 'initial_servo_command':
            self.servo = {int(k): int(v) for k, v in row['pulses'].items()}
        elif kind == 'arm':
            self.servo[int(row['servo_id'])] = int(row['pulse'])
        elif kind == 'look':
            self.servo[6] = int(row['pan_pulse'])

    def observe(self, now, rgb):
        raise RuntimeError("feed frames through the owning pose provider exactly once")

    # -------------------------------------------------- hooks
    def _event(self, now, kind, **detail):
        super()._event(now, kind, **detail)
        if kind == 'look_done':
            self.last_look = {'t': now, 'fixed': bool(detail.get('fixed'))}
            est = self.loc.estimate()
            if detail.get('fixed') and est.get('initialized'):
                self.monitor.trusted((est['x'], est['y']), self._goal_dist(est))
            elif self.look_reason == 'progress_check':
                xy = (est['x'], est['y']) if est.get('initialized') else None
                self.monitor.inconclusive(xy, self._goal_dist(est) if xy is not None else None)

    def _needs_look(self, est, now):
        # Neutral version of the frozen loop policy; thresholds/order unchanged.
        from harness.owncam_drive import DOOR_CHECKPOINTS_M

        if not est.get('initialized'):
            return 'not_initialized'
        if self._uncertain(est):
            return 'uncertain'
        if self.loaded:
            if self.last_look_xy is None:
                self.last_look_xy = (est['x'], est['y'])
            elif self._since_look_m(est) > self._travel_look_m():
                return 'travel'
        elif est.get('fix_age_s') is not None and est['fix_age_s'] > LOOK_IF_NO_FIX_S:
            return 'no_fix'
        if est['x'] < self.door[0]:
            d = math.hypot(self.door[0] - est['x'], self.door[1] - est['y'])
            for cp in DOOR_CHECKPOINTS_M:
                if cp not in self.checkpoints_done and d <= cp:
                    self.checkpoints_done.add(cp)
                    return f'door_checkpoint_{cp}'
        return None

    def _goal_dist(self, est):
        return math.hypot(self.goal[0] - est['x'], self.goal[1] - est['y'])

    def _start_look(self, now, reason, *, allow_backoff=True):
        est = self.loc.estimate()
        look_pose = dict(LOOK_P20)
        if self.loaded:
            look_pose[1] = self.servo.get(1, 1500)
        plan = self.guard.plan(self.servo, look_pose, WIDE_LOOK_PANS, OwnPose.from_estimate(est), loaded=self.loaded,
                               allow_backoff=allow_backoff and self._backoffs_left(reason)
                               and self.gate.allows_estimate(est))
        self.guard_log.append({'t': round(now, 3), 'look_reason': reason,
                               **{k: plan[k] for k in ('pans', 'dropped', 'reason')}, 'backoff': plan['backoff']})
        if plan['backoff'] is not None:
            self._look_backoffs = getattr(self, '_look_backoffs', 0) + 1
            return self._begin_backoff(now, plan['backoff'], then=('look', reason))
        self.sweep_recheck = SweepRecheck()
        commands = super()._start_look(now, reason)
        # Match the checked posture: arm first at the current pan, and preserve a held grip.
        self.arm_target = {**look_pose, 6: int(self.servo.get(6, 1500))}
        if plan['reason'] != 'clear':
            pan0 = int(self.servo.get(6, 1500))
            self.look_queue = list(plan['pans']) or [pan0]
        return commands

    def _arm_step(self):
        est = self.loc.estimate()
        pose, now = OwnPose.from_estimate(est), est['t']
        was_waiting = self.sweep_recheck.last_wait is not None
        result = self.sweep_recheck.check(now, self.guard, self.servo, self.arm_target, pose, loaded=self.loaded)
        if result == 'clear' and was_waiting and self.state == 'look_arm':
            plan = self.guard.plan(self.servo, self.arm_target, WIDE_LOOK_PANS, pose, loaded=self.loaded)
            self.look_queue = list(plan['pans']) or [int(self.servo[6])]
        if result != 'clear' and self.state == 'look_pan':
            pan = reachable_pan(self.guard, self.servo, self.look_queue, pose, loaded=self.loaded)
            if pan is not None:
                self.guard_log.append({'t': round(now, 3), 'reason': 'pan_replanned',
                                       'dropped_target': self.arm_target[6], 'selected_pan': pan})
                self.look_queue = [p for p in self.look_queue if p != pan and self.guard.transition_clear(
                    {**self.servo, 6: pan}, {6: p}, pose, loaded=self.loaded)]
                self.arm_target, self.state_since = {6: pan}, now
                result = self.sweep_recheck.check(now, self.guard, self.servo, self.arm_target, pose, loaded=self.loaded)
        if result != 'clear':
            evidence = self.guard.transition_diagnostic(self.servo, self.arm_target, pose, loaded=self.loaded)
            evidence.update(stage=self.state, waited_s=self.sweep_recheck.waited_s)
            if result == 'blocked':
                self.sweep_failure = evidence
                return self._finish(now, 'sweep_transition_blocked')
            if self.sweep_recheck.waited_s == 0.:
                self.guard_log.append({'t': round(now, 3), 'reason': 'stationary_reobserve', 'guard': evidence})
            return [{'kind': 'hold'}]
        return super()._arm_step()

    def _backoffs_left(self, reason):
        return getattr(self, '_look_backoffs', 0) < MAX_LOOK_BACKOFFS and reason != 'stall_recovery'

    def _begin_backoff(self, now, move, *, then):
        cmd, duration = backoff_commands(move)
        self.backoff = {'cmd': cmd, 'until': now + duration, 'then': then, 'settle_until': None, 'move': dict(move)}
        self._set('guard_backoff', now, move=dict(move), then=list(then))
        return [{'kind': 'hold'}]

    def _tick_backoff(self, now):
        b = self.backoff
        self.loc.predict_to(now)
        if not self.gate.allows_estimate(self.loc.estimate()):
            self.backoff = None
            return self._start_look(now, 'gate_uncertain', allow_backoff=False)
        if now + 1e-9 < b['until']:
            return [dict(b['cmd'])]
        if b['settle_until'] is None:
            b['settle_until'] = now + SETTLE_S
            return [{'kind': 'hold'}]
        if now + 1e-9 < b['settle_until']:
            return [{'kind': 'hold'}]
        self.backoff = None
        self.path = None
        self._set('drive', now)
        return self._start_look(now, b['then'][1], allow_backoff=False)

    def _arrive(self, now):
        fresh = self.last_look is not None and self.last_look['fixed'] and now - self.last_look['t'] <= ARRIVAL_FIX_MAX_AGE_S
        self.loc.predict_to(now)
        if self.gate.allows_estimate(self.loc.estimate()) and fresh:
            return super()._arrive(now)
        if self.arrival_rechecks < ARRIVAL_MAX_RECHECKS:
            self.arrival_rechecks += 1
            return self._start_look(now, 'arrival_recheck')
        self._event(now, 'arrival_unconfirmed', gate=self.gate.state, last_look=self.last_look)
        return self._finish(now, 'arrival_unconfirmed')

    # -------------------------------------------------- control
    def tick(self, now: float) -> list[dict]:
        if self.outcome:
            return []
        if self.monitor.exhausted():
            self._event(now, 'progress_unconfirmed', failed_looks=self.monitor.look_failures)
            return self._finish(now, 'progress_unconfirmed')
        if self.state == 'guard_backoff':
            return self._tick_backoff(now)
        if self.state == 'drive':
            guarded = self._drive_guard(now)
            if guarded is not None:
                return guarded
        cmds = super().tick(now)
        if self.state == 'drive':
            self.monitor.drove(sum(commanded_step_m(c) for c in cmds))
        return cmds

    def _plan(self, est, now):
        """Plan; a plan failure with stall keep-outs drops them and plans once more."""
        if super()._plan(est, now):
            return True
        if self.stall_keepouts and any(k in self.keepouts for k in self.stall_keepouts):
            self.keepouts = [k for k in self.keepouts if k not in self.stall_keepouts]
            self._event(now, 'stall_keepouts_dropped', count=len(self.stall_keepouts))
            self.plan_fails = max(0, self.plan_fails - 1)
            return super()._plan(est, now)
        return False

    def _finish(self, now, outcome):
        if outcome == 'no_path' and self.recoveries:
            outcome = 'blocked'                    # no path after a stall recovery: a blocked route, reported once
        return super()._finish(now, outcome)

    def _drive_guard(self, now):
        self.loc.predict_to(now)
        est = self.loc.estimate()
        if not self.gate.allows_estimate(est):
            if self.gate_looks >= GATE_MAX_LOOKS:
                self._event(now, 'gate_pose_uncertain', gate=self.gate.as_dict())
                return self._finish(now, 'pose_uncertain')
            self.gate_looks += 1
            return self._start_look(now, 'gate_uncertain')
        self.gate_looks = 0
        if est.get('initialized') and est.get('fix_age_s') is not None and est['fix_age_s'] <= TRUSTED_FIX_AGE_S \
                and est['std_xy_m'] <= self.gate.profile.low_xy_m:
            self.monitor.trusted((est['x'], est['y']), self._goal_dist(est))
        if self.monitor.needs_check():
            self.monitor.checks += 1
            return self._start_look(now, 'progress_check')
        if not self.monitor.stalled():
            return None
        pose = OwnPose.from_estimate(est)
        if self.recoveries >= MAX_RECOVERIES or pose is None:
            self._event(now, 'blocked', recoveries=self.recoveries, keepouts=list(self.stall_keepouts))
            return self._finish(now, 'blocked')
        self.recoveries += 1
        return self._start_recovery(now, pose)

    def _start_recovery(self, now, pose: OwnPose):
        tx, ty = self.path[0] if self.path else self.goal
        heading = math.atan2(ty - pose.y, tx - pose.x)
        ahead = (pose.x + STALL_KEEPOUT_AHEAD_M * math.cos(heading), pose.y + STALL_KEEPOUT_AHEAD_M * math.sin(heading))
        keepout = None
        if (math.hypot(ahead[0] - self.goal[0], ahead[1] - self.goal[1]) >= STALL_KEEPOUT_MIN_GOAL_M
                and math.hypot(ahead[0] - self.door[0], ahead[1] - self.door[1]) >= STALL_KEEPOUT_MIN_DOOR_M):
            keepout = {'id': f'stall_{self.recoveries}', 'center_m': [round(ahead[0], 3), round(ahead[1], 3)],
                       'half_extents_m': [STALL_KEEPOUT_HALF_M] * 2,
                       'source': 'own progress stall (own commands vs own trusted estimate)'}
            self.stall_keepouts.append(keepout)
            self.keepouts.append(keepout)
        self.monitor.reset()
        rel = heading - pose.yaw
        move = {'dx_base_m': round(-RECOVERY_BACKOFF_M * math.cos(rel), 4),
                'dy_base_m': round(-RECOVERY_BACKOFF_M * math.sin(rel), 4)}
        clear = self.guard.translation_clear(self.servo, pose, move['dx_base_m'], move['dy_base_m'], loaded=self.loaded)
        self._event(now, 'stall_recovery', recovery=self.recoveries, keepout=keepout, backoff=move if clear else None,
                    commanded_m=round(self.monitor.commanded_m, 3))
        if not clear:
            self.path = None
            return self._start_look(now, 'stall_recovery')
        return self._begin_backoff(now, move, then=('look', 'stall_recovery'))
