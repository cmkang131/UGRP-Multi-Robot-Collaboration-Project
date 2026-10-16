"""Real #363 hooks + pair scheduler on recorded frames; no model, physics or renderer."""
import base64
import hashlib
import json
from types import SimpleNamespace

import pytest

from harness import pair_llm_contract as contract
from harness import pair_llm_inputs as inputs
from harness import pair_llm_decisions as decisions
from harness import zone_pair_highpose_refix as hooks
from harness.pair_llm_case import stub_adapter
from harness.pair_llm_dispatch import PairLink, PairTrial, validate_reply
from harness.pair_llm_eval import decision_evidence
from harness.pair_llm_runtime import ClaimGate, GatedHighRuntime
from harness.pair_llm_stop_adapter import StopAdapter, unknown_belief
from harness.pair_llm_stub import StubModel
from harness.zone_pair_highpose_runtime import Runtime as HighRuntime
from harness.zone_study_inputs import belief_skeleton
from harness.zone_study_protocol import ProtocolError
from tests import test_highpose_refix as base
from tests.test_highpose_refix import short_route, stub_states  # noqa: F401
from tests.test_highpose_refix_hooks import look_team  # noqa: F401
from tests.pair_llm_fakes import make_inputs, offline_only  # noqa: F401
from tests.pair_llm_window_replay import event


def own_executor(ctl):
    return SimpleNamespace(robot_id=ctl.rid, _pair=SimpleNamespace(controller=ctl),
                           job=SimpleNamespace(kind='pair_carry', args={'order_id': 'cargoX'}, job_id='own-job'),
                           belief_projection=belief_skeleton)


def attach(ctls, condition):
    return {c.rid: StopAdapter(own_executor(c), condition=condition, origin_s=0.) for c in ctls}


def poll_windows(adapter):
    for row in adapter.poll():
        adapter.window.on_event(row, origin_s=adapter.origin_s)


@pytest.mark.parametrize('condition', ['rule', 'no_comm'])
def test_polling_actual_hooks_preserves_nonempty_rule_trajectory_bytes(condition):
    _, plain = base.team(base.BEFORE_DOOR, over={'r1': True})
    base.run(plain, 140.)
    _, ctls = base.team(base.BEFORE_DOOR, over={'r1': True})
    adapters = attach(ctls, condition)
    for i in range(1401):
        for a in adapters.values():
            poll_windows(a)
        base.run_one(ctls, i/10)
    for a in adapters.values():
        poll_windows(a)
    before = json.dumps([c.issued_log for c in plain], sort_keys=True).encode()
    after = json.dumps([c.issued_log for c in ctls], sort_keys=True).encode()
    assert all(c.issued_log for c in ctls) and before == after
    assert hashlib.sha256(before).digest() == hashlib.sha256(after).digest()
    from tests.test_pair_llm_windows import assert_frozen_commands
    frozen_bytes = json.dumps([c.issued_log for c in ctls], sort_keys=True, separators=(',', ':')).encode()
    assert_frozen_commands(frozen_bytes, condition + '-hooks.json')
    assert all(c.state == 'released' and c.failure is None for c in ctls)
    rows = [r for a in adapters.values() for r in a.decisions]
    assert len(rows) == 2 and all(r['decided_by'] == 'rule_default' for r in rows)
    assert decision_evidence(condition=condition, success=True, decisions=rows)['classifications'] == (
        [] if condition == 'rule' else ['LLM_INERT'])


@pytest.mark.parametrize('condition', ['no_comm', 'peer_nl'])
def test_fake_reply_flows_through_real_pair_trial_link_and_actual_hook(tmp_path, condition):
    bundled, _, map_bundle = make_inputs('no_comm')
    _, ctls = base.team(base.BEFORE_DOOR)
    adapters = attach(ctls, condition)
    rt = SimpleNamespace(actors={r: a.executor for r, a in adapters.items()}, gate=ClaimGate())
    links = {r: PairLink(rt, r, stop_adapter=a) for r, a in adapters.items()}
    jpeg = bundled.wrist_jpeg

    def policy(rid, index, body, _):
        w = body['decision_window']
        if w and rid == 'r1' and w['kind'] == 'carry_decision':
            return {'kind': 'carry_decision', 'choice': 'set_down'}, []
        return {'kind': 'continue'}, []

    adapter, _ = stub_adapter(StubModel(policy), tmp_path/'ledger')
    trial = PairTrial(contract.scenario(), condition=condition, seed=911, links=links, horizon_s=140.,
                      map_bundle=map_bundle, model_adapter=adapter, model_settings={'model': 'fake'})
    for i in range(1401):
        now = i/10
        for r, link in links.items():
            link.observe({'robot_id': r, 'camera': 'robot_cam', 'frame_id': i+1, 'sim_time': now,
                          'image': base64.b64encode(jpeg).decode(), 'sha256': hashlib.sha256(jpeg).hexdigest()})
        if i == 0:
            base.run_one(ctls, now)
            trial.begin(0.)
        else:
            for a in adapters.values():
                for row in a.poll():
                    trial.on_executor_event(row, at_s=now)
            trial.step_to(now)
            base.run_one(ctls, now)
    trial.finish(140.)
    for a in adapters.values():
        a.poll()
    commands = [r for r in trial.dispatch_log if r['api'] == 'carry_decision']
    assert len(commands) == 1 and commands[0]['ack']['accepted']
    assert commands[0]['args'] == ['set_down']
    assert all(c.refix_count == 1 and c.state == 'released' and c.failure is None for c in ctls)
    own = adapters['r1'].decisions[0]
    assert own['decided_by'] == 'llm' and own['rule_would_do'] == 'continue' and own['llm_choice'] == 'set_down'
    assert any(json.loads(r['user'])['decision_window'] for r in trial.requests)
    forbidden = ('rule_would_do', 'rule_default', 'receipt', 'std_xy_m', 'x_m', 'simulator_state', 'partner_status')
    for row in trial.requests:
        body = json.loads(row['user'])
        projected = json.dumps({'belief': body['own_belief'], 'window': body['decision_window']})
        assert not any(k in projected for k in forbidden)
        assert body['own_belief']['sigma_xy_band'] in ('fix', 'budget', 'over', 'unknown')
        if condition == 'no_comm':
            assert 'inbox' not in body and 'dialogue_window' not in body


@pytest.mark.parametrize('command', ['carry_decision', 'post_look_decision'])
@pytest.mark.parametrize('origin', [0., 1.3, 7.])
def test_late_and_old_window_replies_cannot_latch_another_stop(command, origin):
    called = []
    ctl = SimpleNamespace(rid='r1', carry_decision=lambda *a: called.append(a),
                          post_look_decision=lambda *a: called.append(a))
    a = StopAdapter(own_executor(ctl), condition='peer_nl', origin_s=origin)
    a.controller()

    def open_at(t):
        kind = 'carry_stop_reached' if command == 'carry_decision' else 'relook_result'
        detail = ({'decide_at_s': origin+t+10, 'latch_until_s': origin+t+9.8} if command == 'carry_decision'
                  else {'window_until_s': origin+t+10})
        a.window.on_event(event('r1', kind, t, origin=origin, **detail), origin_s=origin)
    choice = 'set_down' if command == 'carry_decision' else 'look_again'
    open_at(12.)
    old = a.window.reference(12.)
    for now in (22., 23.):
        assert a.command(command, choice, absolute_now=origin+now, window_ref=old)['own_status'] == 'DEADLINE_PASSED'
    open_at(30.)
    assert a.command(command, choice, absolute_now=origin+31., window_ref=old)['own_status'] == 'DEADLINE_PASSED'
    assert not called


def test_actual_post_look_commands_and_caps_are_preserved(look_team):
    _, ctls = look_team()
    adapters, outcomes = attach(ctls, 'no_comm'), []
    seen = set()
    for i in range(2001):
        now = i/10
        for a in adapters.values():
            poll_windows(a)
        a = adapters['r1']
        w = a.window.snapshot(now)
        if w and w['kind'] == 'post_look_decision' and a.window.serial not in seen:
            seen.add(a.window.serial)
            outcomes.append(a.command('post_look_decision', 'look_again', absolute_now=now,
                                      window_ref=a.window.reference(now)))
        base.run_one(ctls, now)
    for a in adapters.values():
        a.poll()
    assert [r['own_status'] for r in outcomes] == ['LATCHED', hooks.LOOK_AGAIN_USED]
    rows = [r for r in adapters['r1'].decisions if r['kind'] == 'post_look_decision']
    assert [r['choice'] for r in rows] == ['look_again', 'regrasp']
    assert adapters['r1'].look_again_total == 1
    assert set(e['event'] for a in adapters.values() for e in a.events) == set(decisions.HOOK_EVENTS)
    # A subsequent own retry cannot replenish the per-case allowance.
    retry = SimpleNamespace(rid='r1', carry_decision=lambda *a: None)
    adapters['r1'].executor._pair.controller = retry
    adapters['r1'].poll()
    assert retry.refix_look_again_total == 1 and adapters['r1'].window.current is None


def test_evaluation_times_keep_both_clocks_and_survive_controller_removal():
    ctl = SimpleNamespace(rid='r1', carry_decision=lambda *a: None,
                          refix_hook_decisions=[{'stop': 1, 'sim_s': 22.3, 'decided_s': 18.3,
                                                'executed_s': 22.3, 'decided_by': 'llm'}])
    a = StopAdapter(own_executor(ctl), condition='no_comm', origin_s=1.3)
    a.poll()
    a.executor._pair = None
    a.poll()
    assert len(a.decisions) == 1
    row = a.decisions[0]
    assert row['decided_s'] == 17. and row['decided_s_absolute'] == 18.3
    assert row['executed_s'] == 21. and row['executed_s_absolute'] == 22.3
    assert decision_evidence(condition='no_comm', success=True, decisions=a.decisions)['last_llm_decision_sim_s'] == 17.


def test_cli_measured_calibration_uses_high_admission_before_any_execution(monkeypatch, tmp_path):
    from harness import zone_pair_highpose_contract as high
    from harness import zone_final_pair_contract as old
    from scripts import run_pair_llm as cli
    seen = []

    def admit(*args):
        seen.append(args)
        raise ValueError('HIGH_ADMISSION_TEST_STOP')
    monkeypatch.setattr(high, 'measured_calibration', admit)
    monkeypatch.setattr(old, 'measured_calibration', lambda *a: pytest.fail('v88 admission is not valid for HIGH'))
    with pytest.raises(ValueError, match='HIGH_ADMISSION_TEST_STOP'):
        cli.main(['--execute', '--condition', 'rule', '--output', str(tmp_path/'unused'),
                  '--expected-source-sha', 'b'*40,
                  '--calibration', str(tmp_path/'not_read.json'), '--calibration-sha256', 'a'*64])
    assert len(seen) == 1 and not (tmp_path/'unused').exists()


def test_stop_record_write_failure_still_closes_own_resources(tmp_path, monkeypatch):
    from harness import pair_llm_case as case
    from tests.pair_llm_fakes import FakeBackend, FakeRuntime, run_arm
    owned = []

    class Backend(FakeBackend):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            owned.append(self)

    class Runtime(FakeRuntime):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            owned.append(self)
    original = case.jsonl

    def full(path, rows):
        if path.name == 'stop_hook_events.jsonl':
            raise OSError('fake stop-record disk failure')
        return original(path, rows)
    monkeypatch.setattr(case, 'jsonl', full)
    result, _, _ = run_arm(tmp_path, 'rule', cap_s=.1, backend=Backend, runtime_factory=Runtime)
    assert result['status'] == 'HOST_ERROR' and 'fake stop-record disk failure' in result['stop_record_error']
    assert len(owned) == 2 and all(r.closed for r in owned)


def test_model_projection_rejects_poisoned_belief_and_window_and_ignores_raw_event_fields():
    bundled, _, _ = make_inputs('no_comm', t=12.)
    poison = {'rule_would_do': 'set_down', 'partner_status': 'uncertain', 'simulator_state': {'x_m': 99.},
              'eval_only': 'CANARY_GT_ERROR'}
    ctl = SimpleNamespace(rid='r1', carry_decision=lambda *a: None,
                          own_belief=lambda now: {**unknown_belief(), **poison},
                          refix_hook_events=[{'event': 'carry_stop_reached', 'sim_s': 12.,
                                              'decide_at_s': 22., 'latch_until_s': 21.8, **poison}])
    a = StopAdapter(own_executor(ctl), condition='peer_nl', origin_s=0.)
    clean_event, = a.poll()
    assert not any(k in json.dumps(clean_event) for k in poison)
    from harness.zone_study_contract import ContractViolation
    with pytest.raises(ContractViolation, match='own_belief'):
        a.own_belief(12.)
    for key in poison:
        for target in ('own_belief', 'decision_window'):
            body = bundled.payload_dict()
            body['decision_window'] = {'kind': 'carry_decision', 'opened_at_sim_s': 12.,
                                       'decide_at_sim_s': 22., 'latch_until_sim_s': 21.8}
            body[target][key] = poison[key]
            with pytest.raises(ProtocolError):
                inputs.PairInputs(body, bundled.wrist_jpeg, bundled.map_png, bundled.pinned)
    ctl.own_belief = lambda now: unknown_belief()
    a.window.on_event(clean_event, origin_s=0.)
    body = bundled.payload_dict()
    body.update(own_belief=a.own_belief(12.), decision_window=a.window.snapshot(12.))
    request = inputs.build_request(inputs.PairInputs(body, bundled.wrist_jpeg, bundled.map_png, bundled.pinned))
    serialized = json.dumps(request)
    assert 'CANARY_GT_ERROR' not in serialized
    assert not any(key in request['messages'][1]['content'] for key in poison)


def test_new_runtime_inherits_the_actual_high_controller_and_registry_pins_it():
    assert issubclass(GatedHighRuntime, HighRuntime)
    b = contract.bundle('no_comm')
    assert b['skill_layer']['bundle_id'] == 'zone-final-pair-highpose-v98'
    assert 'GatedHighRuntime' in b['llm_arm_runtime']
    assert set(decisions.HOOK_EVENTS) == set(hooks.HOOK_EVENTS)


@pytest.mark.parametrize('kind,choice', [(k, c) for k, cs in decisions.HOOK_ACTIONS.items() for c in cs])
def test_reply_choices_use_the_sealed_validator_and_do_not_expand_its_vocabulary(kind, choice):
    from tests.test_pair_llm_status import reply
    bundled, _, _ = make_inputs('no_comm')
    kw = dict(request_id='req_t1', condition='no_comm', actor='r1', order_ids=bundled.order_ids(),
              item_ids=bundled.item_ids(), roles_by_order=bundled.roles_by_order(), vocabulary=bundled.vocabulary(),
              passages=bundled.passages(), location_refs=bundled.location_refs(), robots=('r1', 'r2'))
    action = {'kind': kind, 'choice': choice}
    assert validate_reply(reply(action), **kw)['action'] == action
    for wrong in ({**action, 'choice': 'wait'}, {**action, 'choice': 'give_up'}, {**action, 'rule_would_do': choice}):
        with pytest.raises(ProtocolError):
            validate_reply(reply(wrong), **kw)


@pytest.mark.parametrize('condition', ['rule', 'no_comm', 'peer_nl'])
def test_stop_deadline_is_ten_seconds_from_scheduled_end_not_event(look_team, condition):
    _, ctls = look_team()
    adapters = attach(ctls, condition)
    deliveries = []
    for i in range(701):
        now = i / 10.
        for a in adapters.values():
            for row in a.poll():
                deliveries.append((now, row))
                a.window.on_event(row, origin_s=0.)
        base.run_one(ctls, now)
    carry = [(t, e) for t, e in deliveries if e['detail']['kind'] == 'carry_stop_reached']
    post = [(t, e) for t, e in deliveries if e['detail']['kind'] == 'relook_result']
    assert len(carry) == len(post) == 2
    for delivered, e in carry:
        assert e['sim_s'] == 17.8
        assert delivered == 17.9                       # next-tick delivery
        assert e['detail']['decide_at_s'] == 27.7       # scheduled end 17.7 + 10
        assert e['detail']['latch_until_s'] == 27.5
        assert e['detail']['decide_at_s'] - e['sim_s'] == pytest.approx(9.9)
        assert e['detail']['decide_at_s'] - delivered == pytest.approx(9.8)
    for delivered, e in post:
        assert e['sim_s'] == 52.4 and delivered == 52.5
        assert e['detail']['window_until_s'] == 62.4
    decisions = [r for a in adapters.values() for r in a.decisions]
    assert all(r['decided_by'] == 'rule_default' for r in decisions)
    assert {r['executed_s'] for r in decisions} == {27.7, 62.4}
