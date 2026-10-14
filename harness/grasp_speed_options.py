"""Opt-in simulation speed options for the grasp teacher (all default OFF).

Options change only physics/loop/render settings, never teacher decisions or
observation content. ``adaptive_dt`` selects the contact-profile step only from
commands the robots themselves issued (arm servo 5 or gripper servo 1 leaving
its initial setpoint), never from simulator state.

Spec string: comma separated, e.g. ``adaptive_dt=0.001,idle_freeze,review_period=2``.

``adaptive_dt`` values above 0.001 s were unstable in probes (an idle robot drifted and the
teacher stalled), so the accepted range ends at 0.001 s.
"""
from __future__ import annotations

FINE_DT_S = .00025
KNOWN = ('adaptive_dt', 'idle_freeze', 'review_period')
TRIGGER_SERVOS = (1, 5)


def parse(spec):
    """Return a validated options dict; empty string means the unchanged baseline."""
    out = {}
    for item in filter(None, (x.strip() for x in (spec or '').split(','))):
        key, _, value = item.partition('=')
        if key not in KNOWN:
            raise ValueError(f'unknown speed option {key!r}; known: {KNOWN}')
        if key in out:
            raise ValueError(f'duplicate speed option {key!r}')
        if key == 'adaptive_dt':
            dt = float(value or .001)
            if not FINE_DT_S < dt <= .001:
                raise ValueError('adaptive_dt must be in (0.00025, 0.001] s')
            out[key] = dt
        elif key == 'review_period':
            period = float(value or 2.)
            if period < 1 or abs(period*10-round(period*10)) > 1e-9:
                raise ValueError('review_period must be >=1 s and a multiple of 0.1 s')
            out[key] = period
        else:
            if value:
                raise ValueError(f'{key} takes no value')
            out[key] = True
    return out


class AdaptiveStep:
    """Coarse step until an issued arm/gripper command leaves the initial setpoint."""

    def __init__(self, world, coarse_dt, initial_pulses):
        self.world, self.coarse_dt, self.fine = world, coarse_dt, False
        self.initial = {rid: {s: int(p[s]) for s in TRIGGER_SERVOS} for rid, p in initial_pulses.items()}
        self.events = []
        world.model.opt.timestep = coarse_dt

    def observe(self, rid, applied_pwm, now):
        if self.fine:
            return
        if any(int(applied_pwm[str(s)]) != self.initial[rid][s] for s in TRIGGER_SERVOS):
            self.fine = True
            self.world.model.opt.timestep = FINE_DT_S
            self.events.append({'t': now, 'robot': rid, 'to_dt_s': FINE_DT_S,
                                'reason': 'issued arm/gripper command left initial setpoint'})

    def record(self):
        return {'coarse_dt_s': self.coarse_dt, 'fine_dt_s': FINE_DT_S,
                'switched': self.fine, 'events': self.events}
