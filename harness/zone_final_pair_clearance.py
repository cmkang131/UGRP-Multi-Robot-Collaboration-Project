"""Simulation-only teacher envelope; runtime interlocks remain primary.

2026-10-01 coordinator decision 2: envelopes are advisory; finite geometry,
start clearance and the mandatory runtime interlock remain blocking checks.
"""
import math

from harness.final_environment_measurement_v2 import (  # compatibility for diagnostics
    rectangles, free_floor_area, clearance, require_clearance, geometry_envelope,
)

CLEARANCE_REVIEW = 'configs/zone_final_pair_v88_clearance.json'


def runtime_interlock():
    """Required declaration, not an enable/disable option."""
    return {'required': True, 'minimum_m': .30, 'abort_buffer_m': .05,
            'robot_radius_bound_m': .40, 'max_substep_displacement_m': .01,
            'checks': ['before_substep', 'after_substep', 'before_command', 'eval_0.05_s'],
            'invalid_geometry': 'hold_then_HOST_ERROR',
            'trip': 'hold_then_HOST_ERROR_keep_partial_invalid'}


def _finite(value, *, positive=False):
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError('non-finite or non-positive envelope input')
    return value


def conservative_envelope(static, events, starts, gain_upper, *, sim_cap_s=370., beam=None,
                          pair_cancellation=False):
    """Sum every |command| lease, with NO sign cancellation, even in step pairs.

    Translation <= Kf*integral(|forward|) + Kl*integral(|left|), regardless
    of yaw. A tip at radius R moves at most R*min(total_abs_yaw, 2): arc
    length or the diameter, whichever is smaller. The 0.40 m robot/arm disc
    is retained as well, deliberately overbounding articulated posture changes.
    For loaded, add the beam half-diagonal (>= half-length) to EACH carrier;
    a third disc at the beam start contains BOTH carrier discs. No rigid-pair
    or equal/opposite command cancellation is assumed by default.

    The optional estimate uses the peak absolute signed step integral on each
    axis, plus every non-step absolute lease (including PRBS). Thus opposite
    step pairs cancel but their outbound excursion is retained. It assumes
    symmetric response in fixed axes; yaw, lag and load can invalidate it.
    Never cancel commands BETWEEN carriers or use this estimate as a gate.
    """
    from sim.camera_robot_port import validate_raw_action
    axes = ('forward', 'left', 'turn')
    _finite(sim_cap_s, positive=True)
    gains = {axis: _finite(gain_upper[axis], positive=True) for axis in axes}
    if set(starts) != ({'r1', 'r2'} if beam is not None else {'r1'}):
        raise ValueError('missing collection starts')
    for pose in [*starts.values(), *([beam['pose']] if beam is not None else [])]:
        if len(pose) != 3:
            raise ValueError('invalid start xy/yaw')
        for v in pose:
            _finite(v)
    # Validate all map geometry even if the input has no motion.
    rectangles(static)
    radius, margin = .40, .30
    beam_radius = 0.
    if beam is not None:
        half_length, half_width = beam['half_extents_m']
        beam_radius = math.hypot(_finite(half_length, positive=True),
                                 _finite(half_width, positive=True))
    integrals = {rid: {axis: [] for axis in axes} for rid in starts}
    step_position = {rid: dict.fromkeys(axes, 0.) for rid in starts}
    step_peak = {rid: dict.fromkeys(axes, 0.) for rid in starts}
    lease_end = dict.fromkeys(starts, 0.)
    previous_t = 0.
    for event in events:
        t, rid, action = _finite(event['t']), event['robot_id'], event['action']
        if not previous_t <= t < sim_cap_s or rid not in starts:
            raise ValueError('unordered/out-of-window command or unknown body')
        previous_t = t
        validate_raw_action(action, allow_reverse=True, allow_mecanum=True)
        if action['kind'] in ('arm', 'look', 'wait'):
            continue  # full 0.40 m articulated bound applies also during holds
        if action['kind'] != 'mecanum':
            raise ValueError('unsupported envelope command')
        duration = _finite(action['duration_s'], positive=True)
        if t < lease_end[rid]-1e-8 or t+duration > sim_cap_s+1e-8:
            raise ValueError('overlapping/out-of-window drive lease')
        lease_end[rid] = t+duration
        for axis in axes:
            impulse = _finite(action[axis])*duration
            if pair_cancellation and event.get('phase', '').split('_')[-1] == 'step':
                step_position[rid][axis] += impulse
                step_peak[rid][axis] = max(step_peak[rid][axis], abs(step_position[rid][axis]))
            else:
                integrals[rid][axis].append(abs(impulse))
    bodies = {}
    for rid, start in starts.items():
        absolute = {axis: math.fsum(integrals[rid][axis])+step_peak[rid][axis] for axis in axes}
        translation = math.fsum(gains[a]*absolute[a] for a in ('forward', 'left'))
        yaw = _finite(gains['turn']*absolute['turn'])
        offset = math.dist(start[:2], beam['pose'][:2]) if beam is not None else 0.
        tip_radius = max(radius, offset+beam_radius)
        tip_excursion = tip_radius*min(yaw, 2.)
        disc = translation+tip_excursion+beam_radius+radius+margin
        bodies[rid] = {'start_xy_yaw': list(start), 'absolute_command_integral_s': absolute,
            'translation_bound_m': translation, 'absolute_yaw_bound_rad': yaw,
            'tip_radius_from_chassis_m': tip_radius, 'yaw_tip_excursion_bound_m': tip_excursion,
            'excursion_bound_m': translation+tip_excursion,
            'beam_radius_added_m': beam_radius, 'disc_radius_m': _finite(disc, positive=True)}
        if pair_cancellation:
            bodies[rid]['estimated_excursion_integral_s'] = bodies[rid].pop('absolute_command_integral_s')
            bodies[rid]['step_peak_integral_s'] = step_peak[rid]
            bodies[rid]['step_net_integral_s'] = step_position[rid]
    if beam is not None:
        start = beam['pose']
        disc = max(math.dist(start[:2], starts[rid][:2])+row['disc_radius_m']
                   for rid, row in bodies.items())
        bodies['beam'] = {'start_xy_yaw': list(start), 'disc_radius_m': _finite(disc, positive=True),
            'excursion_bound_m': max(math.dist(start[:2], starts[rid][:2])+row['excursion_bound_m']
                                    for rid, row in bodies.items()),
            'contains_carrier_discs': list(starts), 'half_length_m': beam['half_extents_m'][0],
            'half_diagonal_m': beam_radius}
    for row in bodies.values():
        slack = _finite(clearance(static, row['start_xy_yaw'][:2], row['disc_radius_m']))
        row.update(wall_distance_from_start_m=slack+row['disc_radius_m'],
                   remaining_clearance_m=slack, wall_free=slack > 1e-10)
    admitted = all(row['wall_free'] for row in bodies.values())
    return {'admitted': admitted,
        'reason': 'CONSERVATIVE_ENVELOPE_CLEAR' if admitted else 'CONSERVATIVE_ENVELOPE_EXCEEDS_WALLS',
        'method': ('peak_signed_steps_plus_absolute_prbs' if pair_cancellation
                   else 'whole_schedule_absolute_command_integral'),
        'sign_cancellation': 'within_robot_step_pairs_only' if pair_cancellation else 'none',
        'qualification': ('ADVISORY_ESTIMATE_NOT_A_MOTION_BOUND; symmetric fixed-axis step response assumed'
                          if pair_cancellation else 'ADVISORY_CONDITIONAL_NO_CANCELLATION_BOUND'),
        'sim_window_s': [0., sim_cap_s], 'gain_upper': gains,
        'robot_radius_bound_m': radius, 'wall_margin_m': margin,
        'numeric_guard_m': 1e-10, 'bodies': bodies}


def start_pose_check(static, starts, *, beam=None):
    """Explicit static start gate: 0.30 m plus each body's geometric bound."""
    bodies = {}
    for name, pose in {**starts, **({'beam': beam['pose']} if beam else {})}.items():
        if len(pose) != 3 or not all(math.isfinite(v) for v in pose):
            raise ValueError('invalid start xy/yaw')
        radius = math.hypot(*beam['half_extents_m']) if name == 'beam' else .40
        required = _finite(radius, positive=True)+.30
        slack = _finite(clearance(static, pose[:2], required))
        bodies[name] = {'start_xy_yaw': list(pose), 'body_radius_bound_m': radius,
                        'required_wall_distance_m': required,
                        'wall_distance_from_start_m': slack+required,
                        'remaining_clearance_m': slack, 'admitted': slack > 1e-10}
    return {'admitted': bool(bodies) and all(row['admitted'] for row in bodies.values()),
            'wall_margin_m': .30, 'numeric_guard_m': 1e-10, 'bodies': bodies}


def path_preflight(check, map_id):
    from harness import zone_final_pair_contract as contract
    from harness.zone_final_pair_excitation import design, UNLOADED_POSE, LOADED_BEAM_POSE
    from harness.zone_final_pair_calibration import schedule, teacher_stations
    from harness import zone_final_pair_heldout as heldout
    plan = design(check)
    if heldout.selected(check, map_id):
        plan = heldout.design(check, map_id)
    if map_id != plan['map_id']:
        raise ValueError('collection clearance map differs from registered design')
    try:
        static = contract.resolve(map_id)[0]
        policy = contract.base.read(contract.ROOT / CLEARANCE_REVIEW)
        # These are coordinator assumptions, not qualified plant/model bounds.
        if (policy['schema'] != 'ugrp.final_pair_conservative_envelope.v2'
                or policy['scope'] != 'SIMULATION_ONLY_TEACHER_CALIBRATION'
                or policy['envelope_policy'] != 'ADVISORY'
                or policy['runtime_interlock'] != runtime_interlock()
                or policy['wall_margin_m'] != .30 or policy['runtime_abort_buffer_m'] != .05
                or policy['gain_upper'] != {'forward': 2.62, 'left': 1.86, 'turn': 2*1.149964146433179}
                or plan['clearance'] != {k: runtime_interlock()[k] for k in
                                        ('minimum_m', 'abort_buffer_m', 'robot_radius_bound_m',
                                         'max_substep_displacement_m')}
                or plan['sim_cap_s'] != 370.):
            raise ValueError('coordinator envelope policy differs from registered assumptions')
        loaded = check == 'calibration-loaded'
        beam = None
        if loaded:
            from sim.zone_cargo import CATALOGUE
            beam = {'pose': LOADED_BEAM_POSE,
                    'half_extents_m': CATALOGUE['long_beam'].landing_half_extents_m}
        starts = teacher_stations(static) if loaded else {'r1': UNLOADED_POSE}
        events = schedule(check)
        bounds = {key: conservative_envelope(static, events, starts, policy['gain_upper'],
                  sim_cap_s=plan['sim_cap_s'], beam=beam, pair_cancellation=paired)
                  for key, paired in [('no_cancellation_bound', False), ('pair_cancellation_estimate', True)]}
        start = start_pose_check(static, starts, beam=beam)
        return {'admitted': start['admitted'], 'envelope_policy': 'ADVISORY',
                'scope': policy['scope'], 'decision': '2026-10-01 coordinator decision 2',
                'reason': 'START_POSE_CLEAR_INTERLOCK_REQUIRED' if start['admitted'] else 'START_POSE_TOO_CLOSE_TO_WALL',
                'start_pose_check': start, 'runtime_interlock': runtime_interlock(), **bounds}
    except (ValueError, KeyError, TypeError, OverflowError, OSError) as exc:
        return {'admitted': False, 'reason': 'INVALID_CONSERVATIVE_ENVELOPE_INPUT', 'detail': str(exc)}


def rejection_message(receipt):
    numbers = '; '.join(f"{name}: required={row['required_wall_distance_m']:.6f} m, "
                       f"wall_distance={row['wall_distance_from_start_m']:.6f} m, "
                       f"remaining={row['remaining_clearance_m']:.6f} m"
                       for name, row in receipt.get('start_pose_check', {}).get('bodies', {}).items())
    return 'COLLECTION_PREFLIGHT_REJECTED: ' + receipt['reason'] + ' — ' + (numbers or receipt.get('detail', ''))


def require_collection_clearance(bundle):
    """Recompute admission even for direct callers; never trust a saved PASS."""
    from harness.zone_final_pair_excitation import design
    from harness import zone_final_pair_heldout as heldout
    if bundle.get('execution_bundle_id') == heldout.BUNDLE_ID:
        heldout.validate_bundle(bundle)
    if not bundle['check'].startswith('calibration-'):
        return
    expected = design(bundle['check'])
    if bundle.get('execution_bundle_id') == heldout.BUNDLE_ID or bundle['map_id'] in heldout.MAPS:
        heldout.validate_bundle(bundle)
        expected = heldout.design(bundle['check'], bundle['map_id'])
    if bundle.get('measurement') != expected:
        raise ValueError('collection measurement differs from registered design')
    if bundle.get('runtime_interlock') != runtime_interlock():
        raise ValueError('MANDATORY_COLLECTION_INTERLOCK_REQUIRED')
    receipt = path_preflight(bundle['check'], bundle['map_id'])
    if not receipt['admitted']:
        raise ValueError(rejection_message(receipt))
    return receipt


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
