"""llm_memory v1: own decision log, rejection feedback, peer window marks (no physics, no provider)."""
import copy
import json
from types import SimpleNamespace
import pytest
from harness import e2e_llm_memory as lm
from harness import e2e_s4_live as live
from harness.s4_event_policy import Options
from tests.test_e2e_vote_ref import opened, RH
from tests.test_pair_llm_s4_host import setup_data, no_external_work  # noqa: F401 (fixtures)

REC = [
    dict(call_id='c1', t=537.5, did='GO', seg=0, epoch=1, accepted=True, reason=None),
    dict(call_id='c2', t=543.85, did='ACK', seg=0, epoch=1, accepted=True, reason=None),
    dict(call_id='c3', t=559.6, did='ACK', seg=1, epoch=1, accepted=False, reason='CAPTURED_PEER_GO_REQUIRED'),
    dict(call_id='c4', t=570., did='GO', seg=1, epoch=1, accepted=True, reason=None),
]
WINDOWS = [(530., ['order-5', RH, 1, 0]), (555., ['order-5', RH, 1, 1])]


def test_log_is_causal_bounded_and_feedback_only_after_rejection():
    log = lm.decision_log(REC, 560.)
    assert [r['choice'] for r in log] == ['GO', 'ACK', 'ACK'] and log[-1] == dict(
        sim_s=559.6, kind='route_vote', choice='ACK', result='rejected', seg=1, epoch=1, why='CAPTURED_PEER_GO_REQUIRED')
    assert 'rejected: CAPTURED_PEER_GO_REQUIRED' in lm.feedback(log) and 'own GO' in lm.feedback(log)
    assert lm.feedback(lm.decision_log(REC, 580.)) is None        # latest decision accepted
    many = [dict(call_id=f'x{i}', t=float(i), did='continue', seg=None, epoch=None, accepted=True, reason=None) for i in range(20)]
    assert len(lm.decision_log(many, 100.)) == lm.LOG_N and lm.decision_log(many, 2.5)[-1]['sim_s'] == 2.


def test_peer_marks_flag_earlier_window_without_touching_text():
    reports = [dict(message_id='w1-r2-2', created_at_sim_s=538.7, body=dict(text='I have a grip on the beam; GO.')),
               dict(message_id='w1-r2-9', created_at_sim_s=561., body=dict(text='ok')),
               dict(message_id='w1-r2-0', created_at_sim_s=10., body=dict(text='hi'))]
    marks = lm.peer_marks(reports, WINDOWS, ['order-5', RH, 1, 1])
    assert marks['w1-r2-2'] == dict(seg=0, grip_epoch=1, current=False)
    assert marks['w1-r2-9'] == dict(seg=1, grip_epoch=1, current=True)
    assert marks['w1-r2-0'] == dict(seg=None, grip_epoch=None, current=False)
    assert lm.peer_marks(None, WINDOWS, None) == {}


def test_reason_code_and_attempt_parsing():
    assert lm.code_of('CAPTURED_PEER_GO_REQUIRED') == 'CAPTURED_PEER_GO_REQUIRED'
    assert lm.code_of('ROUTE_VOTE: CLOSED_SCHEMA_REQUIRED') == 'ROUTE_VOTE: CLOSED_SCHEMA_REQUIRED'
    assert lm.code_of("not a mapping ['x']") == 'INVALID_REPLY'
    assert lm.attempt_of(dict(kind='route_vote', choice='ACK', dialogue=dict(seg=1, grip_epoch=1))) == ('ACK', 1, 1)
    assert lm.attempt_of('junk') == ('invalid', None, None)


def project(host, memory, option):
    call = SimpleNamespace(call_id='lm-r1', actor='r1', started_sim_s=6.)
    host.trial.snapshot(call)
    original = host.trial.prepare_call(call).request
    return live.project(original, options=Options(True, True, 'en'), llm_memory=option, memory=memory)


def test_projection_off_is_identical_and_on_adds_only_memory_fields(tmp_path, setup_data):
    host, d = opened(tmp_path, setup_data, 'off')
    memory = dict(decisions=[dict(call_id='c', t=5.5, did='ACK', seg=0, epoch=1, accepted=False, reason='CAPTURED_PEER_GO_REQUIRED')],
                  windows=lm.windows_of(d))
    off = project(host, None, 'off')
    on = project(host, memory, 'v1')
    base, new = json.loads(off['messages'][1]['content']), json.loads(on['messages'][1]['content'])
    assert on['messages'][0]['content'] == off['messages'][0]['content'] + lm.PROMPT_ADD + lm.PRIORITY_RULES
    assert new['own_decision_log'][0]['why'] == 'CAPTURED_PEER_GO_REQUIRED' and 'decision_feedback' in new
    for report in new['peer_reports']:
        assert report.pop('window')['current'] in (True, False)
        for key in ('sent_window', 'received_at_sim_s', 'previous_segment'):
            report.pop(key)
    for key in ('own_decision_log', 'decision_feedback'):
        new.pop(key)
    lm.filter_actions(base)
    assert new == base                       # peer text untouched, protocol candidates narrowed
    with pytest.raises(ValueError):
        project(host, memory, 'v9')
    with pytest.raises(ValueError):
        project(host, None, 'v1')


def test_commands_option_fills_history_from_own_issued_commands():
    mem = lm.Memory()
    for i in range(40):
        mem.command('r1', 1. + i * .05, dict(kind='arm', servo_id=3, pulse=1500))
    mem.command('r1', 10., dict(kind='mecanum', vx=1., duration_s=.5))
    entries = mem.command_entries('r1', 10.2)
    assert [e['kind'] for e in entries] == ['arm', 'mecanum']
    assert entries[0]['arguments'] == dict(servo_id=3, pulse=1500)
    assert entries[1]['arguments'] == dict(vx=1., duration_s=.5)  # requested, never executed duration
    assert mem.command_entries('r2', 10.) == []
    body = dict(sim_time_s=10.2, dialogue=dict(key=None), peer_reports=[], own_command_history=[])
    lm.apply(body, 's', dict(decisions=[], windows=[], commands=entries), commands=True)
    assert body['own_command_history'] == entries


def test_bundles_v330_v331_v332(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle, ROOT
    from harness.e2e_runtime_registration import require_current
    from harness.e2e_post_relook_stack import KEYS
    args, kw = [], {}
    def captured(*a, **k):
        args.extend(a); kw.update(k); return bundle(*a, **k)
    monkeypatch.setattr(p, 'bundle', captured)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1', 276, 'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1', relook_giveup='dev_light_rest_v1', post_relook='carry_nominal_v1')
    bundles = []
    for vote, option, num in (('off', 'v1', 330), ('v1', 'v1', 331), ('off', 'v1_commands', 332)):
        parent = 324
        stack = ('off', 'off', vote, 'shadow_axes_v1', 'phase_v1')
        b = bundle(*args, **kw, **dict(zip(KEYS, stack)), llm_memory=option)
        bundles.append(b)
        assert b['execution_bundle_id'] == f'e2e18-v{num}' and b['llm_memory_parent'] == f'e2e18-v{parent}'
        assert b['e2e_options']['llm_memory'] == option and 'harness/e2e_llm_memory.py' in b['source_sha256']
        require_current(b, ROOT)
        bad = copy.deepcopy(b); bad['e2e_options']['llm_memory'] = 'off'
        with pytest.raises(ValueError):
            require_current(bad, ROOT)
    a, b = (dict(x['e2e_options']) for x in bundles[:2])
    assert a.pop('vote_ref') == 'off' and b.pop('vote_ref') == 'v1' and a == b
    with pytest.raises(ValueError):
        bundle(*args, **kw, llm_memory='v1')                         # needs the v324/v327 stack parent


def test_live_rejection_is_remembered_and_shown_in_the_next_call(tmp_path, setup_data):
    from types import SimpleNamespace as NS
    from harness import e2e_dialogue as dialogue
    from tests.test_e2e_dialogue import build, claim_phase, trigger
    from tests.test_pair_llm_s4_host import advance
    from harness.zone_final_pair_binding import bind

    def factory(*args, **kwargs):
        for link in kwargs['links'].values():
            link.inner.study_options = Options(True, True, 'en')
        host = live.Host(*args, **kwargs)
        host.trial.llm_memory = 'v1'
        return host
    host, inner, wire = bind(build, s4=NS(Host=factory))(tmp_path, setup_data, fault='invalid_ack')
    claim_phase(host, inner)
    gate = host.trial.dialogue
    t = host.trial.scheduler.clock
    gate.begin_epoch(order_id='order-5', route_hash=gate.proposal['route']['route_hash'], grip_epoch=1, seg=0, now=t)
    trigger(host, inner, dialogue.PAIR, t)
    trigger(host, inner, dialogue.PAIR, t + 4)
    advance(host, inner, t + 8, t + 13)
    assert host.trial.memory.rejections, 'rejected reply was not recorded'
    users = [json.loads(r['user']) for r in host.trial.requests if r['robot'] == 'r1']
    logs = [u['own_decision_log'] for u in users if 'own_decision_log' in u]
    assert any(e['result'] == 'rejected' and 'why' in e for log in logs for e in log)
    assert any('decision_feedback' in u for u in users)


@pytest.mark.parametrize('vote_ref', [False, True])
def test_claim_is_not_a_candidate_after_claim_and_each_segment_needs_go(vote_ref):
    body = dict(robot_id='r1', dialogue=dict(approved=True, own_claim=True, key=WINDOWS[1][1],
        own_go_sent=False, own_ack_sent=False, peer_go_ref=None), peer_reports=[],
        action_message_contract=dict(actions=[dict(kind='continue'), dict(kind='claim'),
            dict(kind='approve_route'), dict(kind='route_vote', choice=['GO', 'ACK'],
                **({'vote_ref': 'v123456'} if vote_ref else {'seg': 1, 'grip_epoch': 1}))]))
    original = copy.deepcopy(body)
    lm.filter_actions(body)
    assert [a['kind'] for a in body['action_message_contract']['actions']] == ['continue', 'route_vote']
    assert body['action_message_contract']['actions'][1]['choice'] == ['GO']
    assert body['dialogue'] == original['dialogue']
    assert 'already claimed' in lm.HINTS['CURRENT_APPROVED_OWN_ROLE_CLAIM_REQUIRED']
    body = copy.deepcopy(original)
    body['dialogue'].update(own_go_sent=True, peer_go_ref='current-peer-go')
    lm.filter_actions(body)
    assert body['action_message_contract']['actions'][1]['choice'] == ['ACK']
    body['dialogue']['own_ack_sent'] = True
    lm.filter_actions(body)
    assert body['action_message_contract']['actions'] == [dict(kind='continue')]


def test_delayed_peer_message_keeps_both_send_and_receive_windows_and_exact_body():
    mem = lm.Memory()
    report = dict(message_id='m1', created_at_sim_s=538.7, body={'text': 'GO.'})
    mem.sent_keys['m1'] = WINDOWS[0][1]
    mem.receive('r1', report, 556., WINDOWS[1][1])
    body = dict(sim_time_s=557., dialogue=dict(key=WINDOWS[1][1]), peer_reports=[copy.deepcopy(report)])
    lm.apply(body, '', dict(decisions=[], windows=WINDOWS, sent_keys=mem.sent_keys, receipts=mem.receipts['r1']))
    shown = body['peer_reports'][0]
    assert shown['body'] == report['body']
    assert shown['window'] == dict(seg=1, grip_epoch=1, current=True)
    assert shown['sent_window'] == dict(seg=0, grip_epoch=1, current=False)
    assert shown['received_at_sim_s'] == 556. and shown['previous_segment']
    assert mem.receipts['r2'] == {}


def test_short_vote_rejection_has_captured_segment_and_command_directions_stay_distinct():
    mem = lm.Memory()
    mem.reject('c1', 'r1', dict(action=dict(kind='route_vote', choice='ACK', vote_ref='vbadbad')),
               'VOTE_REF_MISMATCH', dict(view=dict(key=WINDOWS[1][1])))
    assert mem.rejections['c1']['seg'] == 1 and mem.rejections['c1']['epoch'] == 1
    for i, turn in enumerate((1., -1., 1., -1.)):
        mem.command('r1', i, dict(kind='mecanum', forward=0., left=0., turn=turn, duration_s=.1))
    entries = mem.command_entries('r1', 2.)
    assert [e['arguments']['turn'] for e in entries] == [1., -1., 1.]
    for i in range(100):
        mem.command('r1', i + 5, dict(kind='arm', servo_id=3, pulse=1000+i))
    assert len(mem.commands['r1']) == 64 and len(mem.command_entries('r1', 200.)) == lm.COMMAND_N
    assert mem.command_entries('r2', 200.) == []


@pytest.mark.parametrize('arm,seed', [('peer_ko',61001), ('structured',61001),
                                     ('leader_ko',61002), ('no_comm',61001)])
def test_memory_is_applied_to_all_conditions_without_cross_robot_data(tmp_path, setup_data, arm, seed):
    from tests.test_e2e_dialogue import build, claim_phase
    from harness.zone_final_pair_binding import bind
    def factory(*args, **kwargs):
        for link in kwargs['links'].values():
            link.inner.study_options = Options(True, True, 'en')
        host = live.Host(*args, **kwargs)
        host.trial.llm_memory = 'v1'
        return host
    host, inner, wire = bind(build, s4=SimpleNamespace(Host=factory))(tmp_path, setup_data, arm=arm, seed=seed)
    claim_phase(host, inner)
    requests = [json.loads(r['user']) for r in host.trial.requests]
    assert requests and all('own_decision_log' in r for r in requests)
    if arm == 'no_comm':
        assert all(r['peer_reports'] is None for r in requests)
        assert all(r['action_message_contract']['actions'] == [dict(kind='continue')] for r in requests)
        assert all(not r for r in host.trial.memory.receipts.values())
    else:
        assert any(host.trial.memory.receipts.values())
        for r in requests:
            for message in r['peer_reports'] or ():
                assert r['robot_id'] in message['recipients'] and message['received_at_sim_s'] <= r['sim_time_s']


@pytest.mark.parametrize('vote_ref', [False, True])
def test_real_call0021_reconstruction_removes_repeated_claim_and_stale_ack(vote_ref):
    from pathlib import Path
    from harness import e2e_vote_ref as vr
    fixture = json.loads((Path(__file__).resolve().parents[1] /
        'experiments/2026-10-13-e2e18-llmmemory/call-0021-fixture.json').read_text())
    body, system = fixture['body'], fixture['system']
    assert body['dialogue']['own_claim'] and not body['dialogue']['own_go_sent']
    assert fixture['saved_memory'][-1]['why'] == 'CURRENT_APPROVED_OWN_ROLE_CLAIM_REQUIRED'
    rows = [dict(t=r['t'], did=r['did'], seg=r.get('seg'), epoch=r.get('epoch'),
                 accepted=r['result']=='accepted', reason=r.get('why')) for r in fixture['saved_memory']]
    reports = copy.deepcopy(body['peer_reports'])
    if vote_ref:
        body['dialogue']['vote_ref'] = vr.ref_for(body['dialogue']['key'])
        system = vr.prompt(body, system)
    prompt = lm.apply(body, system, dict(decisions=rows, windows=[]))
    actions = body['action_message_contract']['actions']
    assert [a['kind'] for a in actions] == ['continue', 'route_vote']
    assert actions[1]['choice'] == ['GO']
    assert 'already claimed' in body['decision_feedback']
    assert 'Rules, in priority order' in prompt
    assert all(a['body']==b['body'] for a,b in zip(reports,body['peer_reports']))


def test_replay_rejects_paid_relay_before_any_post(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from harness import zone_study_llm_transport as transport
    path = Path(__file__).resolve().parents[1]/'experiments/2026-10-13-e2e18-llmmemory/replay_memory.py'
    spec = importlib.util.spec_from_file_location('llm_memory_replay',path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    class Opener:
        def open(self, target, **kwargs):
            from io import BytesIO
            assert isinstance(target,str) and target.endswith('/identity'), 'unexpected POST'
            return BytesIO(json.dumps(dict(driver_profile='study_gemma4_31b_v1', single_model=True,
                upstream='openrouter_v1', runtime=dict(provider='openrouter'))).encode())
    monkeypatch.setattr(transport,'no_redirect_opener',lambda:Opener())
    with pytest.raises(ValueError,match='PAID_OR_UNKNOWN_RELAY'):
        module.run(tmp_path,10,1,proxy_url='http://127.0.0.1:18424/v1/chat/completions')
