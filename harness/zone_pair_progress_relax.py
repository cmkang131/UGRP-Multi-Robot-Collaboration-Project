"""Probe-only diagnostic: relax the loaded pair's no-progress check (2026-09-30, door-relax envelope, Refs #216).

Finding that motivates it (chain L0 -> L1, ``experiments/2026-09-30-door-relax-envelope``): after the stored re-grasp
between two legs, the pair's ``pregrasp_fix`` is a fresh own fix, so ``ProgressMonitor.trusted`` sets a movement baseline.
The next loaded carry then needs a NEW trusted estimate within ``STALL_COMMANDED_M`` (0.40 m of own commanded travel);
door-leg views give none (``no_usable_geometry``), so ``needs_check`` fires and the loaded pair aborts with
``POSE_UNCERTAIN_PROGRESS``. That is independent of the collision inflation that ``b-v6h`` relaxes. A single-leg stage probe
never sees it (no baseline is ever set there).

``install('p2')`` (added after the p1 cohorts, see the README) keeps stall detection but refuses to arm the baseline from a
stationary fix, i.e. it makes the loaded pair behave as in a single-leg stage probe unless a trusted estimate arrives after the
leg has started moving.

``install('p1')`` raises the constant to 1.2 m (longer than any carry leg's commanded travel, ~0.6 m for the 0.85 m door
leg), i.e. the stall check cannot fire inside one leg. Process-local (the worker runs one case per process); the registered
sources are untouched. It is NOT a proposal for the registered controller: stall detection is what would notice a robot
pushing against a wall, so a real fold-in needs a replacement signal (see the experiment README).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

VARIANTS = {'p1': {'stall_commanded_m': 1.2, 'arm_after_motion': False,
                   'note': 'ProgressMonitor STALL_COMMANDED_M 0.40 -> 1.2 m: no-progress check cannot fire within one carry leg'},
            'p2': {'stall_commanded_m': None, 'arm_after_motion': True,
                   'note': 'stall detection kept (0.40 m); ProgressMonitor.trusted() is ignored until the leg has commanded base '
                           'motion since the last reset, so a stationary re-grasp fix cannot arm the monitor'}}
REGISTERED = {'stall_commanded_m': 0.40, 'arm_after_motion': False}


def variant(name: str) -> dict:
    if name not in VARIANTS:
        raise ValueError(f'unknown progress-relax variant {name!r}; choose one of {sorted(VARIANTS)}')
    return VARIANTS[name]


def install(name: str | None) -> dict | None:
    if name is None:
        return None
    knobs = variant(name)
    from harness import zone_own_guards as g
    patched = []
    if knobs['stall_commanded_m'] is not None:
        g.STALL_COMMANDED_M = float(knobs['stall_commanded_m'])
        patched.append('harness.zone_own_guards.STALL_COMMANDED_M')
    if knobs['arm_after_motion']:
        monitor = g.ProgressMonitor
        drove, reset, trusted = monitor.drove, monitor.reset, monitor.trusted

        def drove_(self, commanded_m):
            before = self.commanded_m
            drove(self, commanded_m)
            if self.commanded_m > before:
                self._moved_since_reset = True

        def reset_(self):
            reset(self)
            self._moved_since_reset = False

        def trusted_(self, xy, goal_dist):
            if self.baseline is None and not getattr(self, '_moved_since_reset', False):
                return None       # a stationary fix (re-grasp look) does not arm the no-progress baseline
            return trusted(self, xy, goal_dist)
        monitor.drove, monitor.reset, monitor.trusted = drove_, reset_, trusted_
        patched.append('harness.zone_own_guards.ProgressMonitor.drove/reset/trusted (arm only after commanded motion)')
    return {'variant': name, **knobs, 'registered': REGISTERED, 'patched': patched,
            'module_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
