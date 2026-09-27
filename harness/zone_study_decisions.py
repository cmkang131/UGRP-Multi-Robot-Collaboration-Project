"""v64 common scheduling with a separate, additive received-message lane.

Common queue entries are never inspected for merging, removed or relabelled.
Both lanes call EventScheduler's eligibility/retry/settlement implementation;
only the message lane waits for an own-job boundary. Budgets remain shared.
"""
from dataclasses import asdict, dataclass

from harness.zone_event_scheduler import EventScheduler
from harness.zone_sim_cost import quantize

DECISION_POLICY = 'v64_common_additive_messages.v3'
MESSAGE_LANE = 'message'


@dataclass(frozen=True)
class DecisionLimits:
    max_calls_total: int = 90
    max_utterances_per_actor: int = 2
    max_utterances_total: int = 6

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) is not int or value < 1:
                raise ValueError(f'{name} must be a positive integer')


class DecisionScheduler(EventScheduler):
    """Messages cannot mutate the v64 common eligibility state.

    One message call may overlap a later common call: otherwise an unsolicited
    delivery could delay an unforeseen common event. The outstanding limit is
    per lane; a message call itself waits for all existing calls. Global send
    and episode limits still stop both lanes. Common-schedule comparisons must
    hold external events/replies fixed and stop at a shared budget boundary.
    """

    def __init__(self, *args, own_job, decision_limits, external_budget_spent=lambda: False, **kwargs):
        super().__init__(*args, **kwargs)
        self.own_job = own_job
        self.decision_limits = decision_limits
        self.external_budget_spent = external_budget_spent
        self.decision_events = []
        self.call_causes = {}
        self._message_waiting = {}
        self._message_serial = 0

    def calls_spent(self):
        return self._calls_started >= self.decision_limits.max_calls_total

    def _push(self, kind, at, tie, payload):
        if kind == 'call_start' and (payload['trigger'] == 'report'
                                     or payload.get('scheduling_lane') == MESSAGE_LANE):
            actor = payload['actor']
            if '_message_token' not in payload:
                retry = payload.get('retry_of', '')
                ids = (self.call_causes[retry]['message_ids'] if retry else
                       [self.inboxes[actor][-1]['message_id']] if self.inboxes[actor] else [])
                if not ids:
                    return  # a label without an actual delivery is not a message cause
                held = self._message_waiting.get(actor)
                if held:
                    held['message_ids'] = sorted(set(held['message_ids']) | set(ids))
                    # Only messages merge. Keep a failed message call's retry root.
                    if retry:
                        held.update(trigger=payload['trigger'], retry_of=retry)
                    payload = held
                else:
                    self._message_serial += 1
                    payload = {**payload, 'scheduling_lane': MESSAGE_LANE,
                               '_message_token': self._message_serial, 'message_ids': list(ids)}
                    self._message_waiting[actor] = payload
            # All common starts at this instant run first, regardless of enqueue order.
            tie = (1., self._rank[actor], 0, 0)
            payload = dict(payload)
        super()._push(kind, at, tie, payload)

    def own_job_boundary(self, actor, *, at):
        """Wake only the message lane, including boundaries with no common trigger."""
        held = self._message_waiting.get(actor)
        if held:
            self._push('call_start', at, (1., self._rank[actor], 0, 0), held)

    def _on_call_start(self, payload):
        actor = payload['actor']
        if payload.get('scheduling_lane') == MESSAGE_LANE:
            held = self._message_waiting.get(actor)
            if not held or held['_message_token'] != payload['_message_token']:
                return  # already consumed by a common snapshot or another message call
            payload = dict(held)
            job = self.own_job(actor)
            if job is not None or self._outstanding(actor) or self._outstanding(actor, MESSAGE_LANE):
                self.metrics[actor]['deferred'] += 1
                self.decision_events.append({'sim_s': self.now(), 'actor': actor,
                    'event': 'deferred_own_job' if job else 'deferred_call',
                    'triggers': [payload['trigger']], 'message_ids': payload['message_ids'],
                    'job_id': (job or {}).get('job_id')})
                return
            # A message follows the existing common call's minimum interval,
            # but its own start must never change the common last-start clock.
            last = max(self._last_start.get(actor, float('-inf')),
                       self._last_start.get((actor, MESSAGE_LANE), float('-inf')))
            if last != float('-inf'):
                earliest = quantize(last + self.policy.min_interval_s, self.params.quantum_s)
                if earliest > self.clock + 1e-9:
                    self._push('call_start', earliest, (1., self._rank[actor], 0, 0), payload)
                    return
        if self.calls_spent() or self.external_budget_spent():
            reason = 'episode_call_cap' if self.calls_spent() else 'pilot_budget_exhausted'
            self.metrics[actor]['budget_refused'] += 1
            self._log(f"call_refused {actor} {payload['trigger']} {reason}",
                      kind='call_refused', actor=actor)
            self.decision_events.append({'sim_s': self.now(), 'actor': actor,
                                         'event': reason, 'triggers': [payload['trigger']]})
            return
        # No queue surgery, eager merge, deferred-pop, or trigger priority override.
        super()._on_call_start(payload)

    def _submit(self, call):
        # This is the actual snapshot boundary, after the core's outstanding,
        # interval and budget gates. Refused/deferred common events consume nothing.
        held = self._message_waiting.pop(call.actor, None)
        ids = list(held['message_ids']) if held else []
        cause = 'message' if call.scheduling_lane == MESSAGE_LANE else 'common'
        if cause == 'message' and not ids:
            raise AssertionError('additive call requires unconsumed delivered messages')
        if ids and cause == 'common':
            call.merged = tuple(sorted(set(call.merged) | {'report'}))
            self.ledger[call.call_id]['merged_triggers'] = call.merged
        self.call_causes[call.call_id] = {'cause': cause, 'message_ids': ids,
                                         'retry_of': call.retry_of}
        try:
            sent = super()._submit(call)
        except BaseException:
            if held:
                self._message_waiting[call.actor] = held
            raise
        if not sent and held:
            self._message_waiting[call.actor] = held
        if sent:
            if ids and cause == 'common':
                self.metrics[call.actor]['merged_triggers'] += 1
            self.decision_events.append({'sim_s': self.now(), 'actor': call.actor,
                'event': 'decision_started', 'call_id': call.call_id,
                'triggers': sorted({call.trigger, *call.merged}),
                'job_id': (self.own_job(call.actor) or {}).get('job_id'),
                **self.call_causes[call.call_id]})
        return sent

    def _resume_deferred(self, call):
        # The core settles both charged call_done and pending 0-send refunds
        # here. Hooking only call_done strands messages after pre-wire failures.
        # Keep the v64 common wake first; the additive lane still checks its
        # own-job boundary, outstanding calls, interval and shared budgets.
        super()._resume_deferred(call)
        self.own_job_boundary(call.actor, at=self.clock)
