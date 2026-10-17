"""Causal own RGB occupancy mapping and opt-in AMCL map augmentation.

Textbook log-odds (Probabilistic Robotics ch9). Sensor probabilities, .05m
resolution and .1/.9 clamping are Cartographer's public 2D defaults, NOT fits
to trajectory truth. No simulator, evaluation file, spawn or peer inputs.
This is a conditional single-map approximation, not a full SLAM posterior.
"""
import math
import numpy as np
from scipy.ndimage import distance_transform_edt
from harness.self_odom_grid import transform
from harness.grid_acceleration import dda as ray_cells

OPTION = 'selfmap_own_grid_v1'
# https://github.com/cartographer-project/cartographer/blob/master/configuration_files/trajectory_builder_2d.lua
# https://github.com/cartographer-project/cartographer/blob/master/cartographer/mapping/probability_values.h
RESOLUTION = .05
HIT = math.log(.55/.45)
MISS = math.log(.49/.51)
LIMIT = math.log(.9/.1)
# Diagnostic eligibility: require the upstream saturation probability AND at
# least the number of distinct-frame hits needed to reach it from prior .5.
# This is a derived policy, NOT an upstream localization acceptance default.
# Count does not establish independence of adjacent RGB images.
MIN_HITS = math.ceil(LIMIT/HIT)


def endpoints(scan):
    """Only actually observed returns; missing columns remain unknown."""
    camera = np.asarray(scan.get('camera') or [0., 0.], float)
    points = [camera+v['range_m']*np.array([math.cos(v['bearing_rad']), math.sin(v['bearing_rad'])])
              for v in scan.get('columns', [])
              if v.get('status') == 'hit' and v.get('range_m') is not None]
    if not scan.get('columns'):
        points = np.unique(np.asarray(scan.get('segments', []), float).reshape(-1, 2), axis=0)
    points = np.asarray(points, float).reshape(-1, 2)
    if not np.isfinite(camera).all() or not np.isfinite(points).all():
        raise ValueError('NONFINITE_OWN_RAYS')
    return camera, points


class OwnGrid:
    def __init__(self):
        self.cells = {}  # (ix,iy): [log_odds, distinct hit frames, free frames]
        self.last_t = None
        self.version = 0
        self.rows = []

    def insert(self, t, pose, scan):
        if self.last_t is not None and t <= self.last_t:
            raise ValueError('NONCAUSAL_OWN_GRID')
        self.last_t = t
        camera, points = endpoints(scan)
        event = dict(t=t, reason='no_pose' if pose is None else 'no_visible_return',
                     blocked_object='own_observed_geometry_identity_unmeasured',
                     minimum_gap_m=None, gap_status='not_measured', hits=0, free=0)
        if pose is not None and len(points):
            camera = transform([camera], pose)[0]
            points = transform(points, pose)
            hit, free = set(), set()
            for p in points:
                keys = ray_cells(camera, p, RESOLUTION)
                hit.add(keys[-1]); free.update(keys[:-1])
            free -= hit  # upstream gives hits priority; one update/cell/frame
            for keys, increment, count_index in ((hit, HIT, 1), (free, MISS, 2)):
                for key in keys:
                    row = self.cells.setdefault(key, [0., 0, 0])
                    row[0] = float(np.clip(row[0]+increment, -LIMIT, LIMIT))
                    row[count_index] += 1
            event.update(reason='inserted_unqualified_pose', hits=len(hit), free=len(free))
            self.version += 1
        self.rows.append(event)
        return event

    def stable_points(self):
        return np.asarray([((x+.5)*RESOLUTION, (y+.5)*RESOLUTION)
            for (x, y), (l, hits, _) in self.cells.items()
            if l >= LIMIT and hits >= MIN_HITS], float).reshape(-1, 2)

    def export(self):
        return dict(resolution_m=RESOLUTION, hit_probability=.55, miss_probability=.49,
                    clamp_probability=[.1, .9], stable_min_hits=MIN_HITS,
                    stable_probability=.9, truth_inputs=0, production_qualified=False,
                    conditional_on_unqualified_amcl_proposals=True,
                    cells=[[x,y,*self.cells[x,y]] for x,y in sorted(self.cells)])


class AugmentedField:
    """Union of authored static occupancy and saturated *past* own cells.

    The unchanged Nav2 sensor model scores ONE field; no second independent
    likelihood or arbitrary likelihood multiplier. Static walls cannot be
    erased by own free-space votes. Pure localization/submap literature
    motivates retaining an immutable reference; this union policy is our
    explicit unqualified adapter, not claimed to implement Cartographer.
    """
    def __init__(self, static, grid, *, option='off'):
        if option not in ('off', OPTION):
            raise ValueError('UNKNOWN_OWN_GRID_OPTION')
        self.static, self.grid, self.option = static, grid, option
        self.free = static.free
        self.version = -1
        self.last_reference_t = None
        self.stable_n = 0
        self.own_dist = None
        self.queries = 0

    def distances(self, points):
        result = self.static.distances(points)
        if self.option == 'off':
            return result
        if self.version != self.grid.version:
            stable = self.grid.stable_points()
            self.stable_n = len(stable)
            self.last_reference_t = self.grid.last_t
            self.own_dist = None
            if len(stable):
                # Two metres is the unchanged Nav2 maximum field distance.
                self.origin = np.floor((stable.min(0)-2.)/RESOLUTION)*RESOLUTION
                size = np.ceil((stable.max(0)+2.-self.origin)/RESOLUTION).astype(int)+1
                occ = np.zeros(tuple(size[::-1]), bool)
                ij = np.floor((stable-self.origin)/RESOLUTION).astype(int)
                occ[ij[:,1],ij[:,0]] = True
                self.own_dist = np.minimum(2., distance_transform_edt(~occ)*RESOLUTION)
            self.version = self.grid.version
        self.queries += 1
        if self.own_dist is not None:
            ij = np.floor((np.asarray(points)-self.origin)/RESOLUTION).astype(int)
            x,y = ij[...,0],ij[...,1]
            valid = (x>=0)&(y>=0)&(x<self.own_dist.shape[1])&(y<self.own_dist.shape[0])
            own = np.full(x.shape, 2.)
            own[valid] = self.own_dist[y[valid],x[valid]]
            result = np.minimum(result, own)
        return result
