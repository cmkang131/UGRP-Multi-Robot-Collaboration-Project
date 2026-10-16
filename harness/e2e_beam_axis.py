"""Default-off undirected beam-axis check; directed near-end geometry is retained."""
import math

OPTION='undirected_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v222.json'


def error(yaw, option='off'):
    if option=='off':return abs(yaw)
    if option!=OPTION:raise ValueError('UNKNOWN_BEAM_AXIS_OPTION')
    # A rectangle's collision footprint is pi-periodic. This does not flip
    # the measured near-end ray or the offset used to recover beam center.
    return abs(.5*math.atan2(math.sin(2*yaw),math.cos(2*yaw)))


def compose(bundle,option):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v221':
        raise ValueError('BEAM_AXIS_REQUIRES_V221')
    bundle['e2e_options']['beam_axis']=option
    bundle.update(schema='ugrp.e2e_ownmap_live.v222',execution_bundle_id='e2e18-v222',workflow_version='7.115.0')
    return (WORKFLOW,)
