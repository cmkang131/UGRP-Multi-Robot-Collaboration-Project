"""Default-off exact speed-up of the own-camera body-shadow depth image.

`own_map_amcl_vendor.visibility.shadow_depths` intersects 480x96 camera rays with
~50 oriented boxes of the robot's own commanded-FK body model. The original
slab test reduces over a length-3 last axis (`.max(-1)`, `.min(-1)`, `.any(-1)`),
the slowest numpy path. The same slab test per axis component on contiguous
1-D arrays gives element-for-element identical floating-point results (max/min
over three values is order independent; every arithmetic step is the same
IEEE operation). Only the own camera ray set and own commanded body boxes are
read; nothing here sees scene, truth pose, or evaluation state.
"""
import copy
import numpy as np

OPTION = 'shadow_axes_v1'
VERSIONS = {('e2e18-v303', OPTION): 316}
PARAMS = dict(patched='harness.own_map_amcl_vendor.visibility.shadow_depths', exact_to_original=True,
              inputs='own_camera_rays_and_commanded_body_boxes_only')


def box_depth_axes(origin, rays, center, axes, half):
    p = (np.asarray(origin)-center) @ axes
    d = np.asarray(rays) @ axes
    low = high = None
    invalid = None
    for k in range(3):
        dk = d[..., k]
        parallel = abs(dk) < 1e-12
        safe = np.where(parallel, 1., dk)
        a, b = (-half[k]-p[k])/safe, (half[k]-p[k])/safe
        lo = np.where(parallel, -np.inf, np.minimum(a, b))
        hi = np.where(parallel, np.inf, np.maximum(a, b))
        bad = parallel & (abs(p[k]) > half[k])
        low, high, invalid = ((lo, hi, bad) if low is None else
                              (np.maximum(low, lo), np.minimum(high, hi), invalid | bad))
    hit = ~invalid & (high >= np.maximum(low, 1e-6))
    return np.where(hit, np.maximum(low, 0.), np.inf)


def shadow_depths_axes(origin, rays, boxes):
    """Per box, run the slab test only on rays that can reach its circumscribed sphere.

    A ray that misses the sphere (or points away from it while the origin is
    outside) cannot hit the box, so the original returns inf for it: skipping
    is exact. A 1e-6 relative margin absorbs rounding of the sphere test.
    """
    rays = np.asarray(rays)
    shape = rays.shape[:-1]
    flat = rays.reshape(-1, 3)
    norm2 = np.einsum('ij,ij->i', flat, flat)
    origin = np.asarray(origin)
    out = {k: np.full(flat.shape[0], np.inf) for k in ('gripper', 'arm', 'chassis')}
    for category, center, axes, half in boxes:
        v = np.asarray(center)-origin
        r2 = float(np.dot(half, half))*(1+1e-6)+1e-9
        vv = float(v @ v)
        if vv <= r2:
            index = slice(None); sub = flat
        else:
            t = flat @ v
            keep = (t > 0) & (vv-t*t/norm2 <= r2)
            index = np.flatnonzero(keep)
            if index.size == 0: continue
            sub = flat[index]
        depth = box_depth_axes(origin, sub, center, axes, half)
        np.minimum(out[category][index], depth, out=depth)
        out[category][index] = depth
    return {k: v.reshape(shape) for k, v in out.items()}


def install(option):
    if option == 'off':
        return
    if option != OPTION:
        raise ValueError('UNKNOWN_PERCEPTION_FAST')
    from harness.own_map_amcl_vendor import visibility
    visibility.shadow_depths = shadow_depths_axes


def compose(bundle, option, controller_timing='off'):
    """v303 (+ this toggle and/or phase timing) -> v316; timing alone -> v317."""
    if option == 'off' and controller_timing == 'off':
        return ()
    if option not in ('off', OPTION) or controller_timing not in ('off', 'phase_v1'):
        raise ValueError('UNKNOWN_PERCEPTION_SPEED_OPTION')
    parent = bundle['execution_bundle_id']
    version = {(('e2e18-v303'), OPTION, 'phase_v1'): 316, ('e2e18-v303', 'off', 'phase_v1'): 317,
               ('e2e18-v303', OPTION, 'off'): 318}.get((parent, option, controller_timing))
    if version is None:
        raise ValueError('PERCEPTION_SPEED_REQUIRES_V303_AND_TIMING_OR_TOGGLE')
    from harness.e2e_speed_phase import PARAMS as TIMING_PARAMS
    bundle['perception_speed_parent'] = parent
    bundle['e2e_options'].update(perception_fast=option, controller_timing=controller_timing)
    if option != 'off':
        bundle['perception_fast_parameters'] = copy.deepcopy(PARAMS)
    if controller_timing != 'off':
        bundle['controller_timing_parameters'] = copy.deepcopy(TIMING_PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json', 'harness/e2e_speed_phase.py', 'harness/e2e_perception_fast.py')


def parent_for_validation(bundle):
    from harness.e2e_speed_phase import PARAMS as TIMING_PARAMS
    o = bundle['e2e_options']
    option, timing = o.get('perception_fast', 'off'), o.get('controller_timing', 'off')
    key = (bundle.get('perception_speed_parent'), option, timing)
    version = {('e2e18-v303', OPTION, 'phase_v1'): 316, ('e2e18-v303', 'off', 'phase_v1'): 317,
               ('e2e18-v303', OPTION, 'off'): 318}.get(key)
    if (version is None or bundle['execution_bundle_id'] != f'e2e18-v{version}'
            or (option != 'off') != ('perception_fast_parameters' in bundle)
            or (option != 'off' and bundle['perception_fast_parameters'] != PARAMS)
            or (timing != 'off') != ('controller_timing_parameters' in bundle)
            or (timing != 'off' and bundle['controller_timing_parameters'] != TIMING_PARAMS)):
        raise ValueError('REGISTERED_PERCEPTION_SPEED_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = bundle['perception_speed_parent']
    for k in ('perception_speed_parent', 'perception_fast_parameters', 'controller_timing_parameters'):
        old.pop(k, None)
    for k in ('perception_fast', 'controller_timing'):
        old['e2e_options'].pop(k, None)
    return old
