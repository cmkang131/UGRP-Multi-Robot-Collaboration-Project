"""Opt-in visual-servo capture region; final ready/grasp gates stay unchanged.

Nav2 docking switches from staging navigation to a fresh perception controller.
This adapts only that handoff to the existing calibrated stopped-base servo.
"""
OPTION = 'capture60_v1'
MPC = 'capture60_mpc_v1'
PARENTS = {(OPTION, 'e2e18-v260'): 263, (MPC, 'e2e18-v262'): 264}
PARAMS = dict(axis_capture_rad=.60, forward_min_m=.10, forward_max_m=.40,
              lateral_max_m=.10, assigned_end_max_error_m=.09,
              fresh_rgb_required=True, final_servo_tolerances_unchanged=True)


def heading_limit(transport):
    option = getattr(transport, 'fine_entry', 'off')
    if option == 'off':
        return .20
    if option not in (OPTION, MPC):
        raise ValueError('UNKNOWN_FINE_ENTRY')
    return PARAMS['axis_capture_rad']


def install(transport, option):
    if option == 'off':
        return
    if option not in (OPTION, MPC):
        raise ValueError('UNKNOWN_FINE_ENTRY')
    transport.fine_entry = option
    if option == MPC:
        from dataclasses import replace
        # Reuse Servo's existing bounded three-pulse receding search. Keep
        # posture ownership, calibration, action set and readiness tolerances.
        for servo in transport.align.values():
            servo.refinements = replace(servo.refinements, coarse_axis_ownership=False)


def parameters(option):
    return dict(PARAMS, fine_selector='existing_receding3' if option == MPC else 'existing_one_step')


def compose(bundle, option):
    if option == 'off':
        return ()
    parent = bundle['execution_bundle_id']
    if (option, parent) not in PARENTS:
        raise ValueError('FINE_ENTRY_REQUIRES_V260_OR_V262')
    version = PARENTS[option, parent]
    bundle['e2e_options']['fine_entry'] = option
    bundle['fine_entry_parameters'] = parameters(option)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}',
                  execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)
