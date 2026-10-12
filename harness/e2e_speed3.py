"""Explicit composition of reviewed E2E behavior and exact speed options."""
from dataclasses import asdict

from harness.e2e_exact_speedups import Options

OPTIONS = ('dt1_v1', 'dt2_v1')
BUNDLE_ID = 'e2e-speed3-v214'
WORKFLOW = 'configs/simulation_workflows.d/e2e_speed3_v214.json'


def compose(bundle, option='off'):
    if option == 'off':
        return ()
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_E2E_SPEED3')
    if bundle['e2e_options'].get('runtime_registration') != 'reviewed_v1':
        raise ValueError('SPEED3_REQUIRES_CURRENT_RUNTIME')
    bundle['speed3_parent_bundle_id'] = bundle['execution_bundle_id']
    bundle.update(schema='ugrp.e2e_ownmap_live.v214', execution_bundle_id=BUNDLE_ID,
                  workflow_version='7.107.0', inherited_results=False)
    bundle['e2e_options']['exact_speedups'] = {k: True for k in asdict(Options())}
    from sim.e2e_speed3_profile import PROFILES
    bundle['e2e_options']['speed3'] = option
    bundle['speed3_profile'] = dict(PROFILES[option], rbpf_audit='final_v1', capture='control_period_cached_v1', camera_resolution=[640,480])
    return (WORKFLOW,)
