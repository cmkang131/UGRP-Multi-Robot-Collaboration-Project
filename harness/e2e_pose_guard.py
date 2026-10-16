"""Default-off full SE(2) innovation rejection for the existing own-map reporter."""
from dataclasses import replace
from harness.ego_pose_continuity import MAHALANOBIS,MAHALANOBIS_SE2,PoseView

OPTION='se2_innovation_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v226.json'


def configure(goal,option='off'):
    if option=='off':return
    if option!=OPTION:raise ValueError('UNKNOWN_POSE_GUARD')
    view=getattr(goal,'_pose_continuity_view',None)
    if not isinstance(view,PoseView) or view.options.correction_gate!=MAHALANOBIS:
        raise ValueError('EXISTING_INNOVATION_REPORTER_REQUIRED')
    view.options=replace(view.options,correction_gate=MAHALANOBIS_SE2)
    view.reporter.options=view.options


def compose(bundle,option,protocol_recovery='off'):
    if option=='off':
        if protocol_recovery!='off':raise ValueError('PROTOCOL_RECOVERY_REQUIRES_SE2_GUARD')
        return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v225' or bundle['e2e_options'].get('pose_fix')!='innovation':
        raise ValueError('POSE_GUARD_REQUIRES_V225_INNOVATION')
    if protocol_recovery!='envelope_retry_v1':raise ValueError('V226_REQUIRES_PROTOCOL_RECOVERY')
    bundle['e2e_options'].update(pose_guard=option,protocol_recovery=protocol_recovery)
    bundle.update(schema='ugrp.e2e_ownmap_live.v226',execution_bundle_id='e2e18-v226',workflow_version='7.119.0')
    return (WORKFLOW,)
