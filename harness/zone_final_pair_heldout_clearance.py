"""V90 admission, isolated from the frozen v88 source closure.

The preflight policy is copied from v88; geometry/interlock helpers remain shared.
No runtime globals in the v88 path are patched or rebound.
"""
from harness.zone_final_pair_clearance import (
    CLEARANCE_REVIEW, conservative_envelope, rejection_message,
    runtime_interlock, start_pose_check,
)


def path_preflight(check, map_id):
    from harness import zone_final_pair_contract as contract
    from harness.zone_final_pair_excitation import UNLOADED_POSE, LOADED_BEAM_POSE
    from harness.zone_final_pair_calibration import schedule, teacher_stations
    from harness import zone_final_pair_heldout as heldout
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


def require_collection_clearance(bundle):
    """Recheck the v90 registration and start gate before creating any owner."""
    from harness import zone_final_pair_heldout as heldout
    heldout.validate_bundle(bundle)
    if bundle.get('measurement') != heldout.design(bundle['check'], bundle['map_id']):
        raise ValueError('collection measurement differs from registered design')
    if bundle.get('runtime_interlock') != runtime_interlock():
        raise ValueError('MANDATORY_COLLECTION_INTERLOCK_REQUIRED')
    receipt = path_preflight(bundle['check'], bundle['map_id'])
    if not receipt['admitted']:
        raise ValueError(rejection_message(receipt))
    return receipt
