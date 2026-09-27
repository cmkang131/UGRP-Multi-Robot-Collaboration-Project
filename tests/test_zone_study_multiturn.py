"""#223 late-leader regression: real inputs/client/ledger/executor, fake wire/clock.

No model, socket, MuJoCo import or physical step. The output-token fixture
isolates the pilot's SIM release times from text-length differences. It does
not estimate provider latency or language understanding.
"""
from collections import Counter
import io
import json
from pathlib import Path
import socket
import sys

import pytest

from harness import zone_study_integration as zi
from harness.zone_event_scheduler import CallPolicy
from harness.zone_sim_cost import CostParams
from harness.zone_send_ledger import SendLedger, completion_body
from harness.zone_study_llm_transport import gemini_client_factory
from tests.test_zone_study_integration import BUNDLE, SCENARIO, links_for


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    monkeypatch.setitem(sys.modules, 'mujoco', None)
    def refuse(*args, **kwargs):
        pytest.fail('network forbidden in multiturn regression')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket.socket, 'connect_ex', refuse)


class TimingTrial(zi.IntegratedTrial):
    def sim_output_tokens(self, raw, utterances):
        rid = json.loads(raw)['request_id'].rsplit('_', 1)[-1]
        # overhead 1 + output tokens*.1 + utterances*.1 = 5.3/5.4/6.0.
        return {'r1': 43, 'r2': 44, 'r3': 50}[rid] - utterances


def make_trial(condition, *, first='claim', policy=None, limits=None, send=True, repeat=False,
               budget=None, tmp_path=None, follow_claim=True, horizon=90.):
    clock = [0.]
    links = links_for(clock)
    requests, turns = [], Counter()

    def wire(request, *, timeout=None):
        body = json.loads(request.data)
        user = next(p['text'] for p in body['messages'][-1]['content'] if p['type'] == 'text')
        payload = json.loads(user)
        rid = payload['robot_id']
        turns[rid] += 1
        requests.append(payload)
        own_messages = [m for m in payload.get('inbox', []) if m['sender'] == 'r3']
        order_id = ('order-2' if rid == 'r1' else 'order-3') if own_messages else 'order-1'
        order = next(o for o in SCENARIO['orders'] if o['order_id'] == order_id)
        action = ({'kind': 'claim', 'order_id': order_id, 'role': 'west',
                   'destination_zone': order['destination_zone']}
                  if first == 'claim' or (own_messages and follow_claim) else {'kind': first})
        messages = []
        if send and rid == 'r3' and (turns[rid] == 1 or repeat) and condition != 'no_comm':
            for peer, target in [('r1', 'order-2'), ('r2', 'order-3')]:
                message = {'recipients': [peer], 'reply_to': None}
                if condition == 'structured':
                    message['message'] = {'act': 'propose', 'item': target,
                                          'zone': 'B' if peer == 'r1' else 'A', 'role': 'west',
                                          'passage': None, 'location_ref': None, 'state': 'unknown',
                                          'confidence': 'low', 'observed_at_sim_s': payload['sim_time_s'],
                                          'reply_to': None}
                else:
                    message['text'] = f'{peer}은 {target}을 맡아 주세요.'
                messages.append(message)
        raw = json.dumps({'request_id': payload['request_id'], 'action': action,
                          'decision_sources': ['own_rgb', 'order_sheet'] + (['message'] if own_messages else []),
                          'messages': messages}, ensure_ascii=False)
        return io.BytesIO(completion_body(raw, usage={'prompt_tokens': 500, 'completion_tokens': 100,
                                                      'total_tokens': 600}))

    settings = {'model': 'offline-multiturn', 'url': 'http://offline.invalid',
                'max_tokens': 768, 'temperature': .2}
    if budget is None:
        ledger = SendLedger(wire)
    else:
        from harness.zone_pilot_budget import REQUESTED, PROXY_SHA256
        from harness.zone_pilot_ledger import PilotSendLedger
        settings = {**REQUESTED, 'url': 'http://127.0.0.1:8391/v1/chat/completions'}
        ledger = PilotSendLedger(store_dir=tmp_path / 'wire', budget=budget, wire=wire,
                                  profile={'source_sha256': PROXY_SHA256, 'url': settings['url']},
                                  context={'condition': condition, 'trial_id': 'offline-multiturn'})
    adapter = zi.ModelAdapter(gemini_client_factory(**settings, study_json=True), ledger)
    trial = TimingTrial(SCENARIO, condition=condition, seed=11, links=links, horizon_s=horizon,
                         map_bundle=BUNDLE, actor='gemini_proxy', model_adapter=adapter,
                         cost_params=CostParams(input_token_s=0., output_token_s=.1, utterance_s=.1),
                         policy=policy, decision_limits=limits)
    trial.begin(0.)
    return trial, clock, links, requests


def advance(trial, clock, links, to, *, boundary=None, outcome='job_done'):
    for tick in range(round(clock[0] * 10) + 1, round(to * 10) + 1):
        clock[0] = tick / 10
        for rid, link in links.items():
            link.ex.now = clock[0]
            job = link.ex.job
            if job and job.kind == 'hold' and clock[0] >= job.started_at + job.args['duration_s']:
                # Legacy v64 wait fixture: advance the own timer, not physics.
                link.ex._finish(clock[0], 'unconfirmed', 'HOLD_ELAPSED')
            if boundary == clock[0] and rid in ('r1', 'r2') and link.ex.job:
                if outcome == 'job_done':
                    link.ex._finish(clock[0], 'unconfirmed', 'TEST_BOUNDARY')
                else:
                    link.ex._fail(clock[0], 'TEST_FAILURE')
            for event in link.ex.drain_events():
                trial.on_executor_event(event, at_s=clock[0])
        trial.step_to(clock[0])


def wait_control_record(trial, requests):
    """Pin every input byte semantically, plus readable times and command args.

    Channel, inbox, dialogue limits and leader roles are condition-specific;
    even request IDs stay in the common-input digest. own_rgb_refs pin the
    actual request JPEGs already checked by the integration tests.
    """
    return {
        'requests': [
            {'actor': p['robot_id'], 'sim_s': p['sim_time_s'],
             'input_sha256': zi.digest(p),
             'common_input_sha256': zi.digest({k: v for k, v in p.items()
                                               if k not in ('condition', 'channel', 'inbox',
                                                            'dialogue_window', 'leader_id', 'role')}),
             'last_command_args': p['own_command_history'][-1]['arguments']
                                  if p['own_command_history'] else None}
            for p in requests],
        'calls': [{'actor': c.actor, 'start': c.started_sim_s, 'end': c.finished_sim_s,
                   'trigger': c.trigger, 'merged': list(c.merged_triggers)}
                  for c in trial.scheduler.calls],
        'dispatch_sha256': zi.digest(trial.dispatch_log),
    }


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_90s_wait_preserves_v64_inputs_and_calls_in_all_conditions(condition):
    golden = json.loads((Path(__file__).parent / 'fixtures/zone_study_multiturn/v64_wait_90s.json').read_text())
    trial, clock, links, requests = make_trial(condition, first='wait', send=False, follow_claim=False)
    advance(trial, clock, links, 90.)
    actual = wait_control_record(trial, requests)
    assert actual == golden['conditions'][condition]
    common = lambda rows: [(r['actor'], r['sim_s'], r['common_input_sha256']) for r in rows]
    assert common(actual['requests']) == common(golden['conditions']['no_comm']['requests'])
    r1 = [p for p in requests if p['robot_id'] == 'r1']
    assert len(r1) == 9
    assert r1[1]['own_command_history'][0]['arguments'] == {'duration_s': 10.0}
    assert not trial.scheduler.messages


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('boundary', [None, 8., 65.3])
def test_deferred_report_never_suppresses_common_timer_or_rearming(condition, boundary):
    trial, clock, links, requests = make_trial(condition, horizon=150.)
    advance(trial, clock, links, 150., boundary=boundary)
    r1 = [p for p in requests if p['robot_id'] == 'r1']
    expected = [0., 8., 65.3, 130.6] if boundary == 8. else [0., 65.3, 130.6]
    assert [p['sim_time_s'] for p in r1] == expected
    if condition != 'no_comm':
        # By the FIRST own boundary or timer, every delivered message has
        # reached an input snapshot. Inbox history itself is retained.
        delivered = {m.message_id for m in trial.scheduler.messages if m.recipient == 'r1'}
        assert {m['message_id'] for m in r1[1]['inbox']} == delivered
        assert delivered
    timer_call = next(c for c in trial.scheduler.calls if c.actor == 'r1' and c.started_sim_s == 65.3)
    assert 'timer' in {timer_call.trigger, *timer_call.merged_triggers}
    assert zi.zo.cost_checks(trial, trial.finish(150.))['ok']


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_late_leader_changes_claim_only_at_own_boundary(condition):
    trial, clock, links, requests = make_trial(condition)
    advance(trial, clock, links, 7.)
    first = {d['actor']: d for d in trial.dispatch_log}
    assert [first[r]['sim_s'] for r in ('r1', 'r2', 'r3')] == [5.3, 5.4, 6.]
    assert all(d['ack']['accepted'] and d['args'][0] == 'order-1' for d in first.values())
    assert len(requests) == 3  # 6.1 delivery cannot interrupt ongoing work
    if condition != 'no_comm':
        assert {m.delivered_sim_s for m in trial.scheduler.messages} == {6.1}
        assert len(trial.scheduler.decision_events) > 3
    advance(trial, clock, links, 14., boundary=8.)
    for rid, target in [('r1', 'order-2'), ('r2', 'order-3')]:
        decisions = [d for d in trial.dispatch_log if d['actor'] == rid]
        second = decisions[1]
        assert second['ack']['accepted'] and second['api'] == 'deliver'
        assert second['args'][0] == (target if condition != 'no_comm' else 'order-1')
        calls = [c for c in trial.scheduler.calls if c.actor == rid]
        assert calls[1].started_sim_s == 8.
        assert calls[1].finished_sim_s == pytest.approx(8. + calls[1].cost.sim_s)
        labels = {calls[1].trigger, *calls[1].merged_triggers}
        assert 'idle' in labels and ('report' in labels) == (condition != 'no_comm')
    result = trial.finish(14.)
    assert zi.zo.cost_checks(trial, result)['ok']
    assert not trial.scheduler.send_violations
    assert trial.send_ledger.sends() == len(requests) == 5
    if condition == 'no_comm':
        assert not result.messages and all('inbox' not in p for p in requests)
        assert all('report' not in {c.trigger, *c.merged_triggers} for c in trial.scheduler.calls)
    else:
        assert result.cost['talk_sim_s'] > 0
        assert all(p['inbox'] for p in requests[3:])
        if condition == 'leader_ko':
            assert trial.leader_id == 'r3'
            assert all(m.sender == 'r3' or m.recipient == 'r3' for m in trial.scheduler.messages)


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_idle_robot_redecides_immediately_after_delivery(condition):
    # continue on an idle executor leaves it idle; explicit wait is a v64 hold.
    trial, clock, links, requests = make_trial(condition, first='continue')
    advance(trial, clock, links, 12.)
    r1 = [p for p in requests if p['robot_id'] == 'r1']
    if condition == 'no_comm':
        assert len(r1) == 1 and links['r1'].job() is None
    else:
        assert [p['sim_time_s'] for p in r1] == [0., 6.1]
        assert links['r1'].job()['order_id'] == 'order-2'
        assert all(d['ack'] is None or d['ack']['accepted'] for d in trial.dispatch_log)


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_explicit_wait_keeps_v64_hold_and_uses_message_at_hold_boundary(condition):
    trial, clock, links, requests = make_trial(condition, first='wait')
    advance(trial, clock, links, 12.)
    assert [p['sim_time_s'] for p in requests if p['robot_id'] == 'r1'] == [0.]
    assert links['r1'].job()['kind'] == 'hold'
    advance(trial, clock, links, 21.)
    r1 = [p for p in requests if p['robot_id'] == 'r1']
    assert [p['sim_time_s'] for p in r1] == [0., 15.3]
    assert r1[1]['own_command_history'][0]['arguments'] == {'duration_s': 10.0}
    if condition != 'no_comm':
        assert r1[1]['inbox'] and links['r1'].job()['order_id'] == 'order-2'


@pytest.mark.parametrize('outcome', ['job_done', 'job_failed'])
def test_common_terminal_triggers_identical_in_all_four_conditions(outcome):
    signatures = []
    for condition in zi.MAIN_CONDITIONS:
        trial, clock, links, requests = make_trial(condition, send=False)
        advance(trial, clock, links, 14., boundary=8., outcome=outcome)
        signatures.append([(c.actor, c.trigger, c.started_sim_s, c.finished_sim_s)
                           for c in trial.scheduler.calls])
        assert len(requests) == 5
    assert all(s == signatures[0] for s in signatures)
    assert signatures[0][-1][1] == ('idle' if outcome == 'job_done' else 'failure')


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('limit', ['actor', 'episode', 'http_actor', 'http_episode'])
def test_call_and_attempt_caps_terminate_idle_dialogue(condition, limit):
    policy = CallPolicy(max_calls_per_actor=2 if limit == 'actor' else 30,
                        max_http_attempts_per_actor=2 if limit == 'http_actor' else 30,
                        max_attempts_total=6 if limit == 'http_episode' else 90)
    limits = zi.DecisionLimits(max_calls_total=6 if limit == 'episode' else 90)
    trial, clock, links, requests = make_trial(condition, first='wait', repeat=True, follow_claim=False,
                                              policy=policy, limits=limits)
    advance(trial, clock, links, 60.)
    assert len(requests) == trial.send_ledger.sends() == 6
    if limit in ('actor', 'http_actor'):
        assert all(m['calls'] == 2 for m in trial.scheduler.metrics.values())
    else:
        assert sum(m['calls'] for m in trial.scheduler.metrics.values()) == 6
    assert trial.quiescent()
    before = len(requests)
    for rid in zi.ROBOTS:
        trial.scheduler.trigger(rid, 'idle')
    advance(trial, clock, links, 70.)
    assert len(requests) == before
    assert trial.finish(70.).end_reason == 'budget_exhausted'


@pytest.mark.parametrize('condition', ['peer_ko', 'leader_ko', 'structured'])
@pytest.mark.parametrize('scope', ['actor', 'episode'])
def test_utterance_caps_are_episode_scoped_and_rejections_still_cost(condition, scope):
    trial, clock, links, _ = make_trial(condition, first='wait', repeat=True,
                                        limits=zi.DecisionLimits(max_utterances_per_actor=1 if scope == 'actor' else 2,
                                                                 max_utterances_total=1 if scope == 'episode' else 6))
    advance(trial, clock, links, 45.)
    assert trial.channel.sent_count() == 1
    assert trial.scheduler.rejected_messages
    assert sum(c.cost.breakdown['utterances'] for c in trial.scheduler.calls) > 1
    assert trial.channel.windows == ['w1']


def test_simultaneous_boundary_and_delivery_coalesce_into_one_call():
    trial, clock, links, requests = make_trial('leader_ko')
    advance(trial, clock, links, 12., boundary=6.1)
    for rid in ('r1', 'r2'):
        assert [p['sim_time_s'] for p in requests if p['robot_id'] == rid] == [0., 6.1]
    assert all(d['ack']['accepted'] for d in trial.dispatch_log)


def test_episode_cap_during_inflight_still_charges_and_finishes():
    trial, clock, links, requests = make_trial('leader_ko', first='continue',
                                              limits=zi.DecisionLimits(max_calls_total=4))
    advance(trial, clock, links, 12.)
    assert len(requests) == 4
    assert len(trial.scheduler.calls) == 4 and not trial.scheduler.holding()
    assert any(e['event'] == 'episode_call_cap' for e in trial.scheduler.decision_events)


@pytest.mark.parametrize('resource', ['tokens', 'attempts'])
def test_persistent_pilot_budget_blocks_followup_before_wire(tmp_path, monkeypatch, resource):
    from harness.zone_pilot_budget import PilotBudget
    from harness.zone_pilot_ledger import PilotSendLedger
    monkeypatch.setattr(PilotSendLedger, '_wait_for_log_boundary', lambda self: {'not_before_ns': None})
    budget = PilotBudget.create(tmp_path / 'fake-pilot.sqlite', identity={'source_head': 'offline-test'})
    trial, clock, links, requests = make_trial('leader_ko', budget=budget, tmp_path=tmp_path)
    advance(trial, clock, links, 7.)
    assert len(requests) == 3
    snap = budget.snapshot()
    left = 5_000_000 - snap['reserved_tokens'] if resource == 'tokens' else 2
    for i in range(1 if resource == 'tokens' else (600 - snap['reserved_attempts']) // 2):
        budget.reserve({'call_id': f'other-{i}', 'trial_id': 'other-offline-task'},
                       {'reserved_tokens': left, 'per_upstream_tokens': left // 2})
    before = budget.snapshot()
    advance(trial, clock, links, 20., boundary=8.)
    assert len(requests) == trial.send_ledger.sends() == 3
    assert len(trial.dispatch_log) == 3
    assert trial.scheduler.unsent_calls
    assert trial.transport.budget_exhausted and trial.decision_budget_spent()
    assert budget.snapshot()['reserved_tokens'] == before['reserved_tokens']
    assert budget.snapshot()['reserved_attempts'] == before['reserved_attempts']
    assert trial.finish(20.).end_reason == 'budget_exhausted'


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
@pytest.mark.parametrize('trigger', ['timer', 'boundary'])
def test_common_trigger_during_decision_keeps_same_start_with_pending_message(condition, trigger):
    # r1 begins a common timer call at 5.5, just before the 6.1 delivery.
    trial, clock, links, requests = make_trial(condition)
    trial.scheduler.trigger('r1', 'timer', at=5.5)
    if trigger == 'timer':
        trial.scheduler.trigger('r1', 'timer', at=6.2)
    advance(trial, clock, links, 18., boundary=8. if trigger == 'boundary' else None)
    starts = [p for p in requests if p['robot_id'] == 'r1']
    assert [p['sim_time_s'] for p in starts] == [0., 5.5, 10.8]
    if condition != 'no_comm':
        assert starts[1]['inbox'] == []  # immutable snapshot, no future message leak
        assert starts[2]['inbox']
    # Even if the earlier reply starts a new job, an already eligible common
    # trigger must not be delayed AGAIN by the pending report.
    call = next(c for c in trial.scheduler.calls if c.actor == 'r1' and c.started_sim_s == 10.8)
    assert ('timer' if trigger == 'timer' else 'idle') in {call.trigger, *call.merged_triggers}


def test_message_during_decision_without_common_trigger_waits_for_next_timer():
    trial, clock, links, requests = make_trial('leader_ko')
    trial.scheduler.trigger('r1', 'timer', at=5.5)
    advance(trial, clock, links, 90.)
    starts = [p for p in requests if p['robot_id'] == 'r1']
    assert [p['sim_time_s'] for p in starts] == [0., 5.5, 65.3]
    assert starts[1]['inbox'] == [] and starts[2]['inbox']


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_common_timer_with_pending_report_obeys_same_minimum_interval(condition):
    trial, clock, links, requests = make_trial(condition, policy=CallPolicy(min_interval_s=70.))
    advance(trial, clock, links, 90.)
    r1 = [p for p in requests if p['robot_id'] == 'r1']
    assert [p['sim_time_s'] for p in r1] == [0., 70.]
    if condition != 'no_comm':
        assert r1[1]['inbox']


@pytest.mark.parametrize('condition', zi.MAIN_CONDITIONS)
def test_same_time_timer_and_message_share_one_common_decision(condition):
    trial, clock, links, requests = make_trial(condition)
    trial.scheduler.timer('r1', at=6.1)
    advance(trial, clock, links, 12.)
    r1 = [p for p in requests if p['robot_id'] == 'r1']
    assert [p['sim_time_s'] for p in r1] == [0., 6.1]
    if condition != 'no_comm':
        assert r1[1]['inbox']
    call = next(c for c in trial.scheduler.calls if c.actor == 'r1' and c.started_sim_s == 6.1)
    assert 'timer' in {call.trigger, *call.merged_triggers}


def test_idle_message_still_obeys_common_minimum_call_interval():
    trial, clock, links, requests = make_trial('leader_ko', first='continue',
                                              policy=CallPolicy(min_interval_s=10.))
    advance(trial, clock, links, 16.)
    assert [p['sim_time_s'] for p in requests if p['robot_id'] == 'r1'] == [0., 10.]
    assert links['r1'].job()['order_id'] == 'order-2'


@pytest.mark.parametrize('invalid', [0, -1, True, 1.5, None])
def test_finite_episode_limits_required(invalid):
    with pytest.raises(ValueError):
        zi.DecisionLimits(max_calls_total=invalid)
