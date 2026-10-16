"""Default-off S2 Nav2 likelihood_field_prob camera adapter.

Nav2 Jazzy likelihood_field_model_prob.cpp:68-73,89-92,165-175,197-228.
LGPL-2.1+ algorithm, Brian Gerkey/Kasper Stoy. Reuses our existing port.
RGB invalid columns are missing, never fabricated max-range observations.
Floor feature likelihoods, KLD, motion, sampling and gates remain unchanged.
"""
import copy
import math

import numpy as np

from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_amcl_update import BEAM, probability_loglik
from harness.zone_solo_cyan_amcl_sensor import endpoints, PARAMS
from harness.zone_solo_cyan_bias_tempering import closure, replace_cell
from harness.zone_solo_cyan_landmarks import landmark_likelihood

OPTION = 'nav2_prob_v1'


def beam_indices(count):
    return np.arange(0, count, max(1, math.ceil(count/PARAMS['max_beams'])))


prob_endpoints = bind(endpoints, beam_indices=beam_indices)


def log_components(field, mapped, px, packet, *, is_converged):
    wall, detail = probability_loglik(field, px, packet.wall, is_converged=is_converged)
    parts = np.array([wall, *(np.log(landmark_likelihood(mapped, px, [f])) for f in packet.features)])
    return parts, detail


def attach(runtime, *, sensor_beamskip='off'):
    if sensor_beamskip == 'off': return runtime
    if sensor_beamskip != OPTION: raise ValueError('unknown sensor_beamskip')
    if hasattr(runtime, 'beamskip_audit'): raise ValueError('ALREADY_ATTACHED')
    inner = runtime.pose.provider; pf = inner.loc._pf; wrapper = pf.update_obs
    selected = closure(wrapper).get('selected')
    if selected is None or selected.__module__ not in (
            'harness.zone_solo_cyan_amcl_update', 'harness.zone_solo_cyan_augmented_start'):
        raise ValueError('requires S2 landmark AMCL stack')
    mapped = closure(selected.__globals__['likelihood'])['mapped']
    state = closure(selected)['state']
    measure = bind(selected.__globals__['endpoints'], endpoints=prob_endpoints)
    audit = dict(option=OPTION, parameters={**PARAMS, **{'beam_skip_'+k:v for k,v in BEAM.items()},
        'do_beamskip':True}, scope='wall only; existing landmark likelihood unchanged',
        missing='exclude invalid RGB beams from beam-skip denominator', gt_inputs=False, rows=[])

    def score(field, px, packet):
        parts, detail = log_components(field, mapped, px, packet, is_converged=state['converged'])
        value = np.exp(parts.sum(0))
        if not np.isfinite(value).all() or np.any(value <= 0):
            raise FloatingPointError('likelihood outside supported numerical range')
        runtime.beamskip_components = parts
        audit['rows'].append(dict(t=float(pf.t), wall_count=len(packet.wall), features=len(packet.features),
            **detail, log_min=float(parts.sum(0).min()), log_max=float(parts.sum(0).max())))
        return value

    pf.update_obs = replace_cell(wrapper, 'selected', bind(selected, endpoints=measure, likelihood=score))
    runtime.beamskip_audit = audit
    previous = runtime.record
    def record():
        out = previous(); out['sensor_beamskip'] = copy.deepcopy(audit)
        return out
    runtime.record = record
    inner.runtime_contract['s2_sensor_beamskip'] = {k:v for k,v in audit.items() if not isinstance(v,list)}
    from harness.zone_solo_cyan_v106 import hp
    inner.identity_sha256 = hp.base.digest(inner.runtime_contract)
    inner.source = 'owncam_pf_s2_beamskip:'+inner.identity_sha256[:8]; runtime.pose.source = inner.source
    return runtime
