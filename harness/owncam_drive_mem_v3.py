"""Memory v3 leg policy: mandatory arrival verification and guarded uncertainty."""
from __future__ import annotations

from harness.owncam_delivery_shared import SharedLegDriver as _LegDriver
from harness.owncam_drive import OwnCamDriver
from harness.owncam_drive_mem import MemoryLookPolicy
from harness.owncam_drive_shared import SharedPoseDriver
from harness.owncam_pose_guard_v3 import GuardedLocalizerV3
from harness.owncam_safety_v3 import LegSafetyV3, MAX_UNVERIFIED_LOOKS

SCHEMA = 'ugrp.owncam_drive_mem.v3'


class LookPolicyV3(MemoryLookPolicy):
    """Only the optional reobservation policy differs in the paired comparison."""
    def _needs_look(self, est, now):
        if self.memory_look_enabled:
            return super()._needs_look(est, now)
        return SharedPoseDriver._needs_look(self, est, now)

    def _start_look(self, now, reason):
        if self.memory_look_enabled:
            return super()._start_look(now, reason)
        self.look_mode = 'full'
        self.look_counts['full'] += 1
        self.memory.reset_view_checks()
        commands = OwnCamDriver._start_look(self, now, reason)
        self.memory.event(now, 'driver_look', reason=reason, mode='full',
                          pans=list(self.look_queue), loaded=bool(self.loaded), **self._sig(self.loc.estimate()))
        return commands


class LegDriverMemV3(LegSafetyV3, LookPolicyV3, _LegDriver):
    def __init__(self, memory, shared_loc, *args, memory_look_enabled=True, **kwargs):
        super().__init__(GuardedLocalizerV3(shared_loc, memory.guard), *args, **kwargs)
        self._init_memory_policy(memory)
        self.memory_look_enabled = bool(memory_look_enabled)
        self._init_safety()
        self.exclude_tracks = ()

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
