"""Approved window-scoped message wake deviation; real scheduler, fake controller only."""
import hashlib
import json
from pathlib import Path
import inspect
import textwrap

import pytest

from harness.pair_llm_decisions import DecisionWindow, HOOK_EVENTS
from tests.pair_llm_fakes import offline_only  # noqa: F401
from tests.pair_llm_window_replay import event, replay

FROZEN = Path(__file__).parent / 'fixtures' / 'pair_llm_3327a0ea'


def scripted_stop(rid, index, body, _):
    return ({'kind': 'release', 'order_id': 'cargoX'} if index == 1 else {'kind': 'continue'}), []


def assert_frozen_commands(data, name):
    expected = (FROZEN / name).read_bytes()
    manifest = json.loads((FROZEN / 'manifest.json').read_text())
    assert manifest['source_sha'] == '3327a0ea686cf15dc56d118fe89bf736b93ba284'
    assert hashlib.sha256(expected).hexdigest() == manifest['files'][name]['sha256']
    assert json.loads(data) and data == expected, 'command trajectory differs from 3327a0ea'


def talk(rid, index, body, _):
    messages = []
    if index == 1 and body['channel']['can_send_to']:
        messages = [{'recipients': body['channel']['can_send_to'], 'reply_to': None,
                     'text': 'ready' if rid == 'r1' else 'checking ' * 35}]
    return {'kind': 'continue'}, messages


@pytest.mark.parametrize('kind', ['carry_stop_reached', 'relook_result'])
def test_text_wakes_inside_each_window_including_text_arriving_during_another_call(tmp_path, kind):
    trial, _ = replay(tmp_path/'new', policy=talk, event_kind=kind)
    old, _ = replay(tmp_path/'old', policy=talk, legacy=True, event_kind=kind)
    for rid in ('r1', 'r2'):
        starts = trial.wakeups(rid)
        assert (12., 'idle') in starts, starts          # event wake, not the 60 s own-job timer
        reads = [r for r in trial.requests if r['robot'] == rid and json.loads(r['user']).get('inbox')]
        assert reads and all(12. < r['sim_s'] < 22. for r in reads)
        assert not [r for r in old.requests if r['robot'] == rid and json.loads(r['user']).get('inbox')]
    # r1's short message arrives while r2 is still thinking its longer first reply.
    first_r2 = next(c for c in trial.scheduler.calls if c.actor == 'r2' and c.started_sim_s == 12.)
    delivered = [m for m in trial.channel.inbox('r2', now_sim_s=24.)]
    assert delivered and delivered[0]['created_at_sim_s'] < first_r2.finished_sim_s


def test_text_outside_a_window_does_not_wake_a_busy_robot(tmp_path):
    def send_immediately(rid, index, body, text):
        return talk(rid, 1 if index == 0 else 2, body, text)
    trial, _ = replay(tmp_path, policy=send_immediately, stop=None, duration=12.)
    assert all(len(trial.wakeups(r)) == 1 for r in ('r1', 'r2'))


@pytest.mark.parametrize('condition', ['rule', 'no_comm'])
def test_rule_and_no_comm_command_bytes_match_3327a0ea(tmp_path, condition):
    new, new_bytes = replay(tmp_path/'new', condition=condition, policy=scripted_stop)
    assert len(json.loads(new_bytes)) == 480
    assert_frozen_commands(new_bytes, condition + '-scheduler.json')
    if new is not None:
        assert any(r['api'] == 'abort' for r in new.dispatch_log)   # the replay's command path actually changes


def test_frozen_trajectory_detects_reviewers_no_comm_wake_delay(tmp_path, monkeypatch):
    from harness import pair_llm_dispatch as mod
    source = textwrap.dedent(inspect.getsource(mod.PairTrial.on_executor_event))
    old = "self.scheduler.trigger(event['robot_id'], 'idle', at=at_s)"
    assert source.count(old) == 1
    source = source.replace(old, "self.scheduler.trigger(event['robot_id'], 'idle', "
                            "at=at_s + (0.1 if self.arm == 'no_comm' else 0.0))")
    namespace = dict(vars(mod))
    exec(compile(source, '<review-wake-delay>', 'exec'), namespace)
    monkeypatch.setattr(mod.PairTrial, 'on_executor_event', namespace['on_executor_event'])
    _, data = replay(tmp_path, condition='no_comm', policy=scripted_stop)
    with pytest.raises(AssertionError, match='command trajectory differs'):
        assert_frozen_commands(data, 'no_comm-scheduler.json')
    before, after = json.loads((FROZEN / 'no_comm-scheduler.json').read_bytes()), json.loads(data)
    first = next((a, b) for a, b in zip(before, after) if a != b)
    assert first[0][0] == first[1][0] == 15.3
    assert first[0][2]['kind'] == 'hold' and first[1][2]['kind'] == 'drive'


@pytest.mark.parametrize('origin', [0., 1.3, 2.6, 7.])
def test_window_times_are_origin_invariant_and_close_at_the_deadline(origin):
    w = DecisionWindow()
    assert w.on_event(event('r1', 'carry_stop_reached', 12., origin=origin,
                           decide_at_s=origin+22., latch_until_s=origin+21.8), origin_s=origin)
    assert w.snapshot(12.) == {'kind': 'carry_decision', 'opened_at_sim_s': 12.,
                               'decide_at_sim_s': 22., 'latch_until_sim_s': 21.8}
    assert not w.is_open(11.9) and w.is_open(21.9) and not w.is_open(22.)
    w.on_event({'event': 'job_failed'}, origin_s=origin)
    assert not w.is_open(15.)


@pytest.mark.parametrize('kind', [k for k in HOOK_EVENTS if k not in ('carry_stop_reached', 'relook_result')])
def test_record_only_events_do_not_open_a_window(kind):
    w = DecisionWindow()
    assert not w.on_event(event('r1', kind, 12.), origin_s=0.)
    assert w.snapshot(12.) is None
