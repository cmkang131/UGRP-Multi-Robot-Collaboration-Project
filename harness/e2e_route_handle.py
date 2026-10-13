"""Model-selected own-route reference, compiled to the validated typed envelope.

The original model text remains in wire evidence. Compilation cannot approve,
claim, grant GO/ACK, choose a recipient, or substitute a different route.
"""
import copy
from harness import e2e_own_inputs as own

OPTION='typed_ref_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v233.json'


def expand(dialogue,value,context):
    if not isinstance(value,dict) or value.get('kind')!='OwnRouteRef':return value
    if getattr(dialogue,'route_handle','off')!=OPTION:raise own.ContractViolation('ROUTE_HANDLE_NOT_ENABLED')
    own.closed(value,('kind','route_hash'),'OWN_ROUTE_REF')
    planned=context['state'].get('own_route')
    if context['actor']!='r1' or planned is None:raise own.ContractViolation('CAPTURED_R1_ROUTE_REQUIRED')
    from harness.e2e_dialogue import wire_route
    route=wire_route(planned)
    if value['route_hash']!=route['route_hash']:raise own.ContractViolation('CAPTURED_ROUTE_HANDLE_MISMATCH')
    return dict(kind='OwnRoute',route=route,source_message_id=None)


def prompt(body,system):
    proposal=body.get('own_route_proposal')
    if body['robot_id']!='r1' or proposal is None:return system
    ref=dict(kind='OwnRouteRef',route_hash=proposal['route']['route_hash'])
    body['route_contract_example']=ref
    body['action_message_contract']['message_element']['contract']=ref
    step=body.get('current_protocol_step',{})
    if step.get('step')=='propose':
        step['instruction']='If you choose to propose this own route, send one message with the exact OwnRouteRef contract below. The host resolves it to this captured validated own route. Do not copy geometry into the reply.'
        body['reply_format_example']=dict(request_id=body['request_id'],action=dict(kind='continue'),
            decision_sources=['own_belief'],messages=[dict(recipients=['r2'],text='Proposing my observed route to B.',reply_to=None,contract=ref)])
    system=system.replace('r1 must send own_route_proposal unchanged as the message contract to r2 (or via the permitted leader).','r1 may select the exact OwnRouteRef contract shown below to propose the captured own route to r2.')
    system=system.replace('contract is the ENTIRE own_route_proposal object, including kind="OwnRoute", route, and source_message_id; never copy only own_route_proposal.route.',
        'contract is the exact route_contract_example OwnRouteRef object; the host resolves only the named captured route.')
    system+=' For this interface, propose by exact OwnRouteRef rather than copying route geometry. This is a typed command argument. No proposal, approval or action occurs unless you explicitly select it in your response.'
    return system


def compose(bundle,option):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v232':raise ValueError('ROUTE_HANDLE_REQUIRES_V232')
    bundle['e2e_options']['route_handle']=option
    bundle.update(schema='ugrp.e2e_ownmap_live.v233',execution_bundle_id='e2e18-v233',workflow_version='7.126.0')
    return (WORKFLOW,)
