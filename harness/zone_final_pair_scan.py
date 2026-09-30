"""Provider-neutral informative receipt for measured v3 wall-column scans.

Use the existing recovery gate (residual support + numerical curvature), with
VIS3's interval likelihood. A scan count or a narrow posterior alone is not a
new absolute fix. This is an unqualified v3 gate, not an accuracy claim.
"""
from types import SimpleNamespace
import math
import numpy as np

from harness.owncam_recovery_v6 import RecoveryLocalizer, likelihood_quality


def quality(vl, pf, obs, pose):
    m = pf.measurement
    vb, vt = pf.expected(pf.px, pose)
    probs = [vl.interval_prob(vb, obs.b_kind, obs.b_lo, obs.b_hi, m['sigma_px'], m.get('open_ends', True))[:, obs.b_kind != vl.NONE]]
    if pf.obs_params['use_top_edge']:
        probs.append(vl.interval_prob(vt, obs.t_kind, obs.t_lo, obs.t_hi, m['sigma_px'], m.get('open_ends', True))[:, obs.t_kind != vl.NONE])
    eps = m['outlier_prob']
    per_feature = np.log(eps+(1.-eps)*np.concatenate(probs, axis=1))
    if per_feature.shape[1] == 0:
        return {'accepted': False, 'informative': False, 'settled': True, 'ambiguous': True}
    point = pf.px[int(np.argmax(per_feature.mean(1)+pf.logw))]
    def loglik(points, _obs, _pose):
        b, t = pf.expected(points, _pose)
        return vl.column_loglik(b, t, _obs, {**m, 'use_top_edge': pf.obs_params['use_top_edge']})
    curvature = RecoveryLocalizer._curvature(SimpleNamespace(_loglik=loglik), point, obs, pose)
    return likelihood_quality(per_feature, pf.logw, floor=math.log(eps), curvature=curvature, settled=True)


def install(pf, vl):
    apply, update = pf.apply_scan, pf.update_obs
    pf.v3_last_fix_quality = None
    def apply_scan(t, obs, pose):
        pf.v3_scan_quality = quality(vl, pf, obs, pose)
        return apply(t, obs, pose)
    def update_obs(t, obs, pose):
        previous = pf.last_scan_t
        pf.v3_scan_quality = None
        result = update(t, obs, pose)
        q = pf.v3_scan_quality
        if result.get('measured') and q and q['informative']:
            pf.v3_last_fix_quality = {**q, 't': t}
        else:
            pf.last_scan_t = previous
            result['measured'] = False
        return result
    pf.apply_scan, pf.update_obs = apply_scan, update_obs


def resample(pf):
    """VIS3 systematic resampling, carrying the pair plant's latent states.

    The frozen VIS3 resampler predates yaw_bias/yaw_extra/drift. Resampling
    poses alone would attach one particle's motion error to another particle.
    """
    pf.logw -= pf.logw.max()
    w = np.exp(pf.logw)
    w /= w.sum()
    ess = 1./np.sum(w*w)
    pf.diag['ess_pre'] = round(float(ess), 1)
    inject, pf._inject = pf._inject, 0.
    if ess >= pf.params['resample_ratio']*pf.n and inject <= 0:
        pf.logw = np.log(np.maximum(w, 1e-300))
        return
    n_new = int(pf.rng.binomial(pf.n, inject)) if inject > 0 else 0
    m = pf.n-n_new
    positions = (np.arange(m)+pf.rng.uniform())/m if m else np.zeros(0)
    idx = np.minimum(np.searchsorted(np.cumsum(w), positions), pf.n-1)
    px, scale, stuck = pf.px[idx].copy(), pf.scale[idx].copy(), pf.stuck[idx].copy()
    extra = {key: getattr(pf, key)[idx].copy() for key in ('yaw_bias', 'yaw_extra', 'drift')
             if getattr(pf, key) is not None}
    rough = np.asarray(pf.params.get('roughen', [0., 0., 0.]), float)
    if np.any(rough > 0) and m:
        px += pf.rng.normal(size=px.shape)*rough
        px[:, 2] = pf.wrap(px[:, 2])
    if n_new:
        mp = pf.params['motion_loaded' if pf.load.loaded else 'motion']
        sd = mp.get('load_transition', {}).get('scale_std', mp['scale_std']) if pf.load.loaded else mp['scale_std']
        px = np.concatenate([px, pf._random_poses(n_new)])
        scale = np.concatenate([scale, 1.+pf.rng.normal(size=(n_new, 3))*sd])
        stuck = np.concatenate([stuck, np.zeros(n_new, bool)])
        for key, values in extra.items():
            spread = {'yaw_bias': mp.get('yaw_bias_std_rad_s', 0.), 'yaw_extra': pf.extra_std,
                      'drift': mp.get('drift_ratio_std', 0.)}[key]
            extra[key] = np.concatenate([values, pf.rng.normal(size=(n_new, *values.shape[1:]))*spread])
        pf.stats['injections'] += 1
        pf.stats['injected_particles'] += n_new
        pf.w_slow = pf.w_fast = 0.
    pf.px, pf.scale, pf.stuck = px, scale, stuck
    for key, values in extra.items():
        setattr(pf, key, values)
    pf.logw = np.zeros(pf.n)
    pf.stats['resamples'] += 1
    pf.diag['injected'] = n_new
