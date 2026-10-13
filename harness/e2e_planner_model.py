"""New Ling registrations over the unchanged v387 Gemma planner settings."""
import copy
from harness.task_planner_model import LING, ModelSelection, DEFAULT_MODEL

VERSIONS = {'off': 401, 'static_first_v1': 402}


def compose(bundle, model=DEFAULT_MODEL, provider='DeepInfra', reasoning='default', prompt_order='off'):
    selection = ModelSelection(model, provider, reasoning)
    if selection == ModelSelection() and prompt_order == 'off': return ()
    if selection != LING or prompt_order not in VERSIONS or bundle['execution_bundle_id'] != 'e2e18-v387':
        raise ValueError('LING_REQUIRES_GATED_V387_PARENT')
    version = VERSIONS[prompt_order]
    bundle.update(planner_model_parent='e2e18-v387',execution_bundle_id=f'e2e18-v{version}',
        schema=f'ugrp.e2e_ownmap_live.v{version}',workflow_version=f'7.{version-107}.0',
        planner_model_parameters=dict(allow_fallbacks=False,temperature=0,max_tokens=768,
            input='own_rgb_and_code_observation_v1',image_hashes_retained=True))
    bundle['e2e_options'].update(planner_model=model,planner_provider=provider,
        planner_reasoning=reasoning,planner_prompt_order=prompt_order)
    return ('harness/e2e_planner_model.py','harness/task_planner_model.py',
        'configs/e2e_task_planner_ling_options.json',f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    b=copy.deepcopy(bundle);o=b['e2e_options'];order=o.get('planner_prompt_order')
    if (ModelSelection(o.get('planner_model'),o.get('planner_provider'),o.get('planner_reasoning'))!=LING
            or order not in VERSIONS or b['execution_bundle_id']!=f'e2e18-v{VERSIONS[order]}'
            or b.pop('planner_model_parent',None)!='e2e18-v387'
            or b.pop('planner_model_parameters',None)!=dict(allow_fallbacks=False,temperature=0,max_tokens=768,
                input='own_rgb_and_code_observation_v1',image_hashes_retained=True)):
        raise ValueError('REGISTERED_LING_PLANNER_REQUIRED')
    for key in ('planner_model','planner_provider','planner_reasoning','planner_prompt_order'):o.pop(key)
    b.update(execution_bundle_id='e2e18-v387',schema='ugrp.e2e_ownmap_live.v387',workflow_version='7.280.0')
    return b
