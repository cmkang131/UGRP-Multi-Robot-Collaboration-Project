"""Own-map RBPF: Grisetti 2007 improved Gaussian proposal + selective resampling.

This is mapping, not localization in a supplied map. Each particle owns its
log-odds grid. No particle is selected using evaluation truth. Settings frozen
before implementation in the experiment README section 19.
"""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import asdict, dataclass
import math

import numpy as np
from scipy.ndimage import distance_transform_edt, map_coordinates
from scipy.special import logsumexp

from harness.self_map_csm import CSMOptions, CorrectedOdomGrid, sample_segments
from harness.self_map_prob import (V7CommandOdometry, V7_SOURCE, V7_COMMAND_SIGMA,
                                  likelihood, moments, offsets_grid, sensor_sigma, wrap)
from harness.self_odom_grid import OdomGrid, transform


@dataclass(frozen=True)
class RBPFOptions:
    particles: int = 30
    seed: int = 20261006

    def __post_init__(self):
        if type(self.particles) is not int or self.particles not in (30, 100):
            raise ValueError('RBPF_PARTICLES_REQUIRE_30_OR_100')
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError('RBPF_INVALID_SEED')


class GridField:
    """Likelihood field from a particle's pre-insertion occupied grid only."""
    def __init__(self, points, resolution=.05):
        self.resolution = resolution
        self.origin = np.floor((points.min(0)-1.)/resolution)*resolution
        size = np.ceil((points.max(0)+1.-self.origin)/resolution).astype(int)+1
        grid = np.ones(tuple(size), bool)
        ij = np.rint((points-self.origin)/resolution).astype(int)
        grid[ij[:, 0], ij[:, 1]] = False
        self.distance = distance_transform_edt(grid)*resolution

    def query(self, points):
        ij = ((points.reshape(-1, 2)-self.origin)/self.resolution).T
        return map_coordinates(self.distance, ij, order=1, mode='constant', cval=10.).reshape(points.shape[:-1])


def log_normal(offset, covariance):
    offset = np.atleast_2d(offset)
    return -.5*(np.einsum('ni,ij,nj->n', offset, np.linalg.inv(covariance), offset)+
                3*math.log(2*math.pi)+np.linalg.slogdet(covariance)[1])


def importance_increment(log_likelihood, pose, prior_mean, prior_cov, proposal_mean, proposal_cov):
    """Eq.6 uses the actual Gaussian proposal, not an uncorrected likelihood."""
    a, b = np.asarray(pose)-prior_mean, np.asarray(pose)-proposal_mean
    a[2], b[2] = wrap(a[2]), wrap(b[2])
    return float(log_likelihood+log_normal(a, prior_cov)[0]-log_normal(b, proposal_cov)[0])


def improved_proposal(field, points, camera, prior, covariance, rng, options):
    """Scan-match mode, local product moments, sample, exact importance ratio.

    A failed match falls back to the motion proposal (Eq.8). Sensor failure does
    not silently reset weights: its likelihood still participates in weighting.
    """
    sigma = sensor_sigma(points, camera, options)
    step = np.array([.1, .1, math.radians(2.)])
    coarse = offsets_grid([5, 5, 4], step)
    sensor = likelihood(field, points, prior+coarse, sigma)
    # MAP registration includes the motion prior as in the paper's Eq.21.
    cost = sensor+log_normal(coarse, covariance)
    mode = coarse[int(np.argmax(cost))]
    fine_step = np.minimum([.05, .05, math.radians(1.)], np.sqrt(np.diag(covariance)))
    offsets = mode+offsets_grid([3, 3, 3], fine_step)
    # Include the prior mode when registration moved the local integration box.
    # These are quadrature samples for a Gaussian approximation, not a discrete PF.
    offsets = np.unique(np.vstack([offsets, np.zeros((1, 3))]), axis=0)
    log_l = likelihood(field, points, prior+offsets, sigma)
    log_product = log_l+log_normal(offsets, covariance)
    best = offsets[int(np.argmax(log_product))]
    distances = field.query(transform(points, prior+best))
    overlap = float(np.mean(distances <= options.overlap_distance_m))
    residual = float(np.sqrt(np.mean(distances**2)))
    boundary = bool(np.any(abs(best) >= np.array([.5, .5, math.radians(8.)])))
    reason = ('search_boundary' if boundary else 'low_overlap' if overlap < options.min_overlap else
              'high_residual' if residual > options.max_residual_m else 'improved_proposal')
    event = {'reason': reason, 'overlap': overlap, 'residual_m': residual, 'search_boundary': boundary,
             'candidates': len(coarse)+len(offsets)}
    if reason == 'improved_proposal':
        delta, cov, weights = moments(offsets, log_product)
        # Numerical jitter only; no claimed confidence below machine precision.
        cov = cov+np.eye(3)*1e-10
        mean = prior+delta
        sample = rng.multivariate_normal(mean, cov)
        ll = float(likelihood(field, points, sample, sigma)[0])
        log_weight = importance_increment(ll, sample, prior, covariance, mean, cov)
        event.update(proposal_mean=mean.tolist(), proposal_covariance=cov.tolist(),
                     posterior_effective_candidates=float(1/(weights@weights)),
                     proposal='scan_matched_gaussian', log_weight_increment=log_weight)
    else:
        sample = rng.multivariate_normal(prior, covariance)
        log_weight = float(likelihood(field, points, sample, sigma)[0])
        event.update(proposal='motion_fallback', log_weight_increment=log_weight)
    sample[2] = wrap(sample[2])
    return sample, log_weight, event


def systematic_indices(weights, rng):
    positions = (rng.random()+np.arange(len(weights)))/len(weights)
    cumulative = np.cumsum(weights)
    cumulative[-1] = 1.
    return np.searchsorted(cumulative, positions)


class CloudOdometry:
    """Command facade: one mean drive integrator propagates every own hypothesis."""
    def __init__(self, owner, start_time, profiles):
        self.owner = owner
        self.driver = V7CommandOdometry(start_time, profiles)
        self.driver.step_callback = owner.propagate

    def __getattr__(self, name):
        return getattr(self.driver, name)

    @property
    def pose(self):
        return tuple(float(x) for x in self.owner.poses[self.owner.best])

    @property
    def covariance(self):
        w = self.owner.weights
        p = self.owner.poses.copy()
        yaw = math.atan2(w@np.sin(p[:, 2]), w@np.cos(p[:, 2]))
        p[:, 2] = wrap(p[:, 2]-yaw)
        center = w@p
        delta = p-center
        return (delta.T*w)@delta+np.einsum('n,nij->ij', w, self.owner.pending_cov)

    def advance(self, t):
        self.driver.advance(t)
        return self.pose

    def command(self, row):
        self.driver.command(row)


class RaoBlackwellizedGrid(OdomGrid):
    # Reuse exactly the validated own-record/cartesian input adapters.
    observe = CorrectedOdomGrid.observe
    observe_contacts = CorrectedOdomGrid.observe_contacts

    def __init__(self, robot_id, *, correction_options=None, **kwargs):
        super().__init__(robot_id, **kwargs)
        if self.resolution_m != .1:
            raise ValueError('RBPF_REQUIRES_010M_GRID')
        self.rbpf_options = RBPFOptions(**(correction_options or {}))
        self.options = CSMOptions()
        self.rng = np.random.default_rng(self.rbpf_options.seed)
        n = self.rbpf_options.particles
        self.poses = np.zeros((n, 3))
        self.pending_cov = np.repeat(self.options.floor()[None], n, 0)
        self.weights = np.full(n, 1/n)
        self.log_weights = np.log(self.weights)
        self.best = 0
        self.maps = [OdomGrid(robot_id, **kwargs) for _ in range(n)]
        self.histories = [[] for _ in range(n)]
        self.odom = CloudOdometry(self, kwargs.get('start_time', 0.), kwargs.get('profiles'))
        self.decisions, self.ledger = [], []
        self.last_attempt = -math.inf
        self.resamples, self.revision = 0, 0

    def propagate(self, body_delta, body_variance):
        c, s = np.cos(self.poses[:, 2]), np.sin(self.poses[:, 2])
        delta = np.column_stack([c*body_delta[0]-s*body_delta[1], s*body_delta[0]+c*body_delta[1],
                                 np.full(len(c), body_delta[2])])
        F = np.repeat(np.eye(3)[None], len(c), 0)
        F[:, 0, 2], F[:, 1, 2] = -delta[:, 1], delta[:, 0]
        R = np.zeros_like(F)
        R[:, 0, 0], R[:, 0, 1], R[:, 1, 0], R[:, 1, 1], R[:, 2, 2] = c, -s, s, c, 1.
        self.pending_cov = F@self.pending_cov@F.transpose(0, 2, 1)+(R*body_variance)@R.transpose(0, 2, 1)
        self.poses += delta
        self.poses[:, 2] = wrap(self.poses[:, 2])

    def resample_if_needed(self):
        neff = float(1/(self.weights@self.weights))
        if neff >= len(self.weights)/2:
            return neff, None
        indices = systematic_indices(self.weights, self.rng)
        maps = []
        for i in indices:
            # Map data is copied, while read-only configuration may be shared.
            grid = copy.copy(self.maps[i])
            grid.cells = self.maps[i].cells.copy()
            maps.append(grid)
        # The selected particle survives deterministic selection if present. No
        # truth or average-pose/map mixing enters the selection after resampling.
        chosen = np.flatnonzero(indices == self.best)
        self.best = int(chosen[0]) if len(chosen) else 0
        self.maps = maps
        self.histories = [self.histories[i].copy() for i in indices]
        self.poses = self.poses[indices].copy()
        self.pending_cov = self.pending_cov[indices].copy()
        self.weights.fill(1/len(indices))
        self.log_weights = np.log(self.weights)
        self.resamples += 1
        return neff, indices.tolist()

    def _observe(self, rec, segments, *, camera_xy, robot_id):
        if robot_id != self.robot_id:
            raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
        key = (rec['t_sim'], rec['view_index'])
        if key in self.seen:
            return []
        camera = np.asarray(camera_xy, float)
        if camera.shape != (2,) or not np.isfinite(camera).all():
            raise ValueError('SELF_MAP_INVALID_CAMERA_ORIGIN')
        self.odom.advance(rec['t_sim'])
        self.seen.add(key)
        event = {'t': rec['t_sim'], 'frame_id': rec['view_index'], 'robot_id': robot_id,
                 'status': 'rejected', 'reason': 'unsettled', 'inserted': False}
        self.decisions.append(event)
        if self.settle_s is not None and (not self.odom.has_servo or
                self.odom.t-self.odom.servo_since+1e-8 < self.settle_s[int(self.odom.loaded)]):
            self.rejected['unsettled'] += 1
            return []
        cutoff = min(4., self.max_range_m if self.max_range_m is not None else 4.)
        local = [np.asarray(s) for s in segments if np.linalg.norm(np.asarray(s)-camera, axis=1).max() < cutoff]
        self.rejected['range_segments'] += len(segments)-len(local)
        if not local:
            event['reason'] = 'no_near_geometry'
            return []
        points = sample_segments(local)
        attempt = rec['t_sim']-self.last_attempt >= 1.-1e-8 and len(points) >= self.options.min_points
        if attempt:
            self.last_attempt = rec['t_sim']
        particle_events = []
        inserted = []
        for i, grid in enumerate(self.maps):
            reason = 'keyframe_interval' if len(points) >= self.options.min_points else 'insufficient_match_points'
            pe = {'particle': i, 'reason': reason, 'proposal': 'deferred'}
            eligible = True
            if attempt:
                past = grid.occupied_points()
                past = past[np.linalg.norm(past-self.poses[i, :2], axis=1) <= 6.]
                cov = self.pending_cov[i]+np.eye(3)*1e-10
                if len(past) >= self.options.min_points:
                    field = GridField(past)
                    pose, increment, details = improved_proposal(field, points, camera, self.poses[i], cov, self.rng, self.options)
                    self.poses[i] = pose
                    self.log_weights[i] += increment
                    pe.update(details)
                    eligible = pe['reason'] == 'improved_proposal'
                else:
                    # First scan conditions only on motion, no fabricated likelihood.
                    self.poses[i] = self.rng.multivariate_normal(self.poses[i], cov)
                    self.poses[i, 2] = wrap(self.poses[i, 2])
                    pe.update(reason='bootstrap', proposal='motion_bootstrap')
                self.pending_cov[i] = np.eye(3)*1e-10
            else:
                # Each inserted scan must be conditioned on a sampled trajectory,
                # not an unsampled Gaussian mean shared by all deferred maps.
                self.poses[i] = self.rng.multivariate_normal(self.poses[i], self.pending_cov[i])
                self.poses[i, 2] = wrap(self.poses[i, 2])
                self.pending_cov[i] = np.eye(3)*1e-10
                pe['proposal'] = 'motion_deferred_no_sensor_weight'
            pe.update(inserted=eligible, pose=self.poses[i].tolist())
            if eligible:
                pose = self.poses[i]
                grid.insert(transform([camera], pose)[0], [transform(s, pose) for s in local])
                self.histories[i].append({'t': rec['t_sim'], 'frame_id': rec['view_index'], 'pose': pose.tolist(),
                                          'camera': camera.tolist(), 'segments': [s.tolist() for s in local]})
                inserted.append(i)
            particle_events.append(pe)
        self.log_weights -= logsumexp(self.log_weights)
        self.weights = np.exp(self.log_weights)
        self.best = int(np.argmax(self.weights))
        selected = self.best
        neff, parents = self.resample_if_needed() if attempt else (float(1/(self.weights@self.weights)), None)
        self.cells = self.maps[self.best].cells
        self.frames = self.maps[self.best].frames
        self.ledger = self.histories[self.best]
        chosen = particle_events[selected]
        self.revision += bool(chosen['inserted'])
        event.update(reason=chosen['reason'], status=('bootstrap' if chosen['reason'] == 'bootstrap' else
                     'accepted' if chosen['reason'] == 'improved_proposal' else 'deferred' if not attempt else 'rejected'),
                     inserted=chosen['inserted'], matching_attempted=attempt, particle_events=particle_events,
                     selected_before_resampling=selected, selected_after_resampling=self.best,
                     neff=neff, resampled=parents is not None, parent_indices=parents,
                     pose=list(self.odom.pose), covariance=self.odom.covariance.tolist(),
                     inserted_particles=len(inserted), map_revision_after=self.revision)
        return local if chosen['inserted'] else []

    def text(self):
        return super().text().replace('drift uncorrected', 'drift uncertain')

    def export(self):
        out = super().export()
        out.update(pose_correction='own_map_rbpf_v1', options=asdict(self.rbpf_options),
                   covariance=self.odom.covariance.tolist(), weights=self.weights.tolist(),
                   particle_poses=self.poses.tolist(), selected_particle=self.best, resamples=self.resamples,
                   particle_cell_counts=[len(g.cells) for g in self.maps],
                   correction_counts=dict(Counter(e['reason'] for e in self.decisions)),
                   noise_source=V7_SOURCE, command_sigma=V7_COMMAND_SIGMA,
                   selection='online_max_weight_particle_with_its_own_map')
        return out
