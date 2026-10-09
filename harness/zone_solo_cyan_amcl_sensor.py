"""Explicit default-off S2 selector for the original AMCL likelihood field.

Nav2 235fc5ce likelihood_field_model.cpp:65-136; ROS navigation f44bb1fc
amcl_laser.cpp:215-302 (LGPL-2.1+, Brian Gerkey / Kasper Stoy).
This ports the original cubic accumulator, not likelihood_field_prob or a
sharpened likelihood. RGB ground endpoints are the existing sensor adapter.
"""
import copy

import numpy as np

from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_likelihood_field import PARAMS as OLD_PARAMS

OPTION = 'amcl_likelihood_field_v1'
PARAMS = dict(sigma_hit=.2, z_hit=.5, z_rand=.5, max_beams=60,
              laser_likelihood_max_dist=2., range_max_m=100.)


def beam_indices(count):
    # C++ integer division. 96 columns / max_beams 60 => step 1, NOT 60 rays.
    step = max(1, (count-1)//(PARAMS['max_beams']-1))
    return np.arange(0, count, step)


def endpoints(cm, obs):
    """Ordered camera columns; missing/occluded rays stay missing, not max range."""
    idx = beam_indices(len(obs.columns))
    points = cm.floor_point(cm.t_of_row(obs.b_lo))
    ranges = np.linalg.norm(points-cm.origin[:2], axis=1)
    optical = (np.c_[points, np.zeros(len(points))]-cm.origin) @ cm._rot
    valid = ((obs.b_kind == 1) & np.isfinite(points).all(1) &
             (optical[:, 2] > 0) & (ranges < PARAMS['range_max_m']))
    return points[idx[valid[idx]]]


def likelihood(field, px, points):
    """Original sensorFunction accumulator, vectorized only over particles.

    The enclosing AMCL update multiplies prior weights by this score and
    normalizes, in log space. Ray order and p=1; p+=pz^3 match the C++ loop.
    """
    px = np.asarray(px, float); points = np.asarray(points, float).reshape(-1, 2)
    p = np.ones(len(px))
    co, si = np.cos(px[:, 2]), np.sin(px[:, 2])
    denom = 2*PARAMS['sigma_hit']*PARAMS['sigma_hit']
    random = PARAMS['z_rand']/PARAMS['range_max_m']
    for point in points:
        hit = np.column_stack((px[:, 0]+co*point[0]-si*point[1],
                               px[:, 1]+si*point[0]+co*point[1]))
        distance = field.distances(hit)
        pz = PARAMS['z_hit']*np.exp(-(distance*distance)/denom)+random
        p += pz*pz*pz
    return p


def install(source):
    """Private function globals retain this PF's update state and policy.

    No module mutation; the existing read-only frozen update remains unchanged
    for other runtimes. Only its endpoint and score dependencies are selected.
    """
    inner = source.provider; pf = inner.loc._pf; update = pf.update_obs
    if update.__module__ not in ('harness.zone_solo_cyan_amcl_update',
                                'harness.zone_solo_cyan_augmented_start'):
        raise ValueError('sensor model requires the S2 Nav2 update adapter')
    assert OLD_PARAMS['sigma_hit_m'] == PARAMS['sigma_hit']
    assert OLD_PARAMS['max_occ_dist_m'] == PARAMS['laser_likelihood_max_dist']
    audit = dict(option=OPTION, parameters=copy.deepcopy(PARAMS), gt_inputs=False,
        normalization='prior weight times score; existing log-space normalization',
        scope='S2 own RGB; existing observed mask, floor filter and odometry triggers unchanged',
        rows=[], endpoint_rows=[])

    def selected_endpoints(cm, obs):
        pts = endpoints(cm, obs)
        audit['endpoint_rows'].append(dict(t=float(pf.t), columns=len(obs.columns),
            selected_before_invalid=len(beam_indices(len(obs.columns))), valid_beams=len(pts)))
        return pts

    def score(field, px, pts):
        value = likelihood(field, px, pts)
        audit['rows'].append(dict(t=float(pf.t), valid_beams=len(pts),
            score_min=float(value.min()), score_max=float(value.max())))
        return value

    pf.update_obs = bind(update, endpoints=selected_endpoints, likelihood=score)
    from harness.zone_solo_cyan_v106 import hp
    inner.runtime_contract['s2_sensor_model'] = dict(option=OPTION, parameters=PARAMS)
    inner.identity_sha256 = hp.base.digest(inner.runtime_contract)
    inner.source = 'owncam_pf_s2_amcl_sensor:' + inner.identity_sha256[:8]
    source.source = inner.source
    return audit


def runtime_class(previous):
    class Runtime(previous):
        def __init__(self, *args, sensor_model='off', **kwargs):
            if sensor_model not in ('off', OPTION):
                raise ValueError('unknown sensor_model')
            if sensor_model != 'off' and kwargs.get('amcl_update') != 'ros_motion_v1':
                raise ValueError('sensor model requires the non-probability AMCL field update')
            super().__init__(*args, **kwargs)
            self.sensor_model = sensor_model
            if sensor_model != 'off':
                try:
                    self.sensor_audit = install(self.pose)
                except Exception:
                    self.close()
                    raise

        def record(self):
            out = super().record()
            if self.sensor_model != 'off':
                out['sensor_model'] = copy.deepcopy(self.sensor_audit)
            return out
    return Runtime
