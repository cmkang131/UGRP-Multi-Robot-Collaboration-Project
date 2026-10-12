"""New-source admission; historical E2E registrations retain their original SHA."""
import hashlib
from pathlib import Path

OPTION = 'reviewed_v1'
BUNDLE_ID = 'e2e-reviewed-runtime-v210'
WORKFLOW_VERSION = '7.103.0'
WORKFLOW = 'configs/simulation_workflows.d/e2e_reviewed_runtime_v210.json'
# Python import closure cannot discover data selected by Path.read_text().
ASSETS = ('experiments/2026-10-07-mapfree-goal-floor/v3-selection.json',
          'configs/e2e_environment_v1.json', 'configs/e2e_stage2_options_v1.json')


def register(bundle, option='off'):
    if option == 'off':
        return ()
    if option != OPTION:
        raise ValueError('UNKNOWN_E2E_RUNTIME_REGISTRATION')
    bundle['parent_execution_bundle_id'] = bundle['execution_bundle_id']
    bundle.update(schema='ugrp.e2e_ownmap_live.v210', execution_bundle_id=BUNDLE_ID,
                  workflow_version=WORKFLOW_VERSION, inherited_results=False)
    # The command estimator has only the measured full-duration profiles.
    # Retain the established ceil-to-full-pulse schedule, including its logged
    # overshoot; do not invent a measured response for fractional durations.
    bundle['e2e_options'].update(runtime_registration=OPTION, pulse_budget='off',
                               pulse_authorization='current_go_v1')
    return (*ASSETS, WORKFLOW, 'scripts/run_e2e_reviewed.py')


def require_current(bundle, root):
    options = bundle['e2e_options']
    if (options.get('runtime_registration') != OPTION or
            bundle['execution_bundle_id'] != BUNDLE_ID or options['pulse_budget'] != 'off' or
            options.get('pulse_authorization') != 'current_go_v1'):
        raise ValueError('E2E_ORIGINAL_CHECKOUT_OR_REVIEWED_RUNTIME_REQUIRED')
    for name in ASSETS:
        expected = bundle['source_sha256'].get(name)
        if expected is None or hashlib.sha256((Path(root)/name).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_HASH_MISMATCH:'+name)
