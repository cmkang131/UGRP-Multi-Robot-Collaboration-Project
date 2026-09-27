"""Publish pose estimates only after a fixed camera-to-estimate SIM delay.

Replay the provider's own inputs in timestamp order on a delayed clock. Neither
report() nor the drivers' loc interface can see an unreleased image update.
Estimate timestamps remain old: the delay must not fabricate a fresh pose.
This adapter contains no simulator state and does not sleep in wall time.
"""
from __future__ import annotations

import copy
import heapq
import math

PERCEPTION_DELAY_S = .16


class _DelayedLocalizer:
    def __init__(self, owner):
        self.owner = owner

    def predict_to(self, now):
        self.owner.report(now)

    def estimate(self):
        return copy.deepcopy(self.owner.provider.loc.estimate())

    def command(self, row):
        # Frozen M2 relocalization issues its own initial-servo command through
        # loc.command rather than the pose source. Keep it on the same clock.
        self.owner.on_command(row)

    def __getattr__(self, name):
        # Drivers also read last_tag_t, motion_profile, load and stats. These
        # belong to the same delayed provider; no second, undelayed filter.
        value = getattr(self.owner.provider.loc, name)
        if callable(value):
            raise AttributeError(f'delayed localizer does not expose {name}')
        return value


class DelayedPoseSource:
    def __init__(self, provider):
        self.provider, self.source = provider, provider.source
        self._loc = _DelayedLocalizer(self)
        self.pending, self.seq, self.now = [], 0, 0.
        self.timing = []

    @property
    def loc(self):
        return self._loc

    @loc.setter
    def loc(self, value):
        # #235's frozen M2 driver replaces the tag PF when relocalizing. Keep
        # the facade, drop pre-reset queued inputs, and fail closed until new
        # frames mature. Never replace a future vision worker with a tag PF.
        from harness.owncam_pose_source import OwnCamPoseSource
        if type(self.provider) is not OwnCamPoseSource:
            raise ValueError('provider needs an explicit relocalization adapter')
        self.provider.loc = value
        self.pending.clear()

    def _queue(self, t, method, *args):
        if not math.isfinite(t) or t < 0:
            raise ValueError('provider input time must be finite and nonnegative')
        self.seq += 1
        heapq.heappush(self.pending, (float(t), self.seq, method, args))

    def on_command(self, row):
        self._queue(float(row['t']), 'on_command', copy.deepcopy(row))

    def set_motion_profile(self, now, name):
        self._queue(float(now), 'set_motion_profile', float(now), name)

    def on_frame(self, now, rgb):
        self._queue(float(now), 'on_frame', float(now), rgb.copy())
        return self.report(now)

    def report(self, now):
        import time
        if not math.isfinite(now) or now < self.now - 1e-9:
            raise ValueError('provider clock must be monotonic')
        self.now = float(now)
        cutoff = max(0., self.now - PERCEPTION_DELAY_S)
        while self.pending and self.pending[0][0] <= self.now - PERCEPTION_DELAY_S + 1e-9:
            t, _, method, args = heapq.heappop(self.pending)
            start = time.monotonic()
            getattr(self.provider, method)(*args)
            if method == 'on_frame':
                self.timing.append({'captured_sim_s': t, 'available_sim_s': t + PERCEPTION_DELAY_S,
                                    'consumed_sim_s': self.now,
                                    'inference_wall_s': time.monotonic() - start})
        return self.provider.report(cutoff)

    def init_prior(self, *args, **kwargs):
        """Future #237 hook: only a preregistered own dock, never a live pose."""
        return self.provider.init_prior(*args, **kwargs)

    def close(self):
        close = getattr(self.provider, 'close', None)
        if close is not None:
            close()
