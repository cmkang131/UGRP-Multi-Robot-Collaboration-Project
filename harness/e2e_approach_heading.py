"""Opt-in rotate-before-straight-pulse alignment for own pregrasp paths."""
OPTIONS=('path10_v1','path20_v1')
VERSIONS=dict(zip(OPTIONS,(261,262)))
THRESHOLDS=dict(zip(OPTIONS,(.10,.20)))


def parameters(option):
    return dict(path_rotate_min_angle_rad=THRESHOLDS[option],scope='own_pregrasp_path',
                command_port='existing_calibrated_single_axis_pulses',final_xy_m=.03,final_yaw_rad=.06)


def kwargs(transport):
    option=getattr(transport,'approach_heading','off')
    if option=='off':return {}
    if option not in OPTIONS:raise ValueError('UNKNOWN_APPROACH_HEADING')
    return dict(rotate_min_angle=THRESHOLDS[option])


def compose(bundle,option):
    if option=='off':return ()
    if option not in OPTIONS or bundle['execution_bundle_id']!='e2e18-v260':
        raise ValueError('APPROACH_HEADING_REQUIRES_V260')
    v=VERSIONS[option];bundle['e2e_options']['approach_heading']=option
    bundle['approach_heading_parameters']=parameters(option)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}',execution_bundle_id=f'e2e18-v{v}',workflow_version=f'7.{v-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json',)
