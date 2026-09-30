"""V88 uses main's measurement-v2 evidence admission and geometry checks.

No qualified motion bounds exist for any v88 collection. Rotation and the
loaded pair/beam additionally exceed the shared translator's supported scope.
"""
from harness import final_environment_measurement_v2 as shared
from harness.final_environment_measurement_v2 import (  # compatibility for diagnostics
    rectangles, free_floor_area, clearance, require_clearance, geometry_envelope,
)

CLEARANCE_REVIEW = 'configs/zone_final_pair_v88_clearance.json'


def path_preflight(check, map_id):
    from harness import zone_final_pair_contract as contract
    from harness.zone_final_pair_excitation import design, UNLOADED_POSE
    from harness.zone_final_pair_calibration import teacher_stations
    plan = design(check)
    if map_id != plan['map_id']:
        raise ValueError('collection clearance map differs from registered design')
    static = contract.resolve(map_id)[0]
    review = contract.base.read(contract.ROOT / CLEARANCE_REVIEW)['profiles'][check]
    # Cover the complete 370 s command window, including initial staging,
    # coast and camera/arm-only tail. No rotation is dropped from segments.
    tail = plan['sim_cap_s'] - plan['motion_start_s'] - sum(s['duration_s'] for s in plan['segments'])
    if tail < 0:
        raise ValueError('collection path exceeds SIM cap')
    loaded = check == 'calibration-loaded'
    path = {**plan, 'initial_hold_s': plan['motion_start_s'],
            'spawn_xy_yaw': teacher_stations(static)['r1'] if loaded else UNLOADED_POSE,
            'path_bodies': ['r1', 'r2', 'beam'] if loaded else ['r1'],
            'segments': [*plan['segments'], {'axis': 'forward', 'duration_s': tail, 'value': 0.}]}
    return shared.path_preflight(static, path, root=contract.ROOT, review=review)


def require_collection_clearance(bundle):
    """Recompute admission even for direct callers; never trust a saved PASS."""
    from harness.zone_final_pair_excitation import design
    if not bundle['check'].startswith('calibration-'):
        return
    if bundle.get('measurement') != design(bundle['check']):
        raise ValueError('collection measurement differs from registered design')
    receipt = path_preflight(bundle['check'], bundle['map_id'])
    if not receipt['admitted']:
        raise ValueError('FULL_PATH_CLEARANCE_REJECTED: ' + receipt['reason'])


def sphere_clearances(static, xyz, radii):
    """Vectorized version for every robot/arm/beam geom at each substep."""
    import numpy as np
    xyz, radii = np.asarray(xyz, float), np.asarray(radii, float)
    if (xyz.ndim != 2 or xyz.shape[1] != 3 or radii.shape != (len(xyz),) or not len(xyz)
            or np.any(radii <= 0)):
        raise ValueError('missing/non-finite clearance geometry')
    for position, radius in zip(xyz, radii):
        geometry_envelope(position, radius, position[:2])
    xy = xyz[:, :2]
    rects = rectangles(static)
    x0, x1, y0, y1 = static['bounds_m']
    x, y = xy.T
    gaps = np.minimum.reduce((x-x0, x1-x, y-y0, y1-y))
    for a, b, c, d in rects:
        gaps = np.minimum(gaps, np.hypot(np.maximum.reduce((a-x, x-b, np.zeros(len(x)))),
                                        np.maximum.reduce((c-y, y-d, np.zeros(len(y))))))
    gaps = gaps-radii
    if not np.isfinite(gaps).all():
        raise ValueError('INVALID_ROBOT_GEOMETRY')
    return gaps
