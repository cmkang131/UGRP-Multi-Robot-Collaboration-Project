"""V91 admission; reuse v90's exact static preflight without rebinding it."""
from harness.zone_final_pair_heldout_clearance import path_preflight, rejection_message
from harness.zone_final_pair_clearance import runtime_interlock


def require_collection_clearance(bundle):
    from harness import zone_final_pair_fast as fast
    fast.validate_bundle(bundle)
    if bundle.get('measurement') != fast.design(bundle['check'], bundle['map_id']):
        raise ValueError('collection measurement differs from registered design')
    if bundle.get('runtime_interlock') != runtime_interlock():
        raise ValueError('MANDATORY_COLLECTION_INTERLOCK_REQUIRED')
    receipt = path_preflight(bundle['check'], bundle['map_id'])
    if not receipt['admitted']:
        raise ValueError(rejection_message(receipt))
    return receipt
