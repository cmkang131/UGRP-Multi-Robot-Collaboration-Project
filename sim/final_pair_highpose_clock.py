"""v98 host clock v2: SIM time counted in integer physics substeps (2026-10-05 coordinator decision).

Why. The shared hosts (sim.final_environment_checks.BaseBackend.advance_to, sim.final_pair_v3) read the clock
as ``float(world.data.time)``, which MuJoCo advances by ``data.time += timestep`` (timestep 0.00025 s, 200
substeps per 0.05 s host tick). The rounding error of that running sum grows to |grid - time| > 1e-8 s at
about 496.0 SIM s (time below the grid) and, after changing sign, again at 612.05 s (time above the grid):
  * the pair control grid and the status barrier (frozen harness.zone_pair_executor / zone_pair_status) assume
    |drift| <= EPS 1e-8; past it the control ticks slip to the 0.05 s phase and a robot polls 0.05 s after the
    0.1 s grid GO -> LATE_OR_EXPIRED_GO -> BARRIER_CLOSE_ABORT (v98 probe align_to_carry 14ba8b5e, 496.75 s);
  * the shared ``while now + dt <= t + 1e-8`` advance loop stops one substep short at 612.05 s and raises
    'inexact SIM advance' (HOST_ERROR), so no 900 s case could finish.

What. The standard remedy (integer time base): keep an integer substep counter N and derive the time from it,
``data.time = round(N * timestep, 9)``, after every physics substep; advance by an integer substep count
``round(t / timestep) - N`` (no comparison of an accumulated float). Every reader of the clock - the runner's
``backend.now``, own-camera frame ``sim_time`` (CameraRobotPort._clock_time), command rows ``t``, port.tick -
then sees the same decimal grid value, so the frozen EPS/sign checks hold for the whole 900 s case cap and the
frozen files stay byte-identical. MuJoCo's integrator does not read data.time (only callbacks/plugins/clock
sensors would; this scene has none - checked by the open-loop replay record). The host-side port.tick uses the
time for drive expiry and servo slew; those comparisons now see grid values (recorded as a behaviour change).

Scope: v98 hosts only (PhysicsBackend for cases, StagedBackend for DEV stage probes). The shared sim/ files and
earlier bundles are unchanged. Runs with this clock are 'host clock v2' and are never pooled with earlier runs.
Calibration collections (check 'calibration-*') keep the parent's advance (v98 never runs them).
"""
from __future__ import annotations

import math

from sim.final_pair_v3 import PhysicsBackend as V3Backend

ID = 'v98_host_clock_v2_integer_substeps'
SCHEMA = 'ugrp.highpose_host_clock.v98.v2'
DIGITS = 9            # decimal digits kept; timestep 0.00025 s has 5, the grid error of N*timestep is < 1e-12 s
SNAP_TOL_S = 1e-7     # same tolerance as the parent's 'inexact SIM advance' check (sim/final_environment_checks.py)


def grid_time(substeps, dt):
    """Clock value at an integer substep count: recomputed from the integer, never accumulated."""
    return round(substeps * dt, DIGITS)


def record():
    return {'id': ID, 'schema': SCHEMA, 'digits': DIGITS, 'snap_tol_s': SNAP_TOL_S,
            'rule': 'data.time = round(N*timestep, 9) after every substep; advance = integer substep count',
            'replaces': 'float(world.data.time) running sum (|drift| > 1e-8 s from ~496.0 s; advance cliff 612.05 s)',
            'decided': '2026-10-05 coordinator decision (clock at the source; frozen executor/status unchanged)',
            'pooling': 'host clock v2: never pooled with runs before it'}


class IntegerClock:
    """Mixin for a v3 physics backend; must precede the backend in the MRO."""
    host_clock = ID

    def _clock_snap(self):
        """Adopt the integer substep count of the current time (after the reset settle) and write the grid value."""
        d = self.world.data
        n = round(float(d.time) / self.dt)
        if abs(float(d.time) - n * self.dt) > SNAP_TOL_S:
            raise RuntimeError('SIM time is not on the substep grid')
        self._substeps = n
        d.time = grid_time(n, self.dt)

    def reset(self, cap):
        super().reset(cap)
        self._clock_snap()
        # The parent made the command ports at the raw settle time (1.3000000000000178 s); the snap moved the clock to
        # 1.3, and a port refuses a time before its own last tick ('sim_time must not move backwards'). Remake them at
        # the grid time exactly as V3Backend.reset remakes them from the issued reset pulses (no command since then).
        from sim.camera_robot_port import CameraRobotPort
        self.ports = {rid: CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
                      for rid in self.ports}
        return self.now

    def advance_to(self, t):
        if self.bundle['check'].startswith('calibration-'):
            return super().advance_to(t)
        if getattr(self, '_substeps', None) is None:
            raise RuntimeError('host clock v2 used before reset')
        if self.deadline is None or not math.isfinite(t) or not self.now - 1e-8 <= t <= self.deadline + 1e-8:
            raise ValueError('advance outside SIM deadline')
        target = round(t / self.dt)
        if abs(t - target * self.dt) > SNAP_TOL_S:
            raise RuntimeError('inexact SIM advance')
        d = self.world.data
        while self._substeps < target:
            for port in self.ports.values():
                port.tick(self.now)
            self.world._physics_step_for(self.world.robot('r1'))
            self._substeps += 1
            d.time = grid_time(self._substeps, self.dt)


class PhysicsBackend(IntegerClock, V3Backend):
    """v98 case host: sim.final_pair_v3.PhysicsBackend with host clock v2."""
