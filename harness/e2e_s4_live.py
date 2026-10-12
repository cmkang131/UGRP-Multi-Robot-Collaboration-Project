"""OwnRoute dialogue with S4's event policy, compact English and durable wire.

The legacy pair handshake is deliberately not mixed with the OwnRoute gate:
only the latter binds order, delivered route, grip epoch and segment together.
"""
import copy
import json
from harness import s4_llm_host as base
from harness import e2e_own_inputs as own
from harness.s4_event_policy import Options, ProjectedInputs
from harness import s4_compact_prompt as prompt
from harness.s4_call_recovery import RetryTransport
from harness.zone_final_pair_binding import bind


EN = '''You are {rid}. r1=end_neg, r2=end_pos carry one long beam; r3 is idle.
Use only your wrist RGB, issued commands, private own map, fixed task and actually delivered peer_reports. An estimate or issued command is not success. Never invent coordinates or a route. Return JSON only with exactly request_id, action, decision_sources, messages. action is an object with kind. messages is an array (empty [] is valid). Copy request_id exactly. Follow reply_format_example for the JSON structure and choose your action from current evidence.
Until a route exists, continue while the own-camera mapper explores. r1 must send own_route_proposal unchanged as the message contract to r2 (or via the permitted leader). r2 must receive that exact proposal before approve_route. Both claim only after approval. No_comm cannot deliver B or approve a route.
GO/ACK use the exact current dialogue.key [order_id,route_hash,grip_epoch,seg]. GO requires own RGB supporting the grip; ACK requires your GO and the current peer_go_ref. Never reuse a previous epoch or segment. When unsure, continue holds transport. Only channel.can_send_to may receive messages. reply_to must be a received ID or null. All prose is English. Examples describe syntax, not evidence.'''


def project(request, *, options, decider='off', epoch_age_s=None, protocol_recovery='off',protocol_progress='off'):
    """Validate before projection; retain the typed E2E action/message contract."""
    r = copy.deepcopy(request)
    b = json.loads(r['messages'][1]['content'])
    own.scan(b)
    if b.get('schema') != own.SCHEMA or 'dialogue' not in b:
        raise base.ContractViolation('E2E_DIALOGUE_INPUT_REQUIRED')
    if not options.compact_prompt_v1 and options.prompt_lang == 'ko' and decider=='off':
        return r
    b['condition'] = prompt.external_condition(b['condition'], options.prompt_lang)
    b['channel']['condition'] = b['condition']
    if options.prompt_lang == 'en' and b['channel'].get('encoding') == 'free_ko':
        b['channel']['encoding'] = 'free_en'
    if options.compact_prompt_v1:
        # All detailed geometry stays in the checked private controller input.
        # Counts/digests are projections, never fabricated observations.
        mapped = b.pop('own_map')
        b['own_map_summary'] = {k: mapped[k] for k in ('robot_id','frame','map_version','pose','goal')}
        b['own_map_summary'].update(walls_count=len(mapped['walls']), source_count=len(mapped['sources']),
                                    own_map_sha256=own.digest(mapped))
        prompt._tail(b, 'own_command_history', 2)
        # Do not truncate peer_reports: route approval requires its actual envelope.
    system = EN.format(rid=b['robot_id']) if options.prompt_lang == 'en' else r['messages'][0]['content']
    if options.prompt_lang=='en':
        b['task']['destination_visual_description']='Blue floor destination B with three white rectangular marks.'
    b['action_message_contract'] = {
        'actions': [dict(kind='continue'), dict(kind='claim', order_id='order-5',
            destination_zone='B', role=own.TASK['fixed_roles'][b['robot_id']]),
            dict(kind='approve_route', route_hash='<dialogue.route_hash>',
                 proposal_message_id='<dialogue.proposal_message_id>'),
            dict(kind='route_vote', choice=['GO','ACK'], order_id='order-5',
                 route_hash='<dialogue.key[1]>', grip_epoch='<dialogue.key[2]>',
                 seg='<dialogue.key[3]>', peer_go_ref='<dialogue.peer_go_ref for ACK; null for GO>')],
        'message_element': dict(recipients=['<channel.can_send_to>'], text='<English own observation>',
                        reply_to=None, contract='<own_route_proposal unchanged, when proposing only>'),
        'decision_sources': ['order_sheet','own_rgb','own_commands','own_belief','message']}
    if b['robot_id'] == 'r3': b['action_message_contract']['actions'] = [dict(kind='continue')]
    if b['channel'].get('encoding') == 'schema':
        b['action_message_contract']['message_element'] = prompt.contracts(b, options.prompt_lang)['message']
        b['action_message_contract']['message_element']['contract'] = '<unchanged OwnRoute when proposing>'
    # Complete typed example, rather than isolated field snippets. This is
    # output syntax, never a synthetic peer observation or accepted decision.
    b['reply_format_example'] = dict(request_id=b['request_id'],action=dict(kind='continue'),
        decision_sources=['order_sheet'],messages=[])
    if decider not in ('off','jev_v1'):raise ValueError('UNKNOWN_DECIDER')
    if decider=='jev_v1':
        b.update(decider=decider,dialogue_epoch_age_s=epoch_age_s)
        b['reply_format_example']['own_rgb_grip']='unknown'
        system=system.replace('exactly request_id, action, decision_sources, messages.',
            'exactly request_id, action, decision_sources, messages, own_rgb_grip.')
        system+=' Return exactly request_id, action, decision_sources, messages, own_rgb_grip. Your action is recorded as a shadow choice. Classify ONLY your current wrist RGB in own_rgb_grip: holding, not_visible, slipping, none, or unknown. Issued gripper commands do not prove holding. If occluded or uncertain, use unknown. Do not infer the partner grip from your image.'
    if protocol_recovery!='off':
        from harness.e2e_protocol_recovery import OPTION,prompt as recovery_prompt
        if protocol_recovery!=OPTION:raise ValueError('UNKNOWN_PROTOCOL_RECOVERY')
        system=recovery_prompt(b,system)
    if protocol_progress!='off':
        from harness.e2e_protocol_progress import OPTION,prompt as progress_prompt
        if protocol_progress!=OPTION:raise ValueError('UNKNOWN_PROTOCOL_PROGRESS')
        system=progress_prompt(b,system)
    b['prompt_lang'] = options.prompt_lang
    own.scan(b)
    if len(r['images']) != 1 or len(r['image_refs']) != 1:
        raise base.ContractViolation('ONE_OWN_RGB_ONLY')
    user = json.dumps(b, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    r.update(messages=[dict(role='system', content=system), dict(role='user', content=user)],
        input_sha256=own.digest(b), prompt_version='ugrp.e2e_s4_live.v2',
        condition=b['condition'], compact_prompt_v1=options.compact_prompt_v1,
        prompt_lang=options.prompt_lang)
    r['request_sha256'] = prompt.pk.request_digest_from_refs(system,user,r['image_refs'])
    r['tokens'] = prompt.pk.request_tokens(system,user,r['images'])
    from harness.pair_llm_billing import billed_tokens
    r['billed_tokens'] = billed_tokens(r['tokens'], system_billed=prompt.pk.count_tokens(system))
    return r


class Trial(base.Trial):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = getattr(self.links['r1'].inner, 'study_options', Options())
        self.decider=getattr(self.links['r1'].inner,'decider','off')
        self.jev_guard_events=[]
        self.protocol_recovery=getattr(self.links['r1'].inner,'protocol_recovery','off')
        from harness.e2e_protocol_recovery import Recovery
        self.protocol_reasks=Recovery()
        self.protocol_progress=getattr(self.links['r1'].inner,'protocol_progress','off')
        from harness.e2e_protocol_progress import Reminders
        self.protocol_reminders=Reminders()
        if not self.own_input_mode or self.dialogue is None:
            raise base.ContractViolation('E2E_OWN_INPUTS_AND_DIALOGUE_REQUIRED')
        self.transport = RetryTransport(self, send_ledger=self.send_ledger, client_factory=self.client_factory)
        self.scheduler.transport = self.transport
        self.event_keys, self.decision_events = {}, []
        if self.options.event_driven_llm:
            self.scheduler.event_available_at = lambda actor,cause:self.scheduler.clock
        self.provenance.update(prompt_lang=self.options.prompt_lang,
            provider='google_aistudio_gemma' if self.client_factory.settings['model'].startswith('gemma-')
                     else 'gemini_subscription_proxy')

    def prepare_call(self, call):
        p = super().prepare_call(call)
        view=self.dialogue.view(call.actor,call.started_sim_s)
        age=None if view['key'] is None else call.started_sim_s-self.dialogue.opened
        request = project(p.request, options=self.options,decider=self.decider,epoch_age_s=age,protocol_recovery=self.protocol_recovery,protocol_progress=self.protocol_progress)
        return type(p)(ProjectedInputs(p.bundled,json.loads(request['messages'][1]['content'])),request,p.request_id)

    def finish_call(self,call,prepared,raw,*,provider_usage=None):
        if self.decider=='jev_v1':
            from harness.three_robot_plan import parse
            from harness.zone_sim_cost import Attempt,call_cost
            value=parse(raw)
            cost=call_cost((Attempt(outcome='ok',input_tokens=prepared.request['billed_tokens']['total_billed'],
                output_tokens=self.sim_output_tokens(raw,len(value['messages'])),utterances=len(value['messages'])),),self.params)
            try:
                self.dialogue.check_action(value['action'],self.dialogue.captures[call.call_id],round(call.started_sim_s+cost.sim_s,6))
            except (base.ContractViolation,KeyError,TypeError,ValueError) as exc:
                self.jev_guard_events.append(dict(call_id=call.call_id,selected_action=copy.deepcopy(value['action']),
                    reason=str(exc),replacement={'kind':'continue'}))
                value['action']={'kind':'continue'}
                raw=json.dumps(value,ensure_ascii=False)
        return super().finish_call(call,prepared,raw,provider_usage=provider_usage)

    def observe_events(self, now):
        if not self.options.event_driven_llm: return
        if self.protocol_recovery=='envelope_retry_v1':self.protocol_reasks.poll(self,now)
        if self.protocol_progress=='stage_retry_v1':self.protocol_reminders.poll(self,now)
        for rid in ('r1','r2','r3'):
            state = self.links[rid].inner.own_inputs_at(now)
            route = state.get('own_route')
            view = self.dialogue.view(rid, now)
            key = (route['route_hash'] if route else None, view['route_hash'], view['approved'],
                   view['own_claim'], tuple(view['key'] or ()),view['own_go_sent'],
                   view['peer_go_ref'],view['own_ack_sent'])
            previous = self.event_keys.get(rid)
            self.event_keys[rid] = key
            if previous is not None and previous != key:
                self.scheduler.trigger(rid,'report',at=now)
                self.decision_events.append(dict(robot_id=rid,at=now,key=list(key),reason='own_route_dialogue_edge'))


class Host(base.Host):
    def __init__(self, *args, **kwargs):
        kwargs['condition'] = prompt.legacy_condition(kwargs['condition'])
        bind(base.Host.__init__, Trial=Trial)(self,*args,**kwargs)

    def step_to(self, at_s):
        self.trial.observe_events(at_s)
        return super().step_to(at_s)
