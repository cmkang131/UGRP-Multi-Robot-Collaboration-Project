"""Measured mapping from simulator command units to MasterPi board units.

Nothing here has a default value. Every number comes from a calibration file
filled from bench measurements (docs/sim2real/tasks/T03_wheel_pulses.md,
T04_servos.md). A file whose `measured` flag is false can only drive the fake
board, never the real I2C board.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

# Simulator wheel order (sim/camera_robot_port.py): front-left, front-right, rear-left, rear-right.
SIM_WHEELS = ('front_left', 'front_right', 'rear_left', 'rear_right')
# Existing chassis rule (scripts/masterpi_control.py MIN_EFFECTIVE_WHEEL_SPEED): board speeds
# with |v| < 35 are forbidden on this chassis because the wheels do not turn reliably.
BOARD_MIN_ABS_SPEED = 35
BOARD_MAX_ABS_SPEED = 100  # board register range, scripts/masterpi_control.py board_signed_speed
# Simulator servo slew (sim/camera_robot_port.py _queue_servos): 2000 PWM units per second.
SIM_SERVO_SLEW_PWM_PER_S = 2000.0


@dataclass(frozen=True)
class WheelMap:
    motor: int          # board motor channel 1..4
    sign: int           # +1 or -1: board direction that makes the sim-positive motion
    points: tuple       # ((sim_abs, board_abs), ...) sorted by sim_abs, measured


@dataclass(frozen=True)
class Calibration:
    robot_id: str
    measured: bool
    source: str | None
    wheels: dict        # sim wheel name -> WheelMap
    servo_min_duration_s: float  # shortest servo move the board accepts (measured/specified)
    sim_no_motion_max: float | None = None  # largest sim wheel value that does not move the sim robot


    def board_speed(self, wheel_index: int, sim_value: float) -> int:
        """Map one simulator wheel value (0 or +-0.31..0.40) to a signed board integer."""
        if sim_value == 0.0:
            return 0
        wheel = self.wheels[SIM_WHEELS[wheel_index]]
        magnitude = abs(sim_value)
        if self.sim_no_motion_max is not None and magnitude <= self.sim_no_motion_max + 1e-9:
            return 0  # the sim robot does not move at this value (sim reference), so the real wheel stays off
        pts = wheel.points
        if not pts[0][0] - 1e-9 <= magnitude <= pts[-1][0] + 1e-9:
            raise ValueError(f'wheel value {sim_value} outside measured range '
                             f'{pts[0][0]}..{pts[-1][0]}')
        board = pts[-1][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 - 1e-9 <= magnitude <= x1 + 1e-9:
                board = y0 if x1 == x0 else y0 + (y1 - y0) * (magnitude - x0) / (x1 - x0)
                break
        board = int(round(board))
        if not BOARD_MIN_ABS_SPEED <= board <= BOARD_MAX_ABS_SPEED:
            raise ValueError(f'mapped board speed {board} outside {BOARD_MIN_ABS_SPEED}..{BOARD_MAX_ABS_SPEED}')
        return wheel.sign * (1 if sim_value > 0 else -1) * board


def _finite(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return float(value)


def parse(data: dict) -> Calibration:
    if not isinstance(data, dict):
        raise ValueError('calibration must be an object')
    wheels = {}
    motors = set()
    for name in SIM_WHEELS:
        row = data['wheels'][name]
        motor = row['motor']
        if motor not in (1, 2, 3, 4) or motor in motors:
            raise ValueError(f'{name}: motor must be a distinct channel 1..4')
        motors.add(motor)
        if row['sign'] not in (1, -1):
            raise ValueError(f'{name}: sign must be +1 or -1')
        points = tuple(sorted((_finite('sim', a), _finite('board', b)) for a, b in row['points']))
        if not points:
            raise ValueError(f'{name}: at least one measured point required')
        wheels[name] = WheelMap(motor, row['sign'], points)
    servo_min = _finite('servo_min_duration_s', data['servo_min_duration_s'])
    if not 0.0 < servo_min <= 3.0:
        raise ValueError('servo_min_duration_s must be in (0, 3]')
    no_motion = data.get('sim_no_motion_max')
    if no_motion is not None:
        no_motion = _finite('sim_no_motion_max', no_motion)
    return Calibration(robot_id=str(data['robot_id']), measured=bool(data['measured']),
                       source=data.get('source'), wheels=wheels, servo_min_duration_s=servo_min,
                       sim_no_motion_max=no_motion)


def load(path: str | Path) -> Calibration:
    return parse(json.loads(Path(path).read_text()))
