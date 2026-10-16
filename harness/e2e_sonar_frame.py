"""Explicit v3 front-sonar frame repair; old source bundles remain unchanged."""
OPTION='site_z_v1'
VERSIONS={'range_v1':245,'range_wall_v1':246,'range_wall_slots_v1':247,'off':248}


def compose(bundle,option):
    if option=='off':return ()
    clearance=bundle['e2e_options'].get('arm_clearance','off')
    expected={'range_v1':242,'range_wall_v1':243,'range_wall_slots_v1':244,'off':241}
    if option!=OPTION or clearance not in expected or bundle['execution_bundle_id']!=f'e2e18-v{expected[clearance]}':
        raise ValueError('SONAR_FRAME_REQUIRES_V241_CLEARANCE_FAMILY')
    version=VERSIONS[clearance]
    bundle['e2e_options']['sonar_frame']=option
    bundle['sonar_mount_interpretation']={'site_axis':'positive_z','origin':'site_transducer_face','cone_axis':'positive_x','old_results_inherited':False}
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}',execution_bundle_id=f'e2e18-v{version}',workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)
