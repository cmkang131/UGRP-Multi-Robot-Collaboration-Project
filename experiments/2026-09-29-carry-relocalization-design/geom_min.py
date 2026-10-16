"""Map-only view geometry for the carry-relocalization design memo (no simulator, no images, no models).

Adapted from experiments/2026-09-29-relocalization-audit/geom.py (PR #276; not yet on main): ray-cast a wrist camera
(issued servo pulses + a robot pose + the static map) against the map's wall/post boxes and the floor plane.
The only change: the map is a parameter, so the same rays can be cast against a 0.10 m wall map (walls_v1, the dev tag map
used by the audit) and a 0.40 m wall map (walls_v3, the final-environment wall height). Audit label only; not a controller input.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.owncam_view import HEIGHT, WIDTH, base_rays, valid_pixel_mask  # noqa: E402
from harness.zone_own_guards import static_boxes  # noqa: E402

FLOOR, WALL, POST, BEYOND = 0, 1, 2, 4


def load_map(map_id):
    return json.loads((ROOT / 'maps' / 'zones' / f'{map_id}.json').read_text())


def with_wall_height(static, height_m):
    """Copy of a static map with every kind=wall obstacle at height_m (footprints unchanged); door posts untouched."""
    out = json.loads(json.dumps(static))
    for o in out['obstacles']:
        if o.get('kind') == 'wall':
            o['height_m'] = float(height_m)
    return out


def _hit_box(o, d, box):
    cx, cy = box['center']
    hx, hy = box['half']
    c, s = math.cos(box['yaw']), math.sin(box['yaw'])
    ox, oy = o[0] - cx, o[1] - cy
    lo = np.array([c * ox + s * oy, -s * ox + c * oy, o[2]])
    ld = np.stack([c * d[:, 0] + s * d[:, 1], -s * d[:, 0] + c * d[:, 1], d[:, 2]], axis=1)
    mn = np.array([-hx, -hy, 0.])
    mx = np.array([hx, hy, box['height']])
    with np.errstate(divide='ignore', invalid='ignore'):
        t1 = (mn - lo) / ld
        t2 = (mx - lo) / ld
    par = np.abs(ld) < 1e-12
    inside = ((lo >= mn) & (lo <= mx))
    t_near = np.where(par, np.where(inside, -np.inf, np.inf), np.minimum(t1, t2))
    t_far = np.where(par, np.where(inside, np.inf, -np.inf), np.maximum(t1, t2))
    tn = t_near.max(axis=1)
    tf = t_far.min(axis=1)
    ok = (tn <= tf) & (tf > 1e-6)
    return np.where(ok, np.maximum(tn, 1e-6), np.inf)


def predict_labels(static, servo, robot_xyyaw, step=4):
    """Per-pixel class (FLOOR/WALL/POST/BEYOND) on a step grid, plus the valid (non-rim) mask. Occlusion by beam/arm ignored."""
    origin, rays, xs, ys, valid = base_rays({int(k): int(v) for k, v in servo.items()}, step)
    x, y, yaw = robot_xyyaw
    c, s = math.cos(yaw), math.sin(yaw)
    rot = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    o = rot @ np.asarray(origin, float) + np.array([x, y, 0.])
    d = rays @ rot.T
    t_floor = np.full(len(d), np.inf)
    down = d[:, 2] < -1e-9
    t_floor[down] = -o[2] / d[down, 2]
    best = t_floor.copy()
    cls = np.where(np.isfinite(t_floor), FLOOR, BEYOND)
    for box in static_boxes(static):
        t = _hit_box(o, d, box)
        hit = t < best
        cls = np.where(hit, POST if box['id'].startswith('post_') else WALL, cls)
        best = np.where(hit, t, best)
    h = len(range(step // 2, HEIGHT, step))
    w = len(range(step // 2, WIDTH, step))
    return cls.reshape(h, w), valid.reshape(h, w), best.reshape(h, w)


def structure_share(static, servo, robot_xyyaw, step=4):
    lab, valid, dist = predict_labels(static, servo, robot_xyyaw, step)
    wall = ((lab == WALL) | (lab == POST)) & valid
    return float(wall.sum() / valid.sum())
