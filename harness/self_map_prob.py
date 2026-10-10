"""Opt-in pose probability primitives. See experiment README section 19.

Only issued commands and own-camera contacts enter this module. The v7 source
is a parameter provenance, never imported (in particular, no MuJoCo dependency).
"""
from __future__ import annotations

import math
import numpy as np
from scipy.special import logsumexp

from harness.self_odom_grid import CommandOdometry, motion_profiles, transform
from harness.self_map_csm import CSMOptions, CorrelativeMatcher, DistanceField
from harness.self_map_csm_v2 import CorrectedOdomGridV2

V7_SOURCE = 'e7b229b6d9809ddf18f345dd179d60d499fce3dd:sim/masterpi_drive_friction_v7.py'
V7_COMMAND_SIGMA = math.sqrt((.025**2+(1/12)**2)/3)


def wrap(angle):
    return (angle+math.pi) % (2*math.pi)-math.pi


def psd_floor(covariance, floor):
    """Loewner floor, including off-diagonal covariance; symmetric by construction."""
    value, vectors = np.linalg.eigh((covariance+covariance.T)/2-floor)
    return floor+(vectors*np.maximum(value, 0.))@vectors.T


def moments(offsets, log_weights):
    """Olson Eq.3 / Grisetti Eq.15-17, on a locally unwrapped yaw chart."""
    weights = np.exp(log_weights-logsumexp(log_weights))
    mean = weights@offsets
    centered = offsets-mean
    return mean, (centered.T*weights)@centered, weights


class V7CommandOdometry(CommandOdometry):
    """Unchanged M1 mean, v7-structured command-rate uncertainty, 1 s correlation.

    The uniform start/friction envelopes are assumptions, NOT measured v7 noise.
    callback is internal RBPF propagation, and receives no observed state.
    """
    def __init__(self, start_time=0., profiles=None, options=None):
        super().__init__(start_time, profiles)
        self.options = options or CSMOptions()
        self.profiles = motion_profiles() if profiles is None else profiles
        self.covariance = self.options.floor()
        self.step_callback = None

    def advance(self, t):
        t = float(t)
        if not math.isfinite(t) or t < self.t-1e-8:
            raise ValueError('SELF_MAP_NON_MONOTONIC_TIME')
        while self.t < t-1e-9:
            before, begin = np.array(self.pose), self.t
            end = min(t, begin+.05)
            if begin < self._predictor.cmd_expires < end:
                end = self._predictor.cmd_expires
            live = begin < self._predictor.cmd_expires and np.any(self._predictor.cmd)
            super().advance(end)
            dt = self.t-begin
            profile = self.profiles['motion_loaded' if self.loaded else 'motion']
            moving = live or np.max(np.abs(self._predictor.vel)) >= .001
            rate = np.abs(np.asarray(profile['gain']))@np.full(3, V7_COMMAND_SIGMA)
            variance = rate**2*dt if moving else np.zeros(3)
            if self.loaded:
                variance[:2] += .02**2*dt
            c, s = math.cos(before[2]), math.sin(before[2])
            rotation = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
            delta = np.array(self.pose)-before
            delta[2] = wrap(delta[2])
            F = np.eye(3)
            F[:2, 2] = [-delta[1], delta[0]]
            self.covariance = F@self.covariance@F.T+rotation@np.diag(variance)@rotation.T
            if self.step_callback is not None:
                self.step_callback(rotation.T@delta, variance)
        super().advance(t)
        return self.pose

    def correct(self, pose, covariance):
        self._predictor.px[0] = pose
        self._predictor.px[0, 2] = wrap(pose[2])
        self.covariance = np.asarray(covariance).copy()


def sensor_sigma(points, camera, options):
    radii = np.linalg.norm(points-camera, axis=1)
    return np.sqrt(options.calibration_floor_m**2+options.field_resolution_m**2/12+
                   (options.pixel_sigma*radii**2/(options.focal_y_px*options.height_lower_bound_m))**2)


def likelihood(field, points, poses, sigma, effective_points=12.):
    """Tempered robust distance-field likelihood, independent count capped at 12."""
    poses = np.atleast_2d(poses)
    c, s = np.cos(poses[:, 2]), np.sin(poses[:, 2])
    world = np.stack([c[:, None]*points[:, 0]-s[:, None]*points[:, 1],
                      s[:, None]*points[:, 0]+c[:, None]*points[:, 1]], -1)+poses[:, None, :2]
    distance = field.query(world)
    z = distance/sigma
    return -.5*np.sum(np.where(z <= 1.5, z*z, 3*z-2.25), axis=1)*min(1., effective_points/len(points))


def offsets_grid(counts, steps):
    return np.stack(np.meshgrid(*[np.arange(-n, n+1)*s for n, s in zip(counts, steps)],
                               indexing='ij'), -1).reshape(-1, 3)


class MomentMatcher(CorrelativeMatcher):
    def match(self, pose, covariance, points, camera, reference, anchor_covariance):
        event = super().match(pose, covariance, points, camera, reference, anchor_covariance)
        if event['status'] != 'accepted':
            return event
        o = self.options
        step = np.array([o.field_resolution_m]*2+[math.radians(o.yaw_step_deg)])
        offsets = offsets_grid(np.rint(np.array(event['search_window'])/step).astype(int), step)
        field = DistanceField(reference, o.field_resolution_m, o.translation_window_m+1.)
        logp = likelihood(field, points, np.asarray(pose)+offsets, sensor_sigma(points, camera, o), o.effective_points)
        logp -= .5*np.einsum('ni,ij,nj->n', offsets, np.linalg.inv(covariance), offsets)
        mean, sampled_cov, weights = moments(offsets, logp)
        # Posterior covariance is conditional on an uncertain submap. Never
        # mistake truncation or wall endpoints for along-wall information.
        D, S = np.diag([1., 1., 2.]), np.diag([1., 1., .5])
        V = np.array(event['observable_axes_scaled']).T
        # Complete the observable basis without depending on eigensolver ordering.
        _, _, vh = np.linalg.svd(V.T, full_matrices=True)
        N = vh[V.shape[1]:].T
        measured = psd_floor(V.T@D@sampled_cov@D@V,
                             V.T@D@(np.asarray(anchor_covariance)+o.floor())@D@V)
        C = S@(V@measured@V.T+N@(N.T@D@covariance@D@N)@N.T)@S
        event.update(covariance=C.tolist(), posterior_mean_delta=mean.tolist(),
                     posterior_moment_covariance=sampled_cov.tolist(), posterior_effective_candidates=float(1/(weights@weights)),
                     covariance_method='Olson_Eq3_observable_moments_anchor_nullspace_floor')
        return event


def insertion_weight(local_points, pose, covariance, options):
    rotated = transform(local_points, (0., 0., pose[2]))
    J = np.zeros((len(rotated), 2, 3))
    J[:, 0, 0], J[:, 1, 1] = 1., 1.
    J[:, 0, 2], J[:, 1, 2] = -rotated[:, 1], rotated[:, 0]
    variance = np.mean(np.einsum('nai,ij,naj->n', J, covariance, J)/2)
    return float(options.calibration_floor_m**2/(options.calibration_floor_m**2+variance))


class ProbabilisticOdomGrid(CorrectedOdomGridV2):
    def __init__(self, robot_id, *, correction_options=None, **kwargs):
        super().__init__(robot_id, correction_options=correction_options, **kwargs)
        self.odom = V7CommandOdometry(kwargs.get('start_time', 0.), kwargs.get('profiles'), self.options)
        self.matcher = MomentMatcher(self.options)
        self.insertion_weights = []

    def insert(self, camera, segments):
        # Only increment magnitudes change; occupied wins over free in one scan.
        world = np.asarray(segments).reshape(-1, 2)
        pose = self.odom.pose
        local = transform(world-np.array(pose[:2]), (0., 0., -pose[2]))
        weight = insertion_weight(local, pose, self.odom.covariance, self.options)
        hit, miss = self.hit, self.miss
        self.hit, self.miss = weight*hit, weight*miss
        try:
            super().insert(camera, segments)
        finally:
            self.hit, self.miss = hit, miss
        self.insertion_weights.append(weight)

    def _observe(self, *args, **kwargs):
        before = len(self.decisions)
        admitted = super()._observe(*args, **kwargs)
        if len(self.decisions) > before and self.decisions[-1]['inserted']:
            self.decisions[-1]['insertion_weight'] = self.insertion_weights[-1]
            self.ledger[-1]['insertion_weight'] = self.insertion_weights[-1]
        return admitted

    def export(self):
        out = super().export()
        out.update(pose_correction='own_map_csm_prob_v1', noise_source=V7_SOURCE,
                   command_sigma=V7_COMMAND_SIGMA, insertion_weights=self.insertion_weights)
        return out
