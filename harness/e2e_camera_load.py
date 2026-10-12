"""Explicit nominal commanded FK under unknown load; never measured joints."""
from contextvars import ContextVar
from contextlib import contextmanager
OPTION='nominal_command_v1'
ACTIVE=ContextVar('e2e_camera_load',default='off')
WORKFLOW='configs/simulation_workflows.d/e2e18_v227.json'

@contextmanager
def using(option):
    if option not in ('off',OPTION):raise ValueError('UNKNOWN_CAMERA_LOAD')
    token=ACTIVE.set(option)
    try:yield
    finally:ACTIVE.reset(token)


def qualification(servo):
    closed=float(servo[1])<=1600
    return dict(camera_load=ACTIVE.get(),geometry_source='own_command_fixed_kinematics',
        grip_command_closed=closed,actual_joint_state_observed=False,actual_load_observed=False,
        load_deformation_compensated=False,loaded_geometry_qualified=False if closed else None)


def compose(bundle,option):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v226':raise ValueError('CAMERA_LOAD_REQUIRES_V226')
    bundle['e2e_options']['camera_load']=option
    bundle.update(schema='ugrp.e2e_ownmap_live.v227',execution_bundle_id='e2e18-v227',workflow_version='7.120.0')
    return (WORKFLOW,)
