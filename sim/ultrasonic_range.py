"""MuJoCo side of the MasterPi front ultrasonic sensor (``harness.ultrasonic_model``).

Cone approximation: ``ray_pattern`` rays from the sensor origin on the chassis
body, one ``mj_multiRay`` per reading plus a re-cast for rays that hit an
excluded body. Minimum-return model: the nearest ray whose directivity x
incidence amplitude clears the threshold sets the range (first echo).

Excluded from the rays (the sensor must not see itself):
* every body in the own robot's kinematic tree (chassis, wheels, arm,
  gripper) via ``model.body_rootid``;
* geom groups 4 (mission-only floor overlays) and 5 (own camera hardware and
  hidden prototypes), the same groups the robot camera hides;
* transparent geoms (``mj_ray`` semantics: rgba alpha 0 is not a surface).

A HELD object is NOT excluded (2026-09-28 correction on #248): it is a separate
free body, and the physical sensor sees its own load whenever the load is in
the cone. There is deliberately no API to exclude it.

The output is ``RangeReading(t, range_m, valid)`` only. ``measure_diagnostic``
additionally returns what the rays hit and is for evaluation/tests only; it
must never be passed to a controller, a provider or a model request.

Stateless with respect to physics: reading the sensor calls no ``mj_step`` and
no ``mj_forward`` (the caller's ``data`` must already be forwarded).
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import mujoco
import numpy as np

from harness.ultrasonic_model import (DEFAULT_SPEC, RangeReading, UltrasonicSpec, crosstalk_range,
                                      first_echo, first_echo_index, incidence_angle, noisy_reading, ray_pattern, reading_rng)
from sim.masterpi_geometry import NOMINAL_WHEEL_RADIUS_M

SENSOR_GEOM_GROUPS = np.array([1, 1, 1, 1, 0, 0], dtype=np.uint8)
MAX_RECASTS = 16


@dataclass
class MujocoUltrasonic:
    model: mujoco.MjModel
    data: mujoco.MjData
    robot_id: str
    seed: int = 0
    spec: UltrasonicSpec = DEFAULT_SPEC
    chassis_body: str | None = None      # default: '<robot_id>__robot', or 'robot' for a single twin
    seq: int = field(init=False, default=0)

    def __post_init__(self):
        name = self.chassis_body or f'{self.robot_id}__robot'
        bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
        if bid < 0 and self.chassis_body is None:
            bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, 'robot')
        if bid < 0:
            raise ValueError(f'missing chassis body for {self.robot_id!r}')
        self.chassis_id = int(bid)
        root = int(self.model.body_rootid[bid])
        self.own_bodies = frozenset(int(b) for b in range(self.model.nbody) if int(self.model.body_rootid[b]) == root)
        # Chassis frame origin is at wheel-axle height; the spec height is from the floor.
        self.local_origin = np.array([self.spec.mount_x_m, self.spec.mount_y_m,
                                      self.spec.mount_z_floor_m - NOMINAL_WHEEL_RADIUS_M])
        dirs, self.alpha = ray_pattern(self.spec)
        p = math.radians(self.spec.mount_pitch_deg)
        pitch = np.array([[math.cos(p), 0., -math.sin(p)], [0., 1., 0.], [math.sin(p), 0., math.cos(p)]])
        self.local_dirs = dirs @ pitch.T
        self.next_due = -math.inf

    # --- geometry -------------------------------------------------------------------------------
    def pose(self) -> tuple[np.ndarray, np.ndarray]:
        """World origin and 3x3 sensor rotation (forward, left, up) from the forwarded chassis."""
        R = self.data.xmat[self.chassis_id].reshape(3, 3)
        return self.data.xpos[self.chassis_id] + R @ self.local_origin, R

    def cast(self, *, include_own: bool = False) -> dict:
        """Per-ray first surface (distance, normal, geom); own robot tree excluded.

        ``include_own=True`` is an evaluation-only diagnostic (what the physical
        sensor would additionally see of its own arm); never a reading.
        """
        excluded = set() if include_own else set(self.own_bodies)
        origin, R = self.pose()
        dirs = np.ascontiguousarray(self.local_dirs @ R.T)
        n = len(dirs)
        geom = np.full(n, -1, np.int32)
        dist = np.full(n, -1.)
        normal = np.zeros(3 * n)
        mujoco.mj_multiRay(self.model, self.data, origin, dirs.ravel(), SENSOR_GEOM_GROUPS, 1,
                           -1 if include_own else self.chassis_id, geom, dist, normal, n, self.spec.max_range_m + .5)
        normal = normal.reshape(n, 3)
        one_geom, one_normal = np.array([-1], np.int32), np.zeros(3)
        for i in range(n):
            travelled = 0.
            for _ in range(MAX_RECASTS):
                if geom[i] < 0 or int(self.model.geom_bodyid[geom[i]]) not in excluded:
                    break
                travelled += dist[i] + 1e-5
                start = origin + dirs[i] * travelled
                d = mujoco.mj_ray(self.model, self.data, start, dirs[i], SENSOR_GEOM_GROUPS, 1,
                                  self.chassis_id, one_geom, one_normal)
                geom[i], normal[i] = one_geom[0], one_normal
                dist[i] = d
            else:
                geom[i], dist[i] = -1, -1.
            if geom[i] >= 0:
                dist[i] += travelled
            else:
                dist[i] = -1.
        dist = np.where((dist >= 0) & (dist <= self.spec.max_range_m + .5), dist, -1.)
        return {'origin': origin, 'dirs': dirs, 'dist': dist, 'normal': normal, 'geom': geom,
                'beta': incidence_angle(dirs, normal)}

    def true_first_echo(self) -> float | None:
        c = self.cast()
        return first_echo(c['dist'], self.alpha, c['beta'], self.spec)

    # --- readings -------------------------------------------------------------------------------
    def due(self, now: float) -> bool:
        return now + 1e-12 >= self.next_due

    def measure(self, now: float, *, peers: Sequence['MujocoUltrasonic'] = ()) -> RangeReading:
        """One reading at SIM time ``now`` (the caller's current, forwarded state)."""
        return self.measure_diagnostic(now, peers=peers)[0]

    def measure_diagnostic(self, now: float, *,
                           peers: Sequence['MujocoUltrasonic'] = ()) -> tuple[RangeReading, dict]:
        """EVALUATION ONLY: the reading plus what the rays hit (never give the dict to a controller)."""
        c = self.cast()
        true = first_echo(c['dist'], self.alpha, c['beta'], self.spec)
        rng = reading_rng(self.seed, self.robot_id, self.seq)
        crosstalk = None
        if self.spec.crosstalk and peers:
            crosstalk = self._crosstalk(c['origin'], peers, rng)
            if crosstalk is not None and (true is None or crosstalk < true):
                true = crosstalk
        reading = noisy_reading(float(now), true, rng, self.spec)
        self.seq += 1
        self.next_due = float(now) + self.spec.period_s
        name = lambda g: mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, int(g)) or str(int(g))
        hit_geoms = sorted({name(g) for g in c['geom'] if g >= 0})
        i = first_echo_index(c['dist'], self.alpha, c['beta'], self.spec)
        return reading, {'true_first_echo_m': true, 'crosstalk_m': crosstalk, 'hit_geoms': hit_geoms,
                         'echo_geom': None if i is None else name(c['geom'][i]),
                         'n_rays': len(c['dist']), 'seq': self.seq - 1}

    def _crosstalk(self, origin, peers, rng) -> float | None:
        """Nearest apparent range from a peer pulse; peers fire at independent phases."""
        best = None
        R_self = self.pose()[1]
        edge = math.cos(math.radians(self.spec.half_angle_deg))
        for peer in peers:
            p_origin, R_peer = peer.pose()
            v = p_origin - origin
            d = float(np.linalg.norm(v))
            if d <= 1e-6 or d > self.spec.max_range_m:
                continue
            u = v / d
            if R_self[:, 0] @ u < edge or R_peer[:, 0] @ -u < edge:
                continue            # outside our receive cone or the peer's transmit cone
            blocked = self._line_blocked(origin, u, d, set(peer.own_bodies))
            if blocked:
                continue
            phase = (rng.random() - .5) * self.spec.period_s
            r = crosstalk_range(d, phase, self.spec)
            if r is not None and (best is None or r < best):
                best = r
        return best

    def _line_blocked(self, origin, u, d, peer_bodies) -> bool:
        excluded = set(self.own_bodies) | peer_bodies
        gid = np.array([-1], np.int32)
        start, travelled = origin.copy(), 0.
        for _ in range(MAX_RECASTS):
            hit = mujoco.mj_ray(self.model, self.data, start, u, SENSOR_GEOM_GROUPS, 1, self.chassis_id, gid, None)
            if hit < 0 or travelled + hit >= d - 1e-3:
                return False
            if int(self.model.geom_bodyid[gid[0]]) not in excluded:
                return True
            travelled += hit + 1e-5
            start = origin + u * travelled
        return True
