"""Default-off, unknown-start AMCL for static maps and own RGB measurements.

Nav2 b58a7573: omni odometry, cubic likelihood field, augmented recovery,
multinomial KLD resampling. Only the sensor adapter is project-specific: the
PR480 wall endpoints / floor-zone boundary lines replace laser returns.
No initial pose, cargo pose, evaluator, simulator or peer-state API exists.
"""
from dataclasses import dataclass, asdict
from contextlib import nullcontext
import math

import numpy as np

from harness.e2e_static_rgb_localizer import StaticRGBLocalizer
from harness.ego_pose_continuity import dominant_cluster
from harness.own_map_amcl_vendor import augmented, field
from harness.own_map_amcl_vendor.landmarks import MapFeatures, landmark_likelihood

OPTIONS = ('off', 'amcl_walls_v1', 'amcl_landmarks_v1')


@dataclass(frozen=True)
class Parameters:
    min_particles: int = 500
    max_particles: int = 2000
    pf_err: float = .05
    # Nav2 passes pf_z directly to the Wilson-Hilferty expression. It does NOT
    # apply inverse_normal(.99); keep that implementation convention explicit.
    pf_z: float = .99
    recovery_alpha_slow: float = .001
    recovery_alpha_fast: float = .1
    alpha: float = .2  # Nav2 alpha1..alpha5 defaults, omnidirectional robot
    update_min_d: float = .25
    update_min_a: float = .2
    resample_interval: int = 1
    max_beams: int = 60
    max_landmarks: int = 32

    def __post_init__(self):
        if (not isinstance(self.min_particles, int) or not isinstance(self.max_particles, int)
                or not 2 <= self.min_particles <= self.max_particles <= 100000):
            raise ValueError('INVALID_PARTICLE_BUDGET')
        if (type(self.resample_interval) is not int or self.resample_interval < 1 or
                type(self.max_beams) is not int or not 1 <= self.max_beams <= 60 or
                type(self.max_landmarks) is not int or not 1 <= self.max_landmarks <= 32):
            raise ValueError('INVALID_MEASUREMENT_BUDGET')
        if (not all(math.isfinite(x) for x in asdict(self).values()) or
                self.pf_err <= 0 or self.pf_z <= 0 or self.alpha < 0 or
                self.update_min_d < 0 or self.update_min_a < 0 or
                not 0 <= self.recovery_alpha_slow <= self.recovery_alpha_fast <= 1):
            raise ValueError('INVALID_AMCL_PARAMETERS')


def create(static_map, *, option='off', seed=64001, parameters=None, profile='off', metrics=None):
    from harness.map_amcl_profiles import parameters_for
    configured = parameters_for(profile)
    if profile != 'off' and parameters is not None:
        raise ValueError('PROFILE_AND_PARAMETERS_ARE_EXCLUSIVE')
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_MAP_AMCL_OPTION')
    if option == 'off':
        return None  # do not even inspect the map on the legacy path
    pf = AMCL(static_map, option=option, seed=seed, parameters=parameters or configured)
    pf.metrics = metrics
    return pf


def sample_limit(bins, p):
    """Nav2 pf_resample_limit, including the k<=1 maximum convention."""
    if bins <= 1:
        return p.max_particles
    x = 1 - 2 / (9 * (bins - 1)) + math.sqrt(2 / (9 * (bins - 1))) * p.pf_z
    return min(p.max_particles, max(p.min_particles,
               math.ceil((bins - 1) / (2 * p.pf_err) * x**3)))


def compose(pose, delta):
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return np.array([pose[0] + c*delta[0] - s*delta[1],
                     pose[1] + s*delta[0] + c*delta[1],
                     math.atan2(math.sin(pose[2]+delta[2]), math.cos(pose[2]+delta[2]))])


def between(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    x, y = b[:2] - a[:2]
    return np.array([c*x+s*y, -s*x+c*y,
                     math.atan2(math.sin(b[2]-a[2]), math.cos(b[2]-a[2]))])


class AMCL(StaticRGBLocalizer):
    """Feed one causal own-camera packet per step; deltas are body-frame SE(2).

    The stored cloud advances at accepted observation epochs, as Nav2 does.
    Between epochs, the report is command-extrapolated (no extra measurement
    or repeated weighting). Camera-pan changes count as a new sensor view.
    Unresolved reports remain estimates, never a navigation-success signal.
    """
    def __init__(self, static_map, *, option, seed, parameters):
        if option not in OPTIONS[1:]:
            raise ValueError('EXPLICIT_MAP_AMCL_OPTION_REQUIRED')
        bounds = np.asarray(static_map['bounds_m'], float)
        if (bounds.shape != (4,) or not np.isfinite(bounds).all() or
                bounds[1] <= bounds[0] or bounds[3] <= bounds[2]):
            raise ValueError('FINITE_STATIC_BOUNDS_REQUIRED')
        self.option, self.parameters = option, parameters
        self.field = field.Field(static_map)
        self.bounds = bounds
        self.rng = np.random.default_rng(seed)
        self.n = parameters.max_particles
        # Reuse PR480 rejection sampling over static free geometry only.
        self.px = self._uniform_free(self.n)
        self.logw = np.zeros(self.n)
        self.landmark_map = MapFeatures(static_map) if option == 'amcl_landmarks_v1' else None
        self.odom = np.zeros(3)
        self.anchor = np.zeros(3)
        self.seen = set()
        self.last_t = None
        self.w_slow = self.w_fast = 0.
        self.updates = self.resamples = 0
        self.metrics = None

    def timed(self, name):
        return self.metrics.measure(name) if self.metrics is not None else nullcontext()

    def measurement_due(self, delta, servo):
        """Peek before expensive RGB extraction; do not consume motion/view state.

        ROS AMCL tests axis displacement from the last accepted update, not
        elapsed time or the most recent command. A new commanded camera view is
        the existing RGB adaptation; it is consumed only by a usable update.
        """
        delta = np.asarray(delta, float)
        if delta.shape != (3,) or not np.isfinite(delta).all():
            raise ValueError('CAUSAL_FINITE_OWN_PACKET_REQUIRED')
        odom = compose(self.odom, delta)
        pending = between(self.anchor, odom)
        changed = (np.any(abs((odom-self.anchor)[:2]) > self.parameters.update_min_d) or
                   abs(pending[2]) > self.parameters.update_min_a)
        view = tuple(int(servo[k]) for k in (3, 4, 5, 6))
        return bool(not self.updates or changed or view not in self.seen)

    def _measurement_score(self, points, features):
        p = self.parameters
        if len(points) > p.max_beams:
            points = points[np.linspace(0, len(points)-1, p.max_beams, dtype=int)]
        if len(features) > p.max_landmarks:
            features = [features[i] for i in np.linspace(0, len(features)-1, p.max_landmarks, dtype=int)]
        score = field.likelihood(self.field, self.px, points)
        if features:
            score *= landmark_likelihood(self.landmark_map, self.px, features)
        return score

    def _predict(self, delta):
        distance = math.hypot(delta[0], delta[1])
        yaw = delta[2]
        sigma = math.sqrt(self.parameters.alpha * (distance**2 + yaw**2))
        noise = self.rng.normal(0., sigma, (self.n, 3))
        bearing = self.px[:, 2] + math.atan2(delta[1], delta[0])
        c, s = np.cos(bearing), np.sin(bearing)
        self.px[:, 0] += (distance+noise[:, 0])*c + noise[:, 2]*s
        self.px[:, 1] += (distance+noise[:, 0])*s - noise[:, 2]*c
        angle = self.px[:, 2] + yaw + noise[:, 1]
        self.px[:, 2] = np.arctan2(np.sin(angle), np.cos(angle))

    def _resample(self, probability):
        p = self.parameters
        cdf = np.cumsum(self._weights())
        cdf[-1] = 1.
        poses, occupied = [], set()
        injected = 0
        limit = p.max_particles
        for _ in range(p.max_particles):
            if self.rng.random() < probability:
                pose = self._uniform_free(1)[0]
                injected += 1
            else:
                pose = self.px[min(np.searchsorted(cdf, self.rng.random(), side='right'), self.n-1)]
            poses.append(pose)
            key = tuple(np.floor(pose / [.5, .5, math.pi/18]).astype(int))
            if key not in occupied:
                occupied.add(key)
                limit = sample_limit(len(occupied), p)
            if len(poses) > limit:  # Nav2 uses strict >, capped by max_particles
                break
        self.px = np.asarray(poses).copy()
        self.n = len(poses)
        self.logw = np.zeros(self.n)
        self.resamples += 1
        if probability > 0:
            self.w_slow = self.w_fast = 0.
        return dict(injected=injected, occupied_bins=len(occupied), kld_limit=limit,
                    samples_after=self.n, capped=self.n == p.max_particles)

    def step(self, *, t, points, delta, servo, features=None):
        t = float(t)
        delta = np.asarray(delta, float)
        points = np.asarray(points, float).reshape(-1, 2)
        if (not math.isfinite(t) or (self.last_t is not None and t <= self.last_t) or
                delta.shape != (3,) or not np.isfinite(delta).all() or not np.isfinite(points).all()):
            raise ValueError('CAUSAL_FINITE_OWN_PACKET_REQUIRED')
        features = features or []
        if len(features) > 32:
            raise ValueError('FEATURE_BUDGET_EXCEEDED')
        # Explicit whitelist: a cargo/robot landmark is never accepted.
        for f in features:
            keys = ('endpoints', 'normal', 'hue') if f.get('kind') == 'floor_line' else ('center', 'width')
            if f.get('kind') not in ('floor_line', 'door'):
                raise ValueError('STATIC_RGB_FEATURES_ONLY')
            if any(not np.isfinite(np.asarray(f[k], float)).all() for k in keys):
                raise ValueError('FINITE_STATIC_RGB_FEATURES_REQUIRED')
            if f['kind'] == 'floor_line':
                if (np.shape(f['endpoints']) != (2, 2) or np.shape(f['normal']) != (2,) or
                        np.shape(f['hue']) != () or not 0 <= f['hue'] <= 180 or
                        not np.isclose(np.linalg.norm(f['normal']), 1., atol=1e-3)):
                    raise ValueError('INVALID_FLOOR_LINE_GEOMETRY')
            elif np.shape(f['center']) != (2,) or np.shape(f['width']) != () or f['width'] <= 0:
                raise ValueError('INVALID_DOOR_GEOMETRY')
        view = tuple(int(servo[k]) for k in (3, 4, 5, 6))
        self.last_t = t
        self.odom = compose(self.odom, delta)
        pending = between(self.anchor, self.odom)
        changed = (np.any(abs((self.odom-self.anchor)[:2]) > self.parameters.update_min_d) or
                   abs(pending[2]) > self.parameters.update_min_a)
        usable_features = features if self.landmark_map is not None else []
        update = bool((len(points) or usable_features) and
                      (not self.updates or changed or view not in self.seen))
        audit = None
        if update:
            with self.timed('motion_model'):
                self._predict(pending)
            with self.timed('measurement_model'):
                score = self._measurement_score(points, usable_features)
            if not np.isfinite(score).all() or np.any(score <= 0):
                raise ValueError('FINITE_POSITIVE_SENSOR_SCORE_REQUIRED')
            prior = self._weights()
            avg = float(prior @ score / self.n)  # before normalization/max-shift
            p = self.parameters
            self.w_slow = avg if self.w_slow == 0 else self.w_slow+p.recovery_alpha_slow*(avg-self.w_slow)
            self.w_fast = avg if self.w_fast == 0 else self.w_fast+p.recovery_alpha_fast*(avg-self.w_fast)
            probability = max(0., 1-self.w_fast/self.w_slow) if self.w_slow > 0 else 0.
            self.logw = np.log(np.maximum(prior, 1e-300)) + np.log(score)
            audit = dict(w_avg=avg, w_slow=self.w_slow, w_fast=self.w_fast,
                         injection_probability=probability, samples_before=self.n)
            # Count accepted sensor updates, never frames or elapsed time.
            if (self.updates+1) % p.resample_interval == 0:
                with self.timed('resample'):
                    audit.update(self._resample(probability))
            if changed:
                self.seen.clear()
            self.seen.add(view)
            self.anchor = self.odom.copy()
            pending = np.zeros(3)
            self.updates += 1
        # Extrapolate each hypothesis, preserving multimodality and its mass.
        cloud = self.px.copy()
        c, s = np.cos(cloud[:, 2]), np.sin(cloud[:, 2])
        cloud[:, 0] += c*pending[0] - s*pending[1]
        cloud[:, 1] += s*pending[0] + c*pending[1]
        cloud[:, 2] = np.arctan2(np.sin(cloud[:, 2]+pending[2]), np.cos(cloud[:, 2]+pending[2]))
        mean, covariance, report = augmented.belief_report(cloud, self._weights())
        # Pending motion uncertainty must not disappear in prediction-only reports.
        variance = self.parameters.alpha * (float(pending[:2] @ pending[:2])+pending[2]**2)
        covariance += np.eye(3)*variance
        report['global_std_xy_m'] = float(np.sqrt(np.trace(covariance[:2, :2])))
        report['circular_yaw_std_rad'] = float(np.sqrt(covariance[2, 2]))
        report['resolved'] = bool(report['resolved'] and covariance[2, 2] <= math.radians(5)**2)
        pose, cluster = dominant_cluster(cloud, self._weights())
        return dict(t=t, pose=pose.tolist(), full_posterior_pose=mean.tolist(),
                    covariance=covariance.tolist(), cluster=cluster, **report,
                    updated=update, n=self.n, updates=self.updates, resamples=self.resamples,
                    sensor=audit, option=self.option, initial_pose_source='uniform_static_free_space',
                    reason='sensor_update' if update else 'motion_gate' if len(points) or usable_features else 'no_points')
