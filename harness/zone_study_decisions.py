"""Own-job decision opportunities for the integrated study; no physics or model I/O.

The legacy offline scheduler is unchanged. Message re-decisions wait for the
own job boundary; start and own safety events retain their common eligibility.
One deferred set per robot coalesces messages/timers while work continues.
"""
from dataclasses import asdict, dataclass
import heapq

from harness.zone_event_scheduler import EventScheduler, TRIGGERS

DECISION_POLICY = 'own_job_boundary_multiturn.v1'


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
    """Keep the core's SIM ordering, send ledger, retries and HTTP budget gates.

Only the integration's eligibility changes. A terminal own-executor event
already queues its common trigger. It consumes the one deferred set when the
job is gone, including report, rather than creating a second decision chain.
Accepted utterance limits are enforced by the existing protocol, not here.
"""

    def __init__(self, *args, own_job, decision_limits, external_budget_spent=lambda: False, **kwargs):
        super().__init__(*args, **kwargs)
        self.own_job = own_job
        self.decision_limits = decision_limits
        self.external_budget_spent = external_budget_spent
        self.decision_events = []

    def calls_spent(self):
        return self._calls_started >= self.decision_limits.max_calls_total

    def _on_call_start(self, payload):
        actor = payload['actor']
        payload = dict(payload)
        labels = {payload['trigger'], *payload.get('merged', ())}
        # Deliveries, completion and timers at one instant are ONE opportunity.
        # Leave retries with their own retry lineage to the core scheduler.
        same = [e for e in self._queue if e.kind == 'call_start' and e.at == self.clock
                and e.payload['actor'] == actor and not e.payload.get('retry_of')]
        for event in same:
            labels.update((event.payload['trigger'], *event.payload.get('merged', ())))
        if same:
            ids = {e.seq for e in same}
            self._queue = [e for e in self._queue if e.seq not in ids]
            heapq.heapify(self._queue)
        # Outstanding calls still use the core's single deferred set. Never
        # consume it before the snapshot of the next actual call.
        held = self._deferred.pop(actor, None)
        if held:
            labels.update((held['trigger'], *held['merged']))
        best = max(labels, key=lambda t: (TRIGGERS[t], t))
        payload.update(trigger=best, merged=tuple(sorted(labels - {best})))
        job = self.own_job(actor)
        if (job is not None and 'report' in labels
                and not labels.intersection({'start', 'failure', 'blockage', 'timeout'})):
            self._defer(actor, best, payload['merged'], 'own_job_boundary')
            self.decision_events.append({'sim_s': self.now(), 'actor': actor,
                                         'event': 'deferred_own_job', 'triggers': sorted(labels),
                                         'job_id': job.get('job_id'), 'job_kind': job['kind']})
            return
        if self.calls_spent() or self.external_budget_spent():
            reason = 'episode_call_cap' if self.calls_spent() else 'pilot_budget_exhausted'
            self.metrics[actor]['budget_refused'] += 1
            self._log(f'call_refused {actor} {best} {reason}', kind='call_refused', actor=actor)
            self.decision_events.append({'sim_s': self.now(), 'actor': actor,
                                         'event': reason, 'triggers': sorted(labels)})
            return
        before = self._calls_started
        super()._on_call_start(payload)
        if self._calls_started > before:
            self.decision_events.append({'sim_s': self.now(), 'actor': actor, 'event': 'decision_started',
                                         'call_id': f'call-{self._calls_started:04d}-{actor}',
                                         'triggers': sorted(labels), 'job_id': (job or {}).get('job_id')})
