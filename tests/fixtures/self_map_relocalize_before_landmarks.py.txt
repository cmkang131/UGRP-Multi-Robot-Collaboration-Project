"""Offline unknown-start adapter around the pinned PR406 AMCL/KLD primitives.

Inputs: a fixed caller-owned grid, own RGB endpoints and command SE(2) deltas.
No file loading, scene, truth pose, map alignment, or command execution here.
"""
import math
import numpy as np
from scipy.ndimage import distance_transform_edt
from harness.own_map_amcl_vendor import field, motion, augmented, kld
from harness.rbpf_rejection import motion_variance


class GridField(field.Field):
    def __init__(self, grid):
        self.res = field.PARAMS['grid_resolution_m']
        resolution = float(grid['resolution_m'])
        factor = round(resolution/self.res)
        if factor < 1 or abs(factor*self.res-resolution)>1e-9:
            raise ValueError('AMCL_GRID_RESOLUTION_MULTIPLE')
        cells = np.asarray(grid['cells'], float)
        if not len(cells) or not np.isfinite(cells).all():
            raise ValueError('FINITE_NONEMPTY_MAP_REQUIRED')
        indices = cells[:, :2].astype(int)
        self.lo = indices.min(0)-10
        hi = indices.max(0)+11
        raw = np.full(tuple((hi-self.lo)[::-1]), 255, np.uint8)
        for (x, y), c in zip(indices-self.lo, cells):
            raw[y, x] = 254 if c[2] > 0 else 0 if c[2] < 0 else 255
        self.raw, self.grid_origin, self.grid_resolution = raw, self.lo*resolution, resolution
        occupied = np.repeat(np.repeat(raw == 254, factor, axis=0), factor, axis=1)
        if not occupied.any():
            raise ValueError('OCCUPIED_MAP_REQUIRED')
        self.origin = self.grid_origin+self.res/2
        self.shape = occupied.shape
        self.dist = np.minimum(distance_transform_edt(~occupied)*self.res, field.PARAMS['max_occ_dist_m'])
        self.free_cells = indices[cells[:, 2] < 0]
        if not len(self.free_cells):
            raise ValueError('OBSERVED_FREE_MAP_REQUIRED')


class Relocalizer:
    def __init__(self, grid, *, seed):
        self.field = GridField(grid)
        self.rng = np.random.default_rng(seed)
        self.n = kld.PARAMS['max_samples']
        self.px = self._uniform_free(self.n)
        self.logw = np.zeros(self.n)
        self._inject = 0.
        self.stats = dict(resamples=0)
        self.policy = kld.Policy()
        self.odom = np.zeros(3)
        self.anchor = None
        self.updates = 0

    def _uniform_free(self, n):
        cells = self.field.free_cells[self.rng.integers(len(self.field.free_cells), size=n)]
        xy = (cells+self.rng.random((n, 2)))*self.field.grid_resolution
        return np.c_[xy, self.rng.uniform(-math.pi, math.pi, n)]

    def _weights(self):
        w = np.exp(self.logw-self.logw.max())
        return w/w.sum()

    def step(self, *, t, points, delta, servo):
        delta = np.asarray(delta, float)
        points = np.asarray(points, float).reshape(-1, 2)
        if delta.shape != (3,) or not np.isfinite(delta).all() or not np.isfinite(points).all():
            raise ValueError('FINITE_OWN_MOTION_AND_POINTS_REQUIRED')
        if np.any(delta):
            step = delta+self.rng.normal(size=(self.n, 3))*np.sqrt(motion_variance(delta))
            c, s = np.cos(self.px[:, 2]), np.sin(self.px[:, 2])
            self.px[:, 0] += c*step[:, 0]-s*step[:, 1]
            self.px[:, 1] += s*step[:, 0]+c*step[:, 1]
            self.px[:, 2] = (self.px[:, 2]+step[:, 2]+math.pi)%(2*math.pi)-math.pi
            c, s = math.cos(self.odom[2]), math.sin(self.odom[2])
            self.odom += [c*delta[0]-s*delta[1], s*delta[0]+c*delta[1], delta[2]]
        change = None if self.anchor is None else self.odom-self.anchor
        changed = change is None or motion.moved(change)
        update = bool(len(points) and (changed or self.policy.new_view(servo)))
        audit = None
        if update:
            prior = self._weights()
            # Bound temporary arrays; same pinned likelihood for every particle.
            ll = np.concatenate([np.log(field.likelihood(self.field, p, points))
                                 for p in np.array_split(self.px, max(1, math.ceil(self.n/4096)))])
            self.logw = np.log(np.maximum(prior, 1e-300))+ll
            self.logw -= self.logw.max()
            audit = self.policy.measure(self, prior, ll, servo, changed)
            self.anchor = self.odom.copy()
            self.updates += 1
        mean, cov, report = augmented.belief_report(self.px, self._weights())
        return dict(t=float(t), pose=mean.tolist(), covariance=cov.tolist(), **report,
            n=self.n, updated=update, reason='sensor_update' if update else 'motion_gate' if len(points) else 'no_points',
            updates=self.updates, resamples=self.stats['resamples'], sensor=audit)


def plan_to_remembered_goal(grid, pose, target):
    """Existing v8 NavFn adapter; no rollout or false physical success claim."""
    if target is None:
        return dict(status='goal_unobserved', path_m=[])
    from harness.public_navigation_monitor import MonitorNavigator
    from harness.public_navigation_unknown import UnknownCostmap
    f = GridField(grid)
    cm = UnknownCostmap(f.raw.copy(), f.grid_origin, f.grid_resolution)
    mask, _ = cm.footprint_mask(np.asarray(pose))
    cm.raw[mask] = 0  # existing Nav2 footprint clearing, planning only
    cm.costs = cm.inflate()
    path = MonitorNavigator().plan_to(cm, pose, target)
    return dict(status='planned' if path else 'no_path', path_m=path)
