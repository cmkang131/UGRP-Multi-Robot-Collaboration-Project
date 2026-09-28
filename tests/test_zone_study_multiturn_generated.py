"""1,000 finite generated schedules, default 30/90 caps and pre-wire faults.

Uses the actual frozen v64 scheduler as oracle, the actual ledger and a scripted
wire. Randomness depends on time/actor/stage, never call IDs or conditions.
"""
import hashlib
import json
import random

import pytest

from harness import zone_event_scheduler as core
from harness.zone_study_decisions import DecisionScheduler, DecisionLimits
from tests.test_zone_study_multiturn import offline_only  # noqa: F401
from tests.test_zone_study_multiturn_properties import v64  # noqa: F401
from tests.test_zone_study_multiturn_exits import deliver


def generated(seed, scheduler_type):
    rng = random.Random(2454000 + seed)
    faults = {(rng.choice(core.DEFAULT_ACTORS), round(rng.randrange(0, 250) * 2.1, 6)):
              rng.choice(('start', 'submit', 'snapshot', 'wire_before')) for _ in range(40)}
    # Every stage appears as the initial failure in one quarter of the seeds.
    faults[('r1', 0.)] = ('start', 'submit', 'snapshot', 'wire_before')[seed % 4]
    snapshots, actions, injected = [], [], []
    class Wire(core.ReplayTransport):
        def submit(self, call):
            point = (call.actor, call.started_sim_s)
            stage = faults.get(point)
            if stage in ('start', 'submit'):
                injected.append((point, stage))
                raise OSError('generated failure at ' + stage)
            if stage == 'snapshot':
                injected.append((point, stage))
                raise ValueError('generated input snapshot failure')
            # An input is a fixture digest of exactly the information available
            # at this boundary, independent of the oracle implementation.
            snapshots.append({'id': call.call_id, 'actor': call.actor, 'at': call.started_sim_s,
                              'inbox': self.scheduler.inbox(call.actor)})
            return super().submit(call)
        def reply(self, call):
            if faults.get((call.actor, call.started_sim_s)) == 'wire_before':
                injected.append(((call.actor, call.started_sim_s), 'wire_before'))
                raise core.NotSent('generated failure immediately before wire')
            outcome = 'error' if int(call.started_sim_s * 10 + seed) % 47 == 0 else 'ok'
            return self._sent(call, core.CallReply(attempts=(core.Attempt(outcome=outcome),),
                                                 action={'command': 'wait'}))
    transport = Wire({})
    kwargs = {'on_action': lambda *args: actions.append(args), 'policy': core.CallPolicy()}
    if scheduler_type is DecisionScheduler:
        kwargs.update(own_job=lambda actor: None, decision_limits=DecisionLimits())
    s = scheduler_type(transport, **kwargs)
    transport.scheduler = s
    # Force the real caps to bind, while preserving ordinary event/timer merges.
    for tick in range(250):
        for actor in core.DEFAULT_ACTORS:
            s.trigger(actor, 'start' if tick == 0 else rng.choice(('idle', 'timer', 'failure')),
                      at=round(tick * 2.1, 6))
    s.run(until_s=600.)
    assert injected
    assert s.send_ledger.sends() == 90
    assert s.budget.used == dict.fromkeys(core.DEFAULT_ACTORS, 30)
    assert s.budget.outstanding() == 0
    assert not s.send_violations and not s.holding()
    return {'calls': [c.to_dict() for c in s.calls],
            'inputs': hashlib.sha256(json.dumps(snapshots, sort_keys=True).encode()).hexdigest(),
            'commands': actions, 'ledger': s.ledger, 'unsent': s.unsent_calls,
            'faults': injected, 'sends': s.send_ledger.to_dict()}


@pytest.mark.parametrize('seed', range(1000))
def test_generated_default_caps_and_all_prewire_failures(v64, seed):
    assert generated(seed, DecisionScheduler) == generated(seed, v64.event_scheduler)


def test_nondefault_outstanding_capacity_preserves_v64_resume_time(v64):
    def run(cls):
        kwargs = {'policy': core.CallPolicy(max_outstanding_per_actor=2, min_interval_s=0.)}
        if cls is DecisionScheduler:
            kwargs.update(own_job=lambda actor: None, decision_limits=DecisionLimits())
        s = cls(core.ReplayTransport({}), **kwargs)
        for at in (0., .1, .2):
            s.trigger('r1', at=at)
        s.run(until_s=5.)
        assert [c.started_sim_s for c in s.calls] == [0., .1, 1.]
        return [c.to_dict() for c in s.calls], s.ledger
    assert run(DecisionScheduler) == run(v64.event_scheduler)
