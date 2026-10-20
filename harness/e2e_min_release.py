"""Rule-script release ``release_open_v1`` (E2E-1p release substitute; default off).

Own commands only (no GT, map, top camera or measured joints):

1. ``stop``: wheels 0, held PWM, for ``stop_ticks``.
2. ``open``: servo 1 (gripper) ramps linearly from the held value to
   ``OPEN_PWM`` over ``ramp_ticks``, then holds ``OPEN_PWM`` for
   ``open_hold_ticks``; servos 3-6 stay at the held PWM; wheels 0.
3. ``backoff``: all four wheels -WHEEL (straight reverse in the contract
   wheel mix) with ``pulse_s`` per tick until the own-command odometry
   (``e2ewarp_selfnav.OwnCommandOdometry`` with the owner-injected nav
   calibration) has integrated ``backoff_m`` of reverse travel.
4. ``done``: wheels 0, open PWM; ``done=True``.

Frozen constants and their provenance (teacher dataset
``outputs/runs/act18-clockaudit-20261019T151956Z/dataset-columns.jsonl``,
release skill, 200 TRAIN episodes):

* ``OPEN_PWM = 2000``: the teacher's gripper value at the end of every
  ``open`` phase and at the first ``retract`` row (200/200 episodes, median
  2000, no other value).  The directive quoted "about 2009"; the data gives
  exactly 2000, so 2000 is used and the discrepancy is recorded.
* ``ramp_ticks = 5``, ``open_hold_ticks = 3``: teacher ``open`` phase median 8
  ticks (min 7, max 8), with the gripper reaching 2000 on the 6th row
  (1500, 1552, 1676, 1824, 1948, 2000, 2000, 2000).
* ``stop_ticks``, ``backoff_m``: prereg values [확인 필요]; defaults 3 ticks and
  0.15 m are placeholders.
"""
from __future__ import annotations

SCHEMA = 'ugrp.e2e_min.release_open_v1'
NAME = 'release_open_v1'
OPEN_PWM = 2000
WHEEL = 0.35          # normalized duty, same magnitude as the nav adapter (WHEEL_PCT)
PULSE_S = 0.10
DEFAULTS = dict(stop_ticks=3, ramp_ticks=5, open_hold_ticks=3, backoff_m=0.15, max_backoff_ticks=60)


class ReleaseOpenV1:
    """Executor protocol: propose(frame, now) -> {'command', 'done'}."""

    def __init__(self, robot, odometry, **params):
        unknown = set(params) - set(DEFAULTS)
        if unknown:
            raise ValueError('unknown release_open_v1 params: ' + ', '.join(sorted(unknown)))
        self.p = {**DEFAULTS, **params}
        if self.p['backoff_m'] <= 0 or self.p['ramp_ticks'] < 1 or self.p['stop_ticks'] < 0:
            raise ValueError('invalid release_open_v1 params')
        self.robot, self.odometry = robot, odometry
        self.held = None
        self.tick = 0
        self.backed_m = 0.0
        self.backoff_ticks = 0
        self.stage = 'stop'
        self.log = []

    def _cmd(self, now, pwm, wheel=0.0):
        moving = wheel != 0.0
        return dict(t=float(now), wheels=[wheel] * 4, duration_s=[PULSE_S if moving else 0.0] * 4,
                    pwm={k: int(v) for k, v in pwm.items()})

    def propose(self, frame, now):
        if getattr(frame, 'robot_id', self.robot) != self.robot:
            raise ValueError('cross-robot release input rejected')
        if self.held is None:
            last = getattr(frame, 'issued', None)
            if not last:
                raise ValueError('release_open_v1 needs the own issued history (held PWM)')
            self.held = {str(k): int(v) for k, v in last[-1]['pwm'].items()}
        p, k = self.p, self.tick
        self.tick += 1
        open_start = p['stop_ticks']
        open_end = open_start + p['ramp_ticks'] + p['open_hold_ticks']
        if k < open_start:
            self.stage = 'stop'
            return self._out(self._cmd(now, self.held), False)
        if k < open_end:
            self.stage = 'open'
            step = min(k - open_start + 1, p['ramp_ticks'])
            g0 = self.held['1']
            g = round(g0 + (OPEN_PWM - g0) * step / p['ramp_ticks'])
            return self._out(self._cmd(now, dict(self.held, **{'1': g})), False)
        opened = dict(self.held, **{'1': OPEN_PWM})
        if self.backed_m < p['backoff_m'] - 1e-12:
            if self.backoff_ticks >= p['max_backoff_ticks']:
                raise ValueError('release_open_v1 backoff tick cap reached')
            self.stage = 'backoff'
            cmd = self._cmd(now, opened, -WHEEL)
            step_m, _ = self.odometry.step(cmd)
            self.backed_m += -step_m
            self.backoff_ticks += 1
            return self._out(cmd, False)
        self.stage = 'done'
        return self._out(self._cmd(now, opened), True)

    def _out(self, cmd, done):
        self.log.append(dict(t=cmd['t'], stage=self.stage, pwm1=cmd['pwm']['1'],
                             wheel=cmd['wheels'][0], backed_m=round(self.backed_m, 4)))
        return dict(command=cmd, done=done)

    def record(self):
        return dict(schema=SCHEMA, name=NAME, robot=self.robot, params=dict(self.p),
                    open_pwm=OPEN_PWM, wheel=WHEEL, pulse_s=PULSE_S,
                    backed_m=round(self.backed_m, 4), ticks=self.tick, inputs='own issued commands only',
                    log=list(self.log))
