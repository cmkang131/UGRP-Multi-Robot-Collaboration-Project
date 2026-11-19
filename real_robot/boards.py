"""Board back ends: a fake board for tests and a persistent I2C board for the Pi.

The I2C frames are the same as scripts/masterpi_control.py (motor register 31..34 with the
legacy Board.py direction flip, servo register 40 with [1, ms_lo, ms_hi, id, pwm_lo, pwm_hi]).
The difference: the bus is opened once and kept, instead of starting the `i2ctransfer`
program for every write, so a write takes well under a millisecond instead of a process start.
"""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

_CONTROL_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'masterpi_control.py'


def _load_control():
    spec = importlib.util.spec_from_file_location('ugrp_masterpi_control', _CONTROL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBoard:
    """Records every write with its clock time. `clock` can be a fake clock for tests."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.writes = []

    def write_motor(self, motor: int, speed: int) -> None:
        if motor not in (1, 2, 3, 4) or not -100 <= speed <= 100:
            raise ValueError('bad motor write')
        self.writes.append(('motor', motor, speed, self.clock()))

    def write_servo(self, servo: int, pwm: int, duration_s: float) -> None:
        self.writes.append(('servo', servo, pwm, round(duration_s * 1000), self.clock()))


class I2CBoard:
    """Real MasterPi expansion board over a persistent smbus2 handle (Pi only)."""

    def __init__(self, bus: int | None = None, clock=time.monotonic):
        import smbus2  # only on the Pi
        self.mc = _load_control()
        self.clock = clock
        self.bus = smbus2.SMBus(self.mc.I2C_BUS if bus is None else bus)

    def write_motor(self, motor: int, speed: int) -> None:
        if speed and abs(speed) < self.mc.MIN_EFFECTIVE_WHEEL_SPEED:
            raise ValueError('values below 35 are forbidden on this chassis')
        value = self.mc.board_signed_speed(motor, speed) & 0xFF
        self.bus.write_byte_data(self.mc.I2C_ADDRESS, self.mc.motor_register(motor), value)

    def write_servo(self, servo: int, pwm: int, duration_s: float) -> None:
        if servo not in self.mc.SERVO_IDS or not self.mc.SERVO_PULSE_MIN <= pwm <= self.mc.SERVO_PULSE_MAX:
            raise ValueError('bad servo write')
        ms = int(round(duration_s * 1000))
        if not 0 < ms <= 0xFFFF:
            raise ValueError('bad servo duration')
        self.bus.write_i2c_block_data(self.mc.I2C_ADDRESS, self.mc.SERVO_REGISTER,
                                      [1, ms & 0xFF, ms >> 8, servo, pwm & 0xFF, pwm >> 8])

    def close(self) -> None:
        for motor in (1, 2, 3, 4):
            try:
                self.write_motor(motor, 0)
            except OSError:
                pass
        self.bus.close()
