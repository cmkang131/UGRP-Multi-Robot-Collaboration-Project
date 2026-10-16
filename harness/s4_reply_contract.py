"""Opt-in full reply examples; native schema forwarding is NOT supported by this proxy."""
import copy
from dataclasses import dataclass
from functools import lru_cache
import json
from harness import s4_pair_epochs as epoch
from harness.s4_call_recovery import RetryTransport
from harness.zone_final_pair_binding import bind
from harness.zone_study_contract import digest

PROMPT = '''reply_contract.schema의 네 루트 키를 반드시 모두 출력합니다. request_id는 현재 값을 그대로 복사합니다.
JSON 객체만 출력하고 설명·코드 펜스는 쓰지 않습니다. example은 형식만 보여주며 행동 지시가 아닙니다.
action은 현재 decision_window 및 자기 RGB로 판단하고, claim 전에는 기존 역할을 맡을지 결정합니다.
decision_sources는 실제 사용한 허용 입력만 적습니다. messages는 no_comm이면 []이고,
나머지 조건의 GO/ACK/loss에는 기존 채널 형식의 통지를 넣습니다. 여분의 루트 키도 금지합니다.'''


@dataclass(frozen=True)
class Inputs:
    base: object
    contract: dict
    def __getattr__(self,name):return getattr(self.base,name)
    def payload_dict(self):return {**self.base.payload_dict(),'reply_contract':copy.deepcopy(self.contract)}
    @property
    def payload_sha256(self):return digest(self.payload_dict())


@lru_cache(maxsize=32)
def system_tokens(total,per_actor,seed,heartbeat,feedback):
    pk=epoch.base.si.pk
    return max(pk.count_tokens(epoch.base.si.system_prompt(c,r,cap_window=total,cap_robot=per_actor,seed=seed)
        +'\n\n'+epoch.base.PROMPT+'\n\n'+epoch.base.heartbeat_prompt(heartbeat)+'\n\n'+epoch.PROMPT
        + ('\n\n'+epoch.CARRY_FORMAT_PROMPT if feedback else '')+'\n\n'+PROMPT)
        for c in epoch.base.old.CONDITIONS for r in epoch.base.si.ROBOTS)


class Trial(epoch.Trial):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if getattr(self.handshake,'retry_429',False):
            self.transport=RetryTransport(self,send_ledger=self.send_ledger,client_factory=self.client_factory)
            self.scheduler.transport=self.transport

    def prepare_call(self,call):
        p=super().prepare_call(call)
        if not getattr(self.handshake,'reply_contract',False):return p
        request=copy.deepcopy(p.request);body=json.loads(request['messages'][1]['content'])
        example=copy.deepcopy(body.get('s4_round',{}).get('reply_example'))
        if example is None:
            choices=body.get('s4_round',{}).get('decision_actions',[])
            action=next((a for a in choices if a['choice']=='continue'),choices[0] if choices else {'kind':'continue'})
            example={'request_id':p.request_id,'action':action,'decision_sources':['own_rgb'],'messages':[]}
        contract={'schema':{'type':'object','additionalProperties':False,
            'required':['request_id','action','decision_sources','messages'],
            'properties':{'request_id':{'type':'string','enum':[p.request_id]},'action':{'type':'object'},
                'decision_sources':{'type':'array','items':{'type':'string'}},'messages':{'type':'array'}}},
            'example':example,'native_schema_enforced':False}
        bundled=Inputs(p.bundled,contract);body['reply_contract']=contract
        system=request['messages'][0]['content']+'\n\n'+PROMPT
        user=json.dumps(body,ensure_ascii=False,sort_keys=True);pk=epoch.base.si.pk
        request.update(input_sha256=bundled.payload_sha256,prompt_version='ugrp.s4_reply_contract.v1',
            messages=[{'role':'system','content':system},{'role':'user','content':user}])
        request['request_sha256']=pk.request_digest_from_refs(system,user,request['image_refs'])
        request['tokens']=pk.request_tokens(system,user,request['images']);caps=body.get(pk.WINDOW_KEY,{})
        request['billed_tokens']=epoch.base.si.billing.billed_tokens(request['tokens'],system_billed=system_tokens(
            caps.get('max_utterances',12),caps.get('max_your_utterances',6),self.seed,
            self.handshake.carry_lease_renewal,self.handshake.carry_protocol_feedback))
        return epoch.base.old.s4.zo.PreparedCall(bundled,request,p.request_id)


class Host(epoch.Host):
    def __init__(self,*args,**kwargs):bind(epoch.base.old.s4.Host.__init__,Trial=Trial)(self,*args,**kwargs)
