"""Probe-only diagnostic: relax the loaded pair's no-progress check (2026-09-30, door-relax envelope, Refs #216).

Finding that motivates it (chain L0 -> L1, ``experiments/2026-09-30-door-relax-envelope``): after the stored re-grasp
between two legs, the pair's ``pregrasp_fix`` is a fresh own fix, so ``ProgressMonitor.trusted`` sets a movement baseline.
The next loaded carry then needs a NEW trusted estimate within ``STALL_COMMANDED_M`` (0.40 m of own commanded travel);
door-leg views give none (``no_usable_geometry``), so ``needs_check`` fires and the loaded pair aborts with
``POSE_UNCERTAIN_PROGRESS``. That is independent of the collision inflation that ``b-v6h`` relaxes. A single-leg stage probe
never sees it (no baseline is ever set there).

Both variants patch the whole ``ProgressMonitor`` class, so they also change the no-progress check of unloaded ``GuardedDriver``
driving, not only the loaded carry. The worker records ``progress_relax`` in result.json (``null`` by default), so the default
output is not byte-identical to before this key existed.

``install('p2')`` (added after the p1 cohorts, see the README) keeps stall detection but refuses to arm the baseline from a
stationary fix, i.e. it makes the loaded pair behave as in a single-leg stage probe unless a trusted estimate arrives after the
leg has started moving.

``install('p2f')`` (2026-09-30, b-v6h gain fix) is the corrected timing rule of ``p2`` and touches ONLY the loaded pair's monitor
(``harness.zone_pair_guards.PairCommandGuard.monitor``), not the unloaded ``GuardedDriver`` monitor. The independent review of ``p2``
found that a stationary fix taken within ``TRUSTED_FIX_AGE_S`` (0.3 s) of the first tiny move could still arm the baseline. The rule
here compares timestamps: the baseline is armed only by a trusted estimate whose FIX time (``report.last_fix_t``, the raw capture SIM
time of the accepted observation) is later than the SIM time of the first issued base-motion command since the last ``reset()``.
A fix taken while standing still, or before the first move command, never arms it. After a baseline exists the registered rules
(0.40 m commanded travel, a newer trusted estimate, look budget) are unchanged. Known limit, stated in the prereg draft: in the door
zone no usable fix arrives, so no baseline is armed and stall detection is absent there (fail-open).

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
# 'p2f' has no entry in VARIANTS' generic knobs: it needs the pair guard object, see install_p2f().
VARIANTS['p2f'] = {'stall_commanded_m': None, 'arm_after_motion': False, 'arm_after_move_start_fix': True,
                   'note': 'loaded-pair monitor only: the baseline is armed only by a trusted estimate whose fix timestamp is later '
                           'than the first issued base-motion command since reset (the corrected p2 timing rule)'}
IGNORED: list[dict] = []          # trusted estimates the p2f rule refused to arm on (this process), dumped into result.json
ARMED: list[dict] = []            # baselines the p2f rule allowed
MAX_LOGGED = 60


def variant(name: str) -> dict:
    if name not in VARIANTS:
        raise ValueError(f'unknown progress-relax variant {name!r}; choose one of {sorted(VARIANTS)}')
    return VARIANTS[name]


def make_moved_fix_monitor(base):
    """A ``ProgressMonitor`` subclass that arms only from a fix newer than the first issued move (rule ``p2f``)."""
    class MovedFixMonitor(base):
        def __init__(self):
            super().__init__()
            self.move_t0 = None            # SIM time of the first issued base-motion command since reset
            self.report_source = None      # callable -> the own PoseReport of the moment trusted() is called

        def note_command(self, row):
            from harness.zone_own_guards import commanded_step_m
            if self.move_t0 is None and commanded_step_m(row) > 0:
                self.move_t0 = float(row['t'])

        def reset(self):
            super().reset()
            self.move_t0 = None

        def trusted(self, xy, goal_dist):
            if self.baseline is None:
                report = self.report_source() if self.report_source is not None else None
                fix_t = getattr(report, 'last_fix_t', None)
                ok = (self.move_t0 is not None and isinstance(fix_t, (int, float)) and fix_t == fix_t and fix_t > self.move_t0)
                row = {'fix_t': fix_t, 'move_t0': self.move_t0, 'commanded_m': round(self.commanded_m, 4)}
                if not ok:
                    if len(IGNORED) < MAX_LOGGED:
                        IGNORED.append(row)
                    return None
                if len(ARMED) < MAX_LOGGED:
                    ARMED.append(row)
            return super().trusted(xy, goal_dist)
    return MovedFixMonitor


def install_p2f() -> list:
    """Patch ``PairCommandGuard`` (the loaded pair's guard) so its own monitor follows rule p2f. The unloaded ``GuardedDriver``
    (harness.zone_own_driver) keeps the registered monitor: its module-level ``ProgressMonitor`` name is not touched."""
    from harness import zone_pair_guards as pg
    if getattr(pg.PairCommandGuard, '_p2f', False):
        raise RuntimeError('p2f is already installed in this process')
    monitor_cls = make_moved_fix_monitor(pg.ProgressMonitor)
    init, on_command = pg.PairCommandGuard.__init__, pg.PairCommandGuard.on_command

    def init_(self, execution):
        init(self, execution)
        self.monitor = monitor_cls()
        self.monitor.report_source = lambda: self.ep.own.last_report

    def on_command_(self, row):
        on_command(self, row)
        if not self.approach:            # the registered guard charges commanded travel only outside the approach
            self.monitor.note_command(row)
    pg.PairCommandGuard.__init__, pg.PairCommandGuard.on_command = init_, on_command_
    pg.PairCommandGuard._p2f = True
    IGNORED.clear()
    ARMED.clear()
    return ['harness.zone_pair_guards.PairCommandGuard.__init__/on_command (loaded pair monitor: arm only from a fix newer than the first move)']


def install(name: str | None) -> dict | None:
    if name is None:
        return None
    knobs = variant(name)
    from harness import zone_own_guards as g
    patched = []
    if knobs.get('arm_after_move_start_fix'):
        patched += install_p2f()
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
