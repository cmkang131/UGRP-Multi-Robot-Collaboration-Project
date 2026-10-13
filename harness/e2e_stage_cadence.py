"""Default-off bounded gaze cadence and explicit command-stage physics profile."""
GAZE='settled_frames_v1'
PHYSICS='pregrasp_dt1_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v232.json'
GAZE_PERIOD_S=2.4
GAZE_SETTLE_S=.8


def settling(transport,rid,now):
    return (getattr(transport,'gaze_cadence','off')==GAZE and
            now<transport.approach.get(rid,{}).get('gaze_settle_until',-1.))


def admit_gaze(transport,rid,now,actions,command):
    if getattr(transport,'gaze_cadence','off')!=GAZE:return [*actions,command]
    state=transport.approach.setdefault(rid,{})
    if not actions or now<state.get('next_gaze',-1.):return [command]
    state.update(next_gaze=now+GAZE_PERIOD_S,gaze_settle_until=now+GAZE_SETTLE_S)
    transport.event(now,'own_gaze_settle',robot_id=rid,until=now+GAZE_SETTLE_S,next_gaze=now+GAZE_PERIOD_S)
    return [*actions,dict(kind='hold')]


def compose(bundle,gaze,physics,protocol):
    if gaze=='off' and physics=='off' and protocol=='off':return ()
    if gaze!=GAZE or physics!=PHYSICS or protocol!='same_route_v1' or bundle['execution_bundle_id']!='e2e18-v231':
        raise ValueError('STAGE_CADENCE_REQUIRES_V231')
    bundle['e2e_options'].update(gaze_cadence=gaze,stage_physics=physics,protocol_idempotency=protocol)
    bundle['stage_physics_profile']=dict(mapping_dt_s=.002,align_dt_s=.001,contact_dt_s=.00025,source='own_execution_phase_and_issued_gripper_command')
    bundle.update(schema='ugrp.e2e_ownmap_live.v232',execution_bundle_id='e2e18-v232',workflow_version='7.125.0')
    return (WORKFLOW,)
