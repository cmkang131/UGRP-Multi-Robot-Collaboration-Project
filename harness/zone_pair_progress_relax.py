"""Probe-only diagnostic: relax the loaded pair's no-progress check (2026-09-30, door-relax envelope, Refs #216).

Finding that motivates it (chain L0 -> L1, ``experiments/2026-09-30-door-relax-envelope``): after the stored re-grasp
between two legs, the pair's ``pregrasp_fix`` is a fresh own fix, so ``ProgressMonitor.trusted`` sets a movement baseline.
The next loaded carry then needs a NEW trusted estimate within ``STALL_COMMANDED_M`` (0.40 m of own commanded travel);
door-leg views give none (``no_usable_geometry``), so ``needs_check`` fires and the loaded pair aborts with
``POSE_UNCERTAIN_PROGRESS``. That is independent of the collision inflation that ``b-v6h`` relaxes. A single-leg stage probe
never sees it (no baseline is ever set there).

``install('p1')`` raises the constant to 1.2 m (longer than any carry leg's commanded travel, ~0.6 m for the 0.85 m door
leg), i.e. the stall check cannot fire inside one leg. Process-local (the worker runs one case per process); the registered
sources are untouched. It is NOT a proposal for the registered controller: stall detection is what would notice a robot
pushing against a wall, so a real fold-in needs a replacement signal (see the experiment README).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

VARIANTS = {'p1': {'stall_commanded_m': 1.2,
                   'note': 'ProgressMonitor STALL_COMMANDED_M 0.40 -> 1.2 m: no-progress check cannot fire within one carry leg'}}
REGISTERED = {'stall_commanded_m': 0.40}


def variant(name: str) -> dict:
    if name not in VARIANTS:
        raise ValueError(f'unknown progress-relax variant {name!r}; choose one of {sorted(VARIANTS)}')
    return VARIANTS[name]


def install(name: str | None) -> dict | None:
    if name is None:
        return None
    knobs = variant(name)
    from harness import zone_own_guards as g
    g.STALL_COMMANDED_M = float(knobs['stall_commanded_m'])
    return {'variant': name, **knobs, 'registered': REGISTERED, 'patched': ['harness.zone_own_guards.STALL_COMMANDED_M'],
            'module_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
