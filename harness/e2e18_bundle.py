"""Explicit E2E18 integration; former bundles retain their registered identity."""
BUNDLE_ID = 'e2e18-v216'
WORKFLOW = 'configs/simulation_workflows.d/e2e18_v216.json'
SPEED4 = dict(render_half=False,rbpf_particles=50,floor_ray_stride=2,
              moving_observation_stride=1,vector_envelopes=True,vector_door_pairs=True)
REQUIRED = dict(speed3='adaptive_v1',explore_deadlock='replan_v1',
    boundary_association='extent_v1',boundary_retry='navigation_v1',boundary_coverage='native_v1',
    boundary_views='standoff_fullquad_v1',b_marker_detect='partial_known_size_v1',
    runtime_registration='reviewed_v1',dev_light=True)


def compose(bundle, partial_accept):
    options=bundle['e2e_options']
    if any(options.get(k)!=v for k,v in REQUIRED.items()) or bundle.get('speed4')!=SPEED4:
        raise ValueError('E2E18_ALL_REGISTERED_OPTIONS_REQUIRED')
    bundle['e2e18_parent_bundle_id']=bundle['execution_bundle_id']
    bundle.update(schema='ugrp.e2e_ownmap_live.v216',execution_bundle_id=BUNDLE_ID,
                  workflow_version='7.109.0',inherited_results=False)
    options['b_partial_accept']=partial_accept
    from harness.e2e_b_partial_accept import PARAMS
    bundle['b_partial_acceptance']=dict(PARAMS,complete_claim=False,source='own_rgb_and_static_size')
    return (WORKFLOW,'maps/zones_e2e/zone_wide_door_e2e_b80_v1.json')


def validate(bundle):
    speed4=SPEED4
    if bundle['execution_bundle_id'] in ('e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271'):
        from harness.e2e_compute_budget import PROFILE
        speed4=PROFILE
    if (bundle['e2e_options'].get('b_partial_accept')!='on_v1' or
        any(bundle['e2e_options'].get(k)!=v for k,v in REQUIRED.items()) or bundle.get('speed4')!=speed4):
        raise ValueError('E2E18_ALL_REGISTERED_OPTIONS_REQUIRED')
