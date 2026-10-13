"""Default-off bounded Gemma speech context; protocol selection retains full input."""
import copy

VERSIONS={('e2e18-v352','recent4_v1'):357,('e2e18-v354','recent4_v1'):358,
          ('e2e18-v356','recent4_v1'):359,('e2e18-v356','recent8_v1'):360}


def compose(bundle,option='off'):
    if option=='off':return ()
    parent=bundle['execution_bundle_id'];version=VERSIONS.get((parent,option))
    if version is None or bundle['e2e_options'].get('dialogue_decider')!='code_v1':
        raise ValueError('SPEECH_CONTEXT_REQUIRES_REGISTERED_CODE_PARENT')
    bundle['speech_context_parent']=parent;bundle['e2e_options']['speech_context']=option
    bundle['speech_context_parameters']=dict(recent_peer_messages=4 if option=='recent4_v1' else 8,
        original_text=True,protocol_input='unchanged',cohort_token_cap=800000)
    bundle.update(execution_bundle_id=f'e2e18-v{version}',schema=f'ugrp.e2e_ownmap_live.v{version}',workflow_version=f'7.{version-107}.0')
    return ('harness/e2e_speech_context.py',f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    parent=bundle.get('speech_context_parent');option=bundle['e2e_options'].get('speech_context');version=VERSIONS.get((parent,option))
    if (version is None or bundle['execution_bundle_id']!=f'e2e18-v{version}' or bundle.get('speech_context_parameters')!=dict(
        recent_peer_messages=4 if option=='recent4_v1' else 8,original_text=True,protocol_input='unchanged',cohort_token_cap=800000)):
        raise ValueError('REGISTERED_SPEECH_CONTEXT_REQUIRED')
    old=copy.deepcopy(bundle);old['execution_bundle_id']=old.pop('speech_context_parent')
    old.pop('speech_context_parameters');old['e2e_options'].pop('speech_context');return old
