"""Opt-in ESS and Gordon (1993) post-resampling roughening, shared consumers.

No new seed, sensor model, GT or process-global patches. The optional floor
is a preregistered engineering bound, not a calibrated accuracy certificate.
"""
import copy
import math
import numpy as np

from harness.pf_observation_consistency import _bind, _closure
from harness.zone_solo_cyan_bias_tempering import replace_cell

OPTIONS = ('off', 'ess_v1', 'roughen_v1', 'roughen_floor_v1')
SCALE = np.array([.02, .02, math.radians(1.)])


def residuals(poses, weights):
    p = np.asarray(poses, float)
    yaw = math.atan2(weights @ np.sin(p[:, 2]), weights @ np.cos(p[:, 2]))
    delta = p.copy()
    delta[:, 2] = np.arctan2(np.sin(p[:, 2]-yaw), np.cos(p[:, 2]-yaw))
    centre = weights @ delta
    return delta-centre, np.r_[centre[:2], yaw+centre[2]]


def covariance_floor(cov):
    scaled = np.asarray(cov)/SCALE[:, None]/SCALE[None, :]
    values, vectors = np.linalg.eigh((scaled+scaled.T)/2)
    return ((vectors*np.maximum(values, 1.)) @ vectors.T)*SCALE[:, None]*SCALE[None, :]


def summary(poses, weights):
    d, _ = residuals(poses, weights)
    cov = (d.T*weights) @ d
    return dict(ess=float(1/(weights@weights)), unique=int(len(np.unique(poses, axis=0))),
                covariance=cov.tolist(), eigenvalues=np.linalg.eigvalsh(cov).tolist())


def roughen(poses, rng):
    """Gordon eq. on p112: sigma_i = K E_i N^(-1/d), K=.2, d=3."""
    d, _ = residuals(poses, np.full(len(poses), 1/len(poses)))
    sigma = .2*np.ptp(d, axis=0)*len(poses)**(-1/3)
    poses += rng.normal(size=poses.shape)*sigma
    poses[:, 2] = np.arctan2(np.sin(poses[:, 2]), np.cos(poses[:, 2]))
    return sigma.tolist()


def floor_cloud(poses, weights, rng):
    """Enforce a floor in the actual cloud, preserving its weighted centre.

    Affine expansion in normalized XY/yaw coordinates; a rank-deficient
    cloud gets a centered, whitened Gaussian realization of the target cov.
    """
    d, centre = residuals(poses, weights)
    z = d/SCALE
    cov = (z.T*weights) @ z
    eigen, vectors = np.linalg.eigh((cov+cov.T)/2)
    if eigen.min() >= 1.:
        return False
    if eigen.min() > 1e-12:
        z = z @ ((vectors*np.sqrt(np.maximum(eigen, 1.)/eigen)) @ vectors.T)
    else:
        z = rng.normal(size=poses.shape)
        z -= weights @ z
        ev, vec = np.linalg.eigh((z.T*weights) @ z)
        z = z @ ((vec/np.sqrt(np.maximum(ev, 1e-15))) @ vec.T)
        z = z @ ((vectors*np.sqrt(np.maximum(eigen, 1.))) @ vectors.T)
    poses[:] = centre+z*SCALE
    poses[:, 2] = np.arctan2(np.sin(poses[:, 2]), np.cos(poses[:, 2]))
    return True


def _audit(option):
    if option not in OPTIONS:
        raise ValueError('unknown resampling_diversity')
    return dict(option=option, ess_fraction=.5, roughening_k=.2, floor_std=SCALE.tolist(),
                gt_inputs=False, seed_changed=False, rows=[])


def attach_s3(runtime, *, resampling_diversity='off'):
    if resampling_diversity == 'off': return runtime
    audit = _audit(resampling_diversity)
    pf = runtime.pose.provider.loc._pf
    wrapper = pf.update_obs
    selected = _closure(wrapper, 'selected').cell_contents
    original = selected.__globals__['resample']

    def resample(p):
        before = summary(p.px, p._weights())
        perform = before['ess'] < p.n/2
        sigma = None
        if perform:
            original(p)  # preserve ancestry of all latent motion states
            if resampling_diversity != 'ess_v1': sigma = roughen(p.px, p.rng)
        floored = (floor_cloud(p.px, p._weights(), p.rng)
                   if resampling_diversity == 'roughen_floor_v1' else False)
        audit['rows'].append(dict(t=float(p.t), before=before, resampled=perform,
            roughening_sigma=sigma, floored=floored, after=summary(p.px, p._weights())))

    # Global policy owns its separate KLD resampler; this call site is tracking only.
    pf.update_obs = replace_cell(wrapper, 'selected', _bind(selected, resample=resample))
    runtime.resampling_diversity_audit = audit
    record = runtime.record
    runtime.record = lambda: {**record(), 'resampling_diversity': copy.deepcopy(audit)}
    return runtime


def attach_ownmap(grid, *, resampling_diversity='off'):
    if resampling_diversity == 'off': return grid
    audit = _audit(resampling_diversity)
    original = grid.resample_if_needed
    if resampling_diversity == 'roughen_floor_v1':
        proposal = getattr(grid, '_selective_proposals', None)
        if proposal is None:
            proposal = grid._observe.__func__.__globals__.get('_proposals')
        if proposal is None:
            raise ValueError('explicit RBPF proposal consumer required')
        audit['proposal_floors'] = 0
        def proposals(instance, *args):
            result = proposal(instance, *args)
            # The RGB proposal replaces conditional covariance with 1e-10,
            # including rejected/deferred frames without a resample call.
            # Floor here, before mixture publication AND the next prediction.
            instance.pending_cov = np.array([covariance_floor(c) for c in instance.pending_cov])
            audit['proposal_floors'] += 1
            return result
        grid._selective_proposals = proposals

    def resample():
        before = summary(grid.poses, grid.weights)
        neff, parents = original()  # existing ESS < N/2; copies maps and histories
        sigma = None
        if parents is not None and resampling_diversity != 'ess_v1':
            sigma = roughen(grid.poses, grid.rng)
        if resampling_diversity == 'roughen_floor_v1':
            # RBPF conditional covariances enter both next proposal and published
            # mixture moments. Do not inflate only the displayed diagnostic.
            grid.pending_cov = np.array([covariance_floor(c) for c in grid.pending_cov])
        audit['rows'].append(dict(t=float(grid.odom.t), before=before, resampled=parents is not None,
            roughening_sigma=sigma, after=summary(grid.poses, grid.weights),
            conditional_min_eigenvalue=float(np.linalg.eigvalsh(grid.pending_cov).min())))
        return neff, parents

    grid.resample_if_needed = resample
    grid.resampling_diversity_audit = audit
    return grid
