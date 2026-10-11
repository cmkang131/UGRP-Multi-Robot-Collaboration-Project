"""Default-off, condition-independent decision events. Never reads evaluation.

Periodic camera/controller ticks continue. LLM timers do not. Every received
message is still an event (the existing scheduler coalesces simultaneous ones).
Unchanged command phases do not replay actions or extend an LLM GO permission.
"""
import copy
from dataclasses import dataclass
import json
from harness import s4_reply_contract as prior
from harness import s4_compact_prompt as prompt
from harness.zone_final_pair_binding import bind


@dataclass(frozen=True)
class Options:
    event_driven_llm: bool = False
    compact_prompt_v1: bool = False
    prompt_lang: str = 'en'

    def __post_init__(self):
        if any(type(v) is not bool for v in (self.event_driven_llm,self.compact_prompt_v1)):
            raise ValueError('event/compact switches must be bool')
        if self.prompt_lang not in ('en','ko'):raise ValueError('prompt_lang must be en or ko')


def phase_group(state):
    for group, states in {
        'grasp':('pregrasp_descend','close','wait_lift'),
        'carry_start':('lift','raise','raise_high','wait_carry'),
        'carry':('carry',), 'set_down':('lower','wait_lower','cp_open','open','released'),
        'reobserve':('refix_look','refix_decide','refix_post_look'),
        'done':('done','failed','aborted')}.items():
        if state in states:return group
    return None


class Events:
    """Edge detector shared by live adapter and recorded-input replay."""
    def __init__(self):
        self.previous={};self.inbox={};self.seen_windows={};self.trace=[]

    def observe(self, actor, payload):
        h=payload.get('pair_handshake') or {};w=payload.get('decision_window') or {}
        choice=h.get('next_pair_choice')
        if h.get('phase')=='wait_go':
            choice='go' if not h.get('own_go_sent') else 'ack_go' if h.get('peer_go_ref') and not h.get('own_ack_sent') else None
        else:choice=None
        epoch=h.get('epoch');phase=phase_group(h.get('own_executor_phase'))
        reasons=[];old=self.previous.get(actor)
        current=(epoch,choice,phase)
        if old is None:reasons.append('initial_claim')
        else:
            if choice and (epoch,choice)!=old[:2]:reasons.append('go_ack_epoch')
            if phase and phase!=old[2]:reasons.append('phase_'+phase)
        if choice and old is None:reasons.append('go_ack_epoch')
        # Time-to-deadline changing is NOT a new decision window.
        key=(epoch,w.get('kind'),w.get('opened_at_sim_s',w.get('opened_sim_s')),
             w.get('latch_until_sim_s')) if w else None
        if key and self.seen_windows.get(actor)!=key:
            reasons.append('decision_window');self.seen_windows[actor]=key
        ids={m['message_id'] for m in payload.get('inbox',[])}
        if ids-self.inbox.setdefault(actor,set()):reasons.append('received_message')
        self.inbox[actor].update(ids)
        belief=payload.get('own_belief') or {}
        abnormal=(belief.get('over_budget') is True,
                  (payload.get('visual_monitor') or {}).get('state'))
        previous_abnormal=self.previous.get((actor,'abnormal'))
        if abnormal!=previous_abnormal and (abnormal[0] or abnormal[1] in ('unknown','grip_lost')):
            reasons.append('own_observation_abnormal')
        rejection=(payload.get('s4_round') or {}).get('previous_rejection')
        if rejection and rejection!=self.previous.get((actor,'rejection')):
            reasons.append('bounded_invalid_retry')
        self.previous[actor]=current;self.previous[(actor,'abnormal')]=abnormal
        self.previous[(actor,'rejection')]=copy.deepcopy(rejection)
        self.trace.append(dict(robot=actor,sim_s=payload.get('sim_time_s'),reasons=reasons))
        return reasons


class Trial(prior.Trial):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.options=getattr(self.handshake,'study_options',Options())
        self.decision_events=Events()
        model=self.client_factory.settings['model']
        self.provenance.update(provider='google_aistudio_gemma' if model.startswith('gemma-') else 'gemini_subscription_proxy',
                               prompt_lang=self.options.prompt_lang)
        if self.options.event_driven_llm:
            # The scheduler's delivered-message lane remains intact for all arms.
            self.scheduler.event_available_at=lambda actor,cause:self.scheduler.clock

    def _arm_reask(self,actor,sim_s):
        if not self.options.event_driven_llm:return super()._arm_reask(actor,sim_s)

    def prepare_call(self,call):
        p=super().prepare_call(call)
        request=prompt.transform(p.request,compact=self.options.compact_prompt_v1,lang=self.options.prompt_lang)
        return type(p)(p.bundled,request,p.request_id)

    def on_executor_event(self,event,*,at_s):
        super().on_executor_event(event,at_s=at_s)
        if not self.options.event_driven_llm:return
        kind=(event.get('detail') or {}).get('kind',event.get('event'))
        # Preserve explicit door/reinspection/anomaly events, including solo r3.
        if kind in ('door_entered','door_passed','reinspection_result','grip_lost','pose_uncertain',
                    'setdown_started','setdown_completed','carry_leg_started','job_failed','job_done'):
            self.scheduler.trigger(event['robot_id'],'report',at=at_s)

    def study_config(self):
        return {**super().study_config(),**vars(self.options),
            'condition':prompt.external_condition(self.arm,self.options.prompt_lang),
            'prompt_version':'ugrp.s4_english_compact.v1' if self.options.prompt_lang=='en' or self.options.compact_prompt_v1 else prior.epoch.base.si.PROMPT_VERSION,
            'legacy_channel_codec':self.condition,'pool_with_korean_or_other_models':False,
            'event_trace':self.decision_events.trace}

    def channel_summary(self):
        row=super().channel_summary()
        if self.options.prompt_lang=='en':
            row.update(condition=prompt.external_condition(self.arm),prompt_lang='en',
                legacy_channel_codec=self.condition,encoding='free_en' if self.spec.encoding=='free_ko' else self.spec.encoding,
                english_prose_check={'method':'Hangul presence; not a fluency score',
                    'hangul_messages':sum(bool(prompt.re.search('[\uac00-\ud7a3]',m.get('body',{}).get('text',''))) for m in self.messages)})
        return row


class Host(prior.Host):
    def __init__(self,*args,**kwargs):
        bind(prior.epoch.base.old.s4.Host.__init__,Trial=Trial)(self,*args,**kwargs)


class Driver(prior.epoch.Driver):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.monitors={};self.monitor_frames={};self.heartbeat_trace=[]

    def poll(self,now):
        trial=self.host.trial
        if not trial.options.event_driven_llm:return super().poll(now)
        rel=now-self.host.links['r1'].origin_s
        # Retain old bounded retry handling and GO/ACK logic, suppress only its
        # periodic carry trigger; edge events below replace the latter.
        self.next_ask.update({r:float('inf') for r in prior.epoch.hs.PAIR})
        super().poll(now)
        for rid in prior.epoch.hs.PAIR:
            link=self.host.links[rid];view=self.handshake.view(rid,rel)
            ctl=link.stop_adapter.controller();view['own_executor_phase']=getattr(ctl,'state',None)
            w=link.stop_adapter.window.snapshot(rel)
            payload=dict(pair_handshake=view,decision_window=w,sim_time_s=rel,
                         own_belief=link.stop_adapter.own_belief(now),
                         s4_round={'previous_rejection':trial.epoch_retry_context.get((rid,view['epoch']))})
            frame=link.frame_at(rel)
            if frame and view['phase']=='carry' and rid not in self.handshake.completed:
                epoch=view['epoch'];key=(rid,epoch)
                own=self.handshake.own[rid]
                if phase_group(view['own_executor_phase']) in ('carry','carry_start'):
                    from harness.s4_grip_visual import GripMonitor, OPTION
                    monitor=self.monitors.setdefault(key,GripMonitor(mode=OPTION))
                    if self.monitor_frames.get(key)!=frame.index:
                        self.monitor_frames[key]=frame.index
                        value=monitor.observe(frame.jpeg,frame.t,{})
                        self.monitors[(key,'result')]=value
                    visual=self.monitors.get((key,'result'),{'state':'unknown'})
                    payload['visual_monitor']=visual
                    if visual['state'] in ('grip_lost','unknown'):
                        # No old "held" replay or fabricated observation. Local
                        # safety stop is independent of message/model latency.
                        if visual.get('reason')!='ANCHOR_ACQUISITION':
                            self.handshake.abort(rid,rel,'EVENT_RGB_'+visual['state'].upper())
                    alive=visual['state']=='held'
                else:
                    alive=view['own_executor_phase'] not in ('done','failed','aborted','idle',None)
                if (alive and not self.handshake.failure and own['committed']
                        and 0<=rel-frame.t<.2 and rel<self.handshake.deadline(rid)
                        and rid not in trial.scheduler.holding()):
                    previous=own['last_response_at'];own['last_response_at']=rel
                    self.heartbeat_trace.append(dict(robot=rid,epoch=epoch,sim_s=rel,frame_sha256=frame.sha256,
                        previous=previous,kind='own_controller_rgb_liveness',command_replayed=False))
            reasons=trial.decision_events.observe(rid,payload)
            # GO/ACK already triggered above. Initial claims come from begin().
            reasons=[r for r in reasons if r not in ('initial_claim','go_ack_epoch')]
            if reasons:trial.scheduler.trigger(rid,'report',at=rel)
