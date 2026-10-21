"""L2 E2E: fake LLM / fake Planner HTTP + fake execution summary (no physics, no network)."""
import copy
import io
import json
import math
import subprocess

import pytest

from harness import e2e_l2 as l2
from harness import e2e_l2_eval as ev

ROOT = l2.Path(l2.__file__).resolve().parents[1]
JPEG = {'r1': b'\xff\xd8r1-first-frame\xff\xd9', 'r2': b'\xff\xd8r2-first-frame\xff\xd9'}


def make_case(seed=8344000, yaw=0.0, r1=(-.9, .2), r2=(1.0, -.3), roles=None):
    return {'plan': {'seed': seed, 'beam_pose': [0.0, 0.0, yaw], 'episode_id': f'ep{seed}',
                     'spawns': {'r1': [*r1, .05, 0.], 'r2': [*r2, .05, 0.]},
                     'roles': roles or {'r1': 'teal', 'r2': 'blue'}, 'object_kind': 'long_beam'},
            'profile': {'p': 1}, 'candidate': 'pairact_p2_r13'}


def reply(act, msg=None, usage=None):
    out = {'act': act, 'message': msg}
    if usage:
        out['usage'] = usage
    return out


def to_peer(robot, body):
    return {'recipients': ['r2' if robot == 'r1' else 'r1'], 'body': body}


class FakeLLM:
    def __init__(self, script):
        self.script, self.seen = script, []

    def __call__(self, robot, dynamic):
        self.seen.append((robot, copy.deepcopy(dynamic)))
        return self.script[(robot, dynamic['round'])]


# --- vendored L1-lite code is byte-identical --------------------------------

def test_l1lite_files_are_vendored_byte_identical():
    for path, blob in l2.L1LITE_SOURCE['blobs'].items():
        got = subprocess.run(['git', '-C', str(ROOT), 'hash-object', path], capture_output=True, text=True)
        assert got.stdout.strip() == blob, path
        at_src = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', f'{l2.L1LITE_SOURCE["sha"]}:{path}'],
                                capture_output=True, text=True)
        assert at_src.stdout.strip() == blob, path   # fails (not skips) if the pinned commit is missing


def test_no_own_channel_class_left():
    src = (ROOT / 'harness/e2e_l2.py').read_text()
    assert 'class L2Channels(Channels)' in src and 'class Channel:' not in src


# --- geometry is eval-only ---------------------------------------------------

def test_ns_beam_is_inadmissible_and_ew_label_follows_yaw():
    assert not l2.case_admissible(make_case(yaw=math.pi / 2))[0]
    assert l2.case_admissible(make_case(yaw=math.radians(59)))[0]
    assert l2.geometry_record(make_case(yaw=0.0))['band_label'] == {'teal': 'west', 'blue': 'east'}
    assert l2.geometry_record(make_case(yaw=math.pi))['band_label'] == {'teal': 'east', 'blue': 'west'}


def test_reference_and_nearer():
    g = l2.geometry_record(make_case())
    assert g['reference_ends'] == {'r1': 'teal', 'r2': 'blue'}
    assert g['nearer_end'] == {'r1': 'teal', 'r2': 'blue'} and not g['nearer_end_conflict']


def test_case_requires_pair_roles():
    with pytest.raises(l2.L2Error):
        l2.geometry_record(make_case(roles={'r1': 'teal', 'r2': 'teal'}))


# --- LLM input has no GT ------------------------------------------------------

def test_brief_has_no_plan_or_geometry():
    case = make_case()
    for cond in l2.CONDITIONS:
        for robot in l2.ROBOTS:
            b = l2.robot_brief(case, robot, cond)
            assert l2.input_leaks(b) == []
            text = json.dumps(b)
            for v in ('-0.9', '0.27', '8344000', 'spawn', 'beam_pose'):
                assert v not in text
            sheet = b['order_sheet']['orders'][0]
            assert sheet['assigned_robot'] is None and 'required_robots' not in sheet


def test_leak_detector_catches_geometry():
    assert l2.input_leaks({'own_observation': {'own_distance_m': 1}}) == ['own_distance_m']


def test_dynamics_have_no_geometry():
    llm = FakeLLM({('r1', 1): reply('end_teal'), ('r2', 1): reply('end_blue')})
    l2.allocate_ends('no_comm', make_case(), ask=llm)
    assert all(l2.input_leaks(d) == [] for _, d in llm.seen)


def test_env_gate_default_off():
    assert not l2.enabled({})
    with pytest.raises(l2.L2Error):
        l2.require_enabled({})


# --- protocol over the L1-lite Channels -------------------------------------

def test_no_comm_split_success_and_no_inbox():
    llm = FakeLLM({('r1', 1): reply('end_teal'), ('r2', 1): reply('end_blue')})
    rec = l2.allocate_ends('no_comm', make_case(), ask=llm)
    assert rec['decisions'] == {'r1': 'teal', 'r2': 'blue'} and rec['success_eligible']
    assert all('inbox' not in d for _, d in llm.seen)   # L1-lite Channels: no inbox key in no_comm
    assert [c['id'] for c in llm.seen[0][1]['candidates']] == ['solo_carry', 'end_teal', 'end_blue']


def test_no_comm_message_dropped():
    rec = l2.allocate_ends('no_comm', make_case(), ask=FakeLLM({
        ('r1', 1): reply('end_teal', to_peer('r1', {'text': 'teal'})), ('r2', 1): reply('end_blue')}))
    assert rec['utterances'] == 0 and rec['message_drops'][0]['reason'] == 'L2_MESSAGE_NOT_ALLOWED'


def test_duplicate_end_not_executable():
    rec = l2.allocate_ends('no_comm', make_case(), ask=FakeLLM({('r1', 1): reply('end_teal'),
                                                                ('r2', 1): reply('end_teal')}))
    assert 'L2_DUPLICATE_END' in rec['errors'] and not rec['success_eligible']
    with pytest.raises(l2.L2Error) as e:
        l2.build_l2_case(make_case(), rec, arm='student')
    assert e.value.code == 'L2_NOT_EXECUTABLE'


def test_solo_fails_closed():
    rec = l2.run_stage('no_comm', make_case(), ask=FakeLLM({('r1', 1): reply('solo_carry')}))
    assert rec['fatal'] and rec['errors'] == ['L2_SOLO_DECISION'] and rec['need_partner'] == {'r1': False}


def test_invalid_answers():
    assert l2.run_stage('no_comm', make_case(), ask=FakeLLM({('r1', 1): reply('end_west')}))['errors'] == ['L2_INVALID_END']
    assert l2.run_stage('no_comm', make_case(), ask=FakeLLM({('r1', 1): {'act': 'end_teal'}}))['errors'] == ['L2_INVALID_DECISION']


def test_structured_l2_enum_and_round_snapshot():
    s = lambda r, act, end: to_peer(r, {'act': act, 'end': end})
    llm = FakeLLM({('r1', 1): reply('end_teal', s('r1', 'claim_end', 'teal')),
                   ('r2', 1): reply('end_teal', s('r2', 'claim_end', 'teal')),
                   ('r1', 2): reply('end_teal', s('r1', 'claim_end', 'teal')),
                   ('r2', 2): reply('end_blue', s('r2', 'ack', 'blue'))})
    rec = l2.allocate_ends('structured', make_case(), ask=llm)
    assert rec['rounds'] == 2 and rec['success_eligible'] and rec['utterances'] == 4
    r2 = {d['round']: d for r, d in llm.seen if r == 'r2'}
    assert r2[1]['inbox'] == [] and r2[2]['inbox'][0]['body'] == {'act': 'claim_end', 'end': 'teal'}


def test_structured_rejects_l1lite_slot_enum_and_free_text():
    for body in ({'act': 'claim_slot', 'slot': 'left'}, {'text': 'teal please'}, {'act': 'claim_end', 'end': 'west'}):
        llm = FakeLLM({('r1', 1): reply('end_teal', to_peer('r1', body)), ('r2', 1): reply('end_blue'),
                       ('r1', 2): reply('end_teal'), ('r2', 2): reply('end_blue')})
        rec = l2.allocate_ends('structured', make_case(), ask=llm)
        assert 'L2_MESSAGE_INVALID' in rec['errors'] and not rec['success_eligible'], body


def test_peer_en_uses_l1lite_free_text_rules():
    long = to_peer('r1', {'text': 'x' * 401})
    llm = FakeLLM({('r1', 1): reply('end_teal', long), ('r2', 1): reply('end_blue', to_peer('r2', {'text': '파랑'})),
                   ('r1', 2): reply('end_teal'), ('r2', 2): reply('end_blue')})
    rec = l2.allocate_ends('peer_en', make_case(), ask=llm)
    assert 'L2_MESSAGE_INVALID' in rec['errors']
    assert sum(m['language_slip'] for m in rec['messages']) == 1


def test_peer_en_three_rounds_then_duplicate():
    t = lambda r: to_peer(r, {'text': 'I will take the teal end.'})
    rec = l2.allocate_ends('peer_en', make_case(), ask=FakeLLM(
        {(r, k): reply('end_teal', t(r)) for r in l2.ROBOTS for k in (1, 2, 3)}))
    assert rec['rounds'] == 3 and 'L2_DUPLICATE_END' in rec['errors'] and rec['utterances'] == 6


def test_leader_en_assign_ack_and_failures():
    case = make_case(seed=8344000)   # leader r1
    llm = FakeLLM({('r1', 1): reply('leader_teal', to_peer('r1', {'text': 'I take teal, you take blue.'})),
                   ('r2', 2): reply('ack_assignment', to_peer('r2', {'text': 'Ack, blue.'}))})
    rec = l2.allocate_ends('leader_en', case, ask=llm)
    assert rec['decisions'] == {'r1': 'teal', 'r2': 'blue'} and rec['success_eligible']
    assert llm.seen[1][1]['role'] == 'follower' and llm.seen[1][1]['leader_id'] == 'r1'
    assert l2.run_stage('leader_en', case, ask=FakeLLM({('r1', 1): reply('leader_teal')}))['errors'] == ['L2_LEADER_UNASSIGNED']
    rec = l2.run_stage('leader_en', case, ask=FakeLLM({
        ('r1', 1): reply('leader_blue', to_peer('r1', {'text': 'You hold teal.'})), ('r2', 2): reply('ack_assignment')}))
    assert 'L2_LEADER_ACK_MISSING' in rec['errors']


# --- binding --------------------------------------------------------------

def test_build_case_changes_only_roles():
    case = make_case()
    rec = l2.allocate_ends('no_comm', case, ask=FakeLLM({('r1', 1): reply('end_blue'), ('r2', 1): reply('end_teal')}))
    out = l2.build_l2_case(case, rec, arm='student')
    assert out['plan']['roles'] == {'r1': 'blue', 'r2': 'teal'}
    rest = copy.deepcopy(out)
    del rest['l2_admin']
    rest['plan']['roles'] = case['plan']['roles']
    assert rest == case
    with pytest.raises(l2.L2Error):
        l2.build_l2_case(case, rec, arm='teacher')


# --- live boundary with a fake Planner HTTP ---------------------------------

class FakeHTTP:
    """Stands in for the relay: returns scripted chat-completion JSON, records requests."""

    def __init__(self, contents, provider='CoreWeave', status=200):
        self.contents, self.provider, self.status, self.requests = list(contents), provider, status, []

    def __call__(self, req, timeout=None):
        self.requests.append(json.loads(req.data))
        body = json.dumps({'provider': self.provider, 'usage': {'prompt_tokens': 900, 'completion_tokens': 30},
                           'choices': [{'finish_reason': 'stop',
                                        'message': {'content': json.dumps(self.contents.pop(0))}}]}).encode()
        resp = io.BytesIO(body)
        resp.status = self.status
        return _Ctx(resp)


class _Ctx:
    def __init__(self, r):
        self.r = r

    def __enter__(self):
        return self.r

    def __exit__(self, *a):
        return False


def test_planner_ask_live_path(tmp_path):
    case = make_case()
    http = FakeHTTP([{'act': 'end_teal', 'message': None}, {'act': 'end_blue', 'message': None}])
    planners = l2.make_planners('http://127.0.0.1:9/v1/chat/completions', tmp_path / 'llm', case, 'no_comm',
                                run_id='t', world_id=0, http_open=http)
    ask = l2.planner_ask(planners, l2.first_frames(JPEG, 0))
    rec = l2.allocate_ends('no_comm', case, ask=ask)
    assert rec['success_eligible'] and rec['usage'][0] == {'robot': 'r1', 'round': 1, 'prompt_tokens': 900,
                                                           'completion_tokens': 30}
    req = http.requests[0]
    assert req['model'] == 'gemma-4-31b-it'
    static = json.loads(req['messages'][1]['content'])
    assert l2.input_leaks(static) == [] and static['robot'] == 'r1'
    image = req['messages'][2]['content'][1]['image_url']['url']
    assert image.startswith('data:image/jpeg;base64,')
    # archive keeps the image hash, not the pixels; no key-like header is archived
    archived = (tmp_path / 'llm' / 'r1' / '00001.request.json').read_text()
    assert 'base64' not in archived and 'removed' in archived and 'Authorization' not in archived
    ledger = l2.planner_ledger(planners)
    assert ledger['r1'][0]['image_count'] == 1 and ledger['r1'][0]['accepted']


def test_planner_rejection_is_no_decision(tmp_path):
    case = make_case()
    http = FakeHTTP([{'act': 'end_teal', 'message': None}], provider='DeepInfra')
    planners = l2.make_planners('http://127.0.0.1:9/v1/chat/completions', tmp_path / 'llm', case, 'no_comm',
                                run_id='t', world_id=0, http_open=http)
    rec = l2.run_stage('no_comm', case, ask=l2.planner_ask(planners, l2.first_frames(JPEG, 0)))
    assert rec['fatal'] and rec['errors'] == ['L2_NO_DECISION']


def test_first_frames_need_both_robots():
    with pytest.raises(l2.L2Error):
        l2.first_frames({'r1': JPEG['r1']}, 0)


def test_check_relay():
    good = {'upstream': dict(l2.PLANNER_PIN), 'alerts': [], 'balance_usd': 5}
    assert l2.check_relay('http://127.0.0.1:8080/v1/chat/completions', identity_open=lambda u: good, environ={})
    with pytest.raises(l2.L2Error) as e:
        l2.check_relay('https://openrouter.ai/api/v1/chat/completions', identity_open=lambda u: good, environ={})
    assert e.value.code == 'L2_SSH_LOOPBACK_RELAY_ONLY'
    bad = dict(good, upstream=dict(l2.PLANNER_PIN, provider='DeepInfra'))
    with pytest.raises(l2.L2Error):
        l2.check_relay('http://127.0.0.1:8080/v1/chat/completions', identity_open=lambda u: bad, environ={})
    with pytest.raises(l2.L2Error) as e:
        l2.check_relay('http://127.0.0.1:8080/v1/chat/completions', identity_open=lambda u: good,
                       environ={'OPENROUTER_API_KEY': 'x'})
    assert e.value.code == 'L2_VM_CREDENTIAL_ENV_FORBIDDEN' and 'x' not in str(e.value).split(':', 1)[1]


def test_no_key_literal_in_l2_code():
    for path in ('harness/e2e_l2.py', 'harness/e2e_l2_eval.py', 'scripts/run_e2e_l2.py'):
        text = (ROOT / path).read_text()
        assert 'sk-' not in text and 'Bearer' not in text and 'Authorization' not in text


# --- evaluator --------------------------------------------------------------

def _ok_record(case, a='end_teal', b='end_blue'):
    return l2.allocate_ends('no_comm', case, ask=FakeLLM({
        ('r1', 1): reply(a, usage={'prompt_tokens': 1000, 'completion_tokens': 100}),
        ('r2', 1): reply(b, usage={'prompt_tokens': 1000, 'completion_tokens': 100})}))


def fake_summary(seed, *, carry=True, teacher_steps=0, student=True):
    s = {'worlds': [{'world': 0, 'seed': seed, 'carry_success': carry, 'carry_failure': None if carry else 'drop',
                     **({'teacher_steps': teacher_steps, 'student_funnel': {'place': carry}} if student else {})}]}
    if student:
        s['student_eval'] = {'mode': 'pairact_r1_student_eval_v1'}
    return s


def test_seed_success_student_and_cost():
    case = make_case()
    r = ev.seed_result(_ok_record(case), l2.geometry_record(case), fake_summary(8344000), arm='student',
                       prices=l2.PRICE_USD_PER_MILLION)
    assert r['success'] and r['llm']['assignment_match'] and r['llm']['decisions_west_east'] == {'r1': 'west', 'r2': 'east'}
    assert r['llm']['usd'] == round((2000 * .1 + 200 * .34) / 1e6, 6)


def test_contamination_and_teacher_fallback_label():
    case = make_case()
    rec, g = _ok_record(case), l2.geometry_record(case)
    assert ev.seed_result(rec, g, fake_summary(8344000, teacher_steps=3), arm='student')['failure_stage'] == 'student_contaminated'
    assert not ev.seed_result(rec, g, fake_summary(8344000, student=False), arm='student')['success']
    t = ev.seed_result(rec, g, fake_summary(8344000, student=False), arm='teacher_fallback')
    assert t['success'] and 'NOT a learned result' in t['arm_label']


def test_llm_failure_not_executed_and_swap_measured():
    case = make_case()
    rec = l2.run_stage('no_comm', case, ask=FakeLLM({('r1', 1): reply('solo_carry')}))
    r = ev.seed_result(rec, l2.geometry_record(case), fake_summary(8344000), arm='student')
    assert not r['executed'] and r['failure_stage'] == 'llm'
    swapped = ev.llm_metrics(_ok_record(case, 'end_blue', 'end_teal'), l2.geometry_record(case))
    assert not swapped['assignment_match'] and not swapped['conflict']


def test_aggregate():
    case = make_case()
    rec, g = _ok_record(case), l2.geometry_record(case)
    rows = [ev.seed_result(rec, g, fake_summary(8344000), arm='student'),
            ev.seed_result(rec, g, fake_summary(8344000, carry=False), arm='student'),
            ev.seed_result(rec, g, {'worlds': []}, arm='student')]
    agg = ev.aggregate(rows)
    assert agg[0]['report'] == '1/3' and agg[0]['failure_stage'] == {'success': 1, 'execution': 1, 'not_executed': 1}


def test_hallucination_flags():
    rec = {'messages': [{'sender': 'r1', 'body': {'text': 'I hold the teal end, about 1.2 m away.'}},
                        {'sender': 'r2', 'body': {'text': 'Then I take the west end.'}}]}
    kinds = sorted((f['robot'], f['kind']) for f in ev.hallucination_flags(rec))
    assert kinds == [('r1', 'stated_distance'), ('r2', 'foreign_end')]
    m = ev.llm_metrics(dict(rec, decisions={}), l2.geometry_record(make_case()))
    assert m['hallucination_n'] == 1
