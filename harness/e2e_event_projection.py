"""Cheap event keys; the actual model request still runs full input validation."""
OPTION='route_hash_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v231.json'


def route_for_events(trial,rid,now):
    robot=trial.links[rid].inner
    if getattr(trial,'event_projection','off')!=OPTION:
        return robot.own_inputs_at(now).get('own_route')
    if robot.now>now+1e-8:raise ValueError('FUTURE_EVENT_OWNER_STATE')
    packet=robot.packet
    return None if packet is None else {'route_hash':packet['route']['route_hash']}


def compose(bundle,event,progress):
    if event=='off' and progress=='off':return ()
    if event!=OPTION or progress!='backup_replan_v1' or bundle['execution_bundle_id']!='e2e18-v230':
        raise ValueError('EVENT_PROJECTION_REQUIRES_V230')
    bundle['e2e_options'].update(event_projection=event,pregrasp_progress=progress)
    bundle.update(schema='ugrp.e2e_ownmap_live.v231',execution_bundle_id='e2e18-v231',workflow_version='7.124.0')
    return (WORKFLOW,)
