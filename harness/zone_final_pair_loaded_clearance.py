"""Same admission rules and thresholds, evaluated on the new v92 schedule."""
from harness.zone_final_pair_clearance import (
    conservative_envelope, start_pose_check, runtime_interlock, rejection_message,
)
from harness import zone_final_pair_loaded_schedule as acquisition


def path_preflight(check, map_id):
    from harness import zone_final_pair_contract as c
    from harness.zone_final_pair_calibration import teacher_stations
    from harness.zone_final_pair_excitation import LOADED_BEAM_POSE
    from harness.zone_final_pair_clearance import path_preflight as original_preflight
    from sim.zone_cargo import CATALOGUE
    plan = acquisition.design(check, map_id)
    # Recheck the original policy/geometry/start rules, never a stored PASS.
    original = original_preflight(check, map_id)
    if not original['admitted']:
        return original
    static = c.resolve(map_id)[0]
    beam = {'pose': LOADED_BEAM_POSE, 'half_extents_m': CATALOGUE['long_beam'].landing_half_extents_m}
    starts = teacher_stations(static)
    policy = c.base.read(c.ROOT/'configs/zone_final_pair_v88_clearance.json')
    events = acquisition.schedule(check)
    bounds = {name: conservative_envelope(static, events, starts, policy['gain_upper'],
              sim_cap_s=plan['sim_cap_s'], beam=beam, pair_cancellation=paired)
              for name, paired in (('no_cancellation_bound', False), ('pair_cancellation_estimate', True))}
    start = start_pose_check(static, starts, beam=beam)
    return {**original, **bounds, 'start_pose_check': start, 'admitted': start['admitted'],
            'schedule_scope': 'v92 720 SIM s; unchanged start gate and abort-only interlock'}


def require_collection_clearance(bundle):
    from harness import zone_final_pair_loaded as loaded
    loaded.validate_bundle(bundle)
    if bundle.get('measurement') != loaded.design(bundle['check'], bundle['map_id']):
        raise ValueError('v92 measurement differs from registered design')
    if bundle.get('runtime_interlock') != runtime_interlock():
        raise ValueError('MANDATORY_COLLECTION_INTERLOCK_REQUIRED')
    receipt = path_preflight(bundle['check'], bundle['map_id'])
    if not receipt['admitted']:
        raise ValueError(rejection_message(receipt))
    return receipt
