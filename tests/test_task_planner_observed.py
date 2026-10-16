import copy
import json
from pathlib import Path

from harness.task_planner_cost_rules import SPECS, FACT_KEYS, extract_english, rule
from scripts.evaluate_task_planner import adapt
from tests.test_task_planner_evidence_gate import route


def test_compositional_tuning_vocabulary_and_negation():
    assert extract_english('pair', "I'm not available; my gripper is occupied.")==['unavailable']
    assert extract_english('next', "I've claimed cyan; red is still free.")==['cyan_claimed']
    assert extract_english('help', 'Cancel the request; the second end is covered.')==['withdrawn']
    assert extract_english('wait', 'I cannot arrive soon; the rendezvous will have to wait.')==['late']
    assert extract_english('route', 'Door_narrow is not clear; door_wide is open.')==['blocked']
    assert extract_english('route', 'Door_narrow is clear. Door_narrow is blocked.')==[]


def test_non_route_own_conflict_and_old_own_not_certainty():
    from scripts.evaluate_task_planner import action
    r=route(98);v=r['input'];v['task']=SPECS['pair']['task'];v['candidates']=SPECS['pair']['actions']
    v['self_state']['travel_estimates']=dict(c_pair=5,delay=30,c_solo=15,c_recruit=20)
    f=dict(subject='r2',predicate='availability',value='unavailable',observed_at=99,source='own RGB estimate')
    v['self_state']['observed_facts']=[f];v['messages'][0]['body']='I am available to take the other end of beam_1.'
    _,ctx,_=adapt(r,'peer_en','on_v1')
    assert ctx['evidence_gate']['archived_reports'][0]['status']=='conflict'
    assert rule(v)[1]['posterior']['unavailable']==.9
    f['observed_at']=60;v['messages'][0]['observation_time_s']=40
    _,ctx,_=adapt(r,'peer_en','on_v1')
    assert ctx['evidence_gate']['archived_reports'][0]['status']=='stale'
    assert rule(v)[1]['posterior']==dict(available=.5,unavailable=.5)


def test_synthetic_sensor_is_noisy_and_eval_metadata_not_in_context():
    from scripts.prepare_task_planner_observed import augment
    r=route();r['case_id']='one';v=r['input'];v['possibilities']=SPECS['route']['worlds']
    sample=dict(available=True,stale=False,age_s=1,sim_s=50,run='r80',request_id='sample',
        evaluation_only=dict(large_error=True),observation=dict(pose_own_m=[1,2,0],observer_pose_own_m=[0,0,0],rgb=dict(frame_id=4)),
        allowed_envelope=dict(own_rgb=dict(t_sim=49,frame_id=4,robot_id='r2',sha256='rawhash'),own_map_summary=dict(pose=dict(mean=[0,0,0])),own_command_history=[]))
    g=dict(case_id='one',domain='route',world='clear',ambiguous=False)
    rows,audit=augment([r],[g],dict(N=1,samples=[sample]),1)
    assert rows[0]['input']['self_state']['observed_facts'][0]['value']=='blocked'
    assert rows[0]['input']['self_state']['observed_facts'][0]['observed_at']==999
    _,ctx,_=adapt(rows[0],'no_comm','on_v1')
    text=json.dumps(ctx)
    for key in ('evaluation_only','large_error','world','rawhash','request_id'):
        assert key not in text
    del sample['evaluation_only']
    rows,_=augment([r],[g],dict(N=1,samples=[sample]),1)
    assert rows[0]['input']['self_state']['observed_facts']==[]
