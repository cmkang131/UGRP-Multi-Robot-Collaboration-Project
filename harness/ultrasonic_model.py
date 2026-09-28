"""MasterPi front ultrasonic range sensor: specification and echo model (no simulator).

2026-09-28 user decision (#221): every robot gets its OWN front ultrasonic
range as a control input, identical in all four communication conditions.
This module is the simulator-free half of the model; ``sim.ultrasonic_range``
casts the rays in MuJoCo and ``harness.ultrasonic_map`` casts the same rays
against the static map. Both share ``ray_pattern``/``first_echo``/``noisy_reading``
so the SIM sensor and the map prediction cannot drift apart.

Provenance of every parameter is in ``PROVENANCE`` (see
``docs/ultrasonic_range_sensor.md``):

* ``official``: Hiwonder glowing ultrasonic product listing (2-400 cm,
  15 deg measuring angle, 40 kHz, I2C 0x77).
* ``sdk``: Hiwonder SDK ``Sonar.getDistance()`` (I2C register 0, 2 bytes
  little-endian, integer millimetres, values > 5000 clamped to 5000, read
  failure returns 99999).
* ``photo_nominal``: the existing SIM appearance geometry
  (``sim.masterpi_geometry.NOMINAL_ULTRASONIC_X_M``, 54 mm centre height).
* ``assumption``: not published for this module; generic HC-SR04 values or a
  modelling choice, to be replaced by the bench calibration in the doc.

A reading carries only ``t``, ``range_m`` and ``valid`` (never a geom, body,
hit point or any other simulator state).
"""
from __future__ import annotations

import hashlib
import json
import math
import zlib
from dataclasses import asdict, dataclass

import numpy as np

SENSOR_MODEL_ID = 'masterpi_ultrasonic_v1'
READING_SCHEMA = 'ugrp.own_ultrasonic_reading.v1'


@dataclass(frozen=True)
class UltrasonicSpec:
    # Mount in the chassis frame (x forward, y left); height is from the floor.
    mount_x_m: float = .078
    mount_y_m: float = 0.
    mount_z_floor_m: float = .054
    mount_pitch_deg: float = 0.
    # Ranging limits.
    min_range_m: float = .02
    max_range_m: float = 4.00
    sdk_clamp_m: float = 5.00
    # Cone: 15 deg is the published "measuring angle"; used as the half-angle
    # of the sampled cone, with one-way directivity 0.5 at the cone edge.
    half_angle_deg: float = 15.
    ring_step_deg: float = 2.5
    ring_base_count: int = 4
    directivity_edge_gain: float = .5
    # Specular reflection: amplitude falls with incidence angle (Gaussian).
    incidence_sigma_deg: float = 15.
    echo_threshold: float = .2
    # Noise, quantisation, timing.
    noise_sigma0_m: float = .003
    noise_rel: float = .01
    quantum_m: float = .001
    period_s: float = .06
    dropout_prob: float = .02
    outlier_prob: float = .01
    # Two-robot interference (off by default, see PROVENANCE['crosstalk']).
    crosstalk: bool = False
    sound_speed_mps: float = 343.

    def sigma_m(self, range_m: float) -> float:
        return self.noise_sigma0_m + self.noise_rel * max(0., float(range_m))


DEFAULT_SPEC = UltrasonicSpec()

PROVENANCE = {
    'min_range_m': 'official: Hiwonder glowing ultrasonic listing, detection distance 2-400 cm',
    'max_range_m': 'official: same listing (400 cm)',
    'sdk_clamp_m': 'sdk: Sonar.getDistance() clamps values > 5000 mm to 5000',
    'quantum_m': 'sdk: Sonar.getDistance() returns integer millimetres',
    'half_angle_deg': ('official: "measurement angle 15 degrees"; whether it is a half or full angle is '
                       'not stated -> assumption: half-angle, directivity 0.5 at the edge'),
    'mount_x_m': 'photo_nominal: sim.masterpi_geometry.NOMINAL_ULTRASONIC_X_M (not measured)',
    'mount_y_m': 'photo_nominal: midpoint of the two transducers (+-17 mm)',
    'mount_z_floor_m': 'photo_nominal: sim/masterpi_dynamics_v2.py ultrasonic geoms at 0.054 m (not measured)',
    'mount_pitch_deg': 'assumption: horizontal (unmeasured)',
    'noise_sigma0_m': 'assumption: HC-SR04 datasheet ranging accuracy 3 mm',
    'noise_rel': 'assumption: 1 % of range (speed of sound, temperature); unmeasured for this module',
    'period_s': 'assumption: HC-SR04 datasheet recommends a measurement cycle over 60 ms',
    'incidence_sigma_deg': 'assumption: specular surfaces; bench calibration planned',
    'echo_threshold': 'assumption: detection threshold on directivity x incidence amplitude',
    'dropout_prob': 'assumption: missed echo rate',
    'outlier_prob': ('assumption: spurious reading rate; the MasterPi avoidance demo averages 5 readings '
                     'with outlier rejection, implying spurious values exist'),
    'crosstalk': ('assumption: OFF by default. Interference between two 40 kHz modules depends on the '
                  'module firmware trigger timing and receive filtering, which are unpublished; enabling '
                  'an unmeasured effect would silently change every run. ON is a robustness option.'),
    'sound_speed_mps': 'physics: 343 m/s at 20 C',
}

SOURCES = {
    'hiwonder_glowing_ultrasonic': 'https://www.hiwonder.com/products/glowing-ultrasonic-sensor',
    'hiwonder_glowy_rgb_ultrasonic': 'https://www.hiwonder.com/products/glowy-rgb-ultrasonic-sensor',
    'hiwonder_sdk_sonar_tonypi': 'https://github.com/Hiwonder/TonyPi/blob/main/HiwonderSDK/hiwonder/Sonar.py',
    'masterpi_sdk_sonar_mirror': 'https://github.com/SquirrelRobotics/MasterPi/blob/main/HiwonderSDK/Sonar.py',
    'masterpi_avoidance_mirror': 'https://github.com/SquirrelRobotics/MasterPi/blob/main/Functions/Avoidance.py',
    'hc_sr04_datasheet': 'https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf',
}


def spec_record(spec: UltrasonicSpec = DEFAULT_SPEC) -> dict:
    value = {'sensor_model_id': SENSOR_MODEL_ID, 'spec': asdict(spec)}
    value['sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return value


@dataclass(frozen=True)
class RangeReading:
    """What the robot's own sensor reports. Nothing else leaves the model."""
    t: float
    range_m: float
    valid: bool

    def as_dict(self) -> dict:
        return {'t': round(float(self.t), 6),
                'range_m': round(float(self.range_m), 4) if self.valid else None,
                'valid': bool(self.valid)}


def ray_pattern(spec: UltrasonicSpec = DEFAULT_SPEC) -> tuple[np.ndarray, np.ndarray]:
    """Unit directions in the sensor frame (x forward, y left, z up) and their off-axis angles.

    Centre ray plus rings every ``ring_step_deg`` up to the half-angle. Ring k
    has ``ring_base_count * k`` rays starting at azimuth 90 deg (straight up), so
    straight up/down/left/right rays are always present.
    """
    dirs, alphas = [[1., 0., 0.]], [0.]
    rings = int(round(spec.half_angle_deg / spec.ring_step_deg))
    for k in range(1, rings + 1):
        a = math.radians(min(spec.half_angle_deg, k * spec.ring_step_deg))
        n = spec.ring_base_count * k
        for j in range(n):
            phi = math.pi / 2 + 2 * math.pi * j / n
            dirs.append([math.cos(a), math.sin(a) * math.cos(phi), math.sin(a) * math.sin(phi)])
            alphas.append(a)
    return np.asarray(dirs, float), np.asarray(alphas, float)


def directivity(alpha_rad, spec: UltrasonicSpec = DEFAULT_SPEC):
    """Round-trip beam gain, 1 on axis, ``directivity_edge_gain`` at the cone edge."""
    edge = math.radians(spec.half_angle_deg)
    k = -math.log(spec.directivity_edge_gain) / (edge * edge)
    alpha = np.asarray(alpha_rad, float)
    return np.where(alpha <= edge + 1e-9, np.exp(-k * alpha * alpha), 0.)


def incidence_gain(beta_rad, spec: UltrasonicSpec = DEFAULT_SPEC):
    s = math.radians(spec.incidence_sigma_deg)
    beta = np.asarray(beta_rad, float)
    return np.exp(-.5 * (beta / s) ** 2)


def incidence_angle(direction: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Angle between the reversed ray and the surface normal (0 = head-on), per ray."""
    d = np.asarray(direction, float).reshape(-1, 3)
    n = np.asarray(normal, float).reshape(-1, 3)
    norm = np.linalg.norm(n, axis=1)
    cos = np.abs(np.einsum('ij,ij->i', -d, n)) / np.where(norm > 0, norm, 1.)
    return np.where(norm > 0, np.arccos(np.clip(cos, 0., 1.)), math.pi / 2)


def first_echo(distance, alpha, beta, spec: UltrasonicSpec = DEFAULT_SPEC):
    """Noise-free first-echo range from per-ray hits, or ``None`` (no echo in range).

    ``distance`` < 0 or non-finite means the ray hit nothing. A ray contributes
    when directivity x incidence gain reaches ``echo_threshold``; the sensor
    reports the nearest contributing ray (time of the first echo).
    """
    i = first_echo_index(distance, alpha, beta, spec)
    return None if i is None else float(np.asarray(distance, float)[i])


def first_echo_index(distance, alpha, beta, spec: UltrasonicSpec = DEFAULT_SPEC) -> int | None:
    """Index of the ray that sets ``first_echo`` (``None`` when no ray contributes)."""
    d = np.asarray(distance, float)
    amp = directivity(alpha, spec) * incidence_gain(beta, spec)
    ok = np.isfinite(d) & (d >= 0.) & (d <= spec.max_range_m) & (amp >= spec.echo_threshold)
    if not ok.any():
        return None
    return int(np.flatnonzero(ok)[np.argmin(d[ok])])


def reading_rng(seed: int, robot_id: str, seq: int) -> np.random.Generator:
    """Independent stream per reading: order of calls elsewhere cannot change it."""
    return np.random.default_rng([int(seed) & 0xFFFFFFFF, zlib.crc32(robot_id.encode()), int(seq)])


def noisy_reading(t: float, true_range_m, rng: np.random.Generator,
                  spec: UltrasonicSpec = DEFAULT_SPEC) -> RangeReading:
    """Apply dropout, spurious values, Gaussian range noise, blind zone and quantisation.

    ``true_range_m`` is the noise-free first echo (``None`` when there is none).
    Draws are made in a fixed order so a given (seed, robot, seq) is repeatable.
    """
    u_drop, u_out, u_val, z = rng.random(), rng.random(), rng.random(), rng.standard_normal()
    if true_range_m is not None and u_drop < spec.dropout_prob:
        return RangeReading(t, float('nan'), False)
    if u_out < spec.outlier_prob:
        r = spec.min_range_m + u_val * (spec.max_range_m - spec.min_range_m)
    elif true_range_m is None:
        return RangeReading(t, float('nan'), False)
    else:
        r = float(true_range_m) + spec.sigma_m(true_range_m) * z
    if r < spec.min_range_m or r > spec.max_range_m:
        return RangeReading(t, float('nan'), False)
    r = round(r / spec.quantum_m) * spec.quantum_m
    return RangeReading(t, min(r, spec.sdk_clamp_m), True)


def sensor_pose(x: float, y: float, yaw: float, spec: UltrasonicSpec = DEFAULT_SPEC):
    """World origin (x, y, z) and unit axis of the sensor for a floor-level base pose."""
    c, s = math.cos(yaw), math.sin(yaw)
    p = math.radians(spec.mount_pitch_deg)
    origin = np.array([x + c * spec.mount_x_m - s * spec.mount_y_m,
                       y + s * spec.mount_x_m + c * spec.mount_y_m, spec.mount_z_floor_m])
    axis = np.array([c * math.cos(p), s * math.cos(p), math.sin(p)])
    return origin, axis


def sensor_rotation(yaw: float, spec: UltrasonicSpec = DEFAULT_SPEC) -> np.ndarray:
    """Sensor-to-world rotation for a level base (columns: forward, left, up)."""
    c, s = math.cos(yaw), math.sin(yaw)
    p = math.radians(spec.mount_pitch_deg)
    cp, sp = math.cos(p), math.sin(p)
    base = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    pitch = np.array([[cp, 0., -sp], [0., 1., 0.], [sp, 0., cp]])
    return base @ pitch


def crosstalk_range(direct_m: float, phase_offset_s: float, spec: UltrasonicSpec = DEFAULT_SPEC):
    """Apparent range of a peer's pulse arriving ``direct_m`` away, fired ``phase_offset_s`` after us.

    The receiver cannot tell the peer's pulse from its own echo, so it reports
    half the arrival time times the speed of sound. ``None`` when the pulse
    arrives before our trigger or after our listening window.
    """
    arrival = phase_offset_s + direct_m / spec.sound_speed_mps
    if arrival <= 0. or arrival > 2. * spec.max_range_m / spec.sound_speed_mps:
        return None
    return .5 * spec.sound_speed_mps * arrival
