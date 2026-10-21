"""E2E-min actuation option: DutyActPort servo-update order (default OFF).

The ACT owner applies a command through ``DutyActPort.apply`` [T 6f057f7e
``sim/grasp_act_port.py``, ``sim/camera_robot_port.py``; O 0362037
``scripts/warp_act_api.py:386-390``]: a servo target is (re)queued only when
its pulse differs from the previous issued command, and queueing first advances
every pending target to the command time (2000 PWM/s).  The nav runner's
``e2e_warp_physics.issue`` writes every target directly and leaves that first
advance to the first substep of the shared tape.  Both paths then decode with
the identical ``control_tape`` (2000 PWM/s slew, relay, wheel deadlines).

The only difference is the target used for the first 0.25 ms substep after a
target change (<= 0.5 PWM).  ``duty_port_v1`` reproduces the owner order
exactly.  Unset keeps ``issue`` byte-identical.  Stdlib only.
"""
from __future__ import annotations

import os

ENV = 'E2E_MIN_ACTUATION'
MODES = ('direct', 'duty_port_v1')
RATE_PWM_S = 2000.0  # CameraRobotPort._advance_servos / control_tape


def mode(environ=None):
    """'direct' (default) or 'duty_port_v1'; only valid with E2E_MIN_HANDOFF."""
    env = os.environ if environ is None else environ
    value = env.get(ENV, '') or 'direct'
    if value not in MODES:
        raise ValueError(f'{ENV} must be unset or one of {MODES}, got {value!r}')
    if value != 'direct':
        from harness import e2e_min_handoff as H
        if not H.enabled(env):
            raise ValueError(f'{ENV}={value} requires {H.ENV}={H.MODE}')
    return value


def advance(port, now):
    """CameraRobotPort._advance_servos on the runner port fields."""
    now = float(now)
    if now < port._servo_tick_time - 1e-12:
        raise ValueError('issued command clock moved backwards')
    allowance = RATE_PWM_S * max(0.0, now - port._servo_tick_time)
    for servo, target in tuple(port._servo_targets.items()):
        current = port._servo_applied.get(servo, float(target))
        moved = current + max(-allowance, min(allowance, float(target) - current))
        port._servo_applied[servo] = moved
        if abs(moved - target) < 1e-9:
            port._servo_targets.pop(servo, None)
    port._servo_tick_time = now


def duty_port_servos(port, pwm, now):
    """Queue only changed pulses, advancing pending targets first (owner order)."""
    pwm = {int(k): int(v) for k, v in pwm.items()}
    previous = getattr(port, '_duty_previous_pwm', None)
    if previous is None:
        # Owner convention: the previous command is the initial issued state.
        previous = {s: int(round(v)) for s, v in port._servo_applied.items()}
    changed = {s: p for s, p in pwm.items() if previous.get(s) != p}
    if changed:
        advance(port, now)
        port._servo_targets.update(changed)
    port._duty_previous_pwm = pwm
    return changed
