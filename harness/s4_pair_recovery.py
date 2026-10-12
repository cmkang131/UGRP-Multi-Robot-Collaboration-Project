"""Default-off S4 recovery. Own request/state only; no simulator inputs."""
import copy
from harness import s4_pair_stage as pair


class Driver(pair.Driver):
    def __init__(self, *args, go_ack_retry=False, **kwargs):
        super().__init__(*args, **kwargs)
        if type(go_ack_retry) is not bool:
            raise ValueError('go_ack_retry must be bool')
        self.go_ack_retry = go_ack_retry
        self.retry_used, self.examined = set(), set()
        self.retry_events = []

    def poll(self, now):
        if self.go_ack_retry and not self.handshake.failure and not self.host.failed:
            rel = now-self.host.links['r1'].origin_s
            trial = self.host.trial
            for call in trial.scheduler.calls:
                if call.call_id in self.examined:
                    continue
                self.examined.add(call.call_id)
                entry = trial.scheduler.ledger[call.call_id]
                snap = trial.pair_snapshots.get(call.call_id, {})
                seen = snap.get('seen', {})
                # No transport/quota/non-normal-completion retry. Only a normal
                # response discarded during the captured GO/ACK window.
                completion = entry.get('completion') or {}
                if (entry['status'] != 'failed' or call.notes.get('send_violation')
                        or completion.get('finish_reason') != 'stop'
                        or seen.get('phase') != 'wait_go' or call.actor not in pair.hs.PAIR):
                    continue
                choice = 'go' if not seen['own_go_sent'] else 'ack_go'
                key = (seen['epoch'], choice)
                once = (call.actor, seen['epoch'])  # one retry total per robot/epoch
                current = self.handshake.view(call.actor, rel)
                own = self.handshake.own.get(call.actor, {})
                if (once in self.retry_used or self.ask_keys.get(call.actor) != key
                        or current['phase'] != 'wait_go' or current['epoch'] != seen['epoch']
                        or rel >= own.get('opened', -float('inf'))+pair.hs.HANDSHAKE_S
                        or (current['own_go_sent'] if choice == 'go' else current['own_ack_sent'])):
                    continue
                self.retry_used.add(once)
                self.ask_keys.pop(call.actor, None)
                self.retry_events.append(dict(robot_id=call.actor, epoch=seen['epoch'], choice=choice,
                    invalid_call_id=call.call_id, at=rel, same_epoch=True,
                    accepted_action_replayed=False, transport_retry=False))
        return super().poll(now)


def settle_without_commands(host, at):
    """Close stopped calls without running events or starting an unsent POST.

    The scheduler's charged call_done payloads retain real usage. Pending
    unsent snapshots are refunded first, then the existing censor routine only
    sees responses already fetched. Delivered channel edges remain untouched.
    """
    if host.finished:
        return getattr(host, 'terminal_settlement', None)
    trial = host.trial
    scheduler = trial.scheduler
    before = dict(sends=trial.send_ledger.sends(), actions=len(trial.actions),
                  deliveries=len(scheduler.messages), dispatch=len(trial.dispatch_log))
    cancelled = []
    for cid, call in list(scheduler._pending.items()):
        if scheduler.send_ledger.sends(cid):
            # This single-thread transport resolves synchronously. A sent call
            # must already be a charged queued reply, never fetched again here.
            raise RuntimeError('sent pending call lacks cached response; preserve ledger')
        scheduler.ledger[cid]['unsent'] = dict(stage='terminal', error='STOPPED_BEFORE_SEND')
        scheduler.ledger[cid]['sends_closed'] = True
        scheduler._release_unsent(call)
        scheduler._pending.pop(cid, None)
        cancelled.append(cid)
    scheduler._censor_outstanding(max(float(at), scheduler.clock))
    scheduler._queue.clear()
    scheduler._deferred.clear()
    scheduler._thinking.clear()
    trial._collect()
    after = dict(sends=trial.send_ledger.sends(), actions=len(trial.actions),
                 deliveries=len(scheduler.messages), dispatch=len(trial.dispatch_log))
    if before != after:
        raise RuntimeError('terminal settlement released work')
    host.finished = True
    host.terminal_settlement = dict(at=at, before=before, after=after,
        unsent_cancelled=cancelled, censored=copy.deepcopy(scheduler.censored),
        channel=trial.channel_summary(), outstanding=sum(
            e['status'] == 'outstanding' for e in scheduler.ledger.values()),
        commands_released=0, research_result=False)
    return host.terminal_settlement
