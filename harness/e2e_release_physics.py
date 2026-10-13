"""Explicit unloaded relook timestep comparison; loaded phases stay fine."""
import copy
from sim.e2e_stage_physics import RELEASE,RELEASE_SETTLE_S

VERSIONS={'e2e18-v275':279,'e2e18-v276':280,'e2e18-v277':281,'e2e18-v278':282,'e2e18-v297':298}
PROFILE=dict(mapping_dt_s=.002,align_dt_s=.001,contact_dt_s=.00025,
             relook_open_dt_s=.001,release_settle_s=RELEASE_SETTLE_S,
             release_basis='both_issued_gripper_open_commands_and_relook_phase',
             source='own_execution_phase_and_issued_gripper_command')


def compose(bundle,option):
    if option!='release_dt1_v1':return ()
    parent=bundle['execution_bundle_id']
    if parent not in VERSIONS:raise ValueError('RELEASE_PHYSICS_CURRENT_ROUTE_REQUIRED')
    v=VERSIONS[parent]
    bundle['release_physics_parent']=parent
    bundle['e2e_options']['stage_physics']=RELEASE
    bundle['stage_physics_profile']=copy.deepcopy(PROFILE)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{v}',execution_bundle_id=f'e2e18-v{v}',
                  workflow_version=f'7.{v-107}.0',inherited_results=False)
    return (f'configs/simulation_workflows.d/e2e18_v{v}.json',)


def parent_for_validation(bundle):
    parent=bundle.get('release_physics_parent')
    if (parent not in VERSIONS or bundle['execution_bundle_id']!=f'e2e18-v{VERSIONS[parent]}'
            or bundle['e2e_options'].get('stage_physics')!=RELEASE
            or bundle.get('stage_physics_profile')!=PROFILE):
        raise ValueError('REGISTERED_RELEASE_PHYSICS_REQUIRED')
    old=copy.deepcopy(bundle)
    old['execution_bundle_id']=parent
    old['e2e_options']['stage_physics']='pregrasp_dt1_v1'
    old['stage_physics_profile']=dict(mapping_dt_s=.002,align_dt_s=.001,contact_dt_s=.00025,
                                    source='own_execution_phase_and_issued_gripper_command')
    return old
