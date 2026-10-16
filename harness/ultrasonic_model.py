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

A reading carries only ``t``, ``range_m``, ``valid`` and a ``status`` the real
SDK can also produce (never a geom, body, hit point or any other simulator
state). Status mapping (Hiwonder SDK ``Sonar.getDistance()``, ROS REP 117):

* ``ok``: an echo inside [min, max] (``valid=True``);
* ``blind``: something closer than ``min_range_m`` (SDK small integer, REP 117 -Inf);
* ``no_echo``: nothing within ``max_range_m`` (SDK >= 4000/5000 clamp, REP 117 +Inf).
  A missed echo (dropout) looks exactly like this on the real sensor, so the
  SIM reports it as ``no_echo`` too; the cause ``dropout`` is only in the
  evaluation diagnostic;
* ``sensor_absent``: I2C read failure (SDK 99999, REP 117 NaN); never produced
  by the SIM model, only by the real-SDK adapter (``harness.range_provider``).

Noise is indexed by the reading TICK ``round(t / period_s)`` and a seed derived
from the episode seed and robot (``sensor_seed``), never from the condition or
the call count, so the four conditions draw matched noise at matched times.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

import numpy as np

SENSOR_MODEL_ID = 'masterpi_ultrasonic_v2'
READING_SCHEMA = 'ugrp.own_ultrasonic_reading.v2'

OK, BLIND, NO_ECHO, SENSOR_ABSENT = 'ok', 'blind', 'no_echo', 'sensor_absent'
STATUSES = (OK, BLIND, NO_ECHO, SENSOR_ABSENT)
DROPOUT = 'dropout'          # diagnostic cause only (reported to the robot as no_echo)


@dataclass(frozen=True)
class UltrasonicSpec:
    # Mount in the chassis frame (x forward, y left); height is from the floor.
    # ``mount_x_m`` is the transducer (bracket) centre; ranges are measured from
    # the transducer FACE ``face_forward_m`` ahead of it (``face_x_m``).
    mount_x_m: float = .078
    mount_y_m: float = 0.
    mount_z_floor_m: float = .054
    mount_pitch_deg: float = 0.
    face_forward_m: float = .006
    # Ranging limits.
    min_range_m: float = .02
    max_range_m: float = 4.00
    sdk_clamp_m: float = 5.00
    # Cone: 15 deg is the published "measuring angle"; used as the half-angle
    # of the sampled cone, with ROUND-TRIP directivity 0.5 at the cone edge
    # (``directivity`` is applied once to the echo amplitude).
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
    # Phase model: free-running modules whose clocks differ by up to
    # ``crosstalk_clock_tol`` -> the relative trigger phase drifts slowly
    # (bursts of consecutive corrupted readings), plus per-reading jitter.
    crosstalk: bool = False
    crosstalk_clock_tol: float = .005
    crosstalk_jitter_s: float = 2e-5
    sound_speed_mps: float = 343.

    def sigma_m(self, range_m: float) -> float:
        return self.noise_sigma0_m + self.noise_rel * max(0., float(range_m))

    @property
    def face_x_m(self) -> float:
        return self.mount_x_m + self.face_forward_m


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
    'face_forward_m': ('photo_nominal: SIM transducer cylinders (half-length 6 mm) put the face 6 mm ahead of '
                       'the bracket centre; ranges are measured from the face (not measured on hardware)'),
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
                  'an unmeasured effect would silently change every run. Evaluations of facing robots '
                  '(pair carry) must turn it ON (harness.ultrasonic_carry.FACING_PAIR_SPEC).'),
    'crosstalk_clock_tol': ('assumption: +-0.5 % relative trigger-period mismatch between free-running '
                            'modules (typical RC/ceramic oscillator tolerance), drawn per robot pair'),
    'crosstalk_jitter_s': 'assumption: 20 us trigger jitter per reading',
    'sound_speed_mps': 'physics: 343 m/s at 20 C',
}

SOURCES = {
    'hiwonder_glowing_ultrasonic': 'https://www.hiwonder.com/products/glowing-ultrasonic-sensor',
    'hiwonder_glowy_rgb_ultrasonic': 'https://www.hiwonder.com/products/glowy-rgb-ultrasonic-sensor',
    'hiwonder_sdk_sonar_tonypi': 'https://github.com/Hiwonder/TonyPi/blob/main/HiwonderSDK/hiwonder/Sonar.py',
    'masterpi_sdk_sonar_mirror': 'https://github.com/SquirrelRobotics/MasterPi/blob/main/HiwonderSDK/Sonar.py',
    'masterpi_avoidance_mirror': ('https://github.com/SquirrelRobotics/MasterPi/blob/main/Functions/Avoidance.py '
                                  '(unofficial mirror, not verified against Hiwonder)'),
    'ros_rep_117': 'https://ros.org/reps/rep-0117.html',
    'thrun_beam_model': 'Thrun, Burgard, Fox, Probabilistic Robotics (2005), 6.3 beam models of range finders',
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
    status: str = OK

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f'unknown reading status {self.status!r}')
        if self.valid != (self.status == OK):
            raise ValueError('valid must be True exactly when status is ok')

    def as_dict(self) -> dict:
        return {'t': round(float(self.t), 6),
                'range_m': round(float(self.range_m), 4) if self.valid else None,
                'valid': bool(self.valid), 'status': self.status}


def invalid(t: float, status: str) -> RangeReading:
    return RangeReading(t, float('nan'), False, status)


def sensor_seed(episode_seed: int, robot_id: str) -> int:
    """Noise seed of one robot's sensor: episode seed and robot only (never the condition)."""
    digest = hashlib.sha256(f'{int(episode_seed)}:own_ultrasonic:{robot_id}'.encode()).digest()
    return int.from_bytes(digest[:8], 'big')


def reading_tick(t: float, spec: 'UltrasonicSpec') -> int:
    return int(round(float(t) / spec.period_s))


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


NOISE_STREAM, CROSSTALK_STREAM = 0, 1


def reading_rng(seed: int, robot_id: str, tick: int, stream: int = NOISE_STREAM) -> np.random.Generator:
    """Independent stream per (seed, robot, tick, stream): call order elsewhere cannot change it.

    The full seed is used (no truncation); ``stream`` separates the reading noise
    from the crosstalk draws so enabling crosstalk never shifts the noise.
    """
    rid = int.from_bytes(hashlib.sha256(robot_id.encode()).digest()[:8], 'big')
    return np.random.default_rng(np.random.SeedSequence([int(seed), rid, int(tick), int(stream)]))


def noisy_reading_with_cause(t: float, true_range_m, rng: np.random.Generator,
                             spec: UltrasonicSpec = DEFAULT_SPEC) -> tuple[RangeReading, str]:
    """Reading plus its cause (``ok``/``blind``/``no_echo``/``dropout``/``outlier``; cause is diagnostic only)."""
    u_drop, u_out, u_val, z = rng.random(), rng.random(), rng.random(), rng.standard_normal()
    if true_range_m is not None and u_drop < spec.dropout_prob:
        return invalid(t, NO_ECHO), DROPOUT
    cause = OK
    if u_out < spec.outlier_prob:
        r, cause = spec.min_range_m + u_val * (spec.max_range_m - spec.min_range_m), 'outlier'
    elif true_range_m is None:
        return invalid(t, NO_ECHO), NO_ECHO
    else:
        r = float(true_range_m) + spec.sigma_m(true_range_m) * z
    if r < spec.min_range_m:
        return invalid(t, BLIND), BLIND
    if r > spec.max_range_m:
        return invalid(t, NO_ECHO), NO_ECHO
    r = round(r / spec.quantum_m) * spec.quantum_m
    return RangeReading(t, min(r, spec.sdk_clamp_m), True), cause


def noisy_reading(t: float, true_range_m, rng: np.random.Generator,
                  spec: UltrasonicSpec = DEFAULT_SPEC) -> RangeReading:
    """Apply dropout, spurious values, Gaussian range noise, blind zone and quantisation.

    ``true_range_m`` is the noise-free first echo (``None`` when there is none).
    Draws are made in a fixed order so a given (seed, robot, tick) is repeatable.
    """
    return noisy_reading_with_cause(t, true_range_m, rng, spec)[0]


def sensor_pose(x: float, y: float, yaw: float, spec: UltrasonicSpec = DEFAULT_SPEC):
    """World origin (transducer face centre) and unit axis of the sensor for a floor-level base pose."""
    c, s = math.cos(yaw), math.sin(yaw)
    p = math.radians(spec.mount_pitch_deg)
    fx = spec.face_x_m
    origin = np.array([x + c * fx - s * spec.mount_y_m,
                       y + s * fx + c * spec.mount_y_m, spec.mount_z_floor_m])
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


def crosstalk_phase(seed: int, pair: tuple[str, str], tick: int, spec: UltrasonicSpec = DEFAULT_SPEC) -> float:
    """Relative trigger phase (s) of ``pair[1]``'s pulse after ``pair[0]``'s trigger at reading ``tick``.

    Phase-correlated: a per-pair initial phase and clock mismatch (drawn once
    from the pair stream) make the phase drift slowly, so a crosstalk window is
    crossed in a burst of consecutive readings; small per-tick jitter on top.
    """
    a, b = sorted(pair)
    base = reading_rng(seed, f'{a}|{b}', 0, CROSSTALK_STREAM)
    phi0 = base.random() * spec.period_s
    drift = (base.random() * 2. - 1.) * spec.crosstalk_clock_tol * spec.period_s
    jitter = reading_rng(seed, f'{a}|{b}', tick, CROSSTALK_STREAM).standard_normal() * spec.crosstalk_jitter_s
    phase = (phi0 + drift * tick + jitter) % spec.period_s
    if pair[0] != a:
        phase = (-phase) % spec.period_s
    return phase - spec.period_s if phase > spec.period_s / 2 else phase
