"""Seeded differential properties against frozen v64 source, no model/physics.

Three frozen modules retain v64's actual scheduling and integration code.
Only transport DTO identities are shared, so a current fake wire's exception
is recognised by both versions. No git/network access is needed by these tests.
"""
import builtins
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random
import sys
import types

import pytest

import harness
from harness import zone_event_scheduler as core
from harness import zone_study_integration as zi
from tests import test_zone_study_multiturn as fixture
from tests.test_zone_study_multiturn import offline_only  # noqa: F401


@pytest.fixture(scope='module')
def v64():
    root = Path(__file__).parent / 'fixtures/zone_study_multiturn/v64'
    manifest = json.loads((root / 'source.json').read_text())
    modules = {}
    package = types.ModuleType('harness')
    package.__dict__.update(harness.__dict__)

    def frozen_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in modules:
            return modules[name]
        if name == 'harness':
            return package
        return builtins.__import__(name, globals, locals, fromlist, level)

    for name in ('zone_event_scheduler', 'zone_study_offline', 'zone_study_integration'):
        source = (root / f'{name}.py.txt').read_bytes()
        assert hashlib.sha256(source).hexdigest() == manifest['files_sha256'][f'harness/{name}.py']
        module = types.ModuleType(f'_frozen_v64_{name}')
        module.__file__ = str(Path(zi.__file__).with_name(f'{name}.py'))
        module.__dict__['__builtins__'] = {**vars(builtins), '__import__': frozen_import}
        sys.modules[module.__name__] = module
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
        modules[f'harness.{name}'] = module
        setattr(package, name, module)
        if name == 'zone_event_scheduler':
            for dto in ('CallReply', 'TransportFailure', 'NotSent'):
                setattr(module, dto, getattr(core, dto))

    class LegacyTimingTrial(module.IntegratedTrial):
        sim_output_tokens = fixture.TimingTrial.sim_output_tokens

        def __init__(self, *args, decision_limits=None, **kwargs):
            super().__init__(*args, **kwargs)

    yield LegacyTimingTrial
    for module in modules.values():
        del sys.modules[module.__name__]


def fault_for(seed, *, zero_send_gap=False):
    def fault(payload, turn):
        tick = round(payload['sim_time_s'] * 10)
        if zero_send_gap and tick < 100:
            if payload['robot_id'] == 'r1' and tick < 60:
                raise OSError('generated initial call and retry failure')
            return
        # Depends only on exogenous time and actor, not condition/turn/call ID.
        value = (seed * 17 + tick * 7 + int(payload['robot_id'][1:]) * 13) % 29
        if value == 0:
            raise OSError('seeded fake wire failure')
        if value == 1:
            raise TimeoutError('seeded fake wire timeout')
    return fault


def prewire_faults(seed, *, zero_send_gap=False):
    # Fixed by external time/actor, never condition, turn or call ID. Force
    # both 0-send entry points across seeds, then scatter more over the stream.
    def selected(actor, at):
        tick = round(at * 10)
        if zero_send_gap and tick < 100:
            return actor == 'r1' and tick == 60
        return (actor == 'r1' and tick == 0) or (seed * 11 + tick * 3 + int(actor[1:])) % 41 == 0

    def prepare(call):
        if seed % 2 == 0 and selected(call.actor, call.started_sim_s):
            raise ValueError('generated pre-wire input failure')

    def store(row, kind, data):
        if seed % 2 == 0 or kind != 'request':
            return
        payload = json.loads(next(p['text'] for p in json.loads(data)['messages'][-1]['content']
                                  if p['type'] == 'text'))
        if selected(payload['robot_id'], payload['sim_time_s']):
            raise OSError('generated pre-wire request storage failure')

    return prepare, store


def event_stream(seed, *, zero_send_gap=False):
    rng = random.Random(245000 + seed)
    events = []
    triggers = ('idle', 'failure', 'blockage', 'timeout', 'retry', 'timer')
    for _ in range(rng.randint(16, 32)):
        tick = rng.choice((55, 60, 61, 80, 100, 153, 653, rng.randint(1, 850)))
        events.append((tick, rng.choice(zi.ROBOTS), rng.choice(triggers)))
    # Force own terminal + timer ties, including the reported second counterexample.
    events.extend([(653, 'r1', 'idle'), (653, 'r1', 'timer')])
    if zero_send_gap:
        # A pending common event could mask a missing message wake. Reserve a
        # gap around the 6.0 call / 6.1 delivery; keep the later random stream.
        events = [e for e in events if e[1] != 'r1' or e[0] >= 100]
        events.append((60, 'r1', 'timer'))
    return sorted(events, key=lambda e: e[0])


def run_stream(seed, condition='no_comm', trial_cls=None, *, communication=False, binding_budget=False,
               zero_send_gap=False):
    policy = core.CallPolicy(min_interval_s=(.5, 2., 8.)[seed % 3],
                             max_retries=seed % 3,
                             max_calls_per_actor=300, max_http_attempts_per_actor=300,
                             max_attempts_total=900)
    if zero_send_gap:
        policy = replace(policy, min_interval_s=2., max_retries=1)
    if binding_budget:
        policy = replace(policy, **({'max_calls_per_actor': 1},
                                    {'max_http_attempts_per_actor': 1},
                                    {'max_attempts_total': 2})[seed % 3])
    prepare_fault, store_fault = prewire_faults(seed, zero_send_gap=zero_send_gap)
    # The original 600 cases retain nonbinding limits for full schedule parity.
    trial, clock, links, requests = fixture.make_trial(
        condition, first='continue' if zero_send_gap else ('continue', 'claim', 'wait')[seed % 3],
        follow_claim=False, send=communication, trial_cls=trial_cls,
        policy=policy, limits=zi.DecisionLimits(max_calls_total=900),
        wire_fault=fault_for(seed, zero_send_gap=zero_send_gap),
        prepare_fault=prepare_fault, store_fault=store_fault, additive_noop=True)
    events = iter(event_stream(seed, zero_send_gap=zero_send_gap))
    pending = next(events, None)
    for tick in range(1, 901):
        # Enqueue own events before advancing the scheduler, as the runner does.
        while pending and pending[0] == tick:
            _, actor, trigger = pending
            trial.scheduler.trigger(actor, trigger, at=tick / 10)
            pending = next(events, None)
        fixture.advance(trial, clock, links, tick / 10,
                        boundary=65.3 if seed % 3 == 1 else None,
                        outcome='job_failed' if seed % 2 else 'job_done')
        if communication and not trial_cls and not trial.decision_budget_spent():
            assert_message_liveness(trial)
    trial.finish(90.)
    assert not trial.scheduler.send_violations
    assert trial.scheduler.unsent_calls  # forced r1 failure really reached settlement
    assert trial.scheduler.budget.used_total() <= policy.max_attempts_total
    assert all(n <= policy.max_http_attempts_per_actor for n in trial.scheduler.budget.used.values())
    if binding_budget:
        assert sum(m['budget_refused'] for m in trial.scheduler.metrics.values()) > 0
    return trial, requests


def assert_message_liveness(trial):
    s = trial.scheduler
    for actor in s._message_waiting:
        if (trial.links[actor].job() is not None or s._outstanding(actor)
                or s._outstanding(actor, 'message') or s.budget.remaining(actor) == 0
                or s.metrics[actor]['calls'] >= s.policy.max_calls_per_actor):
            continue
        last = max(s._last_start.get(actor, float('-inf')),
                   s._last_start.get((actor, 'message'), float('-inf')))
        assert s.now() < last + s.policy.min_interval_s - 1e-9, (actor, s.now(), last)


def signature(trial, requests):
    return {
        'calls': [c.to_dict() for c in trial.scheduler.calls],
        'input_hashes': [zi.digest(p) for p in requests],
        'request_hashes': [r['request_sha256'] for r in trial.requests],
        'dispatch': json.dumps(trial.dispatch_log, sort_keys=True, ensure_ascii=False).encode(),
        'censored': trial.scheduler.censored,
        'unsent': trial.scheduler.unsent_calls,
        # v66 stops arming reasks once HTTP budget is spent; frozen v64 can
        # enqueue more timers that are refused without creating a call. Those
        # diagnostic refusal counts are not calls, inputs, commands or spend.
        'budget': {k: v for k, v in trial.scheduler.budget.to_dict().items() if k != 'refusals'},
        'ledger': trial.scheduler.ledger,
    }


@pytest.mark.parametrize('seed', range(300))
def test_no_comm_bitwise_equivalent_to_frozen_v64(v64, seed):
    old, old_requests = run_stream(seed, trial_cls=v64)
    new, new_requests = run_stream(seed)
    assert signature(new, new_requests) == signature(old, old_requests), seed
    assert all(row['cause'] == 'common' for row in new.scheduler.call_causes.values())


@pytest.mark.parametrize('seed', range(100))
def test_generated_binding_budgets_keep_no_comm_v64_parity(v64, seed):
    old, old_requests = run_stream(seed, trial_cls=v64, binding_budget=True)
    new, new_requests = run_stream(seed, binding_budget=True)
    assert signature(new, new_requests) == signature(old, old_requests), seed
    for condition in zi.MAIN_CONDITIONS[1:]:
        trial, _ = run_stream(seed, condition, communication=True, binding_budget=True)
        # Additional calls may consume a shared finite budget earlier. Compare
        # all common events strictly before the first refusal in either run.
        cutoff = min(e['sim_s'] for tr in (new, trial) for e in tr.scheduler.events
                     if e.get('kind') == 'call_refused')
        assert [r for r in common_schedule(trial) if r[1] < cutoff] == [
            r for r in common_schedule(new) if r[1] < cutoff]


@pytest.mark.parametrize('seed', range(12))
def test_generated_zero_send_gap_cannot_strand_messages(v64, seed):
    old, old_requests = run_stream(seed, trial_cls=v64, zero_send_gap=True)
    baseline, requests = run_stream(seed, zero_send_gap=True)
    assert signature(baseline, requests) == signature(old, old_requests)
    for condition in zi.MAIN_CONDITIONS[1:]:
        trial, requests = run_stream(seed, condition, communication=True, zero_send_gap=True)
        assert common_schedule(trial) == common_schedule(baseline)
        received = next(p for p in requests if p['robot_id'] == 'r1' and p['sim_time_s'] == 8.)
        assert received['inbox']


def common_schedule(trial):
    s = trial.scheduler
    # Ledger includes censored calls; compare multiplicity as well as time sets.
    rows = [row for cid, row in s.ledger.items() if s.call_causes[cid]['cause'] == 'common']
    by_id = {cid: (r['actor'], r['started_sim_s']) for cid, r in s.ledger.items()}
    return [(r['actor'], r['started_sim_s'], r['trigger'],
             tuple(t for t in r['merged_triggers'] if t != 'report'),
             by_id.get(r['retry_of'])) for r in rows]


@pytest.mark.parametrize('seed', range(300))
def test_three_communication_conditions_keep_common_schedule(seed):
    baseline, _ = run_stream(seed)
    expected = common_schedule(baseline)
    for condition in zi.MAIN_CONDITIONS[1:]:
        trial, _ = run_stream(seed, condition, communication=True)
        assert common_schedule(trial) == expected, (seed, condition)
        s = trial.scheduler
        for cid, cause in s.call_causes.items():
            if cause['cause'] == 'message':
                assert cause['message_ids']
                started = s.ledger[cid]['started_sim_s']
                received = {m.message_id for m in s.messages
                            if m.recipient == s.ledger[cid]['actor'] and m.delivered_sim_s <= started}
                assert set(cause['message_ids']) <= received
                if cause['retry_of']:
                    assert s.call_causes[cause['retry_of']]['cause'] == 'message'


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_review_6s_error_retry_message_timer_tie(condition, v64):
    def error(payload, turn):
        if payload['robot_id'] == 'r1' and payload['sim_time_s'] == 5.5:
            raise OSError('review counterexample: error costs 0.5 s')

    def run(cls, cond):
        class RetryTieTrial(cls or fixture.TimingTrial):
            def sim_output_tokens(self, raw, n):
                # Leader 5.9 + delivery 0.1 = 6.0; follower cost is unchanged.
                return super().sim_output_tokens(raw, n) - json.loads(raw)['request_id'].endswith('r3')

        trial, clock, links, requests = fixture.make_trial(cond, trial_cls=RetryTieTrial, wire_fault=error)
        trial.scheduler.trigger('r1', 'timer', at=5.5)
        trial.scheduler.timer('r1', at=6.)
        fixture.advance(trial, clock, links, 20.)
        return trial, requests

    old, old_requests = run(v64, 'no_comm')
    new, new_requests = run(None, condition)
    starts = lambda tr: [c.started_sim_s for c in tr.scheduler.calls if c.actor == 'r1']
    # The reviewed candidate's no_comm count of 3 was itself a v64 divergence:
    # v64 retains a separate timer after the retry, so every condition needs 4.
    assert starts(old) == starts(new) == [0., 5.5, 7.5, 12.8]
    old_retry = next(c for c in old.scheduler.calls if c.actor == 'r1' and c.started_sim_s == 7.5)
    new_retry = next(c for c in new.scheduler.calls if c.actor == 'r1' and c.started_sim_s == 7.5)
    assert old_retry.retry_of == new_retry.retry_of and new_retry.retry_of
    timer = next(c for c in new.scheduler.calls if c.actor == 'r1' and c.started_sim_s == 12.8)
    assert timer.trigger == 'timer' and not timer.retry_of
    assert all(c['cause'] == 'common' for c in new.scheduler.call_causes.values())
    if condition == 'no_comm':
        assert signature(new, new_requests) == signature(old, old_requests)
    else:
        assert {m.delivered_sim_s for m in new.scheduler.messages} == {6.}
        assert next(p for p in new_requests if p['robot_id'] == 'r1' and p['sim_time_s'] == 7.5)['inbox']


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_review_65_3s_terminal_timer_tie(condition, v64):
    old, clock, links, old_requests = fixture.make_trial('no_comm', trial_cls=v64)
    fixture.advance(old, clock, links, 90., boundary=65.3)
    new, clock, links, new_requests = fixture.make_trial(condition)
    fixture.advance(new, clock, links, 90., boundary=65.3)
    starts = lambda tr: [c.started_sim_s for c in tr.scheduler.calls if c.actor == 'r1']
    assert starts(new) == starts(old) == [0., 65.3, 70.6]
    assert all(c['cause'] == 'common' for c in new.scheduler.call_causes.values())
    if condition == 'no_comm':
        assert signature(new, new_requests) == signature(old, old_requests)


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('failure', ['prepare', 'request_store'])
def test_review3_zero_send_wakes_message_at_8s(condition, failure, v64):
    def run(cls):
        faults = []

        def wire_fault(payload, turn):
            if payload['robot_id'] == 'r1' and payload['sim_time_s'] < 6.:
                raise OSError('initial call and its retry fail')

        def prepare_fault(call):
            if failure == 'prepare' and call.actor == 'r1' and call.started_sim_s == 6.:
                faults.append(call.call_id)
                raise ValueError('request construction failed before wire')

        def store_fault(row, kind, data):
            if failure != 'request_store' or kind != 'request':
                return
            payload = json.loads(next(p['text'] for p in json.loads(data)['messages'][-1]['content']
                                      if p['type'] == 'text'))
            if payload['robot_id'] == 'r1' and payload['sim_time_s'] == 6.:
                faults.append(row['call_id'])
                raise OSError('request storage failed once before wire')

        trial, clock, links, requests = fixture.make_trial(
            condition, trial_cls=cls, first='continue', follow_claim=False,
            wire_fault=wire_fault, prepare_fault=prepare_fault, store_fault=store_fault)
        trial.scheduler.timer('r1', at=6.)
        fixture.advance(trial, clock, links, 90.)
        assert len(faults) == 1
        assert trial.scheduler.ledger[faults[0]]['status'] == 'not_sent'
        assert trial.send_ledger.sends(faults[0]) == 0
        assert links['r1'].job() is None
        assert trial.scheduler.budget.remaining('r1') > 0
        return trial, requests

    old, old_requests = run(v64)
    new, new_requests = run(None)
    r1 = lambda requests: [p for p in requests if p['robot_id'] == 'r1']
    if condition == 'no_comm':
        assert signature(new, new_requests) == signature(old, old_requests)
        assert [p['sim_time_s'] for p in r1(new_requests)] == [0., 2.]
    else:
        assert [p['sim_time_s'] for p in r1(old_requests)[:3]] == [0., 2., 8.]
        assert [p['sim_time_s'] for p in r1(new_requests)[:3]] == [0., 2., 8.]
        assert {m.delivered_sim_s for m in new.scheduler.messages} == {6.1}
        assert r1(new_requests)[2]['inbox'] == r1(old_requests)[2]['inbox']
        assert r1(new_requests)[2]['inbox']
        assert not new.scheduler._message_waiting
        cid = next(cid for cid, row in new.scheduler.ledger.items()
                   if row['actor'] == 'r1' and row['started_sim_s'] == 8.)
        assert new.scheduler.call_causes[cid]['cause'] == 'message'


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS[1:])
def test_additive_inflight_call_cannot_delay_a_later_common_event(condition):
    trial, clock, links, requests = fixture.make_trial(condition, first='continue', follow_claim=False)
    trial.scheduler.timer('r1', at=6.2)
    fixture.advance(trial, clock, links, 15.)
    assert [p['sim_time_s'] for p in requests if p['robot_id'] == 'r1'] == [0., 6.1, 6.2]
    rows = [e for e in trial.scheduler.decision_events
            if e['actor'] == 'r1' and e['event'] == 'decision_started']
    assert [(e['sim_s'], e['cause']) for e in rows] == [(0., 'common'), (6.1, 'message'), (6.2, 'common')]
    # Only the initial/common responses arm reasks; extra response cannot add a timer.
    assert trial.scheduler.reask_counts['r1'] == {'armed': 1, 'skipped': 1}


@pytest.mark.parametrize('common_at', [None, 7.])
@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS[1:])
def test_message_retry_keeps_its_cause_or_is_consumed_by_common_snapshot(condition, common_at):
    def error(payload, turn):
        if payload['robot_id'] == 'r1' and payload['sim_time_s'] == 6.1:
            raise OSError('failed additive decision')

    trial, clock, links, requests = fixture.make_trial(
        condition, first='continue', follow_claim=False, wire_fault=error)
    if common_at:
        trial.scheduler.timer('r1', at=common_at)
    fixture.advance(trial, clock, links, 14.)
    rows = [e for e in trial.scheduler.decision_events
            if e['actor'] == 'r1' and e['event'] == 'decision_started']
    assert [e['sim_s'] for e in rows] == [0., 6.1, common_at or 8.1]
    if common_at:
        assert rows[-1]['cause'] == 'common' and rows[-1]['message_ids']
        assert not trial.scheduler._message_waiting
    else:
        assert rows[-1]['cause'] == 'message'
        assert rows[-1]['retry_of'] == rows[-2]['call_id']
        assert rows[-1]['message_ids'] == rows[-2]['message_ids']


def test_own_boundary_without_common_trigger_releases_only_pending_messages():
    trial, clock, links, requests = fixture.make_trial('leader_ko')
    fixture.advance(trial, clock, links, 7.)
    assert len(requests) == 3
    # Some own boundaries carry no scheduler trigger; the message wake is explicit.
    clock[0] = 8.
    links['r1'].ex._finish(8., 'unconfirmed', 'TEST_BOUNDARY')
    for event in links['r1'].ex.drain_events():
        event['scheduler_trigger'] = None
        trial.on_executor_event(event, at_s=8.)
    trial.step_to(8.)
    fixture.advance(trial, clock, links, 14.)
    rows = [e for e in trial.scheduler.decision_events
            if e['actor'] == 'r1' and e['event'] == 'decision_started']
    assert [(e['sim_s'], e['cause']) for e in rows] == [(0., 'common'), (8., 'message')]


@pytest.mark.parametrize('common_first', [False, True])
def test_only_messages_coalesce_and_consume_together(common_first):
    from harness.zone_study_decisions import DecisionLimits, DecisionScheduler
    from harness.zone_sim_cost import Attempt

    job = {'kind': 'deliver', 'job_id': 'own-test-job'}

    def reply(call):
        messages = tuple(core.Message('r3', ('r1',), {'text': text})
                         for text in ('첫 번째 보고입니다.', '두 번째 보고입니다.')) if call.actor == 'r3' else ()
        return core.CallReply(attempts=(Attempt(utterances=len(messages)),), messages=messages)

    scheduler = DecisionScheduler(core.ReplayTransport(reply), own_job=lambda actor: job,
                                  decision_limits=DecisionLimits())
    scheduler.trigger('r1', 'start')
    scheduler.trigger('r3', 'start')
    scheduler.run(until_s=2., close_at_horizon=False)
    assert len(scheduler._message_waiting['r1']['message_ids']) == 2
    if common_first:
        scheduler.timer('r1', at=2.5)
        scheduler.run(until_s=2.5, close_at_horizon=False)
    job = None
    scheduler.own_job_boundary('r1', at=3.)
    scheduler.run(until_s=5.)
    rows = [e for e in scheduler.decision_events if e['actor'] == 'r1' and e['event'] == 'decision_started']
    assert len(rows) == 2
    assert rows[-1]['sim_s'] == (2.5 if common_first else 3.)
    assert rows[-1]['cause'] == ('common' if common_first else 'message')
    assert set(rows[-1]['message_ids']) == {m.message_id for m in scheduler.messages}
    assert not scheduler._message_waiting
