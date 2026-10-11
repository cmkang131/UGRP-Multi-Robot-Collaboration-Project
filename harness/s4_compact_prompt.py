"""English by default; opt-in bounded context, without authored-map inputs.

The legacy validators still validate source records before this projection.
Channel topology/IDs are unchanged; external condition/language stay distinct.
No generated summary, resize, new camera, physics or model call occurs here.
"""
import copy
import hashlib
import json
import re
from harness import zone_study_prompts_ko as pk
from harness.zone_study_contract import digest, STRUCTURED_ACTS, STRUCTURED_STATES, CONFIDENCE

EN_CONDITIONS = {'peer_ko':'peer_en', 'leader_ko':'leader_en', 'peer_nl':'peer_en'}
EN = '''You are {rid}. Decide only your action. r1=end_neg, r2=end_pos (beam); r3=west (cyan).
Use own wrist RGB, issued commands, own estimates, orders and delivered messages only. No truth, peer images or authored map. Commands/estimates are not success. Unseen=unknown; examples are syntax, not evidence.
Return JSON only: request_id (copy), action, decision_sources, messages; no extra root keys. Use the action/message contracts and literal IDs. Cite only sources actually used.
Claim your assigned order; continue retains its controller. Pair actions require a current window/epoch. GO only if own RGB supports holding; ACK only your received peer_go_ref after your GO. Both robots need GO+ACK before departure; continue is not GO. Never repeat accepted GO/ACK.
RGB/response must be <10 SIM seconds old; obey deadlines, one retry per epoch and look_again limits. Reject stale windows. Grip loss/uncertain holding stops the pair; intentional set-down/reinspection need not look held. Preserve safe hold while a decision is pending.
Only channel.can_send_to may receive messages; reply_to must be received. No_comm sends []; others notify GO/ACK/loss. Messages never command peers. Keep dialogue budgets. All prose is English; structured messages use enums, not text.'''
KO = '''당신은 {rid}입니다. 자기 행동만 결정합니다. r1=end_neg, r2=end_pos(빔), r3=west(cyan)입니다.
자기 wrist RGB·발행 명령·자기 추정·주문·실제 수신 메시지만 사용합니다. 정답·타 로봇 영상·정적 지도는 금지합니다. 명령과 추정은 성공이 아니며, 보이지 않으면 unknown입니다. 예시는 형식이지 관측 증거가 아닙니다.
JSON만 출력합니다: request_id(그대로 복사), action, decision_sources, messages. 다른 루트 키는 금지합니다. 제공된 행동·메시지 계약과 ID를 그대로 쓰고 실제 사용한 근거만 적습니다.
자기 주문만 claim하고 continue는 기존 제어 결정을 유지합니다. 빔 행동은 현재 창·epoch에만 유효합니다. 자기 RGB가 파지를 지지할 때만 GO, 자기 GO 후 실제 받은 peer_go_ref에만 ACK합니다. 양쪽 GO+ACK 전에는 출발하지 않습니다. continue는 GO가 아니며 승인된 GO/ACK를 반복하지 않습니다.
RGB·응답은 10 SIM초 미만, 기한·epoch당 재요청 1회·look_again 제한을 지킵니다. 지난 창은 거절합니다. 이탈·파지 불명확이면 양쪽 정지, 의도적 내려놓기·재관측 중에는 파지를 요구하지 않습니다. 결정 대기 중 안전 정지를 유지합니다.
channel.can_send_to 상대에게만 보내고 reply_to는 수신 ID만 씁니다. no_comm은 []; 나머지는 GO/ACK/이탈을 알립니다. 메시지는 타 로봇 명령이 아닙니다. 발화 예산을 지킵니다. 자유 대화는 한국어, 정형 메시지는 enum만 씁니다.'''


def external_condition(condition, lang='en'):
    if lang not in ('en','ko'): raise ValueError('prompt_lang must be en or ko')
    if condition in ('peer_en','leader_en'):
        if lang != 'en': raise ValueError('English condition requires prompt_lang=en')
        return condition
    return EN_CONDITIONS.get(condition,condition) if lang=='en' else condition


def legacy_condition(condition):
    return {'peer_en':'peer_ko','leader_en':'leader_ko'}.get(condition,condition)


def system(rid, lang='en'):
    value=(EN if lang=='en' else KO).format(rid=rid)
    assert len(value)<=1500
    return value


def contracts(body, lang):
    channel=body.get('channel',{})
    action=[{'kind':'claim','order_id':'<order_id>','role':'<own role>','destination_zone':'<order destination>'},
            {'kind':'continue'},{'kind':'release','order_id':'<order_id>'}]
    if body['robot_id'] in ('r1','r2'):
        action += [{'kind':'look_around'},{'kind':'carry_decision','choice':['continue','set_down']},
            {'kind':'post_look_decision','choice':['regrasp','look_again']},
            {'kind':'pair_decision','epoch':'<current epoch>','choice':['go','ack_go','held','grip_lost','unknown'],
             'peer_go_ref':'<received GO id for ack_go; otherwise null>'}]
    message=[]
    if channel.get('encoding')=='schema':
        message={'recipients':'channel.can_send_to','reply_to':'<received id or null>',
            'message':{'act':list(STRUCTURED_ACTS),
                'item':'<order item or null>','zone':'<order zone or null>','role':'<role or null>',
                'passage':'<observed passage or null>','location_ref':'<observed reference or null>',
                'state':[*STRUCTURED_STATES,None],
                'confidence':[*CONFIDENCE,None],'observed_at_sim_s':'<nonnegative observation time or null>',
                'reply_to':'<received id or null>'}}
    elif channel.get('free_text_allowed'):
        message={'recipients':'channel.can_send_to','text':('English' if lang=='en' else '한국어')+'; <=240 characters',
                 'reply_to':'<received id or null>'}
    return dict(actions=action,message=message,decision_sources=['order_sheet','own_rgb','own_commands','own_belief','message'],
                look_again_limits=dict(per_robot_case=1,per_stop=1),
                r3_departure='continue only after S4_DEPARTURE_PENDING; within 10 SIM seconds')


def _tail(body,key,n):
    rows=body.get(key)
    if not isinstance(rows,list):return
    dropped=rows[:-n];body[key]=rows[-n:]
    if dropped:
        # Counts and hashes cannot invent content or deliver previously unseen messages.
        body.setdefault('history_summary',{})[key]=dict(omitted_count=len(dropped),
            last_omitted_id=dropped[-1].get('message_id',dropped[-1].get('command_id'))
            if isinstance(dropped[-1],dict) else dropped[-1])


def project(body, *, compact=False, lang='en'):
    b=copy.deepcopy(body)
    if not compact and lang=='ko': return b
    b['condition']=external_condition(b['condition'],lang)
    if 'channel' in b:
        b['channel']['condition']=b['condition']
        if lang=='en' and b['channel'].get('encoding')=='free_ko':b['channel']['encoding']='free_en'
    # No map or map-derived belief survives an own-input projection.
    if compact:
        b['schema']='ugrp.s4.own_input_projection.v1'
        b.pop('static_map',None)
        if 'static_map' in (b.get('self_belief') or {}).get('sources',[]):
            b['self_belief']={'status':'unknown','reason':'authored_map_derived_belief_omitted'}
        sheet=b.get('order_sheet',{})
        for key in ('map_file_sha256','public_map_sha256','map_id','note_ko'):sheet.pop(key,None)
        for order in sheet.get('orders',[]):order.pop('initial_location',None)
        _tail(b,'inbox',2);_tail(b,'own_command_history',2)
        if 'dialogue_window' in b:_tail(b['dialogue_window'],'sent',2)
        contract=b.get('reply_contract')
        if contract:
            # Retain a full current reply example; the prose already defines
            # the four fields and the actual parser still enforces their types.
            contract['schema']={'required':['request_id','action','decision_sources','messages'],
                                'additionalProperties':False}
    if lang=='en':
        sheet=b.get('order_sheet',{})
        if 'note_ko' in sheet:
            sheet.pop('note_ko');sheet['note']='Orders describe the task, not current inventory or success.'
        belief=b.get('self_belief',{})
        if 'notes_ko' in belief:
            note=belief.pop('notes_ko')
            if note:belief['legacy_note_omitted_sha256']=digest(note)
        for parent in (b.get('s4_round',{}),b.get('reply_contract',{})):
            example=parent.get('reply_example',parent.get('example'))
            for m in (example or {}).get('messages',[]):
                if 'text' in m:m['text']='I report my own visual assessment and current GO/ACK intention.'
    b['action_message_contract']=contracts(b,lang)
    b['prompt_lang']=lang
    return b


def transform(request, *, compact=False, lang='en'):
    if not compact and lang=='ko':return copy.deepcopy(request)
    r=copy.deepcopy(request);b=project(json.loads(r['messages'][1]['content']),compact=compact,lang=lang)
    if compact:
        for key in ('images','image_refs'):
            r[key]=[i for i in r.get(key,[]) if 'STATIC MAP' not in i['label'].upper()]
        if len(r['images'])!=1:raise ValueError('exactly one own wrist RGB required')
    text=system(b['robot_id'],lang)
    # Legacy noncompact English explicitly retains authored map as DEV-only input.
    if not compact:text=text.replace('or authored map','').replace('No truth, peer images .','No truth or peer images.')
    user=json.dumps(b,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    r.update(condition=b['condition'],prompt_lang=lang,compact_prompt_v1=compact,
             prompt_version='ugrp.s4_english_compact.v1',input_sha256=digest(b),
             messages=[dict(role='system',content=text),dict(role='user',content=user)])
    if compact:r.update(payload_schema=b['schema'],input_profile_id='s4_own_rgb_compact_v1')
    r['request_sha256']=pk.request_digest_from_refs(text,user,r['image_refs'])
    r['tokens']=pk.request_tokens(text,user,r['images'])
    # Simulator's synthetic timing remains separate from real countTokens usage.
    from harness.pair_llm_billing import billed_tokens
    r['billed_tokens']=billed_tokens(r['tokens'],system_billed=pk.count_tokens(text))
    return r
