"""Default-off explicit OwnRoute syntax and bounded fresh pre-epoch reasks."""
import copy

OPTION='envelope_retry_v1'


def prompt(body,system):
    # This is a syntax example using only the actor's already validated proposal.
    # It is not a selected action, a received peer message, or an approval.
    proposal=body.get('own_route_proposal')
    if proposal is not None:
        body['route_contract_example']=copy.deepcopy(proposal)
    system+=' Return compact one-line JSON. When proposing, contract is the ENTIRE own_route_proposal object, including kind="OwnRoute", route, and source_message_id; never copy only own_route_proposal.route. decision_sources may contain only order_sheet, own_rgb, own_commands, own_belief, message; own_map_summary is represented by own_belief. An invalid response is rejected and causes no action or message.'
    return system


class Recovery:
    def __init__(self):
        self.examined=set();self.counts={};self.events=[]

    def poll(self,trial,now):
        scheduler=trial.scheduler;dialogue=trial.dialogue
        for call in list(scheduler.calls):
            entry=scheduler.ledger[call.call_id]
            if call.call_id in self.examined or entry['status']=='outstanding':continue
            self.examined.add(call.call_id)
            context=dialogue.captures.get(call.call_id)
            if (not context or entry['status']!='failed' or call.notes.get('send_violation')
                or (entry.get('completion') or {}).get('finish_reason')!='stop'
                or call.actor not in ('r1','r2') or context['view']['key'] is not None
                or dialogue.key is not None):continue
            old=context['state'].get('own_route')
            old_hash=old.get('route_hash') if old else context['view']['route_hash']
            current=trial.links[call.actor].inner.own_inputs_at(now).get('own_route')
            view=dialogue.view(call.actor,now)
            current_hash=current.get('route_hash') if current else view['route_hash']
            if old_hash is None or old_hash!=current_hash or view['own_claim']:continue
            key=(call.actor,old_hash,view['approved'])
            if self.counts.get(key,0)>=2:continue
            self.counts[key]=self.counts.get(key,0)+1
            scheduler.trigger(call.actor,'report',at=now+2.)
            self.events.append(dict(robot_id=call.actor,route_hash=old_hash,
                invalid_call_id=call.call_id,at=now,reask_at=now+2.,attempt=self.counts[key],
                accepted_action_replayed=False,transport_retry=False))
