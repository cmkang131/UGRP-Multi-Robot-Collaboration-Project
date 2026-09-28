"""MuJoCo side of the MasterPi front ultrasonic sensor (``harness.ultrasonic_model``).

Cone approximation: ``ray_pattern`` rays from the transducer FACE on the
chassis body, one ``mj_multiRay`` per reading plus re-casts for rays that hit
an excluded body. Minimum-return model: the nearest ray whose directivity x
incidence amplitude clears the threshold sets the range (first echo).

Excluded from the rays (2026-09-28 review fix, PR #248 P1): ONLY the own
chassis side of the robot tree (chassis body with the sensor housing, wheels):
the physical sensor cannot see behind its own face or its housing. The own ARM
(``<rid>__arm_base`` subtree: shoulder, elbow, wrist, camera, gripper, jaws)
is NOT excluded: the real sensor sees its own gripper whenever it is in the
cone (grasp, lowering). A HELD object is a separate free body and is not
excluded either. There is deliberately no API to exclude the arm or the load.

Also skipped: geom group 4 (mission-only floor overlays) and transparent geoms
(``mj_ray`` semantics: rgba alpha 0 is not a surface; the hidden prototypes in
group 5 are alpha 0).

The output is ``RangeReading(t, range_m, valid, status)`` only.
``measure_diagnostic`` additionally returns what the rays hit and is for
evaluation/tests only; it must never be passed to a controller, a provider or
a model request (``tests/test_ultrasonic_range.py`` checks that no executor
module references it).

Noise is indexed by the reading tick ``round(now / period_s)`` with a seed that
the caller must give (``harness.ultrasonic_model.sensor_seed(episode_seed,
robot_id)``), so matched times get matched noise in every condition.

Stateless with respect to physics: reading the sensor calls no ``mj_step`` and
no ``mj_forward`` (the caller's ``data`` must already be forwarded).
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import mujoco
import numpy as np

from harness.ultrasonic_model import (DEFAULT_SPEC, NOISE_STREAM, RangeReading, UltrasonicSpec,
                                      crosstalk_phase, crosstalk_range, first_echo, first_echo_index,
                                      incidence_angle, noisy_reading_with_cause, ray_pattern, reading_rng,
                                      reading_tick)

SENSOR_GEOM_GROUPS = np.array([1, 1, 1, 1, 0, 1], dtype=np.uint8)
MAX_RECASTS = 16


@dataclass
class MujocoUltrasonic:
    model: mujoco.MjModel
    data: mujoco.MjData
    robot_id: str
    seed: int                            # required: harness.ultrasonic_model.sensor_seed(episode_seed, robot_id)
    spec: UltrasonicSpec = DEFAULT_SPEC
    chassis_body: str | None = None      # default: '<robot_id>__robot', or 'robot' for a single twin
    site: str | None = None              # optional sensor site (e.g. a remodel's ultrasonic site)
    truncated_rays: int = field(init=False, default=0)

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
        self.arm_bodies = frozenset(b for b in self.own_bodies if self._in_arm(b))
        self.chassis_side = frozenset(self.own_bodies - self.arm_bodies)      # the only bodies the rays skip
        self.site_id = None
        if self.site is not None:
            sid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, self.site)
            if sid < 0:
                raise ValueError(f'missing sensor site {self.site!r}')
            self.site_id = int(sid)
        # Chassis frame height above the floor from the model (spawn pose), not a v2 constant.
        chassis_z = float(self.model.body_pos[self.chassis_id][2]) if int(self.model.body_parentid[self.chassis_id]) == 0 else 0.
        self.local_origin = np.array([self.spec.face_x_m, self.spec.mount_y_m, self.spec.mount_z_floor_m - chassis_z])
        dirs, self.alpha = ray_pattern(self.spec)
        p = math.radians(self.spec.mount_pitch_deg)
        pitch = np.array([[math.cos(p), 0., -math.sin(p)], [0., 1., 0.], [math.sin(p), 0., math.cos(p)]])
        self.local_dirs = dirs @ pitch.T
        self.next_due = -math.inf

    def _in_arm(self, body: int) -> bool:
        """Body is the arm base (the chassis child carrying the ``arm_yaw`` joint) or below it."""
        while body > 0 and body != self.chassis_id:
            parent = int(self.model.body_parentid[body])
            if parent == self.chassis_id:
                j0, nj = int(self.model.body_jntadr[body]), int(self.model.body_jntnum[body])
                return any((mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, j) or '').endswith('arm_yaw')
                           for j in range(j0, j0 + nj))
            body = parent
        return False

    # --- geometry -------------------------------------------------------------------------------
    def pose(self) -> tuple[np.ndarray, np.ndarray]:
        """World origin (transducer face) and 3x3 sensor rotation (forward, left, up)."""
        if self.site_id is not None:
            R = self.data.site_xmat[self.site_id].reshape(3, 3)
            return self.data.site_xpos[self.site_id] + R[:, 0] * self.spec.face_forward_m, R
        R = self.data.xmat[self.chassis_id].reshape(3, 3)
        return self.data.xpos[self.chassis_id] + R @ self.local_origin, R

    def cast(self, *, include_chassis: bool = False) -> dict:
        """Per-ray first surface (distance, normal, geom). Only the own chassis side is skipped.

        The own arm/gripper and any held load are always included (the real
        sensor sees them). ``include_chassis=True`` is an evaluation-only
        diagnostic; never a reading.
        """
        excluded = set() if include_chassis else set(self.chassis_side)
        origin, R = self.pose()
        dirs = np.ascontiguousarray(self.local_dirs @ R.T)
        n = len(dirs)
        geom = np.full(n, -1, np.int32)
        dist = np.full(n, -1.)
        normal = np.zeros(3 * n)
        mujoco.mj_multiRay(self.model, self.data, origin, dirs.ravel(), SENSOR_GEOM_GROUPS, 1,
                           -1 if include_chassis else self.chassis_id, geom, dist, normal, n, self.spec.max_range_m + .5)
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
                self.truncated_rays += 1          # diagnostic: too many excluded surfaces on one ray
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
        echo = first_echo(c['dist'], self.alpha, c['beta'], self.spec)
        true = echo
        tick = reading_tick(now, self.spec)
        crosstalk = None
        if self.spec.crosstalk and peers:
            crosstalk = self._crosstalk(c['origin'], peers, tick)
            if crosstalk is not None and (true is None or crosstalk < true):
                true = crosstalk
        rng = reading_rng(self.seed, self.robot_id, tick, NOISE_STREAM)
        reading, cause = noisy_reading_with_cause(float(now), true, rng, self.spec)
        self.next_due = float(now) + self.spec.period_s
        name = lambda g: mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, int(g)) or str(int(g))
        hit_geoms = sorted({name(g) for g in c['geom'] if g >= 0})
        i = first_echo_index(c['dist'], self.alpha, c['beta'], self.spec)
        echo_geom = None if i is None else name(c['geom'][i])
        return reading, {'true_first_echo_m': echo, 'crosstalk_m': crosstalk, 'hit_geoms': hit_geoms,
                         'echo_geom': echo_geom, 'echo_is_own_arm': bool(i is not None and int(
                             self.model.geom_bodyid[c['geom'][i]]) in self.arm_bodies),
                         'cause': cause, 'tick': tick, 'n_rays': len(c['dist']),
                         'truncated_rays_total': self.truncated_rays}

    def _crosstalk(self, origin, peers, tick) -> float | None:
        """Nearest apparent range from a peer pulse (phase-correlated drift, ``crosstalk_phase``)."""
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
            blocked = self._line_blocked(origin, u, d, set(peer.chassis_side))
            if blocked:
                continue
            pair_seed = min((self.robot_id, self.seed), (peer.robot_id, peer.seed))[1]   # shared by both ends
            phase = crosstalk_phase(pair_seed, (self.robot_id, peer.robot_id), tick, self.spec)
            r = crosstalk_range(d, phase, self.spec)
            if r is not None and (best is None or r < best):
                best = r
        return best

    def _line_blocked(self, origin, u, d, peer_bodies) -> bool:
        excluded = set(self.chassis_side) | peer_bodies
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
