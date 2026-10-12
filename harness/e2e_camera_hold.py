"""Separate wheel waiting from actuator trajectory cancellation, opt-in.

Only normal open-gripper mapping/approach holds are translated. Backend
emergency hold/close and loaded/grasp phases retain their original semantics.
"""
OPTION='wheel_only_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v240.json'


def actions(commands,robots,phase,option='off'):
    if option=='off':return commands
    if option!=OPTION:raise ValueError('UNKNOWN_CAMERA_HOLD')
    return [(rid,dict(kind='wait') if a['kind']=='hold' and phase in ('mapping','align')
             and robots[rid].servo.get(1,0)>=1900 else a) for rid,a in commands]


def compose(bundle,option):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v239':
        raise ValueError('CAMERA_HOLD_REQUIRES_V239')
    bundle['e2e_options']['camera_hold']=option
    bundle.update(schema='ugrp.e2e_ownmap_live.v240',execution_bundle_id='e2e18-v240',workflow_version='7.133.0')
    return (WORKFLOW,)
