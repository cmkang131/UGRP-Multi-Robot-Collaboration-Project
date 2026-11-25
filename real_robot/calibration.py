"""Measured mapping from simulator command units to MasterPi board units.

Nothing here has a default value. Every number comes from a calibration file
filled from bench measurements (docs/sim2real/tasks/T03_wheel_pulses.md,
T04_servos.md). A file whose `measured` flag is false can only drive the fake
board, never the real I2C board.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

# Simulator wheel order (sim/camera_robot_port.py): front-left, front-right, rear-left, rear-right.
SIM_WHEELS = ('front_left', 'front_right', 'rear_left', 'rear_right')
# Existing chassis rule (scripts/masterpi_control.py MIN_EFFECTIVE_WHEEL_SPEED): board speeds
# with |v| < 35 are forbidden on this chassis because the wheels do not turn reliably.
BOARD_MIN_ABS_SPEED = 35
BOARD_MAX_ABS_SPEED = 100  # board register range, scripts/masterpi_control.py board_signed_speed
# Simulator servo slew (sim/camera_robot_port.py _queue_servos): 2000 PWM units per second.
SIM_SERVO_SLEW_PWM_PER_S = 2000.0
# Optional per-motion pulse duration scaling (defaults to 1.0 when omitted from calibration).
PULSE_SCALE_KEYS = ('drive', 'rotate', 'strafe')
PULSE_SCALE_MAX = 3.0
DEFAULT_PULSE_SCALE = {k: 1.0 for k in PULSE_SCALE_KEYS}
SERVO_IDS = (1, 3, 4, 5, 6)
SERVO_PWM_MIN = 500
SERVO_PWM_MAX = 2500
RED_HUE_MAX_DEFAULT = 8
RED_SAT_MIN_DEFAULT = 150


@dataclass(frozen=True)
class WheelMap:
    motor: int          # board motor channel 1..4
    sign: int           # +1 or -1: board direction that makes the sim-positive motion
    points: tuple       # ((sim_abs, board_abs), ...) sorted by sim_abs, measured


@dataclass(frozen=True)
class ServoConfig:
    offset_pwm: int = 0
    min_pwm: int = SERVO_PWM_MIN
    max_pwm: int = SERVO_PWM_MAX


@dataclass(frozen=True)
class CameraConfig:
    enabled: bool = False
    f_real: float = 515.7
    pitch_offset_deg: float = 0.0
    yaw_offset_deg: float = 0.0
    roll_offset_deg: float = 0.0
    cx_real: float = 320.0
    cy_real: float = 240.0
    d_real: tuple[float, float, float, float] | None = None
    jpeg_quality: int = 90


@dataclass(frozen=True)
class VisionConfig:
    red_hue_max: int = RED_HUE_MAX_DEFAULT
    red_sat_min: int = RED_SAT_MIN_DEFAULT
    area_scale: float = 1.0
    camera_pitch_offset_deg: float = 0.0


@dataclass(frozen=True)
class Calibration:
    robot_id: str
    measured: bool
    source: str | None
    wheels: dict        # sim wheel name -> WheelMap
    servo_min_duration_s: float  # shortest servo move the board accepts (measured/specified)
    sim_no_motion_max: float | None = None  # largest sim wheel value that does not move the sim robot
    pulse_scale: dict = field(default_factory=lambda: dict(DEFAULT_PULSE_SCALE))
    servos: dict = field(default_factory=lambda: {sid: ServoConfig() for sid in SERVO_IDS})
    camera: CameraConfig = field(default_factory=CameraConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)

    def pulse_scale_for(self, motion: str) -> float:
        """Return the pulse duration scale factor for a classified motion ('drive', 'rotate', 'strafe', 'stop')."""
        if motion == 'stop':
            return 1.0
        if motion not in self.pulse_scale:
            raise ValueError(f'unknown pulse motion {motion!r}')
        return float(self.pulse_scale[motion])

    def servo_pwm(self, servo_id: int, sim_pwm: int) -> tuple[int, bool]:
        """Map one simulator servo PWM (500..2500) to calibrated physical PWM, clamping to safe [min_pwm, max_pwm]."""
        if type(servo_id) is not int or servo_id not in SERVO_IDS:
            raise ValueError(f'unknown servo id {servo_id!r}')
        if type(sim_pwm) is not int or not SERVO_PWM_MIN <= sim_pwm <= SERVO_PWM_MAX:
            raise ValueError(f'servo {servo_id} sim PWM {sim_pwm!r} outside {SERVO_PWM_MIN}..{SERVO_PWM_MAX}')
        cfg = self.servos.get(servo_id, ServoConfig())
        raw = sim_pwm + cfg.offset_pwm
        clamped_val = max(cfg.min_pwm, min(cfg.max_pwm, raw))
        return clamped_val, clamped_val != raw

    def build_camera_warp(self):
        """Instantiate SimCameraWarp if camera warping is enabled in this profile, else None."""
        if not self.camera.enabled:
            return None
        from .camera_warp import SimCameraWarp
        return SimCameraWarp(
            f_real=self.camera.f_real,
            pitch_offset_deg=self.camera.pitch_offset_deg,
            yaw_offset_deg=self.camera.yaw_offset_deg,
            roll_offset_deg=self.camera.roll_offset_deg,
            cx_real=self.camera.cx_real,
            cy_real=self.camera.cy_real,
            d_real=self.camera.d_real,
            jpeg_quality=self.camera.jpeg_quality,
        )

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


def _exact_int(name, value):
    if type(value) is not int:
        raise ValueError(f'{name} must be an integer, got {value!r}')
    return value


def _parse_servos(raw) -> dict[int, ServoConfig]:
    servos = {sid: ServoConfig() for sid in SERVO_IDS}
    if raw is None:
        return servos
    if not isinstance(raw, dict):
        raise ValueError('servos must be an object')
    allowed_fields = {'offset_pwm', 'min_pwm', 'max_pwm'}
    for k, row in raw.items():
        try:
            sid = int(k)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'servos: invalid servo id {k!r}') from exc
        if sid not in SERVO_IDS:
            raise ValueError(f'servos: unknown servo id {sid!r}')
        if not isinstance(row, dict):
            raise ValueError(f'servos.{sid} must be an object')
        unknown = set(row) - allowed_fields
        if unknown:
            raise ValueError(f'servos.{sid}: unknown keys {sorted(unknown)}')
        offset = _exact_int(f'servos.{sid}.offset_pwm', row.get('offset_pwm', 0))
        if not -500 <= offset <= 500:
            raise ValueError(f'servos.{sid}.offset_pwm must be in -500..500, got {offset}')
        min_pwm = _exact_int(f'servos.{sid}.min_pwm', row.get('min_pwm', SERVO_PWM_MIN))
        max_pwm = _exact_int(f'servos.{sid}.max_pwm', row.get('max_pwm', SERVO_PWM_MAX))
        if not (SERVO_PWM_MIN <= min_pwm <= max_pwm <= SERVO_PWM_MAX):
            raise ValueError(f'servos.{sid}: min_pwm..max_pwm ({min_pwm}..{max_pwm}) must be within 500..2500')
        servos[sid] = ServoConfig(offset_pwm=offset, min_pwm=min_pwm, max_pwm=max_pwm)
    return servos


def _parse_camera(raw) -> CameraConfig:
    if raw is None:
        return CameraConfig()
    if not isinstance(raw, dict):
        raise ValueError('camera must be an object')
    allowed = {'enabled', 'f_real', 'pitch_offset_deg', 'yaw_offset_deg', 'roll_offset_deg',
               'cx_real', 'cy_real', 'd_real', 'jpeg_quality'}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f'camera: unknown keys {sorted(unknown)}')
    enabled = raw.get('enabled', False)
    if type(enabled) is not bool:
        raise ValueError('camera.enabled must be a boolean')
    f_real = _finite('camera.f_real', raw.get('f_real', 515.7))
    if f_real <= 0.0:
        raise ValueError(f'camera.f_real must be > 0, got {f_real}')
    pitch = _finite('camera.pitch_offset_deg', raw.get('pitch_offset_deg', 0.0))
    yaw = _finite('camera.yaw_offset_deg', raw.get('yaw_offset_deg', 0.0))
    roll = _finite('camera.roll_offset_deg', raw.get('roll_offset_deg', 0.0))
    for name, val in (('pitch_offset_deg', pitch), ('yaw_offset_deg', yaw), ('roll_offset_deg', roll)):
        if not -60.0 <= val <= 60.0:
            raise ValueError(f'camera.{name} must be in [-60, 60], got {val}')
    cx = _finite('camera.cx_real', raw.get('cx_real', 320.0))
    cy = _finite('camera.cy_real', raw.get('cy_real', 240.0))
    d_raw = raw.get('d_real')
    d_real = None
    if d_raw is not None:
        if not isinstance(d_raw, (list, tuple)) or len(d_raw) != 4:
            raise ValueError('camera.d_real must be a 4-element list or null')
        d_real = tuple(_finite('camera.d_real', v) for v in d_raw)
    jq = _exact_int('camera.jpeg_quality', raw.get('jpeg_quality', 90))
    if not 1 <= jq <= 100:
        raise ValueError(f'camera.jpeg_quality must be in 1..100, got {jq}')
    return CameraConfig(
        enabled=enabled, f_real=f_real, pitch_offset_deg=pitch,
        yaw_offset_deg=yaw, roll_offset_deg=roll,
        cx_real=cx, cy_real=cy, d_real=d_real, jpeg_quality=jq,
    )


def _parse_vision(raw) -> VisionConfig:
    if raw is None:
        return VisionConfig()
    if not isinstance(raw, dict):
        raise ValueError('vision must be an object')
    allowed = {'red_hue_max', 'red_sat_min', 'area_scale', 'camera_pitch_offset_deg'}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f'vision: unknown keys {sorted(unknown)}')
    rhm = _exact_int('vision.red_hue_max', raw.get('red_hue_max', RED_HUE_MAX_DEFAULT))
    if not 0 <= rhm <= RED_HUE_MAX_DEFAULT:
        raise ValueError(f'vision.red_hue_max must be in 0..{RED_HUE_MAX_DEFAULT}, got {rhm}')
    rsm = _exact_int('vision.red_sat_min', raw.get('red_sat_min', RED_SAT_MIN_DEFAULT))
    if not 0 <= rsm <= 255:
        raise ValueError(f'vision.red_sat_min must be in 0..255, got {rsm}')
    asc = _finite('vision.area_scale', raw.get('area_scale', 1.0))
    if asc <= 0.0:
        raise ValueError(f'vision.area_scale must be > 0, got {asc}')
    cp = _finite('vision.camera_pitch_offset_deg', raw.get('camera_pitch_offset_deg', 0.0))
    return VisionConfig(red_hue_max=rhm, red_sat_min=rsm, area_scale=asc, camera_pitch_offset_deg=cp)


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
    raw_scale = data.get('pulse_scale')
    if raw_scale is None:
        pulse_scale = dict(DEFAULT_PULSE_SCALE)
    else:
        if not isinstance(raw_scale, dict):
            raise ValueError('pulse_scale must be an object')
        unknown = set(raw_scale) - set(PULSE_SCALE_KEYS)
        if unknown:
            raise ValueError(f'unknown pulse_scale keys: {sorted(unknown)}')
        pulse_scale = dict(DEFAULT_PULSE_SCALE)
        for key, raw_val in raw_scale.items():
            val = _finite(f'pulse_scale.{key}', raw_val)
            if not 0.0 < val <= PULSE_SCALE_MAX:
                raise ValueError(f'pulse_scale.{key} must be in (0, {PULSE_SCALE_MAX}]')
            pulse_scale[key] = val
    servos = _parse_servos(data.get('servos'))
    camera = _parse_camera(data.get('camera'))
    vision = _parse_vision(data.get('vision'))
    return Calibration(robot_id=str(data['robot_id']), measured=bool(data['measured']),
                       source=data.get('source'), wheels=wheels, servo_min_duration_s=servo_min,
                       sim_no_motion_max=no_motion, pulse_scale=pulse_scale,
                       servos=servos, camera=camera, vision=vision)


def load(path: str | Path) -> Calibration:
    return parse(json.loads(Path(path).read_text()))
