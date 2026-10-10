"""Default-off epoch fencing and finite GO/ACK rounds; own state and RGB only."""
import copy
from dataclasses import dataclass
from functools import lru_cache
import json
from harness import s4_pair_stage as base
from harness import s4_pair_handshake as hs
from harness.zone_final_pair_binding import bind
from harness.zone_study_contract import digest

PROMPT = '''epoch_round_v1: pair_handshake의 epoch/next_pair_choice/own_go_sent/own_ack_sent는 자기 명령 상태입니다.
wait_go에서는 이전 운반 창을 재사용하지 않습니다. next_pair_choice=go는 자기 RGB가 파지를 지지할 때만 go,
ack_go는 보이는 peer_go_ref를 그대로 확인, continue는 상대 GO/commit 대기입니다. 같은 GO/ACK를 반복하지 마십시오.
운반 시 열린 decision_window 행동이 우선입니다. 창이 없으면 현재 자기 단계에 맞춰 held 또는 continue를 선택합니다.
창이 열렸으면 reply_example은 null이며 decision_actions 중 하나를 영상으로 판단해 선택합니다.
s4_round.reply_example은 현재 허용된 형식 예시입니다. 메시지 수신자는 channel.can_send_to에 있어야 합니다.
no_comm은 messages=[]; 다른 조건에서 GO/ACK/loss는 messages에 통지를 반드시 넣습니다.
structured 메시지는 text가 아닌 recipients/reply_to/message 객체입니다. 예시의 모든 필드를 유지하십시오.
s4_round.previous_rejection은 자기 이전 응답 거부 사유입니다. 새 RGB·현재 epoch를 사용해 수정하십시오.
기한·RGB10초·재요청1회 상한은 유지합니다. 예시는 파지 정답이 아니며 시각 불명확/이탈은 unknown/grip_lost로 보고합니다.'''


class Handshake(hs.Handshake):
    def __init__(self, *, epoch_reconnect=False, go_ack_rounds=False, **kwargs):
        super().__init__(**kwargs)
        if any(type(v) is not bool for v in (epoch_reconnect, go_ack_rounds)):
            raise ValueError('epoch recovery switches must be bool')
        self.epoch_reconnect, self.go_ack_rounds = epoch_reconnect, go_ack_rounds
        self.rounds, self.reconnections = {}, []

    def open(self, rid, epoch, now):
        accepted = super().open(rid, epoch, now)
        if accepted:
            self.rounds.setdefault(epoch, {'go_at': {}, 'ack_opened': None})
        return accepted

    def deadline(self, rid):
        own = self.own[rid]
        round = self.rounds.get(own['epoch'], {})
        if self.go_ack_rounds and not own['committed'] and round.get('ack_opened') is not None:
            return round['ack_opened']+hs.HANDSHAKE_S
        return super().deadline(rid)

    def decide(self, rid, action, **kwargs):
        row = super().decide(rid, action, **kwargs)
        if row['accepted'] and action['choice']=='go':
            rnd = self.rounds[action['epoch']]
            rnd['go_at'][rid] = row['at']
            if set(rnd['go_at'])==set(hs.PAIR) and rnd['ack_opened'] is None:
                rnd['ack_opened'] = max(rnd['go_at'].values())
        return row

    def renew_carry(self, rid, action, *, seen, **kwargs):
        original_phase = seen.get('phase'); own = self.own.get(rid)
        rebind = bool(self.epoch_reconnect and own and own['committed']
            and seen.get('epoch')==own['epoch'] and original_phase=='wait_go'
            and seen.get('own_ack_sent'))
        # Never rewrite a saved request. Its current-epoch ACK is a fencing
        # witness; the superclass still enforces frame freshness and lease.
        used = {**seen, 'phase':'carry'} if rebind else seen
        row = super().renew_carry(rid, action, seen=used, **kwargs)
        if row is not None and self.epoch_reconnect:
            row.update(captured_phase=original_phase, same_epoch_rebind=rebind)
            if rebind:self.reconnections.append(copy.deepcopy(row))
        return row

    def record(self):
        return {**super().record(), 'epoch_reconnect':self.epoch_reconnect,
            'go_ack_rounds':self.go_ack_rounds, 'rounds':copy.deepcopy(self.rounds),
            'snapshot_reconnections':copy.deepcopy(self.reconnections)}


@dataclass(frozen=True)
class Inputs:
    base: object
    context: dict
    def __getattr__(self, name):return getattr(self.base, name)
    def payload_dict(self):return {**self.base.payload_dict(), 's4_round':copy.deepcopy(self.context)}
    @property
    def payload_sha256(self):return digest(self.payload_dict())


@lru_cache(maxsize=32)
def system_tokens(total, per_actor, seed, heartbeat):
    return max(base.si.pk.count_tokens(base.si.system_prompt(c,r,cap_window=total,cap_robot=per_actor,seed=seed)
        +'\n\n'+base.PROMPT+'\n\n'+base.heartbeat_prompt(heartbeat)+'\n\n'+PROMPT)
        for c in base.old.CONDITIONS for r in base.si.ROBOTS)


class Trial(base.Trial):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.epoch_retry_context={}

    def snapshot(self, call):
        super().snapshot(call)
        if call.actor not in hs.PAIR or not (self.handshake.epoch_reconnect or self.handshake.go_ack_rounds):return
        seen=self.pair_snapshots[call.call_id]['seen']
        if seen['phase']=='wait_go':
            # Previous own carry window cannot authorize a new grip epoch.
            self._snapshots[(call.actor,round(float(call.started_sim_s),6))]['decision_window']=None
            self._window_refs[call.call_id]=None
        seen['next_pair_choice']=('go' if not seen['own_go_sent'] else
            'ack_go' if seen['peer_go_ref'] and not seen['own_ack_sent'] else 'continue') if seen['phase']=='wait_go' else (
            ('continue' if seen.get('own_executor_phase') in ('lower','wait_open','cp_open','refix_look','refix_post_look','align') else 'held')
            if seen['phase']=='carry' else None)
        own=self.handshake.own.get(call.actor)
        seen['response_deadline_sim_s']=self.handshake.deadline(call.actor) if own else None

    def prepare_call(self, call):
        prepared=super().prepare_call(call)
        if not (self.handshake.epoch_reconnect or self.handshake.go_ack_rounds) or call.actor not in hs.PAIR:return prepared
        if self.pair_snapshots[call.call_id]['seen']['phase'] not in ('wait_go','carry'):return prepared
        request=copy.deepcopy(prepared.request);body=json.loads(request['messages'][1]['content']);seen=self.pair_snapshots[call.call_id]['seen']
        choice=seen.get('next_pair_choice');action={'kind':'continue'}
        if choice in hs.CHOICES:
            action={'kind':'pair_decision','epoch':seen['epoch'],'choice':choice,
                'peer_go_ref':seen['peer_go_ref'] if choice=='ack_go' else None}
        messages=[];targets=body['channel']['can_send_to']
        if self.condition!='no_comm' and choice in ('go','ack_go') and targets:
            target=next((r for r in targets if r in hs.PAIR and r!=call.actor),targets[0])
            msg={'recipients':[target],'reply_to':None}
            if self.condition=='structured':
                msg['message']={'act':'accept' if choice=='ack_go' else 'inform','item':'beam_1','zone':'B',
                    'role':'end_neg' if call.actor=='r1' else 'end_pos','passage':None,'location_ref':None,
                    'state':'held','confidence':'medium','observed_at_sim_s':call.started_sim_s,'reply_to':None}
            else:msg['text']='자기 영상으로 유지 여부를 확인하고 현재 epoch의 출발 의사와 상대 동의를 알립니다.'
            messages=[msg]
        window=body.get('decision_window')
        choices=base.pair.decisions.HOOK_ACTIONS.get((window or {}).get('kind'),())
        example={'request_id':prepared.request_id,
            'action':action,'decision_sources':['own_rgb'],'messages':messages}
        context={'epoch':seen.get('epoch'),'reply_example':None if choices else example,
            'decision_actions':[{'kind':window['kind'],'choice':c} for c in choices],
            'previous_rejection':self.epoch_retry_context.get((call.actor,seen.get('epoch'))) if seen['phase']=='wait_go' else None,
            'retry_bound_per_robot_epoch':1,'go_budget_sim_s':hs.HANDSHAKE_S,'ack_budget_sim_s':hs.HANDSHAKE_S}
        bundled=Inputs(prepared.bundled,context);body['s4_round']=context
        system=request['messages'][0]['content']+'\n\n'+PROMPT;user=json.dumps(body,ensure_ascii=False,sort_keys=True)
        request.update(input_sha256=bundled.payload_sha256,prompt_version='ugrp.s4_epoch_prompt.v1',
            messages=[{'role':'system','content':system},{'role':'user','content':user}])
        request['request_sha256']=base.si.pk.request_digest_from_refs(system,user,request['image_refs'])
        request['tokens']=base.si.pk.request_tokens(system,user,request['images']);caps=body.get(base.si.pk.WINDOW_KEY,{})
        request['billed_tokens']=base.si.billing.billed_tokens(request['tokens'],system_billed=system_tokens(
            caps.get('max_utterances',12),caps.get('max_your_utterances',6),self.seed,self.handshake.carry_lease_renewal))
        return base.old.s4.zo.PreparedCall(bundled,request,prepared.request_id)


class Host(base.Host):
    def __init__(self,*args,**kwargs):bind(base.old.s4.Host.__init__,Trial=Trial)(self,*args,**kwargs)


class Driver(base.Driver):
    def __init__(self,*args,go_ack_retry=False,**kwargs):
        super().__init__(*args,**kwargs);self.go_ack_retry=go_ack_retry
        self.examined,self.retry_used=set(),set();self.retry_events=[];self.epoch_transitions=[];self.last_view={}

    def poll(self, now):
        rel=now-self.host.links['r1'].origin_s;trial=self.host.trial
        for rid in hs.PAIR:
            v=self.handshake.view(rid,rel);key=(v['epoch'],v['phase'])
            if self.handshake.epoch_reconnect and self.last_view.get(rid)!=key:
                self.epoch_transitions.append({'robot_id':rid,'at':rel,'from':self.last_view.get(rid),'to':key})
                self.ask_keys.pop(rid,None);self.next_ask[rid]=rel
                self.last_view[rid]=key
        if self.go_ack_retry and not self.handshake.failure and not self.host.failed:
            for call in trial.scheduler.calls:
                if call.call_id in self.examined:continue
                self.examined.add(call.call_id);entry=trial.scheduler.ledger[call.call_id]
                seen=trial.pair_snapshots.get(call.call_id,{}).get('seen',{})
                if (call.actor not in hs.PAIR or seen.get('phase')!='wait_go' or call.notes.get('send_violation')
                    or (entry.get('completion') or {}).get('finish_reason')!='stop'):continue
                rejected=next((r for r in reversed(self.handshake.decisions) if r['call_id']==call.call_id and not r['accepted']),None)
                failed=entry['status']=='failed';semantic=bool(self.handshake.go_ack_rounds and rejected)
                if not (failed or semantic):continue
                v=self.handshake.view(call.actor,rel);choice='go' if not v['own_go_sent'] else 'ack_go' if not v['own_ack_sent'] and v['peer_go_ref'] else None
                once=(call.actor,seen['epoch'])
                if (choice is None or once in self.retry_used or v['phase']!='wait_go' or v['epoch']!=seen['epoch']
                    or rel>=self.handshake.deadline(call.actor)):continue
                previous=next((r.get('error') for r in reversed(trial.requests) if r['call_id']==call.call_id),None)
                reason=(rejected or {}).get('reason') or previous or 'INVALID_NORMAL_REPLY'
                self.retry_used.add(once);self.ask_keys.pop(call.actor,None)
                if hasattr(trial,'epoch_retry_context'):trial.epoch_retry_context[once]={'call_id':call.call_id,'reason':reason}
                self.retry_events.append({'robot_id':call.actor,'epoch':seen['epoch'],'choice':choice,'invalid_call_id':call.call_id,
                    'at':rel,'same_epoch':True,'semantic_rejection':semantic,'reason':reason,
                    'accepted_action_replayed':False,'transport_retry':False})
        return super().poll(now)
