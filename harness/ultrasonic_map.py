"""Expected ultrasonic range against the STATIC map, and a range measurement model.

Controller-side and simulator-free: inputs are the robot's own pose hypothesis
(x, y, yaw), the pre-built static map (walls, door posts, floor) and the fixed
sensor specification. Live objects (peer robots, cargo) are not in the static
map, so a reading SHORTER than the map prediction is weak evidence (an unmapped
object may be in front). A reading LONGER than the prediction, or no echo where
the map predicts one, is also only moderate evidence against the pose:
specular reflection and multipath produce long readings, unmapped surfaces met
at grazing incidence can shadow a mapped wall, and the map itself has
placement error (review of PR #248, P2-1).

``range_log_likelihood`` is the standard beam-model mixture (Thrun, Burgard,
Fox, *Probabilistic Robotics* 6.3: hit / short / max / rand) plus a specular
(long) term, with a map-error sigma in the hit width, a SMOOTH detection
probability instead of a hard incidence threshold, and a per-reading cap on
the log-likelihood ratio (uncalibrated until the bench step in the doc).
Weights are hypotheses, not fitted values.

The same ``ray_pattern`` / ``first_echo`` as the SIM sensor are used, so the
prediction differs from the SIM reading only by what the static map omits and
by the reading noise.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from harness.ultrasonic_model import (DEFAULT_SPEC, UltrasonicSpec, directivity, first_echo, incidence_angle,
                                      incidence_gain, ray_pattern, sensor_pose, sensor_rotation)

MAP_SIGMA_M = .02          # assumption: static map placement error (walls, posts), per reading
DETECT_WIDTH = .05         # assumption: soft width of the echo threshold in amplitude units


@dataclass(frozen=True)
class ExpectedRange:
    range_m: float | None          # noise-free first echo (hard threshold, = the SIM sensor), None = none
    sigma_m: float | None          # reading noise at that range
    p_detect: float | None = None  # smooth detection probability of the strongest mapped echo
    weak_range_m: float | None = None   # range of the strongest mapped echo even when below threshold

    @property
    def echo(self) -> bool:
        return self.range_m is not None

    def detection(self, spec: UltrasonicSpec = DEFAULT_SPEC) -> tuple[float, float | None]:
        """(p_detect, range used for the hit term); falls back to the hard prediction."""
        if self.p_detect is not None:
            return self.p_detect, self.range_m if self.range_m is not None else self.weak_range_m
        return (1. if self.echo else 0.), self.range_m


def detection_probability(amplitude: float, spec: UltrasonicSpec = DEFAULT_SPEC, width: float = DETECT_WIDTH) -> float:
    """Logistic detection probability around ``echo_threshold`` (no knife-edge at the visibility boundary)."""
    return 1. / (1. + math.exp(-(float(amplitude) - spec.echo_threshold) / width))


def static_boxes(static_map: Mapping) -> list[dict]:
    """Static echo surfaces: map obstacles and landmark door posts (floor handled separately)."""
    boxes = []
    for item in list(static_map.get('obstacles', ())) + list((static_map.get('landmarks') or {}).get('door_posts', ())):
        (cx, cy), (hx, hy) = item['center_m'], item['half_extents_m']
        boxes.append({'id': item['id'], 'center': (float(cx), float(cy)), 'half': (float(hx), float(hy)),
                      'height': float(item['height_m']), 'yaw': float(item.get('yaw_rad') or 0.)})
    return boxes


def _ray_box(origin: np.ndarray, dirs: np.ndarray, box: Mapping) -> tuple[np.ndarray, np.ndarray]:
    """Slab test for many rays against one yawed box on the floor. Returns (t, world normal)."""
    c, s = math.cos(box['yaw']), math.sin(box['yaw'])
    rot = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    h = box['height'] / 2.
    centre = np.array([box['center'][0], box['center'][1], h])
    half = np.array([box['half'][0], box['half'][1], h])
    o = (origin - centre) @ rot                  # world -> box frame (rot is orthonormal)
    d = dirs @ rot
    with np.errstate(divide='ignore', invalid='ignore'):
        inv = 1. / d
        t1, t2 = (-half - o) * inv, (half - o) * inv
    tmin, tmax = np.minimum(t1, t2), np.maximum(t1, t2)
    # Rays parallel to a slab: inside -> unbounded, outside -> miss.
    parallel = np.abs(d) < 1e-12
    inside = np.abs(o) <= half
    tmin = np.where(parallel, np.where(inside, -np.inf, np.inf), tmin)
    tmax = np.where(parallel, np.where(inside, np.inf, -np.inf), tmax)
    near, far = tmin.max(axis=1), tmax.min(axis=1)
    axis = tmin.argmax(axis=1)
    hit = (near <= far) & (near > 1e-9)
    t = np.where(hit, near, -1.)
    local_n = np.zeros_like(d)
    rows = np.arange(len(d))
    local_n[rows, axis] = -np.sign(d[rows, axis])
    return t, local_n @ rot.T


def expected_range(static_map: Mapping, pose_xyyaw: Sequence[float], spec: UltrasonicSpec = DEFAULT_SPEC,
                   *, boxes: list[dict] | None = None) -> ExpectedRange:
    """Noise-free reading the own sensor would give at ``pose`` if only the static map existed."""
    x, y, yaw = (float(v) for v in pose_xyyaw)
    origin, _ = sensor_pose(x, y, yaw, spec)
    local, alpha = ray_pattern(spec)
    dirs = local @ sensor_rotation(yaw, spec).T
    best = np.full(len(dirs), np.inf)
    normal = np.zeros_like(dirs)
    # Floor plane z = 0 terminates downward rays (grazing incidence -> weak echo).
    down = dirs[:, 2] < -1e-12
    t_floor = np.where(down, -origin[2] / np.where(down, dirs[:, 2], 1.), np.inf)
    best = np.where(down, t_floor, best)
    normal[down] = (0., 0., 1.)
    for box in (static_boxes(static_map) if boxes is None else boxes):
        t, n = _ray_box(origin, dirs, box)
        closer = (t > 0) & (t < best)
        best = np.where(closer, t, best)
        normal[closer] = n[closer]
    dist = np.where(np.isfinite(best), best, -1.)
    beta = incidence_angle(dirs, normal)
    r = first_echo(dist, alpha, beta, spec)
    amp = directivity(alpha, spec) * incidence_gain(beta, spec)
    ok = (dist >= 0.) & (dist <= spec.max_range_m)
    if ok.any():
        k = int(np.flatnonzero(ok)[np.argmax(amp[ok])])
        p_det, weak = detection_probability(float(amp[k]), spec), float(dist[k])
    else:
        p_det, weak = 0., None
    if r is not None:
        p_det = max(p_det, .5)          # a hard-threshold echo is at least an even bet
    return ExpectedRange(r, None if r is None else spec.sigma_m(r), p_det, weak)


# --- measurement model -------------------------------------------------------------------------

CONSISTENT = 'consistent'
SHORTER = 'shorter_than_map'            # unmapped object in front: not evidence against the pose
LONGER = 'longer_than_map'              # moderate evidence against the pose (specular/multipath/map error possible)
MISSING_ECHO = 'no_echo_where_map_predicts'
AMBIGUOUS_NO_ECHO = 'no_echo_near_visibility_edge'   # map echo exists but detection is uncertain
UNEXPECTED_ECHO = 'echo_where_map_predicts_none'
BOTH_NONE = 'no_echo_consistent'
BLIND_READING = 'blind_zone'            # something closer than min range: never "consistent"
NO_SENSOR = 'sensor_absent'


def _total_sigma(r: float, spec: UltrasonicSpec, pose_sigma_m: float, map_sigma_m: float) -> float:
    return math.sqrt(spec.sigma_m(r) ** 2 + pose_sigma_m ** 2 + map_sigma_m ** 2)


def range_consistency(range_m: float | None, valid: bool, expected: ExpectedRange,
                      spec: UltrasonicSpec = DEFAULT_SPEC, *, k_sigma: float = 3.,
                      pose_sigma_m: float = 0., map_sigma_m: float = MAP_SIGMA_M, status: str | None = None,
                      p_certain: float = .9) -> str:
    """Classify one reading against the static-map prediction.

    ``pose_sigma_m`` widens the band by the pose uncertainty projected on the
    beam axis (a caller-supplied scalar, e.g. the PF's std along the heading);
    ``map_sigma_m`` by the map placement error. ``status`` (reading status)
    separates the blind zone and a missing sensor from a real no-echo.
    """
    if status == 'blind':
        return BLIND_READING
    if status == 'sensor_absent':
        return NO_SENSOR
    p_det, r_exp = expected.detection(spec)
    if not valid:
        if r_exp is None or p_det < 1. - p_certain:
            return BOTH_NONE
        return MISSING_ECHO if p_det >= p_certain else AMBIGUOUS_NO_ECHO
    if r_exp is None or not expected.echo:
        return UNEXPECTED_ECHO if r_exp is None or abs(range_m - r_exp) > k_sigma * _total_sigma(
            r_exp, spec, pose_sigma_m, map_sigma_m) else CONSISTENT
    band = k_sigma * _total_sigma(r_exp, spec, pose_sigma_m, map_sigma_m)
    if range_m > r_exp + band:
        return LONGER
    if range_m < r_exp - band:
        return SHORTER
    return CONSISTENT


@dataclass(frozen=True)
class BeamWeights:
    """Mixture weights of the detected branch (sum 1) and the undetected branch (short/rand, rest = no echo)."""
    hit: float = .70
    short: float = .12
    specular: float = .08          # long reading: specular / multipath / map error beyond the wall
    rand: float = .03
    max: float = .07               # no echo although the map echo is detectable (dropout, absorption)
    short_rate_per_m: float = 1.5


def range_log_likelihood(range_m: float | None, valid: bool, expected: ExpectedRange,
                         spec: UltrasonicSpec = DEFAULT_SPEC, *, weights: BeamWeights = BeamWeights(),
                         pose_sigma_m: float = 0., map_sigma_m: float = MAP_SIGMA_M,
                         max_abs_llr_nats: float | None = 2., status: str | None = None) -> float:
    """Beam-model log likelihood with soft detection, bounded to +-``max_abs_llr_nats`` around a flat reference.

    ``p(z) = p_det * [hit N(z; r, s) + short Exp + specular U(r, max) + rand U + max 1{no echo}]
           + (1 - p_det) * [short Exp + rand U + (1 - short - rand) 1{no echo}]``
    with ``s^2 = sensor^2 + pose^2 + map^2``. Blind-zone and sensor-absent
    readings carry no pose information (return the reference, 0 LLR).
    """
    w = weights
    span = spec.max_range_m - spec.min_range_m
    ref_valid, ref_invalid = math.log(1. / span), math.log(.5)
    if status in ('blind', 'sensor_absent'):
        return ref_invalid
    p_det, r_exp = expected.detection(spec)
    lam = w.short_rate_per_m
    if not valid:
        p = p_det * w.max + (1. - p_det) * (1. - w.short - w.rand)
        ll, ref = math.log(max(p, 1e-9)), ref_invalid
    else:
        z = float(range_m)
        e_all = lam * math.exp(-lam * z) / (1. - math.exp(-lam * spec.max_range_m))
        undetected = w.short * e_all + w.rand / span
        detected = 0.
        if r_exp is not None:
            s = _total_sigma(r_exp, spec, pose_sigma_m, map_sigma_m)
            hit = w.hit * math.exp(-.5 * ((z - r_exp) / s) ** 2) / (s * math.sqrt(2 * math.pi))
            short = (w.short * lam * math.exp(-lam * z) / max(1. - math.exp(-lam * r_exp), 1e-9)) if z < r_exp else 0.
            spec_long = w.specular / max(spec.max_range_m - r_exp, 1e-3) if z > r_exp else 0.
            detected = hit + short + spec_long + w.rand / span
        ll, ref = math.log(max(p_det * detected + (1. - p_det) * undetected, 1e-12)), ref_valid
    if max_abs_llr_nats is not None:
        ll = min(max(ll, ref - max_abs_llr_nats), ref + max_abs_llr_nats)
    return ll
