"""New Ling registrations over the unchanged v387 Gemma planner settings."""
import copy
from harness.task_planner_model import LING, GEMMA_FP4, ModelSelection, DEFAULT_MODEL

VERSIONS = {'off': 401, 'static_first_v1': 402}
GEMMA_VERSIONS = {'off': 403, 'static_first_v1': 404}


def compose(bundle, model=DEFAULT_MODEL, provider='DeepInfra', reasoning='default', prompt_order='off'):
    selection = ModelSelection(model, provider, reasoning)
    if selection == ModelSelection() and prompt_order == 'off': return ()
    if selection not in (LING,GEMMA_FP4) or prompt_order not in VERSIONS or bundle['execution_bundle_id'] != 'e2e18-v387':
        raise ValueError('LING_REQUIRES_GATED_V387_PARENT')
    version = (GEMMA_VERSIONS if selection==GEMMA_FP4 else VERSIONS)[prompt_order]
    bundle.update(planner_model_parent='e2e18-v387',execution_bundle_id=f'e2e18-v{version}',
        schema=f'ugrp.e2e_ownmap_live.v{version}',workflow_version=f'7.{version-107}.0',
        planner_model_parameters=dict(allow_fallbacks=False,temperature=0,max_tokens=768,
            input='own_rgb_and_code_observation_v1',image_hashes_retained=True))
    if selection==GEMMA_FP4:
        bundle['planner_model_parameters']['rate_limit_policy']='planner_rate_limit_v1'
    bundle['e2e_options'].update(planner_model=model,planner_provider=provider,
        planner_reasoning=reasoning,planner_prompt_order=prompt_order)
    return ('harness/e2e_planner_model.py','harness/task_planner_model.py',
        ('configs/e2e_task_planner_gemma_fp4_options.json' if selection==GEMMA_FP4 else 'configs/e2e_task_planner_ling_options.json'),f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    b=copy.deepcopy(bundle);o=b['e2e_options'];order=o.get('planner_prompt_order')
    selection=ModelSelection(o.get('planner_model'),o.get('planner_provider'),o.get('planner_reasoning'))
    versions=GEMMA_VERSIONS if selection==GEMMA_FP4 else VERSIONS
    parameters=dict(allow_fallbacks=False,temperature=0,max_tokens=768,input='own_rgb_and_code_observation_v1',image_hashes_retained=True)
    if selection==GEMMA_FP4:parameters['rate_limit_policy']='planner_rate_limit_v1'
    if (selection not in (LING,GEMMA_FP4)
            or order not in versions or b['execution_bundle_id']!=f'e2e18-v{versions[order]}'
            or b.pop('planner_model_parent',None)!='e2e18-v387'
            or b.pop('planner_model_parameters',None)!=parameters):
        raise ValueError('REGISTERED_LING_PLANNER_REQUIRED')
    for key in ('planner_model','planner_provider','planner_reasoning','planner_prompt_order'):o.pop(key)
    b.update(execution_bundle_id='e2e18-v387',schema='ugrp.e2e_ownmap_live.v387',workflow_version='7.280.0')
    return b
