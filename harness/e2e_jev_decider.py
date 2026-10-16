"""Opt-in semantic_v2 action selection; no simulator or credential access."""
import copy
import json
import math
from harness import jev_decider_eval as ev
from harness.three_robot_plan import parse

MODE='jev_v1'
GRIP=('holding','not_visible','slipping','none','unknown')


def state(user, grip):
    if grip not in GRIP:raise ValueError('OWN_RGB_GRIP_ENUM_REQUIRED')
    # The offline converter truncated peer text for diagnostics. Live decisions
    # retain every actually delivered message and issued command verbatim.
    u=copy.deepcopy(user)
    u['peer_reports']=u.get('peer_reports') or []
    if 'own_map_summary' not in u:u['own_map_summary']=u['own_map']
    s=ev.real_state_from_request(u)
    age=u.get('dialogue_epoch_age_s')
    if age is not None and (type(age) not in (int,float) or not math.isfinite(age) or age<0):
        raise ValueError('INVALID_EPOCH_AGE')
    s.update(epoch_age_s=age,own_rgb_grip=grip,
        own_rgb_summary='Gemma own wrist RGB grip classification: '+grip,
        own_command_history=copy.deepcopy(u['own_command_history']),
        peer_reports=[dict(sender=p['sender'],text=(p.get('body') or {}).get('text') or
             json.dumps(p.get('body'),ensure_ascii=False,sort_keys=True)) for p in u['peer_reports']])
    return ev.semantic_state(s,'dialogue')


def action(choice,user):
    """Jev chooses a symbol only; all identifiers come from the captured view."""
    d=user['dialogue'];rid=user['robot_id']
    if choice=='continue':return dict(kind='continue')
    if choice=='claim':return dict(kind='claim',order_id='order-5',destination_zone='B',role=user['task']['fixed_roles'][rid])
    if choice=='approve_route':return dict(kind=choice,route_hash=d['route_hash'],proposal_message_id=d['proposal_message_id'])
    if choice not in ('GO','ACK'):raise ValueError('UNCONNECTED_JEV_CHOICE')
    key=d['key']
    # Missing key produces a non-admissible typed action, never an invented epoch.
    key=key if key is not None else [None,None,None,None]
    return dict(kind='route_vote',choice=choice,order_id=key[0],route_hash=key[1],
        grip_epoch=key[2],seg=key[3],peer_go_ref=d['peer_go_ref'] if choice=='ACK' else None)


def transform(request,response,select):
    """Called only inside the Mac relay, after the Gemma upstream response."""
    content=request['messages'][1]['content']
    text=content if isinstance(content,str) else next(p['text'] for p in content if p.get('type')=='text')
    user=json.loads(text)
    if user.get('decider')!=MODE:raise ValueError('JEV_REQUEST_MODE_REQUIRED')
    c=response['choices'][0]
    from harness.llm_completion import assess_completion,normal_completion
    if not normal_completion(assess_completion(response,study_json=False)):
        raise ValueError('NORMAL_GEMMA_RESPONSE_REQUIRED')
    gemma=parse(c['message']['content'])
    if set(gemma)!={'request_id','action','decision_sources','messages','own_rgb_grip'}:
        raise ValueError('GEMMA_GRIP_REPLY_FIELDS_REQUIRED')
    if gemma['request_id']!=user['request_id']:raise ValueError('GEMMA_REQUEST_ID_MISMATCH')
    semantic=state(user,gemma['own_rgb_grip'])
    body=dict(model=ev.JEV_MODEL,state=semantic,questions={'action':dict(type='choice',
        instructions=ev.instructions('dialogue',ev.IMPROVED),criteria=ev.options_for('dialogue',ev.IMPROVED))})
    result=select(body)
    if result.get('status')!='ok':raise ValueError('JEV_UPSTREAM_FAILURE')
    reply=result['body']
    if reply.get('model')!=ev.JEV_MODEL:raise ValueError('JEV_MODEL_MISMATCH')
    choice,confidence,probabilities=ev.parse_jev(reply,'dialogue')
    if not math.isclose(sum(probabilities.values()),1.,abs_tol=1e-4):raise ValueError('JEV_PROBABILITY_SUM')
    value=copy.deepcopy(gemma);value.pop('own_rgb_grip');value['action']=action(choice,user)
    sources=['order_sheet','own_belief','own_commands','own_rgb']
    if user['peer_reports']:sources.append('message')
    value['decision_sources']=sources
    shadow=gemma['action'].get('choice') if gemma['action'].get('kind')=='route_vote' else gemma['action'].get('kind')
    receipt=dict(mode=MODE,model=ev.JEV_MODEL,representation=ev.IMPROVED,choice=choice,
        confidence=confidence,probabilities=probabilities,latency_s=result['latency_s'],usage=reply.get('usage'),
        cost=None,cost_status='not_reported_by_provider',gemma_shadow_action=gemma['action'],
        own_rgb_grip=gemma['own_rgb_grip'],disagreement=choice!=shadow,request=body,response=reply)
    out=copy.deepcopy(response);out['choices'][0]['message']['content']=json.dumps(value,ensure_ascii=False)
    out['ugrp_jev']=receipt
    return out
