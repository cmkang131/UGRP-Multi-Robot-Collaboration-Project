"""Opt-in fourfold axial wall compass for an own-map RBPF.

Standard circular moments + Gaussian-mixture conditioning; no scene/GT input.
Source equations, frozen noise/cadence and limitations: egomap25 README.
"""
import math
from types import MethodType
import numpy as np
from scipy.special import logsumexp
from harness.self_map_prob import wrap

OPTION = 'manhattan_v1'
PERIOD = math.pi/2


def axis_observation(segments, sigma_floor_rad):
    """pycircstat mean(axial_correction=4) and std, weighted by line length."""
    lines = np.asarray(segments, dtype=float).reshape(-1, 2, 2)
    if not np.isfinite(lines).all():
        return None
    delta = lines[:, 1]-lines[:, 0]
    length = np.linalg.norm(delta, axis=1)
    valid = length > 1e-12
    if not np.any(valid):
        return None
    length = length[valid]
    alpha = np.arctan2(delta[valid, 1], delta[valid, 0])
    z = np.sum(length*np.exp(4j*alpha))/length.sum()
    rho = min(1., float(abs(z)))
    if rho < 1e-12:
        return None
    return dict(angle_rad=float(np.angle(z)/4), resultant=rho, segments=int(valid.sum()),
                length_m=float(length.sum()), variance_rad2=-2*math.log(rho)/16+sigma_floor_rad**2)


def condition(prior, covariance, axis, observation, rng):
    """Exact scalar linear-Gaussian product per 90-degree mode; sample mode.

    Sum over >=8 sigma of the unwrapped predictive Gaussian (tail truncation
    only). Cross covariance is preserved by the Joseph update, not zeroed.
    """
    p = np.asarray(covariance, float)
    r = observation['variance_rad2']
    s = float(p[2, 2]+r)
    residual = (axis-observation['angle_rad']-prior[2]+PERIOD/2) % PERIOD-PERIOD/2
    span = max(2, int(math.ceil(8*math.sqrt(s)/PERIOD)))
    branches = np.arange(-span, span+1)
    innovations = residual+branches*PERIOD
    log_likelihood = -.5*(innovations**2/s+math.log(2*math.pi*s))
    normalizer = float(logsumexp(log_likelihood))
    index = int(rng.choice(len(branches), p=np.exp(log_likelihood-normalizer)))
    innovation = innovations[index]
    gain = p[:, 2]/s
    mean = np.asarray(prior)+gain*innovation
    mean[2] = wrap(mean[2])
    identity_minus_kh = np.eye(3)
    identity_minus_kh[:, 2] -= gain
    posterior = identity_minus_kh@p@identity_minus_kh.T+np.outer(gain, gain)*r
    return mean, (posterior+posterior.T)/2, normalizer, dict(
        branch=int(branches[index]), innovation_rad=float(innovation), correction_rad=float(gain[2]*innovation))


def install(grid, *, yaw_prior='off'):
    if yaw_prior == 'off':
        return grid
    if yaw_prior != OPTION or not hasattr(grid, '_selective_state'):
        raise ValueError('MANHATTAN_REQUIRES_SELECTIVE_RBPF')
    if hasattr(grid, '_manhattan_axes'):
        raise ValueError('MANHATTAN_ALREADY_INSTALLED')
    grid._manhattan_axes = None
    grid._manhattan_events = []
    grid._manhattan_observer_base = grid._admitted_scan_observer
    grid._admitted_scan_observer = _observe
    grid._manhattan_resample_base = grid.resample_if_needed
    grid.resample_if_needed = MethodType(_resample, grid)
    grid._manhattan_export_base = grid.export
    grid.export = MethodType(_export, grid)
    return grid


def _observe(self, rec, segments, *, camera_xy, robot_id):
    # Called only by the unchanged motion gate. Preserve all admission checks.
    if robot_id != self.robot_id:
        raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
    camera = np.asarray(camera_xy, float)
    if camera.shape != (2,) or not np.isfinite(camera).all():
        raise ValueError('SELF_MAP_INVALID_CAMERA_ORIGIN')
    self.odom.advance(rec['t_sim'])
    duplicate = (rec['t_sim'], rec['view_index']) in self.seen
    unsettled = self.settle_s is not None and (not self.odom.has_servo or
        self.odom.t-self.odom.servo_since+1e-8 < self.settle_s[int(self.odom.loaded)])
    cutoff = min(4., self.max_range_m if self.max_range_m is not None else 4.)
    local = [s for s in segments if np.linalg.norm(np.asarray(s)-camera, axis=1).max() < cutoff]
    observation = None if duplicate or unsettled else axis_observation(local, math.radians(self.options.covariance_floor_yaw_deg))
    event = dict(t=rec['t_sim'], frame_id=rec['view_index'], status='no_direction', observation=observation)
    initialize = observation is not None and self._manhattan_axes is None
    if observation is not None and not initialize:
        log_likelihoods, corrections = [], []
        for i, axis in enumerate(self._manhattan_axes):
            self.poses[i], self.pending_cov[i], ll, detail = condition(
                self.poses[i], self.pending_cov[i], axis, observation, self.rng)
            log_likelihoods.append(ll)
            corrections.append(detail)
        self.log_weights += log_likelihoods
        self.log_weights -= logsumexp(self.log_weights)
        self.weights = np.exp(self.log_weights)
        self.best = int(np.argmax(self.weights))
        event.update(status='conditioned', particles=len(corrections),
                     nonnearest_modes=sum(d['branch'] != 0 for d in corrections),
                     max_abs_correction_deg=math.degrees(max(abs(d['correction_rad']) for d in corrections)),
                     neff_after_yaw=float(1/(self.weights@self.weights)))
    result = self._manhattan_observer_base(self, rec, segments, camera_xy=camera_xy, robot_id=robot_id)
    if initialize:
        # Bind uncertain axes to sampled first poses, not to an absolute world
        # direction or an independently re-drawn reference on every frame.
        self._manhattan_axes = wrap(self.poses[:, 2]+observation['angle_rad']+
            self.rng.normal(0., math.sqrt(observation['variance_rad2']), len(self.poses)))
        event['status'] = 'initialized'
    if not duplicate:
        self._manhattan_events.append(event)
        self.decisions[-1]['yaw_prior'] = event
    return result


def _resample(self):
    neff, parents = self._manhattan_resample_base()
    if parents is not None and self._manhattan_axes is not None:
        self._manhattan_axes = self._manhattan_axes[parents].copy()
    return neff, parents


def _export(self):
    out = self._manhattan_export_base()
    from collections import Counter
    out.update(yaw_prior=OPTION, manhattan=dict(
        counts=dict(Counter(e['status'] for e in self._manhattan_events)),
        particle_axes_rad=None if self._manhattan_axes is None else self._manhattan_axes.tolist(),
        angular_period_rad=PERIOD, sensor_floor_deg=self.options.covariance_floor_yaw_deg,
        reference='first own scan, per-particle uncertain latent axis'))
    return out
