import copy,json
from harness.task_planner_model import ordered_context,add_model_options

def test_v2_lossless_numeric_and_array_order_and_dynamic_gate():
    ctx={'now_s':1.23,'evidence_gate':{'archived_reports':[{'age':99}]},'robot_id':'r1',
         'schema':'s','public_rules':{'z':1.0,'a':-0.0},'order_sheet':[{'count':2,'id':'b'},{'id':'a'}],
         'task':'t','static_map':{},'condition':'peer_en','can_send_to':['r2'],
         'own':{'z':2,'a':3},'candidates':[{'act':'wait','args':{'until':'x','max_s':1e-9}}]}
    original=copy.deepcopy(ctx);x=ordered_context(ctx,'static_first_v2')
    assert ctx==original and x==ctx and json.loads(json.dumps(x))==ctx
    assert list(x)[:5]==['schema','public_rules','task','static_map','order_sheet']
    assert list(x).index('evidence_gate')>list(x).index('own')
    assert list(x['own'])==['a','z']
    assert x['order_sheet']==original['order_sheet']
    other={k:ctx[k] for k in reversed(ctx)}
    other['public_rules']={'a':-0.0,'z':1.0}
    assert json.dumps(x)==json.dumps(ordered_context(other,'static_first_v2'))
    assert ordered_context(ctx,'off') is ctx

def test_v2_default_stays_off():
    import argparse
    p=argparse.ArgumentParser();add_model_options(p)
    assert p.parse_args([]).planner_prompt_order=='off'
    assert p.parse_args(['--planner-prompt-order','static_first_v2']).planner_prompt_order=='static_first_v2'

def test_frozen_400_preserves_all_information():
    from scripts.check_task_planner_ling import frozen,BASELINE
    import pytest
    if not (BASELINE/'calls.jsonl.zst').exists():pytest.skip('local data')
    rows,_=frozen()
    for r in rows:
        ctx=r['audit'][0]['request']['input']
        assert ordered_context(ctx,'static_first_v2')==ctx

def test_r80_replay_uses_actual_provider_requests_if_available():
    from scripts.replay_task_planner_cache import load,SOURCE,ENVELOPE
    import pytest
    if not SOURCE.exists() or not ENVELOPE.exists():pytest.skip('local r80 archive')
    rows=load()
    assert len(rows)==27 and {r['robot'] for r in rows}=={'r1','r2'}
    assert [r['sim_s'] for r in rows]==sorted(r['sim_s'] for r in rows)
    assert any(a['robot']!=b['robot'] for a,b in zip(rows,rows[1:]))
    for r in rows:
        user=r['request']['messages'][1]['content'];ctx=json.loads(user)
        assert ordered_context(ctx,'static_first_v2')==ctx
        assert 'immutable protocol action' in r['request']['messages'][0]['content']

def test_historical_fallback_is_a_nonmatch_not_a_scoring_crash():
    from scripts.check_task_planner_cache import same_decision
    good={'fallback':False,'audit':[{'decision':{'act':'wait','args':{'until':'x','max_s':1}}}]}
    failed={'fallback':True,'audit':[{'fallback':'previous error'}]}
    assert same_decision(good,good)
    assert not same_decision(good,failed)
    assert not same_decision(failed,good)
