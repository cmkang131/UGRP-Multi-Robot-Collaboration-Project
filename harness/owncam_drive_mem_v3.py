"""Memory v3 leg policy: mandatory arrival verification and guarded uncertainty."""
from __future__ import annotations

import math

from harness.m1_owncam_delivery import _LegDriver
from harness.owncam_drive import LOOK_IF_STD_YAW_RAD
from harness.owncam_drive_mem import MemoryLookPolicy, SHORT_ACCEPT_YAW_RAD
from harness.owncam_pose_guard_v3 import GuardedLocalizerV3
from harness.owncam_sweep_collision import OwnPose, commands_clear, plan_safe_sweep

SCHEMA = 'ugrp.owncam_drive_mem.v3'
MAX_UNVERIFIED_LOOKS = 2


class LegDriverMemV3(MemoryLookPolicy, _LegDriver):
    def __init__(self, memory, shared_loc, *args, **kwargs):
        super().__init__(GuardedLocalizerV3(shared_loc, memory.guard), *args, **kwargs)
        self._init_memory_policy(memory)
        self.verification_since = None
        self.unverified_looks = 0
        self.arrival_verifications = 0
        self.exclude_tracks = ()

    def _needs_look(self, est, now):
        if est.get('initialized') and not self.memory.guard.consistent(now):
            return 'pose_inconsistent'
        return super()._needs_look(est, now)

    def _start_look(self, now, reason):
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
        yaw_limit = SHORT_ACCEPT_YAW_RAD if self.look_mode == 'short' else LOOK_IF_STD_YAW_RAD
        # The inherited `fixed` flag only checks xy. Loaded driving hysteresis
        # also cannot certify a fix: zero travel must not excuse uncertain yaw.
        good = (fixed and math.isfinite(est['std_xy_m']) and math.isfinite(est['std_yaw_rad'])
                and 0 <= est['std_xy_m'] <= self._fix_std_xy_m()
                and 0 <= est['std_yaw_rad'] <= yaw_limit
                and self.memory.look_fix_since(self.current_look_since)
                and self.memory.look_fix_fresh(self.loc.t, (est['x'], est['y']))) if est.get('initialized') else False
        if not good:
            self.unverified_looks += 1
            self._mem_event(self.loc.t, 'fix_unverified', attempts=self.unverified_looks,
                            **self._sig(est), yaw_limit_rad=yaw_limit)
            if self.look_mode == 'short':
                self.look_counts['escalated'] += 1
            if self.unverified_looks >= MAX_UNVERIFIED_LOOKS:
                self._finish(self.loc.t, 'pose_unverified')
                return False
            return True
        self.unverified_looks = 0
        return super()._should_refix(fixed)

    def _plan(self, est, now):
        # New far obstacles seen during this leg must affect the next plan too.
        self.memory._decay_to(now)
        self.keepouts = self.memory.keepouts(exclude=self.exclude_tracks)
        return super()._plan(est, now)

    def tick(self, now):
        current = self.memory.keepouts(exclude=self.exclude_tracks)
        if current != self.keepouts:
            self.keepouts, self.path = current, None
        return super().tick(now)

    def _arrive(self, now):
        est = self.loc.estimate()
        if (self.verification_since is None or not self.memory.look_fix_since(self.verification_since)
                or not self.memory.look_fix_fresh(now, (est['x'], est['y']))):
            if self.unverified_looks >= MAX_UNVERIFIED_LOOKS:
                return self._finish(now, 'arrival_unverified')
            self.unverified_looks += 1
            return self._start_look(now, 'arrival_check')
        return super()._arrive(now)
