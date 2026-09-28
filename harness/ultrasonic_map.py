"""Expected ultrasonic range against the STATIC map, and a range measurement model.

Controller-side and simulator-free: inputs are the robot's own pose hypothesis
(x, y, yaw), the pre-built static map (walls, door posts, floor) and the fixed
sensor specification. Live objects (peer robots, cargo) are not in the static
map, so a reading SHORTER than the map prediction is weak evidence (an unmapped
object may be in front), while a reading clearly LONGER than the prediction, or
no echo where the map predicts a wall well inside the range, is evidence
against the pose. ``range_consistency`` and ``range_log_likelihood`` encode
exactly that asymmetry for PF measurement models and overconfidence checks.

The same ``ray_pattern`` / ``first_echo`` as the SIM sensor are used, so the
prediction differs from the SIM reading only by what the static map omits and
by the reading noise.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from harness.ultrasonic_model import (DEFAULT_SPEC, UltrasonicSpec, first_echo, incidence_angle,
                                      ray_pattern, sensor_pose, sensor_rotation)


@dataclass(frozen=True)
class ExpectedRange:
    range_m: float | None          # noise-free first echo, None = no echo expected
    sigma_m: float | None          # reading noise at that range

    @property
    def echo(self) -> bool:
        return self.range_m is not None


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
    r = first_echo(dist, alpha, incidence_angle(dirs, normal), spec)
    return ExpectedRange(r, None if r is None else spec.sigma_m(r))


# --- measurement model -------------------------------------------------------------------------

CONSISTENT = 'consistent'
SHORTER = 'shorter_than_map'            # unmapped object in front: not evidence against the pose
LONGER = 'longer_than_map'              # map wall should have echoed first: evidence against the pose
MISSING_ECHO = 'no_echo_where_map_predicts'
UNEXPECTED_ECHO = 'echo_where_map_predicts_none'
BOTH_NONE = 'no_echo_consistent'


def range_consistency(range_m: float | None, valid: bool, expected: ExpectedRange,
                      spec: UltrasonicSpec = DEFAULT_SPEC, *, k_sigma: float = 3.,
                      pose_sigma_m: float = 0.) -> str:
    """Classify one reading against the static-map prediction.

    ``pose_sigma_m`` widens the band by the pose uncertainty projected on the
    beam axis (a caller-supplied scalar, e.g. the PF's std along the heading).
    """
    if not valid:
        return MISSING_ECHO if expected.echo else BOTH_NONE
    if not expected.echo:
        return UNEXPECTED_ECHO
    band = k_sigma * math.hypot(spec.sigma_m(expected.range_m), pose_sigma_m)
    if range_m > expected.range_m + band:
        return LONGER
    if range_m < expected.range_m - band:
        return SHORTER
    return CONSISTENT


def range_log_likelihood(range_m: float | None, valid: bool, expected: ExpectedRange,
                         spec: UltrasonicSpec = DEFAULT_SPEC, *, w_hit: float = .80, w_short: float = .15,
                         short_rate_per_m: float = 1.5, pose_sigma_m: float = 0.) -> float:
    """Beam-model log likelihood (hit + unmapped-short + uniform spurious), bounded below.

    Invalid readings: likely when no echo is predicted, ``dropout_prob`` when an
    echo is predicted. Weights are starting values for the v6 integration, not
    fitted parameters.
    """
    span = spec.max_range_m - spec.min_range_m
    w_rand = max(spec.outlier_prob, 1e-3)
    if not valid:
        p = (1. - w_rand) if not expected.echo else max(spec.dropout_prob, 1e-3)
        return math.log(p)
    if not expected.echo:
        # Unmapped object (short) or spurious; no hit term.
        return math.log(w_short * short_rate_per_m * math.exp(-short_rate_per_m * range_m) + w_rand / span)
    sigma = math.hypot(spec.sigma_m(expected.range_m), pose_sigma_m)
    hit = w_hit * math.exp(-.5 * ((range_m - expected.range_m) / sigma) ** 2) / (sigma * math.sqrt(2 * math.pi))
    short = 0.
    if range_m < expected.range_m:
        norm = 1. - math.exp(-short_rate_per_m * expected.range_m)
        short = w_short * short_rate_per_m * math.exp(-short_rate_per_m * range_m) / max(norm, 1e-9)
    return math.log(hit + short + w_rand / span)
