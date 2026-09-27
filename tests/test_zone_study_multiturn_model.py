"""Seeded differential state-machine properties (3,000 streams by default).

The oracle is a standalone Python execution spec, not a copy/subclass of v64.
The second oracle is the hash-checked frozen v64 for no_comm byte comparisons.
CI randomness is fixed; a failure prints its reproducible integer seed.
"""
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from harness import zone_event_scheduler as core
from harness import zone_study_integration as zi
from harness.zone_send_ledger import send
from harness.zone_sim_cost import CostParams
from harness.zone_study_decisions import DecisionScheduler, DecisionLimits
from tests.test_zone_study_multiturn import offline_only  # noqa: F401
from tests.test_zone_study_multiturn_properties import v64  # noqa: F401
from tests.zone_multiturn_reference import ACTORS, U, generated_case, reference, stamp


def number(cid):
    return int(cid.split('-')[1]) if cid else 0


def actual(spec, *, messages=True, frozen=None):
    busy = dict.fromkeys(ACTORS, False)
    snapshots, sends = [], []

    class Wire(core.ReplayTransport):
        def emit(self, call):
            send(call.http_open)
            sends.append((number(call.call_id), stamp(s.clock)))

        def submit(self, call):
            snapshots.append((number(call.call_id), call.actor, stamp(call.started_sim_s),
                              tuple(e['message_id'] for e in s.inbox(call.actor))))
            outcome, extra, immediate = spec.response(call.actor, stamp(call.started_sim_s))
            if outcome == 'snapshot':
                raise OSError('snapshot sends nothing')
            if extra:
                call.reserve(extra)
            if immediate and outcome != 'refund':
                self.emit(call)
            return call

        def reply(self, call):
            outcome, _, _ = spec.response(call.actor, stamp(call.started_sim_s))
            if outcome == 'refund':
                raise core.NotSent('prepared reservation returned before wire')
            if not self.send_ledger.sends(call.call_id):
                self.emit(call)
            return core.CallReply(attempts=(core.Attempt(outcome=outcome),), action='noop')

    class Driver(frozen or DecisionScheduler):
        # Only external own-job event production differs from the real runner.
        # Every call/refund/retry/budget transition is inherited unmodified.
        def _on_observe(self, payload):
            kind = payload.get('external')
            if kind:
                busy[payload['actor']] = kind == 'busy'
                if kind == 'boundary' and not frozen:
                    self.available(payload['actor'], at=self.clock)
            else:
                super()._on_observe(payload)

    policy = core.CallPolicy(min_interval_s=spec.interval / U, max_retries=spec.retries,
                             max_attempts_total=spec.total, max_http_attempts_per_actor=spec.per_actor,
                             max_calls_per_actor=spec.calls, idle_reask_s=spec.reask / U,
                             busy_reask_s=spec.reask / U)
    kwargs = {} if frozen else dict(own_job=lambda a: busy[a],
                                    decision_limits=DecisionLimits(max_calls_total=spec.total))
    # own_job uses None for idle, as the real executor API does.
    if not frozen:
        kwargs['own_job'] = lambda a: {'job': 'own'} if busy[a] else None
    wire = Wire({})
    s = Driver(wire, policy=policy, cost_params=CostParams(input_token_s=0., output_token_s=0.,
                                                          timeout_s=.5), **kwargs)
    trial = SimpleNamespace(scheduler=s, transport=SimpleNamespace(budget_exhausted=False),
                            actors=ACTORS, policy=policy, horizon_s=spec.horizon,
                            links={a: SimpleNamespace(job=lambda a=a: {'own': True} if busy[a] else None)
                                   for a in ACTORS})
    trial.decision_budget_spent = lambda: zi.IntegratedTrial.decision_budget_spent(trial)

    def action(actor, command, at):
        cid = next(r.call_id for r in reversed(s.calls) if r.actor == actor)
        if frozen:
            if s.metrics[actor]['calls'] < policy.max_calls_per_actor and at + spec.reask / U <= spec.horizon:
                s.arm_reask(actor, 'timer' if busy[actor] else 'idle', at=at + spec.reask / U)
        elif s.call_causes[cid]['cause'] == 'common':
            zi.IntegratedTrial._arm_reask(trial, actor, at)
    s.on_action = action
    for index, (at, kind, actor) in enumerate(spec.events):
        if kind == 'message' and messages:
            s._push('message', at, (0., ACTORS.index(actor), 0, 0), {
                'message_id': f'm{index}', 'call_id': 'external-peer', 'sender': 'r3' if actor != 'r3' else 'r1',
                'recipient': actor, 'recipients': (actor,), 'encoding': 'free_ko',
                'body': {'text': '사건열 시험'}, 'broadcast': False, 'reply_to': None,
                'sent_sim_s': 0., 'slot': 0})
        elif kind == 'common':
            s.timer(actor, at=at)
        elif kind in ('busy', 'boundary'):
            s._push('observe', at, (0., ACTORS.index(actor), 0, 0), {'actor': actor, 'external': kind})
    s.arm_observations(('r1',), period_s=.1, first_at=.1)
    s.run(until_s=spec.horizon)
    if frozen:
        return s, snapshots, sends
    rows = []
    for cid, row in s.ledger.items():
        rows.append((number(cid), row['actor'], stamp(row['started_sim_s']),
                     row.get('scheduling_lane', ''), number(row['retry_of']), row['trigger'], row['status'],
                     stamp(row['finished_sim_s']), s.send_ledger.sends(cid), row['reserved_attempts']))
    result = dict(calls=rows, sends=sends,
                  refunds=[(number(r['call_id']), stamp(r['sim_s']), r['refunded']) for r in s.unsent_calls],
                  snapshots=snapshots,
                  retries=sorted((r.cause, number(r.call_id), n) for r, n in s._retries.items()),
                  inputs=[(e.tags[0], e.active, number(e.claimed_by), number(e.retry_of),
                           stamp(e.available_at) if e.available_at != float('inf') else float('inf'))
                          for e in s.event_inputs],
                  end_reason=zi.IntegratedTrial.decision_end_reason(trial))
    assert not s.send_violations
    assert s.budget.outstanding() == 0
    assert s.budget.used_total() == s.send_ledger.sends() <= spec.total
    assert all(n <= spec.per_actor for n in s.budget.used.values())
    assert all(s.budget.call_count(a) == s.metrics[a]['calls'] <= spec.calls for a in ACTORS)
    for cid, cause in s.call_causes.items():
        if cause['retry_of']:
            assert s.call_causes[cause['retry_of']]['cause'] == cause['cause']
        assert s.ledger[cid]['started_sim_s'] <= spec.horizon
    return result, s


@pytest.mark.parametrize('seed', range(3000))
def test_generated_stream_matches_independent_reference(seed):
    spec = generated_case(seed)
    expected = reference(spec)
    observed, _ = actual(spec)
    assert observed == expected, (seed, spec)


def common_rows(s):
    lookup = {cid: (r['actor'], r['started_sim_s']) for cid, r in s.ledger.items()}
    return [(r['actor'], r['started_sim_s'], r['trigger'], lookup.get(r['retry_of']))
            for cid, r in s.ledger.items() if s.call_causes[cid]['cause'] == 'common']


@pytest.mark.parametrize('seed', range(200))
def test_generated_no_comm_bytes_and_additive_common_schedule(v64, seed):
    spec = generated_case(seed)
    _, baseline = actual(spec, messages=False)
    old, _, _ = actual(spec, messages=False, frozen=v64.event_scheduler)
    encode = lambda x: json.dumps(x, sort_keys=True, ensure_ascii=False).encode()
    for get in (lambda s: s.ledger, lambda s: s.trace(), lambda s: s.budget.to_dict(),
                lambda s: s.metrics, lambda s: s.censored):
        assert encode(get(baseline)) == encode(get(old)), seed
    # Under a binding shared budget, extra sends can exhaust it earlier. Compare
    # until either run refuses admission. Condition encodings are exercised by
    # the real integration properties and all review5/review6 chain fixtures.
    _, talking = actual(spec)
    cutoff = min((e['sim_s'] for s in (baseline, talking) for e in s.events
                  if e['kind'] == 'call_refused'), default=float('inf'))
    assert [r for r in common_rows(talking) if r[1] < cutoff] == [
        r for r in common_rows(baseline) if r[1] < cutoff], seed


def test_reporting_counters_cannot_change_account_or_end_reason():
    _, s = actual(replace(generated_case(0), events=(), horizon=.1, total=90))
    trial = SimpleNamespace(scheduler=s, transport=SimpleNamespace(budget_exhausted=False))
    trial.decision_budget_spent = lambda: zi.IntegratedTrial.decision_budget_spent(trial)
    for row in s.metrics.values():
        row['budget_refused'] = row['calls'] = 10000
    assert not s.budget.exhausted()
    assert zi.IntegratedTrial.decision_end_reason(trial) == 'sim_horizon'


@pytest.mark.parametrize('fault,seed', [('lineage', 30), ('timer', 1235), ('termination', 1), ('merged', 479)])
def test_reference_detects_review6_mutations(monkeypatch, fault, seed):
    """The independent oracle must reject the three old defects, not bless them."""
    if fault == 'lineage':
        original = core.EventScheduler._restore_inputs
        def mutate(self, call):
            if not call.scheduling_lane and call.retry_of:
                for source in call.event_inputs:
                    if not source.retry_root:
                        source.retry_root = call.retry_root
            original(self, call)
        monkeypatch.setattr(core.EventScheduler, '_restore_inputs', mutate)
    elif fault == 'merged':
        original = core.EventScheduler._retry
        def mutate(self, call, cost):
            call.event_roots = tuple((e, call.retry_root) for e, root in call.event_roots)
            original(self, call, cost)
        monkeypatch.setattr(core.EventScheduler, '_retry', mutate)
    elif fault == 'timer':
        original = zi.IntegratedTrial._arm_reask
        def mutate(self, actor, at):
            if self.scheduler.budget.remaining(actor) == 0:
                return
            original(self, actor, at)
        monkeypatch.setattr(zi.IntegratedTrial, '_arm_reask', mutate)
    else:
        original = zi.IntegratedTrial.decision_end_reason
        def mutate(self):
            if any(m['budget_refused'] for m in self.scheduler.metrics.values()):
                return 'budget_exhausted'
            return original(self)
        monkeypatch.setattr(zi.IntegratedTrial, 'decision_end_reason', mutate)
    spec = generated_case(seed)
    try:
        observed, _ = actual(spec)
    except AssertionError:
        return  # cause-typed roots reject a cross-cause retry at construction
    assert observed != reference(spec), (fault, seed)
