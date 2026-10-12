"""Default-off model-facing phase instructions and finite no-progress reminders."""
import copy
OPTION='stage_retry_v1'
WORKFLOW='configs/simulation_workflows.d/e2e18_v228.json'


def phase(actor,view,own_route=None):
    if actor not in ('r1','r2') or view['key'] is not None or view['own_claim']:return None
    rh=(own_route or {}).get('route_hash') or view['route_hash']
    if not rh:return None
    if view['approved']:return ('claim',rh)
    if actor=='r1' and view['proposal_message_id'] is None:return ('propose',rh)
    if actor=='r2' and view['proposal_message_id'] is not None:return ('approve',rh)
    return None


def prompt(body,system):
    proposal=body.get('own_route_proposal');view=body['dialogue']
    current=phase(body['robot_id'],view,proposal['route'] if proposal else None)
    if current:
        step,rh=current
        action={'kind':'continue'}
        if step=='claim':action=dict(kind='claim',order_id='order-5',destination_zone='B',role=body['task']['fixed_roles'][body['robot_id']])
        if step=='approve':action=dict(kind='approve_route',route_hash=rh,proposal_message_id=view['proposal_message_id'])
        body['current_protocol_step']=dict(step=step,action_syntax=action,
            instruction={'propose':'Send the whole own_route_proposal as a message contract to the permitted peer.',
            'approve':'Review the actually received route proposal. If accepting it, use this approve_route action and include message as a decision source.',
            'claim':'The route is already approved. To participate, claim your assigned role now. Repeating approve_route does not claim the role.'}[step],
            evidence_scope='Protocol status only. This does not certify a safe grip, map accuracy, or task success. Continue is permitted if you decline or remain uncertain.')
        system+=' Follow current_protocol_step using the actual current evidence. The syntax object describes the required fields, not an already accepted action. Once approved, each robot must claim its own fixed role to start approaching; do not repeat approve_route.'
    return system


class Reminders:
    def __init__(self):self.states={};self.events=[]
    def poll(self,trial,now):
        for rid in ('r1','r2'):
            view=trial.dialogue.view(rid,now)
            from harness.e2e_event_projection import route_for_events
            route=route_for_events(trial,rid,now)
            key=phase(rid,view,route)
            if key is None:self.states.pop(rid,None);continue
            state=self.states.get(rid)
            if state is None or state['key']!=key:
                self.states[rid]=dict(key=key,due=now+12.,count=0);continue
            calls=[c for c in trial.scheduler.calls if c.actor==rid]
            if not calls or state['count']>=3 or now<state['due']:continue
            rows=[trial.scheduler.ledger[c.call_id] for c in calls]
            if any(x['status']=='outstanding' for x in rows):continue
            latest=rows[-1]
            if latest['status']!='done' or (latest.get('completion') or {}).get('finish_reason')!='stop':continue
            state['count']+=1;state['due']=now+12.
            trial.scheduler.trigger(rid,'report',at=now)
            self.events.append(dict(robot_id=rid,phase=key[0],route_hash=key[1],at=now,
                reminder=state['count'],model_decision_required=True,accepted_action_replayed=False))


def compose(bundle,option):
    if option=='off':return ()
    if option!=OPTION or bundle['execution_bundle_id']!='e2e18-v227':raise ValueError('PROTOCOL_PROGRESS_REQUIRES_V227')
    bundle['e2e_options']['protocol_progress']=option
    bundle.update(schema='ugrp.e2e_ownmap_live.v228',execution_bundle_id='e2e18-v228',workflow_version='7.121.0')
    return (WORKFLOW,)
