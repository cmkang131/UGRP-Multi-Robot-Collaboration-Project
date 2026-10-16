import copy,json
import pytest
from harness import e2e_dialogue_decider as dd
from harness import e2e_speech_context as m
from tests.test_e2e_dialogue_decider import user,request,speech
from tests.test_pair_llm_s4_host import setup_data,no_external_work


@pytest.mark.parametrize('option,limit',[('recent4_v1',4),('recent8_v1',8)])
def test_bounded_verbatim_speech_preserves_full_protocol_and_immutable_action(tmp_path,option,limit):
    from scripts.d1_dialogue_upstream import Code
    b=user();b['dialogue_decider']='code_v1';r=b['peer_reports'][0]
    b['peer_reports']=[dict(copy.deepcopy(r),message_id=f'peer-{i}',body=dict(text=f'Original report {i}: awaiting agreement.'),received_at_sim_s=b['sim_time_s']-2,created_at_sim_s=b['sim_time_s']-2) for i in range(56)]
    # A fresh danger older than the speech window still vetoes GO in full input.
    b['peer_reports'][0]['body']['text']='Please stop: danger.'
    original=copy.deepcopy(b);selected=dd.code_select(b)
    assert selected['action']=='WAIT_UNCERTAIN'
    old=dd.speech_request(request(b),selected)
    b['speech_context']=option;seen=[]
    out=Code(tmp_path).complete(request(b),'compact',lambda x:(seen.append(x) or speech('Holding for the reported danger.')))
    assert json.loads(out['choices'][0]['message']['content'])['action']==dd.candidates(b)[selected['action']]
    s=json.loads(seen[0]['messages'][1]['content']);reports=s['context']['peer_reports']
    assert len(reports)==limit and [r['text'] for r in reports]==[r['body']['text'] for r in b['peer_reports'][-limit:]]
    assert s['context']['omitted_older_peer_reports']==56-limit
    assert len(seen[0]['messages'][1]['content'])<len(old['messages'][1]['content'])/3
    assert b['peer_reports']==original['peer_reports'] and dd.code_select(b)==selected
    assert out['ugrp_code_dialogue']['action_immutable'] and out['ugrp_code_dialogue']['decision_model_calls']==0


def test_actual_registration_and_default_off(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    from scripts.s4_proxy_relay import accepted_call_id
    args,kw=[],{}
    def capture(*a,**k):args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture);p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    args[1]=61013;kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',boundary_lifecycle='abort_v1')
    for (parent,option),version in m.VERSIONS.items():
        flags=dict(post_relook='carry_through_v1',body_controller='jev_v1',body_backend='code_v1',body_protocol_stack='code_v1')
        if parent=='e2e18-v352':flags=dict(post_relook='carry_nominal_v1',perception_fast='shadow_axes_v1',controller_timing='phase_v1',llm_memory='v1_commands',dialogue_decider='code_v1',explore_idle='idle5_v1')
        if parent=='e2e18-v356':flags['approach_efficiency']='regulated_v1'
        b=bundle(*args,**kw,**flags,speech_context=option);require_current(b,ROOT)
        assert b['execution_bundle_id']==f'e2e18-v{version}'
        assert m.parent_for_validation(b)['e2e_options']==bundle(*args,**kw,**flags)['e2e_options']
        bad=copy.deepcopy(b);bad['speech_context_parameters']['cohort_token_cap']=1600000
        with pytest.raises(ValueError):require_current(bad,ROOT)
        assert accepted_call_id(f'speed-gate-e2e18-v{version}-s61013-r77:call-0001-r1:1')
    b={};assert m.compose(b)==() and b=={}
