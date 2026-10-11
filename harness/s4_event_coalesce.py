"""Own-event batching; no cached action/GO/visual judgement is ever replayed.

An executing action's progress is telemetry, not a fresh high-level decision.
Delivered messages stay in the scheduler inbox and are read together at the
next decision boundary, or after at most 30 SIM seconds. This changes dialogue
timing and therefore belongs to a separate, default-off DEV cohort.
"""
import copy


class Coalescer:
    MAX_MESSAGE_WAIT_S = 30.
    REQUIRED = frozenset(('initial_claim', 'go_ack_epoch', 'decision_window',
                          'own_observation_abnormal', 'bounded_invalid_retry', 'phase_done'))

    def __init__(self):
        # Local import avoids a dependency cycle with the live adapter.
        from harness.s4_event_policy import Events
        self.edges = Events()
        self.pending = {}
        self.message_since = {}
        self.trace = []

    def observe(self, actor, payload, *, force=()):
        reasons = self.edges.observe(actor, payload)
        now = float(payload.get('sim_time_s', 0))
        if 'received_message' in reasons:
            self.message_since.setdefault(actor, now)
        pending = self.pending.setdefault(actor, set())
        pending.update(r for r in reasons if r in self.REQUIRED)
        pending.update(force)
        since = self.message_since.get(actor)
        if since is not None and now - since >= self.MAX_MESSAGE_WAIT_S:
            pending.add('inbox_max_wait')
        selected = sorted(pending)
        self.trace.append(dict(robot=actor, sim_s=now, observed=reasons,
                               selected=selected, message_since=since))
        return selected

    def acknowledge(self, actor):
        self.pending.pop(actor, None)
        self.message_since.pop(actor, None)

    def next_message_at(self, actor):
        since = self.message_since.get(actor)
        return float('inf') if since is None else since + self.MAX_MESSAGE_WAIT_S


def install(trial):
    """Gate before scheduler reservation/snapshot; retain its durable inbox lane.

    Delayed/unsent starts do not acknowledge an event. The scheduler still owns
    budgets, failure retries, pending-call merging, and all message delivery.
    """
    scheduler = trial.scheduler
    trial.coalescer = Coalescer()
    original = scheduler._on_call_start

    def start(event):
        actor = event['actor']
        if actor in scheduler.holding():
            return original(event)
        now = scheduler.clock
        link = trial.links[actor]
        view = trial.handshake.view(actor, now) if actor in ('r1', 'r2') else {}
        adapter = link.stop_adapter
        window, belief = None, None
        if adapter is not None:
            view['own_executor_phase'] = getattr(adapter.controller(), 'state', None)
            window = adapter.window.snapshot(now)
            belief = adapter.own_belief(now + adapter.origin_s)
        payload = dict(pair_handshake=view, decision_window=window, own_belief=belief,
                       sim_time_s=now, inbox=list(scheduler.inbox(actor)),
                       s4_round={'previous_rejection': trial.epoch_retry_context.get((actor, view.get('epoch')))})
        # Failures and explicit reinspection/door/solo departure events bypass
        # batching, as do scheduler-owned bounded transport retries.
        force = set(trial.coalesce_forced.pop(actor, ()))
        if event['trigger'] in ('failure', 'blockage', 'timeout', 'retry') or event.get('retry_of'):
            force.add('explicit_failure_or_retry')
        reasons = trial.coalescer.observe(actor, payload, force=force)
        if not reasons:
            if event.get('scheduling_lane'):
                until = trial.coalescer.next_message_at(actor)
                for source in event.get('event_inputs', ()):
                    if source.active:
                        source.available_at = until
                return original(event)
            return None
        count = scheduler._calls_started
        result = original(event)
        if scheduler._calls_started > count:
            trial.coalescer.acknowledge(actor)
        return result

    scheduler._on_call_start = start
