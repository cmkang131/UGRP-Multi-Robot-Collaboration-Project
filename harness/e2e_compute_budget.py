"""Default-off smaller visual/particle workload, with an explicit new cohort."""
from dataclasses import asdict
from harness.e2e_speed4 import Options,record
OPTION='lean_v1'
PROFILE=asdict(Options(render_half=True,rbpf_particles=30,floor_ray_stride=4,vector_envelopes=True,vector_door_pairs=True))
WORKFLOW='configs/simulation_workflows.d/e2e18_v236.json'


def compose(bundle,option):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v235':
        raise ValueError('COMPUTE_BUDGET_REQUIRES_V235')
    bundle['e2e_options']['compute_budget']=option
    bundle['speed4']=dict(PROFILE)
    bundle['speed4_record']=record(Options(**PROFILE))
    bundle.update(schema='ugrp.e2e_ownmap_live.v236',execution_bundle_id='e2e18-v236',workflow_version='7.129.0')
    return (WORKFLOW,)
