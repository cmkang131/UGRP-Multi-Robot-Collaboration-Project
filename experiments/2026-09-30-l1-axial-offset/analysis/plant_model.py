#!/usr/bin/env python3
"""Loaded-carry forward plant of the pair (first-order lag) measured from the raw ground-truth beam trace, and the along-track
model built on it. Ground truth is EVAL ONLY: it is used here to identify the plant and to judge, never as a controller input.

Plant (measured, identical in all 278 chain cases, see results/plant_fit.txt):
  beam speed v_ss = 51.23 mm/s for the forward command SPEED/FORWARD_GAIN = 0.0381818  (steady gain 1.3418)
  spin-up lag tau = 0.898 s, stop lag tau_stop = 0.006 s, actuation delay 0.063 s
Registered numbers the controller uses:
  open-loop leg time  T = d / (SPEED * CARRY_ODOM_SCALE['axial'])  with SPEED = 0.06 m/s, CARRY_ODOM_SCALE['axial'] = 0.772
  (scripts/study_owncam_pair_beam.py:94; zone_pair_executor.py:207)
  PF plant           motion_loaded gain[0][0] = 1.4004, tau_s 0.8, tau_stop_s 0.05 (calibration_loop_v2.json)
"""
import math

import numpy as np

SPEED = 0.06
FORWARD_GAIN = 2.2 / 1.4
CMD = SPEED / FORWARD_GAIN                    # 0.0381818 forward command of a carry leg
ODOM_AXIAL = 0.772                            # registered CARRY_ODOM_SCALE['axial']
PLANT = {'v_ss': 0.05123, 'tau': 0.898, 'tau_stop': 0.0063, 'delay': 0.0632}
GAIN_TRUE = PLANT['v_ss'] / CMD               # 1.3418
PF_GAIN, PF_TAU, PF_TAU_STOP = 1.4004, 0.8, 0.05
KAPPA = 0.9483378899463337                    # PR #284 fit (carry_fwd_gain)
TICK = 0.1
ROUTE_X = [None, 1.55, 2.40]                  # route points: sheet_x, 1.55, 2.40 (zone_pair_executor.make_plan)
COAST_MM = 3.76      # measured beam x(rest) - x(command end snapshot), mm: mean of 364 legs, sd 0.22 (v_ss*delay + stop lag)


def F(T, plant=PLANT):
    """Total displacement [m] of a forward command held T seconds (measured to rest)."""
    tau, ts = plant['tau'], plant['tau_stop']
    return plant['v_ss'] * (T - (tau - ts) * (1 - math.exp(-T / tau)))


def lag_travel(T, v, tau, ts):
    """harness/owncam_carry_v6e.lag_travel (the controller's own lag model)."""
    ramp = 1 - math.exp(-T / tau)
    return v * (T - tau * ramp) + v * ramp * ts


def lag_duration(d, v, tau, ts):
    """harness/owncam_carry_v6e.lag_duration (bisection on lag_travel)."""
    lo, hi = 0., d / v + 10 * tau
    for _ in range(80):
        mid = .5 * (lo + hi)
        lo, hi = (mid, hi) if lag_travel(mid, v, tau, ts) < d else (lo, mid)
    return .5 * (lo + hi)


def T_registered(d):
    """Planned open-loop time of the registered axial leg."""
    return d / (SPEED * ODOM_AXIAL)


def T_lag(d, gain=PF_GAIN, tau=PF_TAU, ts=PF_TAU_STOP):
    """Planned time if the axial leg inverted the loaded-plant lag model (harness.owncam_carry_v6e.leg_duration) with `gain`."""
    return lag_duration(d, abs(gain * CMD), tau, ts)


def ticks_l0(T):
    """Commanded time of leg 0: the schedule starts on a tick boundary (+eps): N = ceil(T/0.1) - 1 ticks (validated on 182 cases)."""
    return TICK * (math.ceil(round(T / TICK, 9)) - 1)


def ticks_l1(T, f):
    """Commanded time of leg 1: the schedule start has fractional tick phase f (0.49 < f < 1, from T_plan = 18.351 -> 184 ticks)."""
    n = math.floor(T / TICK) + (1 if (f + (T / TICK - math.floor(T / TICK))) >= 1 else 0)
    return TICK * n


def along_errors(dx, T0, T1, sheet_x, coast=COAST_MM / 1000):
    """Signed along error [m] of the beam at the L0 end and at the L1 end (leg-end snapshots) against the route points 1.55 / 2.40.

    dx = beam x at leg-0 start - sheet x (= placement x - sheet x); T0, T1 = commanded forward times.
    """
    d0 = ROUTE_X[1] - sheet_x
    e0 = dx + F(T0) - coast - d0
    e1 = dx + F(T0) - d0 + F(T1) - coast - (ROUTE_X[2] - ROUTE_X[1])
    return e0, e1


def sheet_of(x, grid=0.1):
    """coarse_order_sheet x: the setup pose rounded to the 0.1 m grid (harness.pair_owncam_approach.coarse_order_sheet)."""
    return round(round(x / grid) * grid, 6)
