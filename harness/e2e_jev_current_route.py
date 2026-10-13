"""Register the existing Mac Jev selector on the current own-RGB route.

Gemma retains all dialogue and grip classification. Only action selection changes;
the captured-route, own-image freshness and current GO/ACK checks stay intact.
"""
PARENT = 'e2e18-v275'
BUNDLE_ID = 'e2e18-v278'
WORKFLOW = 'configs/simulation_workflows.d/e2e18_v278.json'
PARAMS = dict(parent=PARENT, gemma_dialogue=True, gemma_own_rgb_grip=True,
              jev_action_only=True, handshake_windows_unchanged=True)


def compose(bundle):
    if bundle['e2e_options'].get('decider', 'off') != 'jev_v1' or bundle['execution_bundle_id'] != PARENT:
        return ()
    bundle['jev_current_route'] = dict(PARAMS)
    bundle.update(schema='ugrp.e2e_ownmap_live.v278', execution_bundle_id=BUNDLE_ID,
                  workflow_version='7.171.0', inherited_results=False)
    return (WORKFLOW,)


def parent_for_validation(bundle):
    if (bundle['e2e_options'].get('decider') != 'jev_v1'
            or bundle.get('jev_current_route') != PARAMS
            or bundle.get('inherited_results') is not False):
        raise ValueError('REGISTERED_CURRENT_JEV_REQUIRED')
    # Existing parent validation checks every inherited parameter and asset.
    return dict(bundle, execution_bundle_id=PARENT)
