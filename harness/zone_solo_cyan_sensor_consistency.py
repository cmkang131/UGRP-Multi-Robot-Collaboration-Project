"""Default-off S2 PR2005 likelihood product, tempering, selective resampling.

Table 6.3 / 6.6: Gaussian-hit + uniform-random densities, products in log
space. Section 6.3.4: weaken dependent observations by likelihood**alpha.
Alpha=.5 is the existing s2v45/egomap43 constant, NOT a textbook default.
ROS navigation f44bb1fc pf.c:380-394: skip resampling when ESS > N/2.
Own RGB/static map only. No fitting, truth inputs, motion or gate changes.
"""
import copy

import numpy as np

from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_bias_tempering import ALPHA, closure, replace_cell
from harness.zone_solo_cyan_landmarks import PARAMS as FEATURE_PARAMS, landmark_likelihood
from harness.zone_solo_cyan_likelihood_field import PARAMS

OPTION = 'pr_field_temper_ess_v1'
FEATURE_MIXTURE = {**FEATURE_PARAMS, 'random_fraction': PARAMS['z_rand']}
feature_density = bind(landmark_likelihood, PARAMS=FEATURE_MIXTURE)


def log_components(field, mapped, px, packet):
    """Wall observations and each landmark on the same product/log scale.

    Densities in different measurement spaces need not have identical units
    or peaks. Normalisation constants >1 are not themselves a defect.
    Correspondence, sigmas, ray selection and missing-data handling unchanged.
    """
    px = np.asarray(px); wall = np.zeros(len(px))
    c, s = np.cos(px[:, 2]), np.sin(px[:, 2])
    sigma = PARAMS['sigma_hit_m']
    for point in packet.wall:
        xy = np.column_stack((px[:, 0]+c*point[0]-s*point[1],
                              px[:, 1]+s*point[0]+c*point[1]))
        distance = field.distances(xy)
        hit = np.exp(-.5*(distance/sigma)**2)/(np.sqrt(2*np.pi)*sigma)
        wall += np.log(PARAMS['z_hit']*hit+PARAMS['z_rand']/PARAMS['range_max_m'])
    return np.array([wall, *(np.log(feature_density(mapped, px, [f])) for f in packet.features)])


def selective_resample(pf, original):
    ess = float(1/np.sum(pf._weights()**2))
    perform = ess <= pf.n/2
    if perform: original(pf)
    return dict(t=float(pf.t), ess=ess, n=pf.n, resampled=perform)


def attach(runtime, *, sensor_consistency='off'):
    if sensor_consistency == 'off': return runtime
    if sensor_consistency != OPTION: raise ValueError('unknown sensor_consistency')
    if hasattr(runtime, 'sensor_consistency_audit'): raise ValueError('ALREADY_ATTACHED')
    inner = runtime.pose.provider; pf = inner.loc._pf; wrapper = pf.update_obs
    selected = closure(wrapper).get('selected')
    if selected is None or selected.__module__ not in (
            'harness.zone_solo_cyan_amcl_update', 'harness.zone_solo_cyan_augmented_start'):
        raise ValueError('requires S2 landmark AMCL stack')
    mapped = closure(selected.__globals__['likelihood'])['mapped']
    original_resample = selected.__globals__['resample']
    audit = dict(option=OPTION, alpha=ALPHA, z_hit=PARAMS['z_hit'], z_rand=PARAMS['z_rand'],
        ess_fraction=.5, gt_inputs=False, global_policy='existing initial KLD policy unchanged',
        tracking_resampling=[], likelihood_rows=[])

    def score(field, px, packet):
        components = log_components(field, mapped, px, packet)
        ll = ALPHA*components.sum(axis=0)
        # No per-frame max shift here: initial Augmented MCL needs raw scale.
        value = np.exp(ll)
        if not np.isfinite(value).all() or np.any(value <= 0):
            raise FloatingPointError('likelihood outside supported numerical range')
        audit['likelihood_rows'].append(dict(t=float(pf.t), wall_count=len(packet.wall),
            features=len(packet.features), log_min=float(ll.min()), log_max=float(ll.max())))
        return value

    def resample(p):
        audit['tracking_resampling'].append(selective_resample(p, original_resample))

    pf.update_obs = replace_cell(wrapper, 'selected', bind(selected, likelihood=score, resample=resample))
    runtime.sensor_consistency_audit = audit
    previous = runtime.record
    def record():
        out = previous(); out['sensor_consistency'] = copy.deepcopy(audit)
        # Frozen update's counter counts calls. The actual PF counter counts draws.
        for name in ('amcl_update', 'soft_measurement'):
            if isinstance(out.get(name), dict):
                out[name]['resample_calls'] = out[name].get('resamples')
                out[name]['resamples'] = pf.stats['resamples']
        return out
    runtime.record = record
    inner.runtime_contract['s2_sensor_consistency'] = {k:v for k,v in audit.items() if not isinstance(v, list)}
    from harness.zone_solo_cyan_v106 import hp
    inner.identity_sha256 = hp.base.digest(inner.runtime_contract)
    inner.source = 'owncam_pf_s2_sensor_consistency:'+inner.identity_sha256[:8]; runtime.pose.source = inner.source
    return runtime
