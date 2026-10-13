"""Registered, default-off SDK comparisons on the DEV carry-through route.

Each option changes only the already reviewed own-input SDK hook. The route,
current GO/ACK contract and independent physical evaluator retain their guards.
"""
import copy

KEYS = ('approach_floor', 'clip_hysteresis', 'vote_ref', 'perception_fast', 'controller_timing')
PARENT = 'e2e18-v323'
VERSIONS = {
    ('off', 'off', 'off', 'shadow_axes_v1', 'phase_v1'): 324,
    ('off', 'v1', 'off', 'shadow_axes_v1', 'phase_v1'): 325,
    ('v1', 'v1', 'off', 'shadow_axes_v1', 'phase_v1'): 326,
    ('v1', 'v1', 'v1', 'shadow_axes_v1', 'phase_v1'): 327,
}


def parameters(options):
    from harness.e2e_approach_floor import parameters as floor
    from harness.e2e_clip_hysteresis import PARAMS as hysteresis
    from harness.e2e_perception_fast import PARAMS as perception
    from harness.e2e_speed_phase import PARAMS as timing
    out = {}
    for key, value, data in (
            ('approach_floor', options[0], floor('v1')),
            ('clip_hysteresis', options[1], hysteresis),
            ('perception_fast', options[3], perception),
            ('controller_timing', options[4], timing)):
        if value != 'off':
            out[key + '_parameters'] = copy.deepcopy(data)
    return out


def compose(bundle, **options):
    key = tuple(options.get(k, 'off') for k in KEYS)
    if all(value == 'off' for value in key):
        return ()
    if bundle['execution_bundle_id'] != PARENT or key not in VERSIONS:
        raise ValueError('REGISTERED_POST_RELOOK_SDK_COMBINATION_REQUIRED')
    version = VERSIONS[key]
    bundle['post_relook_stack_parent'] = PARENT
    bundle['e2e_options'].update(zip(KEYS, key))
    bundle.update(parameters(key))
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}',
                  execution_bundle_id=f'e2e18-v{version}', workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',
            'harness/e2e_post_relook_stack.py', 'harness/e2e_speed_phase.py',
            'harness/e2e_approach_floor.py', 'harness/e2e_clip_hysteresis.py',
            'harness/e2e_vote_ref.py', 'harness/e2e_perception_fast.py')


def parent_for_validation(bundle):
    key = tuple(bundle['e2e_options'].get(k, 'off') for k in KEYS)
    version = VERSIONS.get(key)
    expected = parameters(key)
    if (bundle.get('post_relook_stack_parent') != PARENT or version is None
            or bundle['execution_bundle_id'] != f'e2e18-v{version}'
            or any(bundle.get(k) != value for k, value in expected.items())
            or any(k + '_parameters' in bundle for k in KEYS
                   if key[KEYS.index(k)] == 'off')):
        raise ValueError('REGISTERED_POST_RELOOK_SDK_COMBINATION_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = PARENT
    old.pop('post_relook_stack_parent')
    for k in KEYS:
        old['e2e_options'].pop(k, None)
        old.pop(k + '_parameters', None)
    return old
