"""Task intents above the existing E2E18 code_v1 body, default off.

Only own captured inputs and the delivered text channel enter Gemma. Existing
route/GO/ACK identifiers stay inside the act executor's safety contract; they
are not task-planner evidence. No evaluator or backend reference is accepted.
"""
from __future__ import annotations
import copy
import json
import math
from dataclasses import replace
from harness.task_planner import Planner, candidate, parse, signature, strong_rule, ModelReply, SYSTEM

VERSIONS = {'gemma_v1':373, 'rule_v1':374}
GATED_VERSIONS = {'gemma_v1':387, 'rule_v1':388}
PARAMETERS = dict(parent='e2e18-v372', call_policy='event_v1', snapshot='prepared_v1',
                  body='code_v1', max_output_tokens=768, repair_calls=1,
                  peer_input='delivered_channel_text_only', solo_beam_forbidden=True,
                  admission_clock='tick_v1', recovery_menu='skip_rejected_v1')


def compose(bundle, option='off', planner_evidence_gate='off'):
    from harness.task_planner_evidence_gate import option as gate_option
    gate_option(planner_evidence_gate)
    if option == 'off' and planner_evidence_gate != 'off': raise ValueError('EVIDENCE_GATE_REQUIRES_PLANNER')
    if option=='off': return ()
    if option not in VERSIONS or bundle['execution_bundle_id']!=PARAMETERS['parent']:
        raise ValueError('TASK_PLANNER_REQUIRES_FIXED_V372_PARENT')
    o=bundle['e2e_options']
    if o.get('body_backend')!='code_v1' or o.get('dialogue_call_policy')!='event_v1' or o.get('call_snapshot')!='prepared_v1':
        raise ValueError('TASK_PLANNER_CODE_BODY_EVENT_SNAPSHOT_REQUIRED')
    version=(GATED_VERSIONS if planner_evidence_gate=='on_v1' else VERSIONS)[option]
    bundle.update(task_planner_parent=PARAMETERS['parent'],task_planner_parameters=copy.deepcopy(PARAMETERS),
        execution_bundle_id=f'e2e18-v{version}',workflow_version=f'7.{version-107}.0',schema=f'ugrp.e2e_ownmap_live.v{version}')
    o['planner']=option
    if planner_evidence_gate=='on_v1':
        from harness.task_planner_evidence_gate import PARAMETERS as gate_parameters
        o['planner_evidence_gate']=planner_evidence_gate
        bundle['planner_evidence_gate_parameters']=copy.deepcopy(gate_parameters)
    return (('harness/task_planner_evidence_gate.py',) if planner_evidence_gate=='on_v1' else ()) + ('harness/e2e_task_planner.py','harness/task_planner.py','harness/task_planner_evidence.py',
            'configs/e2e_task_planner_options.json',f'configs/simulation_workflows.d/e2e18_v{version}.json')


def parent_for_validation(bundle):
    b=copy.deepcopy(bundle);mode=b['e2e_options'].get('planner')
    versions=VERSIONS
    if b['e2e_options'].get('planner_evidence_gate','off')!='off':
        from harness.task_planner_evidence_gate import PARAMETERS as gate_parameters
        if b['e2e_options'].pop('planner_evidence_gate')!='on_v1' or b.pop('planner_evidence_gate_parameters',None)!=gate_parameters:
            raise ValueError('REGISTERED_EVIDENCE_GATE_REQUIRED')
        versions=GATED_VERSIONS
    if (mode not in VERSIONS or b['execution_bundle_id']!=f'e2e18-v{versions[mode]}'
        or b.get('task_planner_parent')!=PARAMETERS['parent'] or b.get('task_planner_parameters')!=PARAMETERS):
        raise ValueError('REGISTERED_TASK_PLANNER_REQUIRED')
    b['execution_bundle_id']=b.pop('task_planner_parent');b.pop('task_planner_parameters');b['e2e_options'].pop('planner')
    return b


def menu(rid, own):
    """Feasibility from own observation/issued commands plus fixed beam order."""
    rows=[candidate('search',dict(area='unobserved_frontier'),expected_s=15.,description='Explore with the existing own-map frontier navigation skill until new task evidence is seen.')]
    visible=own.get('beam_visible',False); holding=own.get('gripper_command')=='closed'
    for direction in ('left','right'):
        rows.append(candidate('search',dict(area=direction),expected_s=2.,
            description=f'Scan {direction} with the existing own-camera skill.'))
        if not holding:
            rows.append(candidate('reroute',dict(via='detour_'+direction),expected_s=3.,
                description=f'Take the bounded {direction} detour and replan from own RGB.'))
    rows.append(candidate('wait',dict(until='new_own_observation_or_partner_message',max_s=5.),expected_s=5.))
    rows.append(candidate('report',dict(fact='request_current_observation'),expected_s=1.))
    if rid in ('r1','r2'):
        partner='r2' if rid=='r1' else 'r1'
        sides=[own['selected_side']] if holding and own.get('selected_side') else ['end_neg','end_pos']
        for side in sides:
            for approach in ('direct','left','right'):
                rows.append(candidate('carry',dict(cargo='beam_1',to='B',via='observed_own_route',
                    approach=approach,mode='joint',partner=partner,side=side),required_robots=2,
                    expected_s=40. if visible else 90.,description='Execute this selected end and approach, then the observed route; current two-party safety approval still required.'))
            rows.append(candidate('help',dict(partner=partner,cargo='beam_1',side=side),required_robots=2,
                expected_s=40. if visible else 90.))
        if holding:
            rows.append(candidate('set_down_and_regrip',{},required_robots=2,expected_s=12.,
                description='Request the existing controlled set-down and new own-RGB alignment; hold until the joint safety gate admits it.'))
    return rows


def own_projection(robot, body, rid, now, selected):
    state=robot.own_inputs_at(now)
    # own_inputs_at validates every RGB timestamp; do not consult transport's
    # shared phase/other robot state when forming task evidence.
    from harness.e2e_own_inputs import validate_map
    validate_map(state['own_map'],rid,now,state['observed_rgb'])
    frame=robot.frame_at(now)
    beam=getattr(robot,'beam',None)
    facts=body.context(rid,now) if body is not None else {}
    last=getattr(robot,'last_beam',None)
    return dict(robot_id=rid,pose=copy.deepcopy(state['own_map']['pose']),
        observed_map=dict(frame=state['own_map']['frame'],map_version=state['own_map']['map_version'],
            goal=copy.deepcopy(state['own_map']['goal']),walls_count=len(state['own_map']['walls'])),rgb=dict(sha256=frame.sha256,t_sim=frame.t),
        own_command_history=copy.deepcopy(facts.get('own_command_history',[])[-8:]),
        beam_visible=bool(beam and beam['rgb']['t_sim']<=now),
        last_direct_beam_observation_at=beam['rgb']['t_sim'] if beam else last['rgb']['t_sim'] if last else None,
        gripper_command='closed' if robot.servo.get(1)==1500 else 'open',
        visual_category=facts.get('visual_category','unknown'),
        own_grip=facts.get('own_grip','unknown'),
        observed_facts=[dict(subject=rid,predicate='grip',value='slipping' if 'slipping' in str(facts.get('own_grip')) else 'holding',
            observed_at=frame.t,source='own RGB hypothesis')] if 'slipping' in str(facts.get('own_grip')) or str(facts.get('own_grip','')).startswith('holding') else [],
        nearby_obstacle=copy.deepcopy(facts.get('peer_in_own_rgb',{})),
        blocked=bool(facts.get('blocked_persistently',False)),
        selected_side=selected.get('args',{}).get('side') if selected else None,
        own_stage=getattr(robot.goal,'stage','unknown'))


class Executive:
    def __init__(self,trial,transport,body,mode,append,planner_evidence_gate='off'):
        from harness.task_planner_evidence_gate import option
        self.evidence_gate=option(planner_evidence_gate)
        self.trial,self.tr,self.body,self.mode,self.append=trial,transport,body,mode,append
        self.planners={r:Planner(r,'peer_en',leader='r1',planner_evidence_gate=planner_evidence_gate) for r in trial.actors}
        self.active={};self.started={};self.ends={};self.pending={};self.rows=[];self.last_edges={}
        self.request_context={};self.original_prepared={};self.route_snapshots={};self.selected_routes={};self.nudged=set();self.sequence=0;self.delayed=set()
        self.tr.task_roles={}
        self.interrupted=False;self.holds=[];self.regrip_open_seen=set();self.event_stamp={};self.late_attempts={};self.own_protocol={}
        for p in self.planners.values():
            from collections import deque
            p.inbox=deque(maxlen=6)

    def record(self,**row):
        self.rows.append(row);self.append(row)

    def receive(self,rid,now):
        p=self.planners[rid]
        for e in self.trial.channel.inbox(rid,now_sim_s=now):
            # Typed route contracts, peer vote references and keyword votes
            # never cross into the planner. Preserve actual NL bytes only.
            text=(e.get('body') or {}).get('text')
            if not isinstance(text,str) or not text.strip():continue
            at=e.get('created_at_sim_s',now);delivered=e.get('delivered_at_sim_s',e.get('received_at_sim_s',now))
            if delivered is None:delivered=now
            p.receive(dict(id=e['message_id'],sender=e['sender'],recipient=rid,
                sent_at=at,delivered_at=delivered,body=text),now)

    def context(self,rid,now):
        self.receive(rid,now)
        own=own_projection(self.tr.robots[rid],self.body,rid,now,self.active.get(rid))
        own['interrupted_segment_requires_regrip']=self.interrupted
        ctx=self.planners[rid].context(now=now,orders=[dict(order_id='order-5',cargo='beam_1',required_robots=2,destination_zone='B')],
            static_map=dict(source='none: this E2E18 scenario maps its own camera views'),own=own,candidates=menu(rid,own),
            task='Deliver beam_1 to the blue B area. Choose your end, joint work, approach, route/recovery, waiting or regripping. The beam requires two robots. r3 can observe and report. Use only actual received text for partner information.')
        robot=self.tr.robots[rid];beam=getattr(robot,'beam',None)
        target=getattr(robot.goal,'entities',{}).get('B')
        if rid in ('r1','r2') and beam and target and target.get('source')=='own':
            from harness.e2e_carrier_axes import station
            for c in ctx['candidates']:
                if c['args'].get('side'):
                    endpoint,_,_=station(beam,target['center_m'],c['args']['side'])
                    distance=math.dist(own['pose']['mean'][:2],endpoint[:2])
                    c['preview'].update(distance_m=distance,approach_distance_m=distance,
                        expected_s=40.+distance/.1,source='own RGB beam/B map and own command pose; uncertain travel estimate')
        routes=getattr(self.tr.robots[rid].goal,'task_route_candidates',{}) if rid=='r1' else {}
        if routes:
            from harness.e2e_task_planner_routes import preview
            expanded=[]
            for c in ctx['candidates']:
                if c['act']!='carry':expanded.append(c);continue
                for route_id,packet in routes.items():
                    chosen=copy.deepcopy(c);chosen['args']['via']=route_id;chosen['preview'].update(preview(packet));expanded.append(chosen)
            ctx['candidates']=expanded
        if self.interrupted:
            ctx['candidates']=[c for c in ctx['candidates'] if c['act'] not in ('carry','help')]
        ctx['candidates']=[c for c in ctx['candidates'] if self.check(rid,c) is None]
        from harness.task_planner_evidence_gate import apply
        ctx=apply(ctx,self.evidence_gate)
        for row in ctx['candidates']:
            row['preview']['evidence_refs']=[e['message_id'] for e in row['preview'].pop('evidence')]
        return ctx

    def check(self,rid,value):
        a=value['args'];robot=self.tr.robots[rid]
        if len(value.get('message',''))>240:return 'TASK_MESSAGE_MAX_240_CHARS'
        if self.interrupted and value['act'] in ('carry','help'):return 'INTERRUPTED_SEGMENT_REQUIRES_REGRIP_AND_NEW_OWN_ROUTE'
        if value['act']=='carry' and a['mode']!='joint':return 'BEAM_REQUIRES_TWO_ROBOTS'
        current=self.active.get(rid,{})
        if (value['act']=='carry' and current.get('act')=='carry' and robot.servo.get(1)==1500
                and a.get('via')!=current['args'].get('via')):return 'SET_DOWN_AND_REPLAN_BEFORE_CHANGING_LOADED_ROUTE'
        if a.get('side'):
            from harness.e2e_task_planner_wire import read_status
            for message in reversed(self.planners[rid].inbox):
                status=read_status(message['body'])
                if status and status.get('kind')=='claim':
                    if status.get('role')==a['side']:return 'RECEIVED_PARTNER_CLAIM_OCCUPIES_REQUESTED_END'
                    break
        if a.get('side') and self.tr.task_roles.get(rid)!=a['side'] and any(r==rid and c.get('kind')=='arm' for _,r,c in getattr(self.tr,'queue',[])):
            return 'OWN_ARM_BATCH_ACTIVE_CANNOT_CHANGE_END'
        if a.get('side') and robot.servo.get(1)==1500 and self.tr.task_roles.get(rid)!=a['side']:
            return 'CANNOT_CHANGE_END_WHILE_GRIPPER_COMMANDED_CLOSED'
        if value['act']=='set_down_and_regrip' and self.tr.state not in ('wait_go_ack','carry','grasp_go_ack','grasp_lift','planner_regrip_wait'):
            return 'REGRIP_REQUIRES_CURRENT_CARRY_OR_GRASP'
        if value['act']=='reroute' and robot.servo.get(1)==1500:return 'SET_DOWN_BEFORE_INDIVIDUAL_DETOUR'
        return None

    def start(self,rid,value,now):
        refusal=self.check(rid,value)
        if refusal:return dict(accepted=False,reason=refusal)
        if value['act'] in ('wait','set_down_and_regrip') and self.tr.state in ('carry','grasp_lift','wait_go_ack','grasp_go_ack'):
            self.interrupt(now)
        self.active[rid]=copy.deepcopy(value);self.started[rid]=now;self.nudged.discard(rid);self.delayed.discard(rid)
        self.body.units.pop(rid,None) if hasattr(self.body,'units') else None
        self.body.pending.pop(rid,None) if hasattr(self.body,'pending') else None
        selected=self.selected_routes.pop(rid,None)
        if selected is not None:self.tr.robots[rid].packet=copy.deepcopy(selected)
        if value['args'].get('side'):
            old=self.tr.task_roles.get(rid);self.tr.task_roles[rid]=value['args']['side']
            if old!=value['args']['side']:
                self.tr.approach.pop(rid,None);self.tr.aligned.pop(rid,None)
                if hasattr(self.tr,'dialogue'):
                    self.tr.dialogue.claims.discard(rid);self.tr.dialogue.votes.pop(rid,None)
        duration=value['args'].get('max_s',15. if value['act']=='search' and value['args']['area']=='unobserved_frontier' else 2. if value['act'] in ('search','report') else 3. if value['act']=='reroute' else 60.)
        self.ends[rid]=now+duration
        self.record(event='act_started',robot_id=rid,sim_s=now,decision=copy.deepcopy(value))
        return dict(accepted=True,executor='e2e18/code_v1')

    def interrupt(self,now):
        # Cancel the unissued remainder. Never count a partial calibrated leg
        # as completed or replay it from its start. Replan from new own RGB.
        self.interrupted=True;self.tr.task_interrupted=True
        self.tr.queue.clear();self.tr.queue_until=now;self.tr.authorizations.clear();self.tr.permit=None
        self.holds=[(r,dict(kind='hold')) for r in ('r1','r2')]
        self.tr.epoch+=1
        self.tr.dialogue.begin_epoch(order_id='order-5',route_hash=self.tr.plan['agreement_route_hash'],
            grip_epoch=self.tr.epoch,seg=self.tr.seg,now=now)
        self.tr.set('planner_regrip_wait',now)
        for r in ('r1','r2'):
            self.planners[r].trigger('grip_anomaly',now,'own joint command interrupted; regrip/new route required')
        self.record(event='carry_interrupted',sim_s=now,remaining_commands_cancelled=True)

    def tick(self,now):
        if self.tr.state=='planner_regrip_wait' and all(self.active.get(r,{}).get('act')=='set_down_and_regrip' for r in ('r1','r2')):
            if self.tr.dialogue.allowed(self.tr.dialogue.key,now):self.tr._lower(now)
        if self.interrupted and not getattr(self.tr,'task_interrupted',True):self.interrupted=False
        for rid in self.planners:
            self.receive(rid,now)
            robot=self.tr.robots[rid];p=self.planners[rid]
            # Detect events only from this robot's own categories, not eval.
            f=self.body.context(rid,now);edge=(f.get('blocked_persistently'),f.get('visual_category'),f.get('own_grip'),bool(f.get('peer_in_own_rgb',{}).get('in_path')))
            old=self.last_edges.get(rid);self.last_edges[rid]=edge
            if old is not None and old!=edge:
                if edge[3]:p.trigger('s4_occupied',now,'own RGB shows an obstacle in the approach')
                if edge[0]:p.trigger('s2_blocked',now,'own path repeatedly blocked')
                if edge[1]=='not_visible' and old[1]!='not_visible':p.trigger('s5_missing',now,'target missing in own view')
                if 'slipping' in str(edge[2]):p.trigger('grip_anomaly',now,'own RGB grip anomaly')
            if rid in self.active and self.active[rid]['act'] in ('carry','help') and now-self.started[rid]>=15 and rid not in self.delayed:
                self.delayed.add(rid);p.trigger('s3_partner_delayed',now,'joint act has not completed within the own 15 s observation window')
            if rid in self.active and now>=self.ends[rid]:
                value=self.active.pop(rid)
                history=getattr(getattr(self.body,'memory',{}).get(rid),'history',[])
                observed=any(h.get('t',-1)>=self.started[rid] and h.get('outcome') in ('bounded_skill_finished','observed_after_motion') for h in history)
                status='success' if value['act']=='wait' or value['act'] in ('search','reroute') and observed else 'failure'
                p.feedback(value,status,'bounded own act completed; no delivery success inferred' if status=='success' else 'bounded action deadline; verify from new own observations',now,now-self.started[rid])
                self.record(event='act_result',robot_id=rid,sim_s=now,status=status,decision=value)

    def restrict(self,rid,now,kind,choices,proposal,facts):
        """Code can reject/hold, but cannot substitute a different task direction."""
        value=self.active.get(rid)
        hold={k:v for k,v in choices.items() if k in ('hold_and_reobserve','wait_and_reobserve','hold_and_wait')}
        if value is None or value['act'] in ('wait','report'):return hold
        act,args=value['act'],value['args']
        if act=='search':
            if args['area']=='unobserved_frontier':
                return choices if self.tr.state=='mapping' else hold
            wanted=('scan_'+args['area'], 'search_own_beam')
        elif act=='reroute':wanted=(args['via'],)
        elif act in ('carry','help'):
            direction=args.get('approach','direct')
            if direction!='direct' and rid not in self.nudged:
                wanted=('detour_'+direction,)
                history=getattr(getattr(self.body,'memory',{}).get(rid),'history',[])
                if any(h.get('choice') in wanted and h.get('t',-1)>=self.started[rid] and h.get('outcome') in ('bounded_skill_finished','observed_after_motion') for h in history):
                    self.nudged.add(rid)
                else:return {**hold,**{k:v for k,v in choices.items() if k in wanted}}
            return {k:v for k,v in choices.items() if not k.startswith(('detour_','back_off','recover_','replan_'))}
        elif act=='set_down_and_regrip':
            if self.tr.state in ('lower_open','relook_camera','relook','mapping','align','grasp_close','grasp_lift'):return choices
            return hold
        else:return hold
        allowed={k:v for k,v in choices.items() if k in wanted};return {**hold,**allowed}


def install(trial,transport,body,option='off',append=lambda row:None,planner_evidence_gate='off',planner_selection=None,planner_prompt_order='off'):
    if option=='off':return None
    if option not in VERSIONS or trial.dialogue_call_policy!='event_v1' or body is None:
        raise ValueError('TASK_PLANNER_RUNTIME_REQUIREMENTS')
    from harness.e2e_admission_clock import install as clock_install
    clock_install(trial,PARAMETERS['admission_clock'])
    if hasattr(body,'safe_menu'):
        from harness.e2e_recovery_menu import install as recovery_install
        recovery_install(body,PARAMETERS['recovery_menu'])
    executive=Executive(trial,transport,body,option,append,planner_evidence_gate)
    executive.selection=planner_selection;executive.prompt_order=planner_prompt_order
    trial.task_planner=executive;transport.task_planner=executive
    for robot in transport.robots.values():robot.goal.task_planner_enabled=True
    prepare=trial.prepare_call;finish=trial.finish_call
    def prepare_task(call):
        original=prepare(call);ctx=executive.context(call.actor,call.started_sim_s)
        ctx['planner_backend']=option
        request=copy.deepcopy(original.request)
        from harness import zone_study_prompts_ko as pk, pair_llm_billing as billing
        from harness.task_planner_model import ordered_context
        user=json.dumps(ordered_context(ctx,planner_prompt_order),ensure_ascii=True,sort_keys=planner_prompt_order=='off')
        request['messages']=[dict(role='system',content=SYSTEM),dict(role='user',content=user)]
        request['schema']='ugrp.task_planner.v1'
        tokens=pk.request_tokens(SYSTEM,user,request['images'])
        request['tokens']=tokens;request['billed_tokens']=billing.billed_tokens(tokens,system_billed=pk.count_tokens(SYSTEM))
        request['request_sha256']=pk.request_digest_from_refs(SYSTEM,user,request['image_refs'])
        executive.route_snapshots[call.call_id]=copy.deepcopy(getattr(transport.robots[call.actor].goal,'task_route_candidates',{}))
        executive.request_context[call.call_id]=copy.deepcopy(ctx);executive.original_prepared[call.call_id]=original
        return type(original)(original.bundled,request,original.request_id)
    trial.prepare_call=prepare_task
    # Snapshot wrapper is installed by the runner AFTER this wrapper: all own
    # body facts, event and report metadata are frozen when submit occurs.
    return connect(executive)


def rule(context):
    """Same-input native strong baseline; no fixed end assignment."""
    own=context['own'];rows=context['candidates'];reports=context['received_messages']
    text=' '.join(m['body'] for m in reports if context['now_s']-m['sent_at']<=30).lower()
    conflicts=[e for e in context.get('evidence_assessment',{}).get('reports',[]) if e.get('conflicts_with_own_observation') and e.get('last_directly_observed_at') is not None]
    if context.get('planner_evidence_gate')=='on_v1':
        conflicts=[e for e in context['evidence_gate']['archived_reports'] if e['status']=='conflict']
    if conflicts:
        desired=[c for c in rows if c['act']=='search']
    elif own.get('interrupted_segment_requires_regrip') or 'slipping' in str(own.get('own_grip')):
        desired=[c for c in rows if c['act']=='set_down_and_regrip']
    elif own.get('blocked'):
        desired=[c for c in rows if c['act']=='reroute']
    elif own.get('beam_visible') or own.get('gripper_command')=='closed':
        desired=[c for c in rows if c['act']=='carry' and c['args']['approach']=='direct']
        # One delivered peer sentence may reserve an end. No shared role table.
        if ('end_neg' in text) != ('end_pos' in text):
            opposite='end_pos' if 'end_neg' in text else 'end_neg'
            desired=[c for c in desired if c['args']['side']==opposite] or desired
    else:
        desired=[c for c in rows if c['act']=='search' and c['args']['area']=='unobserved_frontier']
        recent=context['own_act_results']
        last=recent[-1].get('args',{}).get('area') if recent else None
        desired=[c for c in desired if c['args']['area']!=last] or desired
    if not desired:return strong_rule(context)
    failed={signature(r) for r in context['own_act_results'] if r.get('status') in ('failure','refused') and 'act' in r}
    def cost(c):
        p=c['preview'];return ((p.get('expected_s') or 30.)+(100 if signature(c) in failed else 0),signature(c))
    chosen=min(desired,key=cost)
    a=chosen['args']
    message=(f"I will carry beam_1 at {a['side']} toward B via {a['via']} with a {a['approach']} approach." if chosen['act']=='carry' else f"I will {chosen['act']} using {next(iter(a.values()), 'my own observation')}.")
    return dict(act=chosen['act'],args=copy.deepcopy(chosen['args']),message=message[:240],reason='Own observation, recent received text and bounded failure memory.')


def connect(executive):
    """Use the existing ledger/client once per admitted event (+ one repair)."""
    from harness.s4_call_recovery import RetryTransport
    from harness.llm_completion import normal_completion,completion_record
    import time
    trial=executive.trial
    trial.send_ledger.task_planner_contract=True
    from harness.task_planner_model import ordered_context
    finish=trial.finish_call
    class Transport(RetryTransport):
        def _reply(self,call):
            self.resolved.append(call.call_id)
            prepared=self.pipeline.prepare_call(call)
            ctx=executive.request_context.pop(call.call_id)
            original=executive.original_prepared.pop(call.call_id)
            planner=executive.planners[call.actor];planner.fallback=rule
            while planner.events and planner.events[0]['at']<=ctx['now_s']:planner.events.popleft()
            client=self.client_factory(call.http_open)
            client.require_json_reply='task_planner_v1'
            client.timeout=min(client.timeout,planner.deadline_s)
            client.max_tokens=PARAMETERS['max_output_tokens']
            before=len(planner.audit)
            def model(request,*,timeout_s):
                started=time.monotonic()
                if getattr(executive,'selection',None) is not None:
                    import base64,hashlib
                    images=prepared.request['images'];refs=prepared.request['image_refs']
                    if len(images)!=len(refs):raise ValueError('OWN_IMAGE_REF_COUNT')
                    for image,ref in zip(images,refs):
                        raw_image=base64.b64decode(image['image'].split(',',1)[1],validate=True)
                        if hashlib.sha256(raw_image).hexdigest()!=ref.get('bytes_sha256',ref.get('sha256')):
                            raise ValueError('OWN_RGB_HASH_MISMATCH')
                try:
                    raw=client.complete([dict(role='system',content=request['system']),
                        dict(role='user',content=json.dumps(ordered_context(request['input'],getattr(executive,'prompt_order','off')),sort_keys=getattr(executive,'prompt_order','off')=='off'))],images=prepared.request['images'])
                except Exception:
                    reasons=(client.last_completion or {}).get('rejection_reasons',[])
                    if client.last_text and reasons and set(reasons)<= {'study_reply_fields_missing_or_extra','study_reply_incomplete_or_non_json'}:
                        return ModelReply(client.last_text,'stop',time.monotonic()-started,{**(client.last_usage or {}),**getattr(client,'last_provider_metadata',{})})
                    raise
                return ModelReply(raw,'stop' if normal_completion(client.last_completion) else 'abnormal',
                    time.monotonic()-started,{**(client.last_usage or {}),**getattr(client,'last_provider_metadata',{})})
            class Port:
                def check(self,value):return executive.check(call.actor,value)
                def start(self,value):return dict(accepted=True,deferred_until='scheduler_release')
            used=executive.late_attempts.get(call.actor,0)
            result=(planner._fallback(ctx,Port(),'LATE_REPAIR_EXHAUSTED') if used>=2 else
                planner.decide(ctx,model,Port(),repair_budget=max(0,1-used)))
            executive.late_attempts[call.actor]=used+sum('request' in a for a in planner.audit[before:])
            value=result['decision']
            executive.record(event='task_decision',robot_id=call.actor,call_id=call.call_id,
                sim_s=call.started_sim_s,mode=executive.mode,result=result,audit=copy.deepcopy(planner.audit[before:]))
            # The upper act is immutable. Existing route receipt, claim and
            # GO/ACK code below only admits the selected joint act safely.
            from harness import e2e_dialogue_decider as protocol
            user=json.loads(original.request['messages'][1]['content'])
            routes=executive.route_snapshots.pop(call.call_id,{})
            selected_route=routes.get((value or {}).get('args',{}).get('via'))
            if selected_route is not None:
                executive.selected_routes[call.actor]=copy.deepcopy(selected_route)
                capture=trial.dialogue.captures[call.call_id]
                capture['state']['own_route']=copy.deepcopy(selected_route['route'])
                capture['state']['own_map']=copy.deepcopy(selected_route['route']['own_map'])
                user['own_route_proposal']=copy.deepcopy(selected_route['proposal'])
                user['route_contract_example']=copy.deepcopy(selected_route['proposal'])
                user['action_message_contract']['message_element']['contract']=copy.deepcopy(selected_route['proposal'])
            selected=dict(action='WAIT',own_grip='unknown',own_alignment='unknown')
            if value and value['act'] in ('carry','help','set_down_and_regrip'):
                safety=copy.deepcopy(user)
                # No lexical peer vote inference in this planner path.
                for receipt in protocol.call_reports(safety):receipt['body']={'text':''}
                safety.pop('active_safety_reports',None)
                selected=protocol.code_select(safety)
                side=value['args'].get('side') or executive.tr.task_roles.get(call.actor)
                if side:user['task']['fixed_roles'][call.actor]=side
            text=value['message'] if value else ''
            if not text:text='I am checking my own observations before continuing.'
            assembled=protocol.assemble(user,selected,text[:240])
            if assembled['action']['kind']=='claim' and value:
                assembled['action']['role']=value['args'].get('side',assembled['action']['role'])
            from harness.e2e_task_planner_wire import compile_messages
            for message in assembled['messages']:
                if message.get('contract'):
                    message['contract']=trial.dialogue.outgoing(message['contract'],trial.dialogue.captures[call.call_id])
            assembled['messages']=compile_messages(assembled['messages'])
            executive.pending[call.call_id]=copy.deepcopy(value)
            trial.dialogue.captures[call.call_id]['planner_role']=(value or {}).get('args',{}).get('side') or executive.tr.task_roles.get(call.actor)
            # Keep task wire request and token accounting in the original
            # archive, while validating the executor's compiled safety action.
            effective=type(prepared)(prepared.bundled,prepared.request,prepared.request_id)
            usage=client.last_usage
            reply=finish(call,effective,json.dumps(assembled),provider_usage=usage)
            if reply.action is None and value:
                rejected=trial.memory.rejections.get(call.call_id,{}) if hasattr(trial,'memory') else {}
                planner.feedback(value,'refused',rejected.get('reason','COMPILED_SAFETY_ACTION_REFUSED'),call.started_sim_s)
                executive.record(event='compiled_act_refused',call_id=call.call_id,robot_id=call.actor,reason=rejected.get('reason'))
                value=None
            if executive.mode=='rule_v1':
                from harness.zone_sim_cost import Attempt
                reply=replace(reply,attempts=(Attempt(outcome='ok',input_tokens=0,output_tokens=0,utterances=len(assembled['messages'])),))
            return replace(reply,action=dict(kind='task_planner_release',call_id=call.call_id,
                safety_action=copy.deepcopy(reply.action),decision=value),
                completion=completion_record(client.last_completion))
    transport=Transport(trial,send_ledger=trial.send_ledger,client_factory=trial.client_factory)
    trial.transport=transport;trial.scheduler.transport=transport
    def release(rid,action,now):
        cid=action['call_id'];value=action['decision']
        ack=executive.start(rid,value,now) if value else dict(accepted=False,reason='NO_SAFE_ACT')
        if value and not ack['accepted']:executive.planners[rid].feedback(value,'refused',ack['reason'],now)
        if ack['accepted'] and action.get('safety_action'):
            try:
                trial.dialogue.apply(cid,action['safety_action'],now)
                if action['safety_action'].get('kind')!='continue':executive.own_protocol[rid]={k:v for k,v in action['safety_action'].items() if k not in ('peer_go_ref','proposal_message_id')}
            except (ValueError,KeyError) as exc:
                executive.record(event='safety_refusal',robot_id=rid,sim_s=now,reason=str(exc))
                executive.planners[rid].feedback(value,'refused',str(exc),now)
                executive.active.pop(rid,None)
                ack['accepted']=False
        if ack['accepted']:executive.late_attempts.pop(rid,None)
        executive.pending.pop(cid,None)
    trial.scheduler.on_action=release
    original_step=executive.tr.step if hasattr(executive.tr,'step') else None
    if original_step is not None:
        def step(now):
            holds=executive.holds;executive.holds=[]
            return holds+original_step(now)
        executive.tr.step=step
    # Existing event_v1 compares own changes and actual channel facts. Keep
    # protocol identifiers out of the task planner admission state as well.
    previous_state=trial.call_state
    def state(rid,now):
        own,unused,inbox=previous_state(rid,now)
        text=[dict(e,body={'text':(e.get('body') or {}).get('text','')}) for e in inbox]
        history=executive.planners[rid].memory
        last=history[-1] if history else None
        local_body=getattr(executive.body,'memory',{}).get(rid)
        from harness.e2e_task_planner_wire import read_vote,read_status,read_route
        safety=[e['message_id'] for e in text if read_vote(e['body']['text']) or read_status(e['body']['text']) or read_route(e['body']['text'])]
        return own,dict(last_act_result=copy.deepcopy(last),channel_safety_event=safety[-4:],
            own_execution_stage=list(local_body.key) if local_body is not None and local_body.key else None,
            own_protocol_command=executive.own_protocol.get(rid),
            own_proposable_route=unused.get('proposable_route'),
            own_safety=executive.last_edges.get(rid),own_event=executive.event_stamp.get(rid)),text
    trial.call_state=state
    def observe(now):
        executive.tick(now)
        for rid,p in executive.planners.items():
            local=[e for e in p.events if e['kind']!='partner_message']
            if local:executive.event_stamp[rid]=copy.deepcopy(local[-1])
        for rid in trial.actors:
            current=state(rid,now)
            from harness.e2e_dialogue_call_policy import digest
            key=digest(current[:2])
            if getattr(trial,'_call_state_edges',{}).get(rid)!=key:
                if not hasattr(trial,'_call_state_edges'):trial._call_state_edges={}
                trial._call_state_edges[rid]=key;trial.scheduler.trigger(rid,'report',at=now)
    trial.observe_events=observe
    return executive


def progress(trial,now):
    from collections import Counter
    executive=getattr(trial,'task_planner',None)
    if executive is None:return None
    rows=[r for r in executive.rows if r.get('event')=='task_decision']
    usage=trial.token_progress(now) if hasattr(trial,'token_progress') else {}
    requests=len(trial.send_ledger.entries)
    model_requests=requests if executive.mode=='gemma_v1' else 0
    return dict(mode=executive.mode,sim_s=now,decision_events=len(rows),http_requests=requests,
        model_requests=model_requests,model_request_cap=300,
        call_cap_expected_sim_s=300*now/requests if requests and now else None,
        token_progress=usage,act_distribution=dict(Counter((r['result']['decision'] or {}).get('act','refused') for r in rows)),
        fallback_decisions=sum(r['result']['fallback'] for r in rows),
        executed_act_distribution=dict(Counter(r['decision']['act'] for r in executive.rows if r.get('event')=='act_started')),
        basis='actual ledger requests and task decisions; HTTP attempts include repair/errors; rule arm makes zero provider calls')
