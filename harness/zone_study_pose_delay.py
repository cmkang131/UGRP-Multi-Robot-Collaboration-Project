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


def delay_contract(worker_charge=None):
    """Fixed delivery delay, independent of uncharged inference wall time."""
    if worker_charge is not None and worker_charge.get('charged') is not False:
        raise ValueError('worker SIM charge would duplicate the fixed perception delay')
    return {'schema': 'ugrp.pose_delay.v1', 'wrapper_count': 1,
            'camera_to_estimate_sim_s': PERCEPTION_DELAY_S,
            'worker_inference_sim_s': 0., 'effective_sim_s': PERCEPTION_DELAY_S,
            'worker_sim_time_charge': copy.deepcopy(worker_charge),
            'estimate_clock': 'capture time; predict only to released cutoff',
            'wall_time': 'recorded separately; no wall sleep'}


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
        if isinstance(provider, DelayedPoseSource):
            raise ValueError('perception delay must be applied exactly once')
        self.provider, self.source = provider, provider.source
        cfg = getattr(provider, 'cfg', {})
        self.delay = delay_contract(cfg.get('sim_time_charge'))
        self._loc = _DelayedLocalizer(self)
        self.pending, self.seq, self.now = [], 0, 0.
        self.timing = []
        self.rejections = []
        self._last_frame_t = None
        self._frame_floor = 0.
        self._started = False
        self._closed = False

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
        if self._closed:
            raise RuntimeError('delayed pose provider is closed')
        if not math.isfinite(t) or t < 0:
            raise ValueError('provider input time must be finite and nonnegative')
        self.seq += 1
        heapq.heappush(self.pending, (float(t), self.seq, method, args))

    def on_command(self, row):
        self._started |= row['t'] > 0 or row['kind'] != 'initial_servo_command'
        self._queue(float(row['t']), 'on_command', copy.deepcopy(row))

    def set_motion_profile(self, now, name):
        self._started = True
        self._queue(float(now), 'set_motion_profile', float(now), name)

    def get_motion_params(self):
        # Do not drain pending inputs or expose a future profile to the guard.
        return self.provider.get_motion_params()

    def on_frame(self, now, rgb, *, captured_sim_s=None):
        # Optional capture time is for delayed transport. Receipt time must
        # never be substituted for the image's old capture/fix timestamp.
        captured = now if captured_sim_s is None else captured_sim_s
        if not all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) and t >= 0
                   for t in (now, captured)):
            raise ValueError('frame capture/receipt time must be finite and nonnegative')
        self._started = True
        if (captured > now or captured < max(self._frame_floor, self.now - PERCEPTION_DELAY_S) - 1e-9
                or (self._last_frame_t is not None and captured <= self._last_frame_t)):
            self.rejections.append({'captured_sim_s': captured, 'received_sim_s': now,
                                    'reason': 'future_stale_or_duplicate'})
        else:
            self._last_frame_t = float(captured)
            self._queue(float(captured), 'on_frame', float(captured), None if rgb is None else rgb.copy())
        return self.report(now)

    def report(self, now):
        import time
        if self._closed:
            raise RuntimeError('delayed pose provider is closed')
        if not math.isfinite(now) or now < self.now - 1e-9:
            raise ValueError('provider clock must be monotonic')
        self.now = float(now)
        cutoff = max(0., self.now - PERCEPTION_DELAY_S)
        while self.pending and self.pending[0][0] <= self.now - PERCEPTION_DELAY_S + 1e-9:
            t, _, method, args = heapq.heappop(self.pending)
            start = time.monotonic()
            if method == 'begin_observation':
                self.provider.begin_observation(args[0], args[1], lost=args[2])
            else:
                getattr(self.provider, method)(*args)
            if method == 'on_frame':
                self.timing.append({'captured_sim_s': t, 'available_sim_s': t + PERCEPTION_DELAY_S,
                                    'consumed_sim_s': self.now,
                                    'inference_wall_s': time.monotonic() - start})
        return self.provider.report(cutoff)

    def init_prior(self, *args, **kwargs):
        """Future #237 hook: only a preregistered own dock, never a live pose."""
        if self._closed or self._started or self.now > 0:
            raise RuntimeError('dock prior must be set before runtime inputs')
        return self.provider.init_prior(*args, **kwargs)

    def expected_observability(self, pose, pan, static_map):
        return self.provider.expected_observability(pose, pan, static_map)

    def begin_relocalization(self, now, servo):
        if getattr(self.provider, 'recovery_v6', False):
            return self.begin_observation(now, servo)
        # Reset on the already released clock. Commands/new frames still wait
        # the full perception delay; pending pre-reset captures cannot be fixes.
        self.report(now)
        self._started = True
        self._frame_floor = float(now)
        # Keep all own issued commands/profiles in order. Only captures from
        # before this scan can no longer provide its fresh fix.
        self.pending[:] = [row for row in self.pending if row[2] != 'on_frame']
        heapq.heapify(self.pending)
        cutoff = max(0., float(now) - PERCEPTION_DELAY_S)
        self.provider.begin_relocalization(cutoff, servo)
        from harness.owncam_pose_source import OwnCamPoseSource
        if type(self.provider) is OwnCamPoseSource:
            # The historical tag path creates a new PF and still needs its
            # setup servo command on the capture clock. Vision keeps history.
            self.on_command({'t': float(now), 'kind': 'initial_servo_command', 'pulses': dict(servo)})

    def begin_observation(self, now, servo, *, lost=False):
        # Queue on the capture clock. Do not clear pending observations or
        # advance the underlying PF beyond the already released cutoff.
        self._started = True
        self._queue(float(now), 'begin_observation', float(now), dict(servo), lost)


    def close(self):
        if self._closed:
            return
        self._closed = True
        self.pending.clear()
        close = getattr(self.provider, 'close', None)
        if close is not None:
            close()

    def record(self):
        record = getattr(self.provider, 'record', None)
        return {'delay': copy.deepcopy(self.delay), 'closed': self._closed,
                'applied_perception_delay_s': PERCEPTION_DELAY_S,
                'frame_rejections': copy.deepcopy(self.rejections),
                'provider': record() if record is not None else None}
