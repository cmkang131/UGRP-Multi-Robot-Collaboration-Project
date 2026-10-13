"""Default-off comparisons combining existing body, perception and dialogue hooks.

No new motion policy: preserve the registered v335/v336 body candidate and its
current GO/ACK guards. fast_v1 enables the existing exact shadow computation;
memory_v1 additionally supplies the existing current-window memory/short vote.
"""
import copy

OPTIONS = ('off', 'fast_v1', 'memory_v1')
VERSIONS = {('e2e18-v335', 'fast_v1'): 340, ('e2e18-v336', 'fast_v1'): 341,
            ('e2e18-v335', 'memory_v1'): 342, ('e2e18-v336', 'memory_v1'): 343}
KEYS = ('perception_fast', 'controller_timing', 'llm_memory', 'vote_ref')


def values(option):
    return dict(perception_fast='shadow_axes_v1', controller_timing='phase_v1',
                llm_memory='v1' if option == 'memory_v1' else 'off',
                vote_ref='v1' if option == 'memory_v1' else 'off')


def parameters(option):
    from harness.e2e_perception_fast import PARAMS as perception
    from harness.e2e_speed_phase import PARAMS as timing
    from harness.e2e_llm_memory import LOG_N, COMMAND_N
    out = dict(perception_fast_parameters=copy.deepcopy(perception),
               controller_timing_parameters=copy.deepcopy(timing))
    if option == 'memory_v1':
        out['llm_memory_parameters'] = dict(log_n=LOG_N, command_n=COMMAND_N)
    return out


def compose(bundle, option='off'):
    if option == 'off':
        return ()
    parent = bundle['execution_bundle_id']
    version = VERSIONS.get((parent, option))
    o = bundle['e2e_options']
    if version is None or not o.get('dev_light') or any(o.get(k, 'off') != 'off' for k in KEYS):
        raise ValueError('REGISTERED_BODY_ARCHITECTURE_STACK_REQUIRED')
    bundle['architecture_stack_parent'] = parent
    bundle['architecture_stack_option_presence'] = {k: k in o for k in KEYS}
    o.update(architecture_stack=option, **values(option))
    bundle.update(parameters(option))
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}',
                  execution_bundle_id=f'e2e18-v{version}', workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',
            'harness/e2e_architecture_stack.py', 'harness/e2e_perception_fast.py',
            'harness/e2e_speed_phase.py', 'harness/e2e_llm_memory.py', 'harness/e2e_vote_ref.py')


def parent_for_validation(bundle):
    o = bundle['e2e_options']
    option = o.get('architecture_stack')
    parent = bundle.get('architecture_stack_parent')
    version = VERSIONS.get((parent, option))
    presence = bundle.get('architecture_stack_option_presence', {})
    if (version is None or not o.get('dev_light')
            or bundle['execution_bundle_id'] != f'e2e18-v{version}'
            or set(presence) != set(KEYS) or any(type(v) is not bool for v in presence.values())
            or any(o.get(k) != v for k, v in values(option).items())
            or any(bundle.get(k) != v for k, v in parameters(option).items())
            or (option == 'fast_v1' and 'llm_memory_parameters' in bundle)):
        raise ValueError('REGISTERED_BODY_ARCHITECTURE_STACK_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = parent
    old.pop('architecture_stack_parent')
    old.pop('architecture_stack_option_presence')
    old['e2e_options'].pop('architecture_stack')
    for k in KEYS:
        old['e2e_options'].pop(k)
        if presence[k]:
            old['e2e_options'][k] = 'off'
    for k in parameters(option):
        old.pop(k)
    return old
