"""Registered comparison: bounded rule body + rule protocol + Gemma speech."""
import copy

PARENT = 'e2e18-v349'
VALUES = dict(llm_memory='v1_commands', dialogue_decider='code_v1',
              perception_fast='shadow_axes_v1', controller_timing='phase_v1')


def parameters():
    from harness.e2e_llm_memory import LOG_N, COMMAND_N
    from harness.e2e_perception_fast import PARAMS as perception
    from harness.e2e_speed_phase import PARAMS as timing
    return dict(llm_memory_parameters=dict(log_n=LOG_N, command_n=COMMAND_N),
                perception_fast_parameters=copy.deepcopy(perception), controller_timing_parameters=copy.deepcopy(timing))


def compose(bundle, option='off'):
    if option == 'off': return ()
    o = bundle['e2e_options']
    if (option != 'code_v1' or bundle['execution_bundle_id'] != PARENT
            or o.get('body_backend') != 'code_v1' or not o.get('dev_light')
            or any(o.get(k, 'off') != 'off' for k in VALUES)):
        raise ValueError('REGISTERED_CODE_BODY_PARENT_REQUIRED')
    bundle['body_protocol_stack_parent'] = PARENT
    bundle['body_protocol_stack_presence'] = {k: k in o for k in VALUES}
    o.update(body_protocol_stack=option, **VALUES)
    bundle.update(parameters())
    bundle.update(execution_bundle_id='e2e18-v350', schema='ugrp.e2e_ownmap_live.v350', workflow_version='7.243.0')
    return ('configs/simulation_workflows.d/e2e18_v350.json', 'harness/e2e_code_stack.py',
            'harness/e2e_dialogue_decider.py', 'scripts/d1_dialogue_upstream.py',
            'harness/e2e_llm_memory.py', 'harness/e2e_perception_fast.py', 'harness/e2e_speed_phase.py')


def parent_for_validation(bundle):
    o = bundle['e2e_options']; presence = bundle.get('body_protocol_stack_presence', {})
    if (bundle['execution_bundle_id'] != 'e2e18-v350' or bundle.get('body_protocol_stack_parent') != PARENT
            or o.get('body_protocol_stack') != 'code_v1' or set(presence) != set(VALUES)
            or any(type(v) is not bool for v in presence.values())
            or any(o.get(k) != v for k, v in VALUES.items())
            or any(bundle.get(k) != v for k, v in parameters().items())):
        raise ValueError('REGISTERED_CODE_STACK_REQUIRED')
    parent = copy.deepcopy(bundle); parent['execution_bundle_id'] = parent.pop('body_protocol_stack_parent')
    parent.pop('body_protocol_stack_presence'); parent['e2e_options'].pop('body_protocol_stack')
    for k in VALUES:
        parent['e2e_options'].pop(k)
        if presence[k]: parent['e2e_options'][k] = 'off'
    for k in parameters(): parent.pop(k)
    return parent
