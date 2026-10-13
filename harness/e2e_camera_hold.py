"""Separate wheel waiting from actuator trajectory cancellation, opt-in.

Only normal open-gripper mapping/approach holds are translated. Backend
emergency hold/close and loaded/grasp phases retain their original semantics.
"""
OPTION='wheel_only_v1'
ZERO='zero_wheel_v1'
ZERO_WORKFLOW='configs/simulation_workflows.d/e2e18_v241.json'
WORKFLOW='configs/simulation_workflows.d/e2e18_v240.json'


def actions(commands,robots,phase,option='off'):
    if option=='off':return commands
    if option not in (OPTION,ZERO):raise ValueError('UNKNOWN_CAMERA_HOLD')
    stop=dict(kind='wait') if option==OPTION else dict(kind='mecanum',forward=0.,left=0.,turn=0.,duration_s=0.)
    return [(rid,dict(stop) if a['kind']=='hold' and phase in ('mapping','align')
             and robots[rid].servo.get(1,0)>=1900 else a) for rid,a in commands]


def compose(bundle,option):
    if option=='off':return ()
    if option not in (OPTION,ZERO) or bundle['execution_bundle_id']!='e2e18-v239':
        raise ValueError('CAMERA_HOLD_REQUIRES_V239')
    bundle['e2e_options']['camera_hold']=option
    version=240 if option==OPTION else 241
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}',execution_bundle_id=f'e2e18-v{version}',workflow_version=f'7.{version-107}.0')
    return (WORKFLOW if option==OPTION else ZERO_WORKFLOW,)
