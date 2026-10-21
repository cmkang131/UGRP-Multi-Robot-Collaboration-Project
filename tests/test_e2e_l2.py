"""L2 E2E: fake LLM + fake execution summary (no physics, no HTTP)."""
import copy
import math

import pytest

from harness import e2e_l2 as l2
from harness import e2e_l2_eval as ev


def make_case(seed=8343000, yaw=0.0, r1=(-.9, .2), r2=(1.0, -.3), roles=None):
    return {'plan': {'seed': seed, 'beam_pose': [0.0, 0.0, yaw], 'episode_id': f'ep{seed}',
                     'spawns': {'r1': [*r1, .05, 0.], 'r2': [*r2, .05, 0.]},
                     'roles': roles or {'r1': 'teal', 'r2': 'blue'}, 'object_kind': 'long_beam'},
            'profile': {'p': 1}, 'candidate': 'pairact_p2_r13'}


def reply(end=None, msg=None, solo=False, usage=None):
    out = {'need_partner': not solo, 'act': 'solo_carry' if solo else end, 'message': msg}
    if usage:
        out['usage'] = usage
    return out


def to_peer(robot, body):
    return {'to': ['r2' if robot == 'r1' else 'r1'], 'body': body}


class FakeLLM:
    """Scripted per (robot, round) replies; records every dynamic it saw."""

    def __init__(self, script):
        self.script, self.seen = script, []

    def __call__(self, robot, dynamic):
        self.seen.append((robot, copy.deepcopy(dynamic)))
        value = self.script[(robot, dynamic['round'])]
        return value(dynamic) if callable(value) else value


# --- geometry -------------------------------------------------------------

def test_east_west_mapping_follows_yaw():
    assert l2.end_to_band(make_case(yaw=0.0)['plan']) == {'west': 'teal', 'east': 'blue'}
    assert l2.end_to_band(make_case(yaw=math.pi)['plan']) == {'west': 'blue', 'east': 'teal'}


def test_north_south_beam_is_inadmissible():
    ok, why = l2.case_admissible(make_case(yaw=math.pi / 2))
    assert not ok and 'north-south' in why
    with pytest.raises(l2.L2Error) as e:
        l2.end_to_band(make_case(yaw=math.pi / 2)['plan'])
    assert e.value.code == 'L2_CASE_EAST_WEST_AMBIGUOUS'
    assert l2.case_admissible(make_case(yaw=math.radians(59)))[0]


def test_reference_and_distances():
    g = l2.geometry_record(make_case())
    assert g['reference_ends'] == {'r1': 'west', 'r2': 'east'}
    assert g['nearer_end'] == {'r1': 'west', 'r2': 'east'} and not g['nearer_end_conflict']
    assert g['min_total_distance_ends'] == {'r1': 'west', 'r2': 'east'}
    assert g['own_distances']['r1']['west'] == round(math.dist((-.9, .2), (-.27, 0)), 2)


def test_case_requires_pair_roles():
    bad = make_case(roles={'r1': 'teal', 'r2': 'teal'})
    with pytest.raises(l2.L2Error):
        l2.geometry_record(bad)


# --- briefs ---------------------------------------------------------------

def test_brief_has_only_own_observation():
    case = make_case()
    for robot in l2.ROBOTS:
        b = l2.robot_brief(case, robot, 'peer_en')
        assert b['own_observation']['own_distance_m'] == l2.own_distances(case['plan'], robot)
        assert not l2.brief_has_peer_data(b, case)
        text = repr(b)
        assert 'teal' not in text and 'blue' not in text   # band colours never shown
        sheet = b['order_sheet']['orders'][0]
        assert sheet['assigned_robot'] is None and 'required_robots' not in sheet


def test_leader_role_only_in_leader_condition():
    case = make_case(seed=8343001)
    assert l2.robot_brief(case, 'r2', 'leader_en')['role'] == 'leader'
    assert l2.robot_brief(case, 'r2', 'peer_en')['role'] == 'worker'


def test_env_gate_default_off():
    assert not l2.enabled({})
    with pytest.raises(l2.L2Error):
        l2.require_enabled({})
    assert l2.enabled({'E2E_L2': 'on_v1'})


# --- protocol -------------------------------------------------------------

def test_no_comm_split_success():
    llm = FakeLLM({('r1', 1): reply('end_west', usage={'prompt_tokens': 100, 'completion_tokens': 10}),
                   ('r2', 1): reply('end_east')})
    rec = l2.allocate_ends('no_comm', make_case(), ask=llm)
    assert rec['decisions'] == {'r1': 'west', 'r2': 'east'} and rec['success_eligible']
    assert rec['utterances'] == 0 and all(not d['inbox'] for _, d in llm.seen)
    assert {c['id'] for c in llm.seen[0][1]['candidates']} == {'solo_carry', 'end_west', 'end_east'}


def test_no_comm_message_is_dropped_not_sent():
    msg = to_peer('r1', {'text': 'I take west'})
    rec = l2.allocate_ends('no_comm', make_case(), ask=FakeLLM({('r1', 1): reply('end_west', msg),
                                                                ('r2', 1): reply('end_east')}))
    assert rec['utterances'] == 0 and rec['message_drops'][0]['reason'] == 'L2_MESSAGE_NOT_ALLOWED'


def test_no_comm_duplicate_end_not_executable():
    rec = l2.allocate_ends('no_comm', make_case(), ask=FakeLLM({('r1', 1): reply('end_west'),
                                                                ('r2', 1): reply('end_west')}))
    assert 'L2_DUPLICATE_END' in rec['errors'] and not rec['success_eligible'] and not rec['fatal']
    with pytest.raises(l2.L2Error) as e:
        l2.build_l2_case(make_case(), rec, arm='student')
    assert e.value.code == 'L2_NOT_EXECUTABLE'


def test_solo_decision_fails_closed():
    with pytest.raises(l2.L2Error) as e:
        l2.allocate_ends('no_comm', make_case(), ask=FakeLLM({('r1', 1): reply(solo=True)}))
    assert e.value.code == 'L2_SOLO_DECISION' and e.value.record['fatal']
    assert e.value.record['need_partner'] == {'r1': False} and not e.value.record['success_eligible']


def test_need_partner_act_mismatch_is_invalid():
    bad = {'need_partner': False, 'act': 'end_west', 'message': None}
    rec = l2.run_stage('no_comm', make_case(), ask=FakeLLM({('r1', 1): bad}))
    assert rec['fatal'] and 'L2_INVALID_DECISION' in rec['errors']


def test_unknown_candidate_and_bad_keys():
    rec = l2.run_stage('no_comm', make_case(), ask=FakeLLM({('r1', 1): reply('end_north')}))
    assert rec['errors'] == ['L2_INVALID_END']
    rec = l2.run_stage('no_comm', make_case(), ask=FakeLLM({('r1', 1): {'act': 'end_west'}}))
    assert rec['errors'] == ['L2_INVALID_DECISION']


def test_structured_resolves_collision_in_round_two():
    s = lambda r, act, end: to_peer(r, {'act': act, 'end': end})
    llm = FakeLLM({('r1', 1): reply('end_west', s('r1', 'claim_end', 'west')),
                   ('r2', 1): reply('end_west', s('r2', 'claim_end', 'west')),
                   ('r1', 2): reply('end_west', s('r1', 'claim_end', 'west')),
                   ('r2', 2): lambda d: reply('end_east', s('r2', 'ack', 'east'))})
    rec = l2.allocate_ends('structured', make_case(), ask=llm)
    assert rec['rounds'] == 2 and rec['decisions'] == {'r1': 'west', 'r2': 'east'} and rec['success_eligible']
    # round-1 snapshot: r2 did not see r1's same-round claim
    r2_round1 = [d for r, d in llm.seen if r == 'r2' and d['round'] == 1][0]
    assert r2_round1['inbox'] == []
    r2_round2 = [d for r, d in llm.seen if r == 'r2' and d['round'] == 2][0]
    assert r2_round2['inbox'][0]['body'] == {'act': 'claim_end', 'end': 'west'}


def test_structured_rejects_free_text():
    llm = FakeLLM({('r1', 1): reply('end_west', to_peer('r1', {'text': 'west please'})),
                   ('r2', 1): reply('end_east'), ('r1', 2): reply('end_west'), ('r2', 2): reply('end_east')})
    rec = l2.allocate_ends('structured', make_case(), ask=llm)
    assert 'L2_MESSAGE_INVALID' in rec['errors'] and not rec['success_eligible']


def test_peer_en_three_rounds_then_duplicate():
    t = lambda r: to_peer(r, {'text': 'I will take the west end.'})
    script = {(r, k): reply('end_west', t(r)) for r in l2.ROBOTS for k in (1, 2, 3)}
    rec = l2.allocate_ends('peer_en', make_case(), ask=FakeLLM(script))
    assert rec['rounds'] == 3 and 'L2_DUPLICATE_END' in rec['errors'] and rec['utterances'] == 6


def test_peer_en_language_slip_recorded():
    script = {('r1', 1): reply('end_west', to_peer('r1', {'text': '서쪽 맡을게'})),
              ('r2', 1): reply('end_east', to_peer('r2', {'text': 'ok east'})),
              ('r1', 2): reply('end_west'), ('r2', 2): reply('end_east')}
    rec = l2.allocate_ends('peer_en', make_case(), ask=FakeLLM(script))
    assert rec['success_eligible'] and sum(m['language_slip'] for m in rec['messages']) == 1


def test_leader_en_assign_and_ack():
    case = make_case(seed=8343000)   # leader r1
    llm = FakeLLM({('r1', 1): reply('leader_west', to_peer('r1', {'text': 'I take west, you take east.'})),
                   ('r2', 2): reply('ack_assignment', to_peer('r2', {'text': 'Ack, east.'}))})
    rec = l2.allocate_ends('leader_en', case, ask=llm)
    assert rec['decisions'] == {'r1': 'west', 'r2': 'east'} and rec['success_eligible']
    assert llm.seen[1][1]['inbox'][0]['body']['text'].startswith('I take west')


def test_leader_en_missing_message_and_ack():
    rec = l2.run_stage('leader_en', make_case(), ask=FakeLLM({('r1', 1): reply('leader_west')}))
    assert rec['errors'] == ['L2_LEADER_UNASSIGNED'] and rec['fatal']
    llm = FakeLLM({('r1', 1): reply('leader_east', to_peer('r1', {'text': 'You go west.'})),
                   ('r2', 2): reply('ack_assignment')})
    rec = l2.run_stage('leader_en', make_case(), ask=llm)
    assert 'L2_LEADER_ACK_MISSING' in rec['errors']


# --- binding --------------------------------------------------------------

def test_build_case_changes_only_roles():
    case = make_case(yaw=math.pi)   # west = blue band
    rec = l2.allocate_ends('no_comm', case, ask=FakeLLM({('r1', 1): reply('end_west'), ('r2', 1): reply('end_east')}))
    out = l2.build_l2_case(case, rec, arm='student')
    assert out['plan']['roles'] == {'r1': 'blue', 'r2': 'teal'}
    rest = copy.deepcopy(out)
    del rest['l2_admin']
    rest['plan']['roles'] = case['plan']['roles']
    assert rest == case
    assert out['l2_admin']['original_roles'] == {'r1': 'teal', 'r2': 'blue'}
    with pytest.raises(l2.L2Error):
        l2.build_l2_case(case, rec, arm='teacher')


def test_planner_binding_not_wired():
    with pytest.raises(NotImplementedError):
        l2.planner_ask(None, {}, {})


def test_price_table_reads_pinned_planner():
    p = l2.price_table()
    assert p['prompt'] > 0 and p['completion'] > 0 and p['model']


# --- evaluator with fake execution summaries --------------------------------

def _ok_record(case):
    return l2.allocate_ends('no_comm', case, ask=FakeLLM({
        ('r1', 1): reply('end_west', usage={'prompt_tokens': 1000, 'completion_tokens': 100}),
        ('r2', 1): reply('end_east', usage={'prompt_tokens': 1000, 'completion_tokens': 100})}))


def fake_summary(seed, *, carry=True, teacher_steps=0, student=True):
    s = {'worlds': [{'world': 0, 'seed': seed, 'success': carry, 'carry_success': carry,
                     'carry_failure': None if carry else 'drop',
                     **({'teacher_steps': teacher_steps, 'student_funnel': {'place': carry}} if student else {})}]}
    if student:
        s['student_eval'] = {'mode': 'pairact_r1_student_eval_v1'}
    return s


def test_seed_success_student():
    case = make_case()
    rec = _ok_record(case)
    r = ev.seed_result(rec, l2.geometry_record(case), fake_summary(8343000), arm='student',
                       prices={'prompt': .09, 'completion': .34})
    assert r['success'] and r['llm']['assignment_match'] and r['failure_stage'] is None
    assert r['llm']['usd'] == round((2000 * .09 + 200 * .34) / 1e6, 6)


def test_student_contamination_and_teacher_summary_rejected():
    case = make_case()
    rec, g = _ok_record(case), l2.geometry_record(case)
    r = ev.seed_result(rec, g, fake_summary(8343000, teacher_steps=3), arm='student')
    assert not r['success'] and r['failure_stage'] == 'student_contaminated'
    r = ev.seed_result(rec, g, fake_summary(8343000, student=False), arm='student')
    assert not r['success']
    r = ev.seed_result(rec, g, fake_summary(8343000, student=False), arm='teacher_fallback')
    assert r['success'] and 'NOT a learned result' in r['arm_label']


def test_llm_failure_is_not_executed_even_if_summary_has_row():
    case = make_case()
    rec = l2.run_stage('no_comm', case, ask=FakeLLM({('r1', 1): reply(solo=True)}))
    r = ev.seed_result(rec, l2.geometry_record(case), fake_summary(8343000), arm='student')
    assert not r['success'] and not r['executed'] and r['failure_stage'] == 'llm'


def test_execution_failure_and_aggregate():
    case = make_case()
    rec, g = _ok_record(case), l2.geometry_record(case)
    ok = ev.seed_result(rec, g, fake_summary(8343000), arm='student')
    bad = ev.seed_result(rec, g, fake_summary(8343000, carry=False), arm='student')
    missing = ev.seed_result(rec, g, {'worlds': []}, arm='student')
    assert bad['failure_stage'] == 'execution' and missing['failure_stage'] == 'not_executed'
    agg = ev.aggregate([ok, bad, missing])
    assert agg[0]['report'] == '1/3' and agg[0]['failure_stage'] == {'success': 1, 'execution': 1, 'not_executed': 1}


def test_mismatched_assignment_is_measured():
    case = make_case()
    rec = l2.allocate_ends('no_comm', case, ask=FakeLLM({('r1', 1): reply('end_east'), ('r2', 1): reply('end_west')}))
    m = ev.llm_metrics(rec, l2.geometry_record(case))
    assert rec['success_eligible'] and not m['assignment_match'] and not m['conflict']


def test_hallucination_flags():
    case = make_case()
    g = l2.geometry_record(case)
    d1 = g['own_distances']['r1']['west']
    rec = {'messages': [
        {'sender': 'r1', 'to': ['r2'], 'round': 1, 'body': {'text': f'I am {d1} m from the west end.'}},
        {'sender': 'r2', 'to': ['r1'], 'round': 1, 'body': {'text': 'I am 3.7 m away, taking the north end.'}},
        {'sender': 'r1', 'to': ['r2'], 'round': 2, 'body': {'text': 'You said 3.7 m, fine.'}}]}
    flags = ev.hallucination_flags(rec, g)
    kinds = sorted((f['robot'], f['kind']) for f in flags)
    assert kinds == [('r2', 'foreign_end'), ('r2', 'ungrounded_distance')]
