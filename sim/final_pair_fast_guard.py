"""V91-only abort interlock. No scheduler input and no physics modification.

Static geometry and excitation are immutable during a pinned collection. The
scalar chassis clearance keeps math.hypot rounding; sphere gaps use exactly the
old NumPy arithmetic. Batched envelope norms may differ by a few ulps from BLAS
dot, so decisions near the bound are recomputed with the original scalar norm.
"""
import math

import numpy as np

from harness.final_environment_measurement_v2 import rectangles, geometry_envelope


class WallArrays:
    def __init__(self, static):
        self.rects = np.asarray(rectangles(static), dtype=float)
        self.bounds = np.asarray(static['bounds_m'], dtype=float)

    def distances(self, xy):
        x, y = np.asarray(xy, float).T
        x0, x1, y0, y1 = self.bounds
        boundary = np.minimum.reduce((x-x0, x1-x, y-y0, y1-y))
        a, b, c, d = self.rects.T
        dx = np.maximum(np.maximum(a-x[..., None], x[..., None]-b), 0.)
        dy = np.maximum(np.maximum(c-y[..., None], y[..., None]-d), 0.)
        return boundary, dx, dy

    def require_clearance(self, xy, plan):
        xy = np.asarray(xy, float)
        safety = plan['clearance']
        radius = safety['robot_radius_bound_m']
        if not np.isfinite(xy).all() or not math.isfinite(radius) or radius <= 0:
            raise ValueError('missing/non-finite clearance measurement')
        boundary, dx, dy = self.distances(xy)
        # math.hypot and np.hypot need not round identically. Only one chassis
        # is checked in v91; retain scalar hypot after vectorizing wall offsets.
        gap = min(float(boundary), *(math.hypot(x, y) for x, y in zip(dx, dy))) - radius
        if gap < safety['minimum_m'] + safety['abort_buffer_m'] - 1e-10:
            raise ValueError('CLEARANCE_ABORT: static-map wall margin not available')
        return gap

    def sphere_clearances(self, xyz, radii):
        xyz, radii = np.asarray(xyz, float), np.asarray(radii, float)
        if (xyz.ndim != 2 or xyz.shape[1] != 3 or radii.shape != (len(xyz),)
                or not len(xyz) or np.any(radii <= 0)):
            raise ValueError('missing/non-finite clearance geometry')
        if not np.isfinite(xyz).all() or not np.isfinite(radii).all():
            raise ValueError('INVALID_ROBOT_GEOMETRY')
        boundary, dx, dy = self.distances(xyz[:, :2])
        gaps = np.minimum(boundary, np.hypot(dx, dy).min(axis=1))-radii
        if not np.isfinite(gaps).all():
            raise ValueError('INVALID_ROBOT_GEOMETRY')
        return gaps


def geometry_envelopes(xyz, radii, xy):
    xyz, radii = np.asarray(xyz, float), np.asarray(radii, float)
    if (xyz.ndim != 2 or xyz.shape[1] != 3 or radii.shape != (len(xyz),)
            or not np.isfinite(xyz).all() or not np.isfinite(radii).all()
            or np.any(radii < 0)):
        raise ValueError('INVALID_ROBOT_GEOMETRY')
    distance = np.linalg.norm(xyz[:, :2]-xy, axis=1)
    envelope = distance+radii
    if not np.isfinite(envelope).all():
        raise ValueError('INVALID_ROBOT_GEOMETRY')
    return envelope


def require_envelope(xyz, radii, xy, bound):
    envelope = geometry_envelopes(xyz, radii, xy)
    # Two-term square/sum vs BLAS dot can change final rounding. A deliberately
    # conservative 8-ulp neighbourhood falls back before making any decision.
    near = np.abs(envelope-bound) <= 8*np.spacing(bound)
    for i in np.flatnonzero(near):
        envelope[i] = geometry_envelope(xyz[i], radii[i], xy)
    if envelope.max() > bound:
        raise ValueError('ROBOT_ENVELOPE_BOUND_EXCEEDED')


class FastGuard:
    """Mixin used only by the v91 owner; v88/v90 methods stay byte-identical."""
    def collection_guard(self):
        import mujoco
        from harness import zone_final_pair_contract as contract
        from harness.zone_final_pair_excitation import design

        m, d = self.world.model, self.world.data
        try:
            if not hasattr(self, '_fast_plan'):
                self._fast_plan = design(self.bundle['check'])
                self._fast_walls = WallArrays(self.scene.config['static_map'])
            plan, walls = self._fast_plan, self._fast_walls
            robots = contract.ROBOTS if self.bundle['check'] == 'calibration-loaded' else ('r1',)
            cached = getattr(self, '_guard_groups', None)
            if cached is None:
                names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) or '' for i in range(m.ngeom)]
                groups = [(rid, np.array([i for i, n in enumerate(names) if n.startswith(rid+'__')], int)) for rid in robots]
                if self.bundle['check'] == 'calibration-loaded':
                    beam_id = int(m.body('cargo_beam').id)
                    groups.append(('beam', np.array([i for i in range(m.ngeom) if int(m.geom_bodyid[i]) == beam_id], int)))
                if any(not len(ids) for _, ids in groups):
                    raise ValueError('MISSING_COLLECTION_GEOMETRY')
                self._guard_groups = (m.ngeom, groups)
            else:
                count, groups = cached
                if count != m.ngeom:
                    raise ValueError('COLLECTION_GEOMETRY_CHANGED')
            minimum = float('inf')
            for rid, ids in groups[:len(robots)]:
                xy = np.asarray(d.body(rid+'__robot').xpos[:2], float)
                minimum = min(minimum, walls.require_clearance(xy, plan))
                require_envelope(d.geom_xpos[ids], m.geom_rbound[ids], xy,
                                 plan['clearance']['robot_radius_bound_m'])
            for name, ids in groups:
                xyz = np.asarray(d.geom_xpos[ids], float)
                gaps = walls.sphere_clearances(xyz, m.geom_rbound[ids])
                xy = xyz[:, :2]
                if np.any(gaps < .35-1e-10):
                    raise ValueError('CLEARANCE_ABORT: collection geometry wall margin')
                previous = self._last_guard_xy.get(name)
                if previous is not None and np.any(np.linalg.norm(xy-previous, axis=1) > plan['clearance']['max_substep_displacement_m']):
                    raise ValueError('SUBSTEP_DISPLACEMENT_BOUND_EXCEEDED')
                self._last_guard_xy[name] = xy.copy()
                minimum = min(minimum, float(gaps.min()))
            self._clearance_min = minimum
        except Exception as exc:
            for port in self.ports.values():
                port.hold(self.now)
            self._append('eval_only/clearance_abort.jsonl', {'t': self.now, 'reason': str(exc),
                         'static_map_sha256': self.bundle['map_sha256']})
            raise

    def _post_state(self):
        m, d = self.world.model, self.world.data
        return (m, d, float(d.time), d.qpos.copy(), d.qvel.copy(), m.ngeom,
                d.geom_xpos.copy(), d.xpos.copy(), m.geom_rbound.copy())

    def _same_post_state(self, state):
        if state is None:
            return False
        m, d = self.world.model, self.world.data
        return (state[0] is m and state[1] is d and state[2] == d.time and state[5] == m.ngeom
                and np.array_equal(state[3].view(np.uint8), d.qpos.view(np.uint8))
                and np.array_equal(state[4].view(np.uint8), d.qvel.view(np.uint8))
                and np.array_equal(state[6], d.geom_xpos) and np.array_equal(state[7], d.xpos)
                and np.array_equal(state[8], m.geom_rbound))

    def advance_to(self, t):
        if self.deadline is None or not math.isfinite(t) or not self.now-1e-8 <= t <= self.deadline+1e-8:
            raise ValueError('advance outside SIM deadline')
        # Local lifetime: command/capture/eval/reset boundaries always recheck.
        # Only the next pre-substep check may reuse a successful post-check.
        post = None
        while self.now+self.dt <= t+1e-8:
            if not self._same_post_state(post):
                self.collection_guard()
            for port in self.ports.values():
                port.tick(self.now)
            self.world._physics_step_for(self.world.robot('r1'))
            self.collection_guard()
            post = self._post_state()
        if abs(self.now-t) > 1e-7:
            raise RuntimeError('inexact SIM advance')
