"""New-source admission; historical E2E registrations retain their original SHA."""
import hashlib
from pathlib import Path

OPTION = 'reviewed_v1'
BUNDLE_ID = 'e2e-reviewed-runtime-v210'
WORKFLOW_VERSION = '7.103.0'
NATIVE_COVERAGE_ID = 'e2e-boundary-native-v213'
WORKFLOW = 'configs/simulation_workflows.d/e2e_reviewed_runtime_v210.json'
# Python import closure cannot discover data selected by Path.read_text().
ASSETS = ('experiments/2026-10-07-mapfree-goal-floor/v3-selection.json',
          'configs/e2e_environment_v1.json', 'configs/e2e_stage2_options_v1.json')


def register(bundle, option='off'):
    if option == 'off':
        return ()
    if option != OPTION:
        raise ValueError('UNKNOWN_E2E_RUNTIME_REGISTRATION')
    native = bundle['execution_bundle_id'] == NATIVE_COVERAGE_ID
    bundle['parent_execution_bundle_id'] = bundle['execution_bundle_id']
    bundle.update(schema='ugrp.e2e_ownmap_live.v210', execution_bundle_id=BUNDLE_ID,
                  workflow_version=WORKFLOW_VERSION, inherited_results=False)
    # The command estimator has only the measured full-duration profiles.
    # Retain the established ceil-to-full-pulse schedule, including its logged
    # overshoot; do not invent a measured response for fractional durations.
    bundle['e2e_options'].update(runtime_registration=OPTION, pulse_budget='off',
                               pulse_authorization='current_go_v1')
    if native:
        bundle.update(schema='ugrp.e2e_ownmap_live.v213', execution_bundle_id=NATIVE_COVERAGE_ID,
                      workflow_version='7.106.0', parent_execution_bundle_id=BUNDLE_ID)
    return (*ASSETS, WORKFLOW, 'scripts/run_e2e_reviewed.py')


def require_current(bundle, root):
    if bundle['execution_bundle_id']=='e2e18-v346':
        from harness.e2e_body_code import parent_for_validation as code_parent
        return require_current(code_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v344','e2e18-v345'):
        from harness.e2e_body_skills import parent_for_validation as skill_parent
        return require_current(skill_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v340','e2e18-v341','e2e18-v342','e2e18-v343'):
        from harness.e2e_architecture_stack import parent_for_validation as architecture_parent
        return require_current(architecture_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v330','e2e18-v331','e2e18-v332'):
        from harness.e2e_llm_memory import parent_for_validation as memory_parent
        return require_current(memory_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v335','e2e18-v336','e2e18-v337'):
        from harness.e2e_body_controller import parent_for_validation as body_parent
        return require_current(body_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v324','e2e18-v325','e2e18-v326','e2e18-v327','e2e18-v328','e2e18-v329'):
        from harness.e2e_post_relook_stack import parent_for_validation as stack_parent
        return require_current(stack_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v316','e2e18-v317','e2e18-v318'):
        from harness.e2e_perception_fast import parent_for_validation as perception_parent
        return require_current(perception_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v320','e2e18-v321','e2e18-v322','e2e18-v323'):
        from harness.e2e_post_relook import parent_for_validation as post_parent
        return require_current(post_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v314','e2e18-v315'):
        from harness.e2e_vote_ref import parent_for_validation as vote_parent
        return require_current(vote_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v312','e2e18-v313'):
        from harness.e2e_clip_hysteresis import parent_for_validation as hyst_parent
        return require_current(hyst_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v310','e2e18-v311'):
        from harness.e2e_approach_floor import parent_for_validation as floor_parent
        return require_current(floor_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v302','e2e18-v303','e2e18-v304','e2e18-v305'):
        from harness.e2e_relook_giveup import parent_for_validation as giveup_parent
        return require_current(giveup_parent(bundle),root)
    if bundle['execution_bundle_id'] in ('e2e18-v279','e2e18-v280','e2e18-v281','e2e18-v282','e2e18-v298','e2e18-v301'):
        from harness.e2e_release_physics import parent_for_validation
        return require_current(parent_for_validation(bundle),root)
    if bundle['execution_bundle_id'] == 'e2e18-v278':
        from harness.e2e_jev_current_route import parent_for_validation
        return require_current(parent_for_validation(bundle), root)
    options = bundle['e2e_options']
    if (options.get('runtime_registration') != OPTION or
            bundle['execution_bundle_id'] not in (BUNDLE_ID, NATIVE_COVERAGE_ID, 'e2e-speed3-v214', 'e2e-speed3-v215', 'e2e18-v216','e2e18-v217','e2e18-v218','e2e18-v219','e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') or options['pulse_budget'] != 'off' or
            options.get('pulse_authorization') != 'current_go_v1'):
        raise ValueError('E2E_ORIGINAL_CHECKOUT_OR_REVIEWED_RUNTIME_REQUIRED')
    if bundle['execution_bundle_id'] == NATIVE_COVERAGE_ID and not (
            options.get('boundary_coverage') == 'native_v1' and options.get('dev_light') is True and
            options.get('boundary_association') == 'extent_v1'):
        raise ValueError('DEV_BOUNDARY_NATIVE_REGISTRATION_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e-speed3-v214','e2e-speed3-v215','e2e18-v216','e2e18-v217','e2e18-v218','e2e18-v219','e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from sim.e2e_speed3_profile import PROFILES
        mode=options.get('speed3')
        if mode not in PROFILES or any(bundle.get('speed3_profile',{}).get(k)!=v for k,v in PROFILES[mode].items()):
            raise ValueError('SPEED3_PROFILE_MISMATCH')
        if not options.get('exact_speedups') or not all(options['exact_speedups'].values()):
            raise ValueError('SPEED3_ALL_EXACT_OPTIONS_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v216','e2e18-v217','e2e18-v218','e2e18-v219','e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e18_bundle import validate
        validate(bundle)
        if bundle['execution_bundle_id'] in ('e2e18-v219','e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('speed5')!='lean_v3' or bundle.get('opencv_threads')!=1 or bundle.get('coarse_grid_dtype')!='float32'):
            raise ValueError('E2E18_SPEED5_PROFILE_MISMATCH')
        if bundle['execution_bundle_id']=='e2e18-v218' and (options.get('speed5')!='lean_v2' or bundle.get('opencv_threads')!=1):
            raise ValueError('SPEED5_RUNTIME_PROFILE_MISMATCH')
    if bundle['execution_bundle_id'] in ('e2e18-v220','e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e_observation_cadence import limits
        if options.get('observation_cadence')!='on_v1' or bundle.get('estimator_cadence')!=limits(bundle['speed3_profile']['observation_period_s']):
            raise ValueError('CADENCE_PROFILE_MISMATCH')
    if bundle['execution_bundle_id'] in ('e2e18-v221','e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('route_guard')!='dev_nominal_v1' or not options.get('dev_light')):
        raise ValueError('DEV_ROUTE_GUARD_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v222','e2e18-v223','e2e18-v224','e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and options.get('beam_axis')!='undirected_v1':
        raise ValueError('UNDIRECTED_BEAM_AXIS_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v223','e2e18-v224','e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('route_coverage')!='native_v1' or not options.get('dev_light')):
        raise ValueError('DEV_ROUTE_COVERAGE_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v224','e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('carrier_axes')!='beam_v1' or options.get('carrier_approach')!='standoff_v1'):
        raise ValueError('RGB_CARRIER_AXES_AND_APPROACH_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v225','e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('route_extent')!='goal_envelope_v1' or options.get('record_scalars')!='python_v1'):
        raise ValueError('DEV_GOAL_ENVELOPE_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v226','e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('pose_guard')!='se2_innovation_v1' or options.get('protocol_recovery')!='envelope_retry_v1'):
        raise ValueError('SE2_INNOVATION_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v227','e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('camera_load')!='nominal_command_v1' or options.get('route_tokens')!='1600_v1' or bundle.get('model_request_overrides')!={'max_tokens':1600}):
        raise ValueError('CURRENT_E2E_CAMERA_LOAD_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v228','e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('protocol_progress')!='stage_retry_v1' or options.get('route_cost')!='bounded_morphology_v1'):
        raise ValueError('CURRENT_PROTOCOL_PROGRESS_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v229','e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('align_progress')!='dev_continue_v1' or options.get('pregrasp_recovery')!='bounded_search_v1'):
        raise ValueError('CURRENT_DEV_ALIGN_RECOVERY_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v230','e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('pregrasp_gaze')!='own_bearing_v1' or options.get('search_bearing')!='last_seen_v1' or options.get('pulse_admission')!='finish_active_v1'):
        raise ValueError('CURRENT_PREGRASP_GAZE_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v231','e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('event_projection')!='route_hash_v1' or options.get('pregrasp_progress')!='backup_replan_v1'):
        raise ValueError('CURRENT_EVENT_PROGRESS_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v232','e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('protocol_idempotency')!='same_route_v1' or options.get('gaze_cadence')!='settled_frames_v1' or options.get('stage_physics')!='pregrasp_dt1_v1' or bundle.get('stage_physics_profile')!=dict(mapping_dt_s=.002,align_dt_s=.001,contact_dt_s=.00025,source='own_execution_phase_and_issued_gripper_command')):
        raise ValueError('CURRENT_STAGE_CADENCE_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v233','e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('route_handle')!='typed_ref_v1' or options.get('boundary_frame')!='observed_own_v1'):
        raise ValueError('CURRENT_ROUTE_HANDLE_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v234','e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('beam_end_model')!='long_side_v1' or options.get('beam_avoidance')!='own_obstacle_v1'):
        raise ValueError('CURRENT_BEAM_END_MODEL_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v235','e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('pregrasp_acquire')!='remember_scan_v1' or options.get('align_queues')!='per_robot_v1' or options.get('beam_decode')!='once_v1' or options.get('mapping_acquire')!='interleaved_v1'):
        raise ValueError('CURRENT_PREGRASP_ACQUISITION_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v236','e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e_compute_budget import PROFILE,OPTION as COMPUTE_OPTION
        if options.get('compute_budget')!=COMPUTE_OPTION or bundle.get('speed4')!=PROFILE:
            raise ValueError('CURRENT_COMPUTE_BUDGET_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v237','e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e_mapping_cadence import PROFILE as CADENCE_PROFILE
        if options.get('mapping_cadence')!='0p6_v1' or options.get('stale_station')!='expire12_v1' or bundle.get('mapping_cadence_profile')!=CADENCE_PROFILE:
            raise ValueError('CURRENT_MAPPING_CADENCE_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v238','e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('carrier_goal')!='seek_own_B_v1' or options.get('blocked_path_recovery')!='backup_v1'):
        raise ValueError('CURRENT_APPROACH_RECOVERY_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v239','e2e18-v240','e2e18-v241','e2e18-v242','e2e18-v243','e2e18-v244','e2e18-v245','e2e18-v246','e2e18-v247','e2e18-v248','e2e18-v249','e2e18-v250','e2e18-v251','e2e18-v252','e2e18-v253','e2e18-v254','e2e18-v255','e2e18-v256','e2e18-v257','e2e18-v258','e2e18-v259','e2e18-v260','e2e18-v261','e2e18-v262','e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') and (options.get('perception_settle')!='command0p6_v1' or options.get('landmark_cache')!='bounded64_v1' or options.get('camera_motion')!='slow_scan_v1'):
        raise ValueError('CURRENT_CAMERA_SETTLE_REQUIRED')
    if bundle['execution_bundle_id']=='e2e18-v240' and options.get('camera_hold')!='wheel_only_v1':
        raise ValueError('CURRENT_CAMERA_HOLD_REQUIRED')
    if bundle['execution_bundle_id']=='e2e18-v241' and options.get('camera_hold')!='zero_wheel_v1':
        raise ValueError('CURRENT_ZERO_WHEEL_WAIT_REQUIRED')
    from harness.e2e_arm_clearance import VERSIONS
    if bundle['execution_bundle_id'] in {f'e2e18-v{v}' for v in VERSIONS.values()}:
        if bundle['execution_bundle_id']!=f"e2e18-v{VERSIONS.get(options.get('arm_clearance'))}" or options.get('camera_hold')!='zero_wheel_v1':
            raise ValueError('REGISTERED_ARM_CLEARANCE_REQUIRED')
    from harness.e2e_sonar_frame import VERSIONS as SONAR_VERSIONS
    if bundle['execution_bundle_id'] in {f'e2e18-v{v}' for v in SONAR_VERSIONS.values()}:
        if options.get('camera_hold')!='zero_wheel_v1' or options.get('sonar_frame')!='site_z_v1' or bundle['execution_bundle_id']!=f"e2e18-v{SONAR_VERSIONS.get(options.get('arm_clearance','off'))}":
            raise ValueError('REGISTERED_SONAR_FRAME_REQUIRED')
    from harness.e2e_acquisition_mobility import VERSIONS as MOBILITY_VERSIONS,PARAMS as MOBILITY_PARAMS
    if bundle['execution_bundle_id'] in {f'e2e18-v{v}' for v in MOBILITY_VERSIONS.values()}:
        if (options.get('camera_hold')!='zero_wheel_v1' or options.get('sonar_frame')!='site_z_v1'
                or options.get('arm_clearance')!='range_wall_v1'
                or bundle['execution_bundle_id']!=f"e2e18-v{MOBILITY_VERSIONS.get(options.get('acquisition_mobility'))}"
                or bundle.get('acquisition_mobility_parameters')!=MOBILITY_PARAMS):
            raise ValueError('REGISTERED_ACQUISITION_MOBILITY_REQUIRED')
    from harness.e2e_approach_commit import VERSIONS as COMMIT_VERSIONS,PARAMS as COMMIT_PARAMS,AGE
    if bundle['execution_bundle_id'] in {f'e2e18-v{v}' for v in COMMIT_VERSIONS.values()}:
        mode=options.get('approach_commit')
        if (options.get('camera_hold')!='zero_wheel_v1' or options.get('sonar_frame')!='site_z_v1'
                or options.get('arm_clearance')!='range_wall_v1' or options.get('acquisition_mobility')!='resume_v1'
                or bundle['execution_bundle_id']!=f'e2e18-v{COMMIT_VERSIONS.get(mode)}'
                or bundle.get('approach_commit_parameters')!={**COMMIT_PARAMS,'max_age_s':AGE.get(mode)}):
            raise ValueError('REGISTERED_APPROACH_COMMIT_REQUIRED')
    from harness.e2e_scan_guard import VERSIONS as SCAN_VERSIONS,PARAMS as SCAN_PARAMS
    if bundle['execution_bundle_id'] in {f'e2e18-v{v}' for v in SCAN_VERSIONS.values()}:
        if (options.get('camera_hold')!='zero_wheel_v1' or options.get('sonar_frame')!='site_z_v1'
                or options.get('arm_clearance')!='range_wall_v1' or options.get('acquisition_mobility')!='resume_v1'
                or options.get('approach_commit')!='memory60_view_v1'
                or bundle['execution_bundle_id']!=f"e2e18-v{SCAN_VERSIONS.get(options.get('scan_guard'))}"
                or bundle.get('scan_guard_parameters')!=SCAN_PARAMS):
            raise ValueError('REGISTERED_SCAN_GUARD_REQUIRED')
    from harness.e2e_fine_view import VERSIONS as FINE_VERSIONS,parameters as fine_parameters
    if bundle['execution_bundle_id'] in {f'e2e18-v{v}' for v in FINE_VERSIONS.values()}:
        mode=options.get('fine_view')
        if (options.get('camera_hold')!='zero_wheel_v1' or options.get('sonar_frame')!='site_z_v1'
                or options.get('arm_clearance')!='range_wall_v1' or options.get('acquisition_mobility')!='resume_v1'
                or options.get('approach_commit')!='memory60_view_v1' or options.get('scan_guard')!='map_v1'
                or bundle['execution_bundle_id']!=f'e2e18-v{FINE_VERSIONS.get(mode)}'
                or bundle.get('fine_view_parameters')!=fine_parameters(mode)):
            raise ValueError('REGISTERED_FINE_VIEW_REQUIRED')
    from harness.e2e_approach_heading import VERSIONS as HEADING_VERSIONS,parameters as heading_parameters
    if bundle['execution_bundle_id'] in {f'e2e18-v{v}' for v in HEADING_VERSIONS.values()}:
        mode=options.get('approach_heading')
        if (options.get('camera_hold')!='zero_wheel_v1' or options.get('sonar_frame')!='site_z_v1'
                or options.get('arm_clearance')!='range_wall_v1' or options.get('acquisition_mobility')!='resume_v1'
                or options.get('approach_commit')!='memory60_view_v1' or options.get('scan_guard')!='map_v1'
                or options.get('fine_view')!='inspect60_v1' or bundle.get('fine_view_parameters')!=fine_parameters('inspect60_v1')
                or bundle['execution_bundle_id']!=f'e2e18-v{HEADING_VERSIONS.get(mode)}'
                or bundle.get('approach_heading_parameters')!=heading_parameters(mode)):
            raise ValueError('REGISTERED_APPROACH_HEADING_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v263','e2e18-v264','e2e18-v265','e2e18-v266','e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e_fine_entry import OPTION as ENTRY_OPTION, MPC as ENTRY_MPC, parameters as entry_parameters
        combined=bundle['execution_bundle_id']!='e2e18-v263'
        entry=ENTRY_MPC if combined else ENTRY_OPTION
        if (options.get('fine_entry')!=entry or bundle.get('fine_entry_parameters')!=entry_parameters(entry)
                or options.get('camera_hold')!='zero_wheel_v1' or options.get('sonar_frame')!='site_z_v1'
                or options.get('arm_clearance')!='range_wall_v1' or options.get('acquisition_mobility')!='resume_v1'
                or options.get('approach_commit')!='memory60_view_v1' or options.get('scan_guard')!='map_v1'
                or options.get('fine_view')!='inspect60_v1' or bundle.get('fine_view_parameters')!=fine_parameters('inspect60_v1')
                or options.get('approach_heading','off')!=('path20_v1' if combined else 'off')
                or (combined and bundle.get('approach_heading_parameters')!=heading_parameters('path20_v1'))):
            raise ValueError('REGISTERED_FINE_ENTRY_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v265','e2e18-v266','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e_station_heading import VERSIONS as STATION_VERSIONS, parameters as station_parameters
        mode=options.get('station_heading')
        station_version=266 if bundle['execution_bundle_id'] in ('e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') else int(bundle['execution_bundle_id'].rsplit('v',1)[1])
        if (mode not in STATION_VERSIONS or station_version!=STATION_VERSIONS[mode]
                or bundle.get('station_heading_parameters')!=station_parameters(mode)):
            raise ValueError('REGISTERED_STATION_HEADING_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v267','e2e18-v268','e2e18-v269','e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e_clip_recovery import parameters as clip_parameters
        mode='back6_v1' if bundle['execution_bundle_id']=='e2e18-v269' else 'back3_v1'
        if (options.get('clip_recovery')!=mode or bundle.get('clip_recovery_parameters')!=clip_parameters(mode)
                or options.get('station_heading','off')!=('off' if bundle['execution_bundle_id']=='e2e18-v267' else 'station20_v1')):
            raise ValueError('REGISTERED_CLIP_RECOVERY_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v270','e2e18-v271','e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e_station_handoff import VERSIONS as HANDOFF_VERSIONS, PARAMS as HANDOFF_PARAMS
        mode=options.get('station_handoff')
        handoff_version=271 if bundle['execution_bundle_id'] in ('e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') else int(bundle['execution_bundle_id'].rsplit('v',1)[1])
        if (mode not in HANDOFF_VERSIONS or handoff_version!=HANDOFF_VERSIONS[mode]
                or bundle.get('station_handoff_parameters')!=HANDOFF_PARAMS):
            raise ValueError('REGISTERED_STATION_HANDOFF_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v272','e2e18-v273','e2e18-v274','e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e_capture_pose import VERSIONS as CAPTURE_VERSIONS, parameters as capture_parameters
        mode=options.get('capture_pose')
        if (mode not in CAPTURE_VERSIONS or (273 if bundle['execution_bundle_id'] in ('e2e18-v275','e2e18-v276','e2e18-v277','e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300') else int(bundle['execution_bundle_id'].rsplit('v',1)[1]))!=CAPTURE_VERSIONS[mode]
                or bundle.get('capture_pose_parameters')!=capture_parameters(mode)):
            raise ValueError('REGISTERED_CAPTURE_POSE_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v275','e2e18-v276','e2e18-v277'):
        from harness.e2e_relook_search import VERSIONS as RELOOK_VERSIONS, PARAMS as RELOOK_PARAMS
        mode=options.get('relook_search')
        if (mode not in RELOOK_VERSIONS or bundle['execution_bundle_id']!=f'e2e18-v{RELOOK_VERSIONS[mode]}' or bundle.get('relook_search_parameters')!=RELOOK_PARAMS):
            raise ValueError('REGISTERED_RELOOK_SEARCH_REQUIRED')
    if bundle['execution_bundle_id'] in ('e2e18-v295','e2e18-v296','e2e18-v297','e2e18-v300'):
        from harness.e2e_acquire_standoff import VERSIONS as STANDOFF_VERSIONS, parameters as standoff_parameters
        key=(options.get('beam_lost_standoff'),options.get('arm_clearance_align_skip'),options.get('acquire_scan_fast'))
        if bundle['execution_bundle_id'] in ('e2e18-v297','e2e18-v300'):
            from harness.e2e_relook_search import PARAMS as RELOOK_PARAMS
            if (key!=(('v1','v1','v1') if bundle['execution_bundle_id']=='e2e18-v297' else ('v1','off','off')) or options.get('relook_search')!='view5_pan_v1'
                    or bundle.get('relook_search_parameters')!=RELOOK_PARAMS or bundle.get('standoff_relook_parent')!='e2e18-v276'
                    or any(bundle.get(k)!=v for k,v in standoff_parameters(*key).items())):
                raise ValueError('REGISTERED_ACQUIRE_STANDOFF_REQUIRED')
        elif (STANDOFF_VERSIONS.get(key)is None or bundle['execution_bundle_id']!=f'e2e18-v{STANDOFF_VERSIONS[key]}'
                or any(bundle.get(k)!=v for k,v in standoff_parameters(*key).items())):
            raise ValueError('REGISTERED_ACQUIRE_STANDOFF_REQUIRED')
    for name in ASSETS:
        expected = bundle['source_sha256'].get(name)
        if expected is None or hashlib.sha256((Path(root)/name).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_HASH_MISMATCH:'+name)
