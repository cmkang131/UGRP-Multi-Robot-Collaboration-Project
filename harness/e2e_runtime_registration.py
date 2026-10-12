"""New-source admission; historical E2E registrations retain their original SHA."""
import hashlib
from pathlib import Path

OPTION = 'reviewed_v1'
BUNDLE_ID = 'e2e-reviewed-runtime-v210'
WORKFLOW_VERSION = '7.103.0'
NATIVE_COVERAGE_ID = 'e2e-boundary-native-v213'
WORKFLOW = 'configs/simulation_workflows.d/e2e_reviewed_runtime_v210.json'
# Python import closure cannot discover data selected by Path.read_text().
ASSETS = ('experiments/2026-10-07-mapfree-goal-floor/v3-selection.json',
          'configs/e2e_environment_v1.json', 'configs/e2e_stage2_options_v1.json')


def register(bundle, option='off'):
    if option == 'off':
        return ()
    if option != OPTION:
        raise ValueError('UNKNOWN_E2E_RUNTIME_REGISTRATION')
    native = bundle['execution_bundle_id'] == NATIVE_COVERAGE_ID
    bundle['parent_execution_bundle_id'] = bundle['execution_bundle_id']
    bundle.update(schema='ugrp.e2e_ownmap_live.v210', execution_bundle_id=BUNDLE_ID,
                  workflow_version=WORKFLOW_VERSION, inherited_results=False)
    # The command estimator has only the measured full-duration profiles.
    # Retain the established ceil-to-full-pulse schedule, including its logged
    # overshoot; do not invent a measured response for fractional durations.
    bundle['e2e_options'].update(runtime_registration=OPTION, pulse_budget='off',
                               pulse_authorization='current_go_v1')
    if native:
        bundle.update(schema='ugrp.e2e_ownmap_live.v213', execution_bundle_id=NATIVE_COVERAGE_ID,
                      workflow_version='7.106.0', parent_execution_bundle_id=BUNDLE_ID)
    return (*ASSETS, WORKFLOW, 'scripts/run_e2e_reviewed.py')


def require_current(bundle, root):
    options = bundle['e2e_options']
    if (options.get('runtime_registration') != OPTION or
            bundle['execution_bundle_id'] not in (BUNDLE_ID, NATIVE_COVERAGE_ID, 'e2e-speed3-v214', 'e2e-speed3-v215', 'e2e18-v216','e2e18-v217','e2e18-v218','e2e18-v219','e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225') or options['pulse_budget'] != 'off' or
            options.get('pulse_authorization') != 'current_go_v1'):
        raise ValueError('E2E_ORIGINAL_CHECKOUT_OR_REVIEWED_RUNTIME_REQUIRED')
    if bundle['execution_bundle_id'] == NATIVE_COVERAGE_ID and not (
            options.get('boundary_coverage') == 'native_v1' and options.get('dev_light') is True and
            options.get('boundary_association') == 'extent_v1'):
        raise ValueError('DEV_BOUNDARY_NATIVE_REGISTRATION_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e-speed3-v214','e2e-speed3-v215','e2e18-v216','e2e18-v217','e2e18-v218','e2e18-v219','e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225'):
        from sim.e2e_speed3_profile import PROFILES
        mode=options.get('speed3')
        if mode not in PROFILES or any(bundle.get('speed3_profile',{}).get(k)!=v for k,v in PROFILES[mode].items()):
            raise ValueError('SPEED3_PROFILE_MISMATCH')
        if not options.get('exact_speedups') or not all(options['exact_speedups'].values()):
            raise ValueError('SPEED3_ALL_EXACT_OPTIONS_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v216','e2e18-v217','e2e18-v218','e2e18-v219','e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225'):
        from harness.e2e18_bundle import validate
        validate(bundle)
        if bundle['execution_bundle_id'] in ('e2e18-v219','e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225') and (options.get('speed5')!='lean_v3' or bundle.get('opencv_threads')!=1 or bundle.get('coarse_grid_dtype')!='float32'):
            raise ValueError('E2E18_SPEED5_PROFILE_MISMATCH')
        if bundle['execution_bundle_id']=='e2e18-v218' and (options.get('speed5')!='lean_v2' or bundle.get('opencv_threads')!=1):
            raise ValueError('SPEED5_RUNTIME_PROFILE_MISMATCH')
    if bundle['execution_bundle_id'] in ('e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225'):
        from harness.e2e_observation_cadence import limits
        if options.get('observation_cadence')!='on_v1' or bundle.get('estimator_cadence')!=limits(bundle['speed3_profile']['observation_period_s']):
            raise ValueError('CADENCE_PROFILE_MISMATCH')
    if bundle['execution_bundle_id'] in ('e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225') and (options.get('route_guard')!='dev_nominal_v1' or not options.get('dev_light')):
        raise ValueError('DEV_ROUTE_GUARD_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225') and options.get('beam_axis')!='undirected_v1':
        raise ValueError('UNDIRECTED_BEAM_AXIS_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v223','e2e18-v224','e2e18-v225') and (options.get('route_coverage')!='native_v1' or not options.get('dev_light')):
        raise ValueError('DEV_ROUTE_COVERAGE_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v224','e2e18-v225') and (options.get('carrier_axes')!='beam_v1' or options.get('carrier_approach')!='standoff_v1'):
        raise ValueError('RGB_CARRIER_AXES_AND_APPROACH_REQUIRED')
    if bundle['execution_bundle_id']=='e2e18-v225' and (options.get('route_extent')!='goal_envelope_v1' or options.get('record_scalars')!='python_v1'):
        raise ValueError('DEV_GOAL_ENVELOPE_REQUIRED')
    for name in ASSETS:
        expected = bundle['source_sha256'].get(name)
        if expected is None or hashlib.sha256((Path(root)/name).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_HASH_MISMATCH:'+name)
