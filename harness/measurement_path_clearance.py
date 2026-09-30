"""Offline swept-disc bounds, conditional on an independently bounded plant.

Intervals cover positive/negative gains and drive/stop time constants separately.
The world-axis speed error includes cross-axis motion, yaw, slip and model error;
it is not inferred from a single run or from first-order fit residuals. No physics.
"""
from __future__ import annotations

import math


def _interval(value, *, positive=False):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in value)
            or value[0] > value[1] or (positive and value[0] <= 0)):
        raise ValueError('INVALID_MOTION_BOUNDS')
    return tuple(value)


def _nonnegative(value):
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('INVALID_MOTION_BOUNDS')
    return value


def _outward(lo, hi):
    return math.nextafter(lo, -math.inf), math.nextafter(hi, math.inf)


def _blend(previous, target, weights):
    # Each coefficient is nonnegative: enumerate the interval corners.
    values = [w * v + (1 - w) * u for w in weights for v in previous for u in target]
    return _outward(min(values), max(values))


def _step(position, velocity, command, duration, bounds):
    gains = bounds['positive_gain'] if command >= 0 else bounds['negative_gain']
    target = tuple(sorted(command * g for g in gains))
    tau = bounds['drive_tau_s'] if command else bounds['stop_tau_s']
    decay = tuple(math.exp(-duration / q) for q in tau)
    # Integral weight q*(1-exp(-h/q))/h increases monotonically with q.
    weight = tuple(-q * math.expm1(-duration / q) / duration for q in tau)
    mean_velocity = _blend(velocity, target, weight)
    error = bounds['world_speed_error_m_s']
    end = _outward(position[0] + duration * (mean_velocity[0] - error),
                   position[1] + duration * (mean_velocity[1] + error))
    # At EVERY time in this cell, velocity is in the convex hull of v0 and G*u.
    # This swept interval includes a reversal's interior extremum even when the
    # endpoints (or every sampled pose) look safe. Conservatism may reject a path.
    swept = _outward(position[0] + duration * min(0., velocity[0] - error, target[0] - error),
                     position[1] + duration * max(0., velocity[1] + error, target[1] + error))
    return end, _blend(velocity, target, decay), swept


def _box_clearance(static, walls, xy, radius):
    x, y = xy
    x0, x1, y0, y1 = static['bounds_m']
    gaps = [x[0] - x0, x1 - x[1], y[0] - y0, y1 - y[1]]
    for a, b, c, d in walls:
        gaps.append(math.hypot(max(a - x[1], x[0] - b, 0.),
                               max(c - y[1], y[0] - d, 0.)))
    return min(gaps) - radius


def full_path_clearance(static, walls, plan, bounds):
    """Conservative lower bound over the entire continuous commanded path.

    `bounds` must include BOTH directions, both time constants, initial state
    intervals and a world-axis model-error speed bound. Finite grid samples alone
    are not an uncertainty envelope. Evidence qualification belongs to admission.
    """
    if not isinstance(bounds, dict) or set(bounds) != {'forward', 'left'}:
        raise ValueError('MISSING_MOTION_BOUNDS')
    axes = ('forward', 'left')
    for axis in axes:
        row = bounds[axis]
        for key in ('positive_gain', 'negative_gain', 'drive_tau_s', 'stop_tau_s'):
            _interval(row[key], positive=True)
        _interval(row['initial_velocity_m_s'])
        for key in ('initial_position_error_m', 'world_speed_error_m_s'):
            _nonnegative(row[key])
    if plan['spawn_xy_yaw'][2] != 0:
        raise ValueError('UNSUPPORTED_MEASUREMENT_HEADING')
    dt = plan['control_period_s']
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError('INVALID_PATH_PERIOD')
    positions = [(p - bounds[a]['initial_position_error_m'], p + bounds[a]['initial_position_error_m'])
                 for a, p in zip(axes, plan['spawn_xy_yaw'][:2])]
    velocities = [bounds[a]['initial_velocity_m_s'] for a in axes]
    radius = plan['clearance']['robot_radius_bound_m']
    minimum = _box_clearance(static, walls, positions, radius)
    worst = [0., 0.]
    step_count = 0
    segments = [{'duration_s': plan['initial_hold_s'], 'axis': 'forward', 'value': 0.}, *plan['segments']]
    for segment in segments:
        steps = round(segment['duration_s'] / dt)
        if steps < 0 or abs(steps * dt - segment['duration_s']) > 1e-8:
            raise ValueError('PATH_BOUNDARY_OFF_GRID')
        for _ in range(steps):
            swept = []
            for i, axis in enumerate(axes):
                command = segment['value'] if segment['axis'] == axis else 0.
                positions[i], velocities[i], sweep = _step(positions[i], velocities[i], command, dt, bounds[axis])
                if not all(math.isfinite(v) for pair in (positions[i], velocities[i], sweep) for v in pair):
                    raise ValueError('NONFINITE_PATH_ENVELOPE')
                swept.append(sweep)
            gap = _box_clearance(static, walls, swept, radius)
            if not math.isfinite(gap):
                raise ValueError('NONFINITE_PATH_ENVELOPE')
            if gap < minimum:
                minimum, worst = gap, [step_count * dt, (step_count + 1) * dt]
            step_count += 1
    required = plan['clearance']['minimum_m'] + plan['clearance']['abort_buffer_m']
    return {'minimum_lower_bound_m': minimum, 'worst_interval_s': worst,
            'required_clearance_m': required, 'satisfies_margin': minimum >= required,
            'continuous_path': True, 'cells': step_count,
            'scope': 'conditional interval bound, not evidence that the plant lies within these bounds'}


def point_model_bounds(models):
    """Diagnostic witnesses only; zero residual/slip is NOT a plant bound."""
    return {axis: {'positive_gain': [g, g], 'negative_gain': [g, g],
                   'drive_tau_s': [td, td], 'stop_tau_s': [ts, ts],
                   'initial_velocity_m_s': [0., 0.], 'initial_position_error_m': 0.,
                   'world_speed_error_m_s': 0.}
            for axis, (g, td, ts) in models.items()}
