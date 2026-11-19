"""Pi-side executor: runs the simulator's 14-value command with the simulator's timing.

Semantics copied from the simulator (so a command means the same thing on both sides):
- Wheels (solo_pipeline/scripts/run_grasp_act_student.py, `port._set_motors` + `deadlines`):
  every new command overwrites all four wheels at once; wheel i then runs until
  `receive_time + duration_s[i]` and stops by itself. The board has no duration field
  (a motor register holds a speed until the next write), so this class writes the stop.
- Servos (sim/camera_robot_port.py `_queue_servos`): a servo is sent only when its PWM
  changes, and moves at 2000 PWM/s from the last issued PWM. The board takes a move
  time in ms, so the move time is |delta| / 2000 s.

Because each wheel pulse is at most 0.15 s (contract) and the stop is written here on the
Pi, wheels stop within 0.15 s after the last command even if the laptop link drops. No
separate watchdog constant is needed for the wheels.

Nothing is clipped silently: an invalid or unmappable command is rejected as a whole
and logged, and nothing from it is written.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from .calibration import SIM_SERVO_SLEW_PWM_PER_S, Calibration

_CONTRACT_PATH = Path(__file__).resolve().parents[1] / 'solo_pipeline' / 'harness' / 'grasp_act_contract.py'


def _load_contract():
    spec = importlib.util.spec_from_file_location('ugrp_grasp_act_contract', _CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = _load_contract()


class Executor:
    def __init__(self, board, calibration: Calibration, log=None):
        self.board = board
        self.cal = calibration
        self.log = log if log is not None else (lambda event: None)
        self.last_seq = None
        self.speeds = [0, 0, 0, 0]          # board speed currently written per sim wheel
        self.deadlines = [None] * 4         # receive-clock time to stop each wheel
        self.pwm = {}                       # last issued PWM per servo id (int keys)

    # -- servos -----------------------------------------------------------------
    def initialize_servos(self, pwm: dict, duration_s: float, now: float) -> None:
        """First pose: the real servos' position is unknown, so the move time is given explicitly."""
        for key, value in pwm.items():
            servo = int(key)
            if servo not in contract.SERVOS or type(value) is not int or not 500 <= value <= 2500:
                raise ValueError(f'invalid initial servo {key}={value}')
        for key, value in pwm.items():
            self.board.write_servo(int(key), value, duration_s)
            self.pwm[int(key)] = value
        self.log({'event': 'init_servos', 't_recv': now, 'pwm': dict(pwm), 'duration_s': duration_s})

    # -- commands ---------------------------------------------------------------
    def apply(self, seq: int, row: dict, now: float) -> dict:
        """Apply one command row received at Pi time `now`. Returns the logged event."""
        event = {'event': 'command', 'seq': seq, 't_recv': now, 'requested': row}
        try:
            if self.last_seq is not None and seq <= self.last_seq:
                raise ValueError(f'stale sequence {seq} <= {self.last_seq}')
            value = contract.command(row)
            if set(self.pwm) != set(contract.SERVOS):
                raise ValueError('servos not initialized')
            speeds = [self.cal.board_speed(i, w) for i, w in enumerate(value['wheels'])]
            servo_moves = []
            for key, target in value['pwm'].items():
                servo = int(key)
                delta = abs(target - self.pwm[servo])
                if delta == 0:
                    continue
                duration = delta / SIM_SERVO_SLEW_PWM_PER_S
                raised = duration < self.cal.servo_min_duration_s
                servo_moves.append((servo, target, max(duration, self.cal.servo_min_duration_s), duration, raised))
        except (ValueError, KeyError, TypeError) as exc:
            event.update(status='rejected', reason=str(exc))
            self.log(event)
            return event
        written = []
        for i, speed in enumerate(speeds):
            motor = self.cal.wheels[_wheel_name(i)].motor
            self.board.write_motor(motor, speed)
            self.speeds[i] = speed
            self.deadlines[i] = now + value['duration_s'][i] if speed else None
            written.append({'motor': motor, 'speed': speed, 't_write': self.board.clock()})
        servos = []
        for servo, target, duration, sim_duration, raised in servo_moves:
            self.board.write_servo(servo, target, duration)
            self.pwm[servo] = target
            servos.append({'servo': servo, 'pwm': target, 'duration_s': duration,
                           'sim_duration_s': sim_duration, 'duration_raised': raised,
                           't_write': self.board.clock()})
        self.last_seq = seq
        event.update(status='applied', motors=written, servos=servos,
                     deadlines=list(self.deadlines))
        self.log(event)
        return event

    def poll(self, now: float) -> list:
        """Write the stop for every wheel whose pulse has ended. Call often (ms scale)."""
        stops = []
        for i, deadline in enumerate(self.deadlines):
            if deadline is not None and now >= deadline:
                motor = self.cal.wheels[_wheel_name(i)].motor
                self.board.write_motor(motor, 0)
                self.speeds[i] = 0
                self.deadlines[i] = None
                stops.append({'motor': motor, 'deadline': deadline, 't_write': self.board.clock(),
                              'late_s': self.board.clock() - deadline})
        if stops:
            self.log({'event': 'pulse_end', 'stops': stops})
        return stops

    def next_deadline(self):
        pending = [d for d in self.deadlines if d is not None]
        return min(pending) if pending else None

    def stop_all(self, reason: str) -> None:
        for i in range(4):
            self.board.write_motor(self.cal.wheels[_wheel_name(i)].motor, 0)
            self.speeds[i] = 0
            self.deadlines[i] = None
        self.log({'event': 'stop_all', 'reason': reason, 't_write': self.board.clock()})


def _wheel_name(i):
    from .calibration import SIM_WHEELS
    return SIM_WHEELS[i]
