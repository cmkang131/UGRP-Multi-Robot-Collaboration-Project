"""Offline geometry helpers for the re-localisation view audit (no simulator, no network).

Ground-truth robot pose + the ISSUED servo pulses + the static map give which pixels of a recorded wrist frame
show walls / door posts / wall tags. This is an audit label only; nothing here is a controller input.
"""
from __future__ import annotations

import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.owncam_view import HEIGHT, WIDTH, base_rays, project_base_points, valid_pixel_mask  # noqa: E402
from harness.zone_own_guards import static_boxes  # noqa: E402

MAP_ID = 'zone_wide_door_tags_v2_dock_v3'
FLOOR, WALL, POST, TAG, BEYOND = 0, 1, 2, 3, 4
CLASS_NAMES = {FLOOR: 'floor', WALL: 'wall', POST: 'door_post', TAG: 'tag', BEYOND: 'beyond'}


@lru_cache(maxsize=1)
def static_map():
    return json.loads((ROOT/'maps'/'zones'/f'{MAP_ID}.json').read_text())


def _servo_pose(commanded_servo):
    return {int(k): int(v) for k, v in commanded_servo.items()}


def _boxes():
    out = []
    for b in static_boxes(static_map()):
        out.append(b)
    return out


def _hit_box(o, d, box):
    """Nearest positive ray parameter of the ray o + t d against an oriented box (z in [0, height]); inf if none."""
    cx, cy = box['center']
    hx, hy = box['half']
    c, s = math.cos(box['yaw']), math.sin(box['yaw'])
    ox, oy = o[0]-cx, o[1]-cy
    lo = np.array([c*ox + s*oy, -s*ox + c*oy, o[2]])
    ld = np.stack([c*d[:, 0] + s*d[:, 1], -s*d[:, 0] + c*d[:, 1], d[:, 2]], axis=1)
    mn = np.array([-hx, -hy, 0.])
    mx = np.array([hx, hy, box['height']])
    with np.errstate(divide='ignore', invalid='ignore'):
        t1 = (mn - lo)/ld
        t2 = (mx - lo)/ld
    par = np.abs(ld) < 1e-12
    inside = ((lo >= mn) & (lo <= mx))
    t_near = np.where(par, np.where(inside, -np.inf, np.inf), np.minimum(t1, t2))
    t_far = np.where(par, np.where(inside, np.inf, -np.inf), np.maximum(t1, t2))
    tn = t_near.max(axis=1)
    tf = t_far.min(axis=1)
    ok = (tn <= tf) & (tf > 1e-6)
    return np.where(ok, np.maximum(tn, 1e-6), np.inf)


def predict_labels(servo, robot_xyyaw, step=4):
    """Per-pixel class (FLOOR/WALL/POST/BEYOND) on a step-spaced grid; tags are added separately.

    Returns (labels HxW at grid resolution, valid HxW at grid resolution). BEYOND = ray hits neither floor nor a box
    (above the horizon, over the wall tops).
    """
    origin, rays, xs, ys, valid = base_rays(_servo_pose(servo), step)
    x, y, yaw = robot_xyyaw
    c, s = math.cos(yaw), math.sin(yaw)
    rot = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    o = rot @ np.asarray(origin, float) + np.array([x, y, 0.])
    d = rays @ rot.T
    t_floor = np.full(len(d), np.inf)
    down = d[:, 2] < -1e-9
    t_floor[down] = -o[2]/d[down, 2]
    best = t_floor.copy()
    cls = np.where(np.isfinite(t_floor), FLOOR, BEYOND)
    for box in _boxes():
        t = _hit_box(o, d, box)
        hit = t < best
        is_post = box['id'].startswith('post_')
        cls = np.where(hit, POST if is_post else WALL, cls)
        best = np.where(hit, t, best)
    h = len(range(step//2, HEIGHT, step))
    w = len(range(step//2, WIDTH, step))
    return cls.reshape(h, w), valid.reshape(h, w)


@lru_cache(maxsize=1)
def _tags():
    return static_map()['landmarks']['tags']


def tag_mask(servo, robot_xyyaw, shape=(HEIGHT, WIDTH), plate_m=0.09):
    """Full-resolution bool mask of wall-tag plates (0.09 m plate) that face the camera."""
    x, y, yaw = robot_xyyaw
    c, s = math.cos(yaw), math.sin(yaw)
    mask = np.zeros(shape, np.uint8)
    pose = _servo_pose(servo)
    rot_inv = np.array([[c, s, 0.], [-s, c, 0.], [0., 0., 1.]])
    for tag in _tags():
        nx, ny = tag['normal_xy']
        cx, cy, cz = tag['center_m']
        # facing test: camera position (world) must be on the normal side
        if (x-cx)*nx + (y-cy)*ny <= 0.:
            continue
        # plate corners on the wall face: tangent = (-ny, nx) horizontal, up = z
        tx, ty = -ny, nx
        h = plate_m/2
        pts_w = np.array([[cx + a*tx*h, cy + a*ty*h, cz + b*h] for a, b in ((-1, 1), (1, 1), (1, -1), (-1, -1))])
        base = (pts_w - np.array([x, y, 0.])) @ rot_inv.T
        px = project_base_points(pose, base)
        if np.isnan(px).any():
            continue
        if np.abs(px).max() > 5000:
            continue
        cv2.fillPoly(mask, [np.round(px).astype(np.int32)], 1)
    return mask.astype(bool)


def full_valid():
    return valid_pixel_mask(1)
