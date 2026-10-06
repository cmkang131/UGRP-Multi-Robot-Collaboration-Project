"""Opt-in, robot-private command odometry and inverse-sensor occupancy grid.

No static scene, pose observations, peer data or simulator. References and parameter
choices: experiments/2026-10-05-ego-wall-map-probe/README.md, section 16.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from harness.owncam_localizer import DEFAULT_PARAMS, OwnCamLocalizer

CALIBRATION = 'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json'
CALIBRATION_SHA256 = '126cadaa9265ed2ae2b034f675e67c227193a2e1678f6b0c82dd53b186e6fc72'
ROOT = Path(__file__).resolve().parents[1]


def motion_profiles():
    raw = (ROOT / CALIBRATION).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CALIBRATION_SHA256:
        raise ValueError('SELF_MAP_CALIBRATION_CHANGED')
    params = json.loads(raw)['params']
    return {key: params[key] for key in ('motion', 'motion_loaded')}


class _PredictionOnly(OwnCamLocalizer):
    def _map_logprior(self, px):
        return np.zeros(len(px))


class CommandOdometry:
    """Reuse the existing predictor at unit slip, zero noise and a zero start pose.

    The empty, unbounded constructor geometry only satisfies the PF interface; no
    surveyed geometry is read. Measurement updates are never called. Gripper-command
    load selection matches stage C; this is a commanded load, not measured contact.
    """
    def __init__(self, start_time=0., profiles=None):
        params = copy.deepcopy(DEFAULT_PARAMS)
        params.update(copy.deepcopy(motion_profiles() if profiles is None else profiles))
        params['particles'] = 1
        for key in ('motion', 'motion_loaded'):
            if key in params:
                p = params[key]
                p.update(noise_rel=[0., 0., 0.], noise_abs=[0., 0., 0.], scale_std=0., scale_walk=0.)
                for extra in ('load_transition', 'yaw_bias_std_rad_s', 'drift_ratio_std'):
                    p.pop(extra, None)
        self._predictor = _PredictionOnly(
            {'bounds_m': [-math.inf, math.inf, -math.inf, math.inf], 'obstacles': [],
             'landmarks': {'tags': []}}, params)
        self._predictor.initialized = True
        self._predictor.t = float(start_time)
        self.servo_since = float(start_time)
        self.has_servo = False

    @property
    def t(self):
        return self._predictor.t

    @property
    def pose(self):
        return tuple(float(v) for v in self._predictor.px[0])

    @property
    def loaded(self):
        return self._predictor.load.loaded

    def advance(self, t):
        t = float(t)
        if not math.isfinite(t) or t < self.t - 1e-8:
            raise ValueError('SELF_MAP_NON_MONOTONIC_TIME')
        # Split exactly at command expiry; inherited integrator uses <= 50 ms steps.
        expiry = self._predictor.cmd_expires
        if self.t < expiry < t:
            self._predictor.predict_to(expiry)
        self._predictor.predict_to(max(t, self.t))
        self._predictor.t = max(t, self.t)
        return self.pose

    def command(self, row):
        kind = row['kind']
        if kind not in ('initial_servo_command', 'arm', 'look', 'mecanum', 'drive', 'hold', 'stop'):
            raise ValueError('SELF_MAP_UNKNOWN_COMMAND')
        fields = {'initial_servo_command': ('pulses',), 'arm': ('servo_id', 'pulse'),
                  'look': ('pan_pulse',), 'mecanum': ('forward', 'left', 'turn', 'duration_s'),
                  'drive': ('forward', 'turn', 'duration_s')}.get(kind, ())
        clean = {'t': float(row['t']), 'kind': kind, **{k: row[k] for k in fields}}
        if kind in ('mecanum', 'drive') and (any(not math.isfinite(float(clean[k])) for k in fields)
                                           or clean['duration_s'] < 0):
            raise ValueError('SELF_MAP_INVALID_COMMAND')
        self.advance(clean['t'])
        clean['t'] = self.t
        before = dict(self._predictor.servo)
        self._predictor.command(clean)
        if self._predictor.servo != before:
            self.servo_since = self.t
        self.has_servo |= bool(self._predictor.servo)
        self._predictor.load.loaded = self._predictor.servo.get(1, 2000) <= 1600


def transform(points, pose):
    points = np.asarray(points, float)
    x, y, yaw = pose
    c, s = math.cos(yaw), math.sin(yaw)
    return points @ np.array([[c, s], [-s, c]]) + [x, y]


def ray_cells(start, end, resolution):
    """Amanatides-Woo 2D cell traversal, including start and endpoint cells."""
    a, b = np.asarray(start, float) / resolution, np.asarray(end, float) / resolution
    cell, target = np.floor(a).astype(int), np.floor(b).astype(int)
    delta = b - a
    step = np.sign(delta).astype(int)
    t_delta = np.full(2, np.inf)
    t_max = np.full(2, np.inf)
    for axis in range(2):
        if delta[axis]:
            boundary = cell[axis] + (1 if step[axis] > 0 else 0)
            t_max[axis] = (boundary - a[axis]) / delta[axis]
            t_delta[axis] = abs(1 / delta[axis])
    cells = [tuple(cell)]
    while not np.array_equal(cell, target):
        # An endpoint exactly on an edge may round to either neighbouring cell.
        # Never step an axis past its endpoint cell (finite segment traversal).
        axis = int(np.argmin(np.where(cell == target, np.inf, t_max)))
        cell[axis] += step[axis]
        t_max[axis] += t_delta[axis]
        cells.append(tuple(cell))
    return cells


class OdomGrid:
    """Sparse log odds, unknown prior .5, one hit/miss update per frame/cell."""
    def __init__(self, robot_id, *, resolution_m=.10, max_range_m=4., settle_s=(.25, 2.25),
                 start_time=0., profiles=None, text_top_k=6, text_max_tokens=384):
        if not math.isfinite(resolution_m) or resolution_m <= 0:
            raise ValueError('SELF_MAP_INVALID_RESOLUTION')
        if max_range_m is not None and (not math.isfinite(max_range_m) or max_range_m <= 0):
            raise ValueError('SELF_MAP_INVALID_RANGE')
        if settle_s is not None and (len(settle_s) != 2 or any(not math.isfinite(v) or v < 0 for v in settle_s)):
            raise ValueError('SELF_MAP_INVALID_SETTLE')
        if text_top_k < 1 or text_max_tokens < 128:
            raise ValueError('SELF_MAP_INVALID_TEXT_BUDGET')
        self.robot_id = robot_id
        self.resolution_m, self.max_range_m = resolution_m, max_range_m
        self.settle_s = settle_s
        self.text_top_k, self.text_max_tokens = text_top_k, text_max_tokens
        self.odom = CommandOdometry(start_time, profiles)
        self.cells = {}
        self.seen = set()
        self.frames = 0
        self.rejected = {'unsettled': 0, 'range_segments': 0}
        self.hit, self.miss = math.log(.7/.3), math.log(.4/.6)
        self.lo, self.hi = math.log(.1192/.8808), math.log(.971/.029)

    def insert(self, camera, segments):
        """Geometry already in this grid frame. Also used by the separate eval oracle."""
        occupied, free = set(), set()
        for a, b in segments:
            # Sample at <= half a cell to cover the observed face continuously.
            n = max(2, int(math.ceil(np.linalg.norm(b-a) / (self.resolution_m/2))) + 1)
            for p in np.linspace(a, b, n):
                keys = ray_cells(camera, p, self.resolution_m)
                occupied.add(keys[-1])
                free.update(keys[:-1])
        for keys, increment in ((free - occupied, self.miss), (occupied, self.hit)):
            for key in keys:
                self.cells[key] = min(self.hi, max(self.lo, self.cells.get(key, 0.) + increment))
        self.frames += 1

    def observe(self, record, *, camera_xy, robot_id):
        from harness.self_wall_memory import validate_record
        if robot_id != self.robot_id:
            raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
        rec = validate_record(record)
        key = (rec['t_sim'], rec['view_index'])
        if key in self.seen:
            return []
        camera = np.asarray(camera_xy, float)
        if camera.shape != (2,) or not np.isfinite(camera).all():
            raise ValueError('SELF_MAP_INVALID_CAMERA_ORIGIN')
        pose = self.odom.advance(rec['t_sim'])
        self.seen.add(key)
        if self.settle_s is not None and (not self.odom.has_servo or
                self.odom.t-self.odom.servo_since + 1e-8 < self.settle_s[int(self.odom.loaded)]):
            self.rejected['unsettled'] += 1
            return []
        local = []
        for r1, a1, r2, a2, _ in rec['seg']:
            ends = np.array([[r1*math.cos(a1), r1*math.sin(a1)], [r2*math.cos(a2), r2*math.sin(a2)]])
            if self.max_range_m is not None and np.linalg.norm(ends-camera, axis=1).max() > self.max_range_m:
                self.rejected['range_segments'] += 1
                continue
            local.append(ends)
        if local:
            self.insert(transform([camera], pose)[0], [transform(seg, pose) for seg in local])
        return local

    def occupied_points(self):
        return np.array([((x+.5)*self.resolution_m, (y+.5)*self.resolution_m)
                         for (x, y), value in sorted(self.cells.items()) if value > 0.]).reshape(-1, 2)

    def lines(self):
        """Deterministic Hough peaks + TLS, split at gaps; geometry from occupied cells only."""
        pts = self.occupied_points()
        lines = []
        for _ in range(self.text_top_k * 3):
            if len(pts) < 3:
                break
            best = np.zeros(len(pts), bool)
            for angle in np.arange(0., math.pi, math.pi/60):
                bins = np.floor((pts @ [math.cos(angle), math.sin(angle)]) / self.resolution_m).astype(int)
                labels, counts = np.unique(bins, return_counts=True)
                mask = bins == labels[np.argmax(counts)]
                if mask.sum() > best.sum():
                    best = mask
            support, pts = pts[best], pts[~best]
            if len(support) < 3:
                break
            center = support.mean(0)
            _, _, vt = np.linalg.svd(support-center, full_matrices=False)
            axis = vt[0]
            projected = (support-center) @ axis
            order = np.argsort(projected)
            groups = np.split(order, np.flatnonzero(np.diff(projected[order]) > 2*self.resolution_m)+1)
            for group in groups:
                if len(group) >= 3:
                    a, b = center + projected[group[[0, -1]]][:, None]*axis
                    length = float(np.linalg.norm(b-a))
                    lines.append({'a': a.tolist(), 'b': b.tolist(), 'length_m': length, 'cells': len(group)})
        return sorted(lines, key=lambda s: (-s['length_m'], s['a'], s['b']))[:self.text_top_k]

    def text(self):
        # ASCII UTF-8 bytes bound the token count for byte-level BPE tokenizers.
        # The budget covers this string, not the surrounding caller's entire prompt.
        out = 'self_map: own camera, start odom (m; x forward, y left); drift uncorrected; walls '
        lines = self.lines()
        if not lines:
            return out + 'none yet'
        for line in lines:
            a, b = line['a'], line['b']
            part = f"({a[0]:.2f},{a[1]:.2f})->({b[0]:.2f},{b[1]:.2f}); "
            if len((out+part).encode('utf-8')) > self.text_max_tokens:
                break
            out += part
        return out.rstrip('; ')

    def export(self):
        return {'schema': 'ugrp.self_map.odom_grid_v1', 'robot_id': self.robot_id,
                'frame': 'own start chassis: x forward, y left, metres', 'pose_xyyaw': self.odom.pose,
                'resolution_m': self.resolution_m, 'frames': self.frames, 'rejected': dict(self.rejected),
                'cells': [[int(x), int(y), v] for (x, y), v in sorted(self.cells.items())]}
