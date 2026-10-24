"""L1-lite: order sheet, private constraints, four channels, fail-closed, eval.

CPU only.  The LLM is stubbed everywhere: no HTTP request is made and no
physics/renderer is imported.
"""
import copy
import json
import os

import numpy as np
import pytest

from harness import e2ewarp_l1lite as L
from harness import e2ewarp_l1lite_eval as E
from harness import e2ewarp_nav_gate as gate
from harness.e2e_warp_runtime import Channels
from harness.zone_study_contract import ContractViolation

FORWARD = 0.004024203361827748
YAW = 1.7275488814064257
ENV_KEYS = (gate.L1LITE_ENV, gate.GATE_MODE_ENV, gate.ARRIVAL_ENV,
            gate.ARRIVAL_ODOM_M_ENV, gate.ARRIVAL_GROUND_M_ENV)


@pytest.fixture(autouse=True)
def _clean_state():
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    gate.clear_slot_decisions()
    yield
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    gate.clear_slot_decisions()


def reply(act, body=None, to='r2'):
    return dict(act=act,
                message=None if body is None else dict(recipients=[to], body=body))


def scripted(rows):
    """A stub ``ask`` replaying one answer per robot; records the dynamic rows."""
    calls = []
    queues = {robot: list(values) for robot, values in rows.items()}

    def ask(robot, dynamic):
        calls.append(dict(robot=robot, dynamic=copy.deepcopy(dynamic)))
        queue = queues.get(robot) or []
        if not queue:
            raise AssertionError('no scripted reply for ' + robot
                                 + ' round ' + str(dynamic.get('round')))
        item = queue.pop(0)
        if callable(item):
            item = item(dynamic)
        return copy.deepcopy(item)

    ask.calls = calls
    return ask


# ---------------------------------------------------------------------------
# Order sheet and the deterministic private-constraint table


def test_order_sheet_is_v_l1lite_two_unassigned_deliveries():
    sheet = L.order_sheet()
    assert sheet['version'] == 'v_l1lite'
    assert [o['order_id'] for o in sheet['orders']] == ['B-left', 'B-right']
    assert [o['slot'] for o in sheet['orders']] == ['left', 'right']
    assert all(o['assigned_robot'] is None for o in sheet['orders'])
    assert all(o['count'] == 1 and o['required_robots'] == 1 for o in sheet['orders'])
    assert all(o['destination_zone'] == 'B' for o in sheet['orders'])
    assert L.ORDER_SHEET['orders'] == sheet['orders']
    assert L.ORDER_SHEET_VERSION == 'v_l1lite'


def test_constraint_table_is_balanced_deterministic_and_pinned():
    assert L.table_violations(L.TEST_TABLE) == []
    assert L.table_violations(L.constraint_table()) == []
    assert L.TABLE_SEEDS == (601, 602, 603, 604, 605, 606)
    rows = {seed: L.all_constraints(seed) for seed in L.TABLE_SEEDS}
    constrained = {seed: next(r for r, slot in rows[seed].items() if slot)
                   for seed in L.TABLE_SEEDS}
    assert sorted(constrained.values()).count('r1') == 3
    assert sorted(constrained.values()).count('r2') == 3
    slots = [rows[seed][constrained[seed]] for seed in L.TABLE_SEEDS]
    assert slots.count('left') == 3 and slots.count('right') == 3
    # The no_comm rule collides on exactly the four pre-registered seeds.
    collisions = [seed for seed in L.TABLE_SEEDS
                  if L.default_slot(seed, 'r1') == L.default_slot(seed, 'r2')]
    assert collisions == [601, 602, 604, 605]
    assert len(L.constraint_table_digest()) == 64
    assert L.constraint_table_digest() == L.constraint_table_digest()
    # Private-constraint output is a fresh copy: a caller cannot mutate the table.
    table = L.constraint_table()
    table[601]['slot'] = 'left'
    assert L.all_constraints(601)['r1'] == 'right'


def test_table_violations_detect_a_tampered_table():
    # Break the slot balance only (601 r1 right -> left, 606 r2 right -> left).
    table = L.constraint_table()
    table[601] = dict(robot='r1', slot='left')
    table[606] = dict(robot='r2', slot='left')
    issues = L.table_violations(table)
    assert any('slot balance' in issue for issue in issues)
    # Every constrained robot keeps its own lane slot: 3/3 and 3/3 hold but
    # the collision count (0) leaves the pre-registered table (4).
    table = L.constraint_table()
    for seed in (601, 602, 603):
        table[seed] = dict(robot='r1', slot='left')
    for seed in (604, 605, 606):
        table[seed] = dict(robot='r2', slot='right')
    assert any('collisions' in issue for issue in L.table_violations(table))
    del table[606]
    assert any('exactly seeds' in issue for issue in L.table_violations(table))


def test_unknown_seed_or_robot_fails_closed():
    with pytest.raises(L.L1LiteError, match='SEED_UNKNOWN'):
        L.private_constraint(999, 'r1')
    with pytest.raises(L.L1LiteError, match='SEED_UNKNOWN'):
        L.all_constraints(True)
    with pytest.raises(L.L1LiteError, match='ROBOT_UNKNOWN'):
        L.private_constraint(602, 'r3')


def test_private_constraint_appears_only_in_its_owner_brief():
    for seed in L.TABLE_SEEDS:
        constraints = L.all_constraints(seed)
        owner = next(r for r, slot in constraints.items() if slot)
        peer = next(r for r in L.ROBOTS if r != owner)
        own_brief = L.robot_brief(seed, owner, 'structured')
        peer_brief = L.robot_brief(seed, peer, 'structured')
        assert own_brief['own_constraint']['slot'] == constraints[owner]
        assert own_brief['own_constraint']['robot'] == owner
        assert own_brief['own_constraint']['private'] is True
        assert peer_brief['own_constraint'] is None
        peer_blob = json.dumps(peer_brief)
        assert 'own_constraint": null' in peer_blob
        assert 'Loading constraint for' not in peer_blob
        assert L.constraint_text(owner, constraints[owner]) not in peer_blob
        assert 'constraint_table' not in peer_blob
        # The navigation adapter allowlist must reject the brief outright, so a
        # private constraint cannot ride into the controller static either.
        from harness.e2ewarp_nav_mode import nav_static
        with pytest.raises(ValueError, match='metadata only'):
            nav_static(own_brief)


def test_brief_carries_reply_format_guidance_for_every_condition():
    # Smoke 2026-10-24: leader_en failed twice with
    # L1LITE_LEADER_REPORT_MISSING because the brief never stated the free
    # message body shape ({"text": "..."}).  The guidance is a common
    # component: same text for both robots of a condition, no private rows.
    for seed in L.TABLE_SEEDS:
        for condition in L.CONDITIONS:
            briefs = [L.robot_brief(seed, r, condition) for r in L.ROBOTS]
            texts = [b["reply_format"] for b in briefs]
            assert all(isinstance(t, str) and t for t in texts)
            assert texts[0] == texts[1]
            text = texts[0]
            assert '"act"' in text and '"message"' in text
            if condition == "no_comm":
                assert '"message" must be null' in text
            elif condition == "structured":
                assert '"slot"' in text and "no free text" in text
            else:
                assert '{"text": "<your message in English>"}' in text
                assert "bare string" in text
            assert "Loading constraint for" not in text


# ---------------------------------------------------------------------------
# Four-channel schemas (transport validation only)


def test_condition_set_matches_the_runner():
    from harness.e2e_warp_runtime import COMM_CONDITIONS
    assert set(L.CONDITIONS) == set(COMM_CONDITIONS)


def test_no_comm_channel_has_no_inbox_and_rejects_any_message():
    channel = Channels('no_comm', 601, message_schema='l1lite')
    assert channel.inbox('r1') == {}
    with pytest.raises(ContractViolation, match='no messages'):
        channel.send('r1', {'recipients': ['r2'], 'body': {'text': 'hello'}}, now=0.)
    assert channel.events == []


def test_structured_channel_accepts_the_fixed_enum_only():
    channel = Channels('structured', 601, message_schema='l1lite')
    channel.send('r1', {'recipients': ['r2'],
                        'body': {'act': 'my_constraint', 'slot': 'right'}}, now=0.)
    assert channel.inbox('r2')['inbox'][0]['body'] == {'act': 'my_constraint',
                                                       'slot': 'right'}
    for body in ({'text': 'free text'}, {'act': 'inform', 'slot': 'left'},
                 {'act': 'claim_slot', 'slot': 'centre'},
                 {'act': 'claim_slot'}):
        with pytest.raises(ContractViolation):
            channel.validate('r1', {'recipients': ['r2'], 'body': body})


def test_peer_en_channel_is_free_english_only():
    channel = Channels('peer_en', 603, message_schema='l1lite')
    channel.send('r1', {'recipients': ['r2'],
                        'body': {'text': 'I can only take B-left.'}}, now=0.)
    assert channel.inbox('r2')['inbox'][0]['body']['text'].startswith('I can')
    with pytest.raises(ContractViolation):
        channel.validate('r1', {'recipients': ['r2'],
                                'body': {'act': 'claim_slot', 'slot': 'left'}})
    with pytest.raises(ContractViolation):
        channel.validate('r1', {'recipients': ['r2'], 'body': {'text': '   '}})
    assert L.message_language_slip('peer_en', {'text': '나는 왼쪽만 가능해'})
    assert not L.message_language_slip('peer_en', {'text': 'left only'})


def test_leader_rotation_is_seed_mod_two():
    assert L.leader_for_seed(601) == 'r2'
    assert L.leader_for_seed(602) == 'r1'
    assert Channels('leader_en', 601, message_schema='l1lite').leader == 'r2'
    channel = Channels('leader_en', 601, message_schema='l1lite')
    assert channel.inbox('r1')['role'] == 'follower'
    assert channel.inbox('r2')['role'] == 'leader'


# ---------------------------------------------------------------------------
# no_comm: zero messages, pre-registered default rule, fail-closed collisions


def test_no_comm_allocation_uses_the_default_rule_with_zero_messages():
    ask = scripted({'r1': [reply('slot_left')], 'r2': [reply('slot_right')]})
    record = L.allocate_slots('no_comm', 603, ask=ask)
    assert record['decisions'] == {'r1': 'left', 'r2': 'right'}
    assert record['utterances'] == 0
    assert record['messages'] == []
    assert len(record['calls']) == 2
    assert record['success_eligible'] is True
    assert record['constraint_ok'] == {'r1': True, 'r2': True}


def test_no_comm_never_delivers_a_message_even_if_the_model_tries():
    ask = scripted({'r1': [reply('slot_left', {'text': 'hello'})],
                    'r2': [reply('slot_right')]})
    record = L.allocate_slots('no_comm', 603, ask=ask)
    assert record['utterances'] == 0 and record['messages'] == []
    assert len(record['message_drops']) == 1


def test_no_comm_collision_records_the_named_duplicate_error():
    ask = scripted({'r1': [reply('slot_right')], 'r2': [reply('slot_right')]})
    record = L.allocate_slots('no_comm', 601, ask=ask)
    assert record['decisions'] == {'r1': 'right', 'r2': 'right'}
    assert record['errors'] == ['L1LITE_DUPLICATE_SLOT']
    assert record['distinct'] is False
    assert record['success_eligible'] is False


def test_no_comm_decision_off_the_default_rule_fails_closed():
    # seed 603 default: r1 left, r2 right.  r1 returning the non-default slot
    # is not a fallback case: the candidate list only advertised the default.
    ask = scripted({'r1': [reply('slot_right')], 'r2': [reply('slot_right')]})
    with pytest.raises(L.L1LiteError) as info:
        L.allocate_slots('no_comm', 603, ask=ask)
    assert info.value.code == 'L1LITE_INVALID_SLOT'
    assert info.value.record['decisions'] == {}


# ---------------------------------------------------------------------------
# structured / peer_en: one claim round and at least one answer round


def test_structured_exchange_claims_both_slots_and_resolves_in_round_two():
    def claim(robot, slot):
        def answer(dynamic):
            to = 'r2' if robot == 'r1' else 'r1'
            return reply('slot_' + slot, {'act': 'claim_slot', 'slot': slot}, to=to)
        return answer

    ask = scripted({'r1': [claim('r1', 'left'), claim('r1', 'left')],
                    'r2': [claim('r2', 'right'), claim('r2', 'right')]})
    record = L.allocate_slots('structured', 603, ask=ask)
    assert record['decisions'] == {'r1': 'left', 'r2': 'right'}
    assert record['rounds'] == 2
    assert record['utterances'] == 4
    assert len(record['calls']) == 4
    assert record['success_eligible'] is True


def test_peer_messages_are_visible_only_from_round_two():
    seen = {}

    def claim(robot, slot):
        def answer(dynamic):
            seen[(robot, dynamic['round'])] = copy.deepcopy(dynamic)
            to = 'r2' if robot == 'r1' else 'r1'
            return reply('slot_' + slot, {'act': 'claim_slot', 'slot': slot}, to=to)
        return answer

    ask = scripted({'r1': [claim('r1', 'left'), claim('r1', 'left')],
                    'r2': [claim('r2', 'right'), claim('r2', 'right')]})
    L.allocate_slots('structured', 603, ask=ask)
    assert seen[('r1', 1)]['inbox'] == [] and seen[('r2', 1)]['inbox'] == []
    assert seen[('r1', 2)]['inbox'][0]['body']['slot'] == 'right'
    assert seen[('r2', 2)]['inbox'][0]['body']['slot'] == 'left'


def test_duplicate_after_max_rounds_is_named_but_drivable():
    ask = scripted({'r1': [reply('slot_left')] * 3,
                    'r2': [reply('slot_left')] * 3})
    record = L.allocate_slots('structured', 601, ask=ask)
    assert record['rounds'] == 3
    assert record['decisions'] == {'r1': 'left', 'r2': 'left'}
    assert record['errors'] == ['L1LITE_DUPLICATE_SLOT']
    assert record['success_eligible'] is False


def test_structured_free_text_is_dropped_and_recorded():
    ask = scripted({
        'r1': [reply('slot_left', {'text': 'take the right half'})] * 2,
        'r2': [reply('slot_right', {'act': 'claim_slot', 'slot': 'right'}, to='r1')] * 2,
    })
    record = L.allocate_slots('structured', 603, ask=ask)
    assert record['decisions'] == {'r1': 'left', 'r2': 'right'}
    assert record['utterances'] == 2  # only the peer's valid messages were sent
    assert 'L1LITE_MESSAGE_INVALID' in record['errors']
    assert len(record['message_drops']) == 2


def test_peer_en_exchange_can_disclose_a_constraint():
    ask = scripted({
        'r1': [reply('slot_right', {'text': 'I am constrained to B-right; take B-left.'},
                     to='r2'),
               reply('slot_right', {'text': 'Confirmed: I take B-right.'}, to='r2')],
        'r2': [reply('slot_right', {'text': 'I can take B-left.'}, to='r1'),
               reply('slot_left', {'text': 'Agreed: moving to B-left.'}, to='r1')],
    })
    record = L.allocate_slots('peer_en', 601, ask=ask)
    assert record['decisions'] == {'r1': 'right', 'r2': 'left'}
    assert record['utterances'] == 4
    assert record['success_eligible'] is True
    assert any(row['body']['text'].startswith('I am constrained')
               for row in record['messages'])


# ---------------------------------------------------------------------------
# leader_en: the follower reports, the leader assigns both slots, the follower acks


def _report(text='I can only use B-right.'):
    return reply('report_status', {'text': text}, to='r2')


def test_leader_assigns_both_slots_and_the_follower_acks():
    ask = scripted({
        'r1': [_report(),
               reply('ack_assignment', {'text': 'Acknowledged: I take B-right.'}, to='r2')],
        'r2': [reply('take_left', {'text': 'I take B-left; you take B-right.'}, to='r1')],
    })
    record = L.allocate_slots('leader_en', 601, ask=ask)  # 601 % 2 -> r2 leader
    assert record['leader'] == 'r2'
    assert record['decisions'] == {'r2': 'left', 'r1': 'right'}
    assert record['rounds'] == 3
    assert record['utterances'] == 3
    assert record['success_eligible'] is True
    assert [(row['robot'], row['round']) for row in record['transcript']] == [
        ('r1', 1), ('r2', 2), ('r1', 3)]


def test_leader_sees_the_follower_report_before_assigning():
    """Codex 2026-10-20 §2: the follower's constraint can reach the leader."""
    ask = scripted({
        'r1': [_report('My private constraint: I can only use B-right.'),
               reply('ack_assignment', {'text': 'ok'}, to='r2')],
        'r2': [reply('take_left', {'text': 'You take B-right.'}, to='r1')],
    })
    L.allocate_slots('leader_en', 601, ask=ask)
    leader_call = next(c for c in ask.calls if c['robot'] == 'r2')
    texts = [row['body']['text'] for row in leader_call['dynamic']['inbox']]
    assert texts == ['My private constraint: I can only use B-right.']
    # The follower's first call had an empty inbox (it speaks first).
    assert ask.calls[0]['robot'] == 'r1' and not ask.calls[0]['dynamic']['inbox']


def test_follower_report_message_is_required():
    ask = scripted({'r1': [reply('report_status')], 'r2': []})
    with pytest.raises(L.L1LiteError) as info:
        L.allocate_slots('leader_en', 601, ask=ask)
    assert info.value.code == 'L1LITE_LEADER_REPORT_MISSING'
    assert info.value.record['fatal'] is True


def test_follower_report_as_bare_string_body_is_rejected():
    """Regression (smoke 2026-10-24, Codex re-review recommendation): the
    follower's report body sent as a bare string instead of {"text": ...}
    must fail channel validation, drop the message, and surface as
    L1LITE_LEADER_REPORT_MISSING -- the exact leader_en failure mode the
    brief reply_format guidance now warns against."""
    ask = scripted({'r1': [reply('report_status', 'I can only use B-right.',
                                  to='r2')],
                    'r2': []})
    with pytest.raises(L.L1LiteError) as info:
        L.allocate_slots('leader_en', 601, ask=ask)
    assert info.value.code == 'L1LITE_LEADER_REPORT_MISSING'
    record = info.value.record
    assert record['fatal'] is True
    assert 'L1LITE_MESSAGE_INVALID' in record['errors']
    assert record['message_drops'][0]['robot'] == 'r1'


def test_leader_assignment_message_is_required():
    ask = scripted({'r1': [_report()], 'r2': [reply('take_left')]})
    with pytest.raises(L.L1LiteError) as info:
        L.allocate_slots('leader_en', 601, ask=ask)
    assert info.value.code == 'L1LITE_LEADER_UNASSIGNED'


def test_follower_ack_is_required():
    ask = scripted({'r1': [_report(), reply('ack_assignment')],  # ack without message
                    'r2': [reply('take_left', {'text': 'assignment'}, to='r1')]})
    with pytest.raises(L.L1LiteError) as info:
        L.allocate_slots('leader_en', 601, ask=ask)
    assert info.value.code == 'L1LITE_LEADER_ACK_MISSING'


# ---------------------------------------------------------------------------
# Fail-closed decision contract


def test_missing_or_malformed_decision_fails_closed():
    def none_ask(robot, dynamic):
        raise L.L1LiteError('L1LITE_NO_DECISION', detail='planner returned none')
    with pytest.raises(L.L1LiteError) as info:
        L.allocate_slots('structured', 603, ask=none_ask)
    assert info.value.code == 'L1LITE_NO_DECISION'
    assert info.value.record['condition'] == 'structured'

    malformed = scripted({'r1': [{'act': 'slot_left'}],
                          'r2': [reply('slot_right')]})
    with pytest.raises(L.L1LiteError) as info:
        L.allocate_slots('structured', 603, ask=malformed)
    assert info.value.code == 'L1LITE_INVALID_DECISION'


def test_allocator_rejects_unknown_condition_and_seed():
    with pytest.raises(L.L1LiteError, match='CONDITION_UNKNOWN'):
        L.allocate_slots('peer_ko', 603, ask=scripted({}))
    with pytest.raises(L.L1LiteError, match='SEED_UNKNOWN'):
        L.allocate_slots('no_comm', 610, ask=scripted({}))


# ---------------------------------------------------------------------------
# Default OFF: the r5 fixed slot mapping and queue bytes are unchanged


def calibration(tmp_path):
    payload = dict(schema=gate.CALIBRATION_SCHEMA, measured=True, measured_n=60,
                   source_sha='d182b67' + 'a' * 33,
                   constants=dict(forward_m_per_pct_s=FORWARD,
                                  yaw_deg_per_pct_s=YAW),
                   per_robot={rid: dict(forward_m_per_pct_s=FORWARD,
                                        yaw_deg_per_pct_s=YAW)
                              for rid in gate.ROBOTS})
    path = tmp_path / 'nav_gate_calibration.json'
    path.write_text(json.dumps(payload))
    return gate.load_calibration(path)


def r5_queue(tmp_path, seed=601, l1lite=False):
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V230_R5
    os.environ[gate.ARRIVAL_ENV] = 'odom_projection'
    if l1lite:
        os.environ[gate.L1LITE_ENV] = 'on_v1'
    record = calibration(tmp_path)
    queue = gate.gate_queue_fields(seed, calibration=record)
    queue['sim_budget_s'] = queue['nav_sim_budget_s']
    queue['seed'] = seed
    queue['condition'] = 'structured'
    if l1lite:
        queue.update(L.queue_fields(seed, gate.ROBOTS))
    return queue, record


def test_default_off_keeps_the_fixed_r5_slot_mapping(tmp_path):
    queue, record = r5_queue(tmp_path)
    assert queue['nav_slots'] == {'r1': 'left', 'r2': 'right'}
    assert not [key for key in queue if str(key).startswith('nav_l1lite')]
    gate.validate_gate_queue(queue)
    assert gate.slot_assignment() == gate.SLOT_BY_ROBOT
    assert gate.decided_slot_decisions() is None
    nav = gate.navigation_factory('r1', {'destination_zone': 'B',
                                         'slots': gate.SLOT_BY_ROBOT},
                                  calibration=record)
    assert nav.slot == 'left'


def test_default_channels_keep_the_legacy_schema():
    channel = Channels('structured', 601)
    assert channel.message_schema == 'legacy'
    with pytest.raises(ContractViolation):
        channel.validate('r1', {'recipients': ['r2'],
                                'body': {'act': 'claim_slot', 'slot': 'left'}})


def test_binding_a_decision_requires_the_l1lite_marker():
    with pytest.raises(ValueError, match='REQUIRE_L1LITE'):
        gate.bind_slot_decisions({'r1': 'left', 'r2': 'right'})
    os.environ[gate.L1LITE_ENV] = 'on_v1'
    with pytest.raises(ValueError, match='UNBOUND'):
        gate.slot_assignment()


def test_bound_decision_replaces_slot_by_robot(tmp_path):
    queue, record = r5_queue(tmp_path)
    os.environ[gate.L1LITE_ENV] = 'on_v1'
    gate.bind_slot_decisions({'r1': 'right', 'r2': 'left'}, robots=gate.ROBOTS)
    assert gate.slot_assignment() == {'r1': 'right', 'r2': 'left'}
    nav = gate.navigation_factory('r1', {'destination_zone': 'B',
                                         'slots': {'r1': 'right'}},
                                  calibration=record)
    assert nav.slot == 'right'
    with pytest.raises(ValueError, match='NAV_SLOT_MISMATCH'):
        gate.navigation_factory('r1', {'destination_zone': 'B',
                                       'slots': {'r1': 'left'}},
                                calibration=record)


def test_l1lite_queue_pins_the_table_and_forbids_prepared_slots(tmp_path):
    queue, _record = r5_queue(tmp_path, l1lite=True)
    gate.validate_gate_queue(queue)
    L.validate_queue(queue, seed=601, condition='structured')
    assert queue['nav_l1lite_constraints_sha256'] == L.constraint_table_digest()
    assert 'nav_slots' not in queue

    tampered = copy.deepcopy(queue)
    tampered['nav_slots'] = {'r1': 'left', 'r2': 'right'}
    with pytest.raises(L.L1LiteError) as info:
        L.validate_queue(tampered, seed=601, condition='structured')
    assert info.value.code == 'L1LITE_SLOTS_RUNTIME_DECISION'

    tampered = copy.deepcopy(queue)
    tampered['nav_l1lite_constraints_sha256'] = '0' * 64
    with pytest.raises(L.L1LiteError) as info:
        L.validate_queue(tampered, seed=601, condition='structured')
    assert info.value.code == 'L1LITE_CONSTRAINT_TABLE_MISMATCH'

    tampered = copy.deepcopy(queue)
    tampered['seed'] = 607
    with pytest.raises(L.L1LiteError):
        L.validate_queue(tampered, seed=607, condition='structured')


def test_l1lite_queue_records_the_seed_split(tmp_path):
    queue, _record = r5_queue(tmp_path, l1lite=True)
    assert queue['nav_l1lite_seed_split'] == 'test'
    gate.validate_gate_queue(queue)
    (tmp_path / 'dev').mkdir()
    dev, _record = r5_queue(tmp_path / 'dev', seed=701, l1lite=True)
    assert dev['nav_l1lite_seed_split'] == 'dev'
    L.validate_queue(dev, seed=701, condition='structured')
    tampered = copy.deepcopy(queue)
    tampered['nav_l1lite_seed_split'] = 'dev'
    with pytest.raises(L.L1LiteError) as info:
        L.validate_queue(tampered, seed=601, condition='structured')
    assert info.value.code == 'L1LITE_SEED_SPLIT_MISMATCH'


def test_l1lite_markers_require_the_environment(tmp_path):
    queue, _record = r5_queue(tmp_path, l1lite=True)
    os.environ.pop(gate.L1LITE_ENV)
    with pytest.raises(L.L1LiteError) as info:
        L.validate_queue(queue, seed=601, condition='structured')
    assert info.value.code == 'L1LITE_ENV_REQUIRED'


def test_l1lite_requires_the_r5_gate_mode(tmp_path):
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V230_R4
    os.environ[gate.ARRIVAL_ENV] = 'odom_projection'
    record = calibration(tmp_path)
    os.environ[gate.L1LITE_ENV] = 'on_v1'
    queue = gate.gate_queue_fields(601, calibration=record)
    queue['sim_budget_s'] = queue['nav_sim_budget_s']
    queue['seed'] = 601
    queue['condition'] = 'structured'
    queue.update(L.queue_fields(601, gate.ROBOTS))
    with pytest.raises(L.L1LiteError) as info:
        L.validate_queue(queue, seed=601, condition='structured')
    assert info.value.code == 'L1LITE_REQUIRES_V230_R5'


# ---------------------------------------------------------------------------
# Evaluator: main metric components and auxiliary metrics


def allocation(**overrides):
    value = dict(errors=[], fatal=False, success_eligible=True, messages=[],
                 utterances=0, deadlock=False)
    value.update(overrides)
    return value


def success_kwargs():
    return dict(slots={'r1': 'left', 'r2': 'right'},
                constraints={'r1': 'left', 'r2': None},
                final_gt={'r1': [4.6, -1.75], 'r2': [4.6, -2.45]},
                claims={'r1': True, 'r2': True}, zone=E.ZONE_B,
                contacts_available=True, robot_robot_contacts=0,
                allocation=allocation())


def test_slot_zones_split_zone_b_north_left_south_right():
    assert E.slot_zone(E.ZONE_B, 'left')['center_m'] == pytest.approx([4.6, -1.75])
    assert E.slot_zone(E.ZONE_B, 'right')['center_m'] == pytest.approx([4.6, -2.45])
    assert E.in_rect([4.6, -1.5], E.slot_zone(E.ZONE_B, 'left'))
    assert not E.in_rect([4.6, -2.6], E.slot_zone(E.ZONE_B, 'left'))
    assert E.in_rect([4.6, -2.6], E.slot_zone(E.ZONE_B, 'right'))


def test_evaluator_success_requires_every_component():
    report = E.evaluate(**success_kwargs())
    assert report['success'] is True
    assert report['eval_only'] is True and report['research_result'] is False
    for key in ('allocation_ok', 'distinct_slots', 'arrival_in_chosen_slot',
                'claims_2_of_2', 'constraint_ok', 'robot_contact_zero'):
        assert report['success_components'][key] is True, key


@pytest.mark.parametrize('overrides', [
    dict(final_gt={'r1': [4.6, -2.45], 'r2': [4.6, -2.45]}),   # r1 outside own half
    dict(claims={'r1': False, 'r2': True}),
    dict(robot_robot_contacts=1),
    dict(contacts_available=False),
    dict(constraints={'r1': 'right', 'r2': None}),
    dict(constraints={}),
    dict(allocation=allocation(success_eligible=False,
                               errors=['L1LITE_DUPLICATE_SLOT'])),
    dict(allocation=None),
    dict(final_gt={'r1': None, 'r2': [4.6, -2.45]}),
])
def test_any_failed_component_keeps_success_false(overrides):
    kwargs = success_kwargs()
    kwargs.update(overrides)
    assert E.evaluate(**kwargs)['success'] is False


def test_same_slot_choice_fails_even_when_both_are_inside():
    kwargs = success_kwargs()
    kwargs.update(slots={'r1': 'left', 'r2': 'left'},
                  final_gt={'r1': [4.6, -1.75], 'r2': [4.6, -1.6]},
                  constraints={'r1': 'left', 'r2': None})
    report = E.evaluate(**kwargs)
    assert report['success_components']['distinct_slots'] is False
    assert report['success'] is False


def test_evaluator_aux_metrics_and_pinned_cost():
    kwargs = success_kwargs()
    kwargs.update(claim_sim_s={'r1': 39.7, 'r2': 39.9}, sim_s=39.9,
                  usage=[{'usage': dict(prompt_tokens=1198, completion_tokens=22)}] * 2,
                  min_center_distance_m=0.177, min_body_gap_m=0.0457,
                  utterances=4)
    aux = E.evaluate(**kwargs)['aux']
    assert aux['completion_sim_s'] == 39.9
    assert aux['llm']['calls'] == 2
    assert aux['llm']['total_tokens'] == 2440
    assert aux['llm']['cost_usd'] == pytest.approx(0.00025456, rel=1e-9)
    assert aux['utterances'] == 4
    assert aux['min_center_distance_m'] == 0.177
    assert aux['min_body_gap_m'] == 0.0457
    assert aux['deadlock_60s'] is False


def test_60s_deadlock_without_both_claims_is_flagged():
    kwargs = success_kwargs()
    kwargs.update(claims={'r1': True, 'r2': False}, sim_s=60.0)
    assert E.evaluate(**kwargs)['aux']['deadlock_60s'] is True


def test_hallucination_report_flags_false_constraint_and_unknown_slot():
    messages = [
        dict(sender='r1', sim_s=1.0, body={'act': 'my_constraint', 'slot': 'left'}),
        dict(sender='r2', sim_s=2.0, body={'text': 'I will take B-center.'}),
        dict(sender='r1', sim_s=3.0, body={'text': 'You take B-right.'}),
    ]
    report = E.hallucination_report(messages, {'r1': 'right', 'r2': None})
    kinds = [item['kind'] for item in report['items']]
    assert kinds.count('false_constraint_claim') == 1
    assert kinds.count('unknown_slot_mention') == 1
    assert report['count'] == 2


def test_evaluate_run_recounts_raw_artifacts(tmp_path):
    run = tmp_path / 'run'
    (run / 'world-00').mkdir(parents=True)
    geometry = dict(eval_only=True, robot_qpos_adr={'r1': 0, 'r2': 10},
                    destination=dict(kind='zone_B', zone='B',
                                     center_m=[4.6, -2.1],
                                     half_extents_m=[0.3, 0.7]))
    (run / 'world-00' / 'eval-geometry.json').write_text(json.dumps(geometry))
    ticks, nq = 5, 30
    qpos = np.zeros((ticks, 1, nq))
    for tick in range(ticks):
        qpos[tick, 0, 0] = -0.925 + 1.38125 * tick      # r1 east -> 4.6
        qpos[tick, 0, 1] = -2.375 + 0.15625 * tick      # -> -1.75 (left half)
        qpos[tick, 0, 3] = 1.0
        qpos[tick, 0, 10] = -0.925 + 1.38125 * tick     # r2 east -> 4.6
        qpos[tick, 0, 11] = -2.875 + 0.11 * tick        # -> -2.435 (right half)
        qpos[tick, 0, 13] = 1.0
    np.savez_compressed(run / 'evaluation-state.npz', qpos=qpos, dt=.1)
    (run / 'result.json').write_text(json.dumps(
        dict(status='NAV_ARRIVAL_UNVERIFIED', sim_s=39.9, source_sha='a' * 40)))
    (run / 'nav-events.json').write_text(json.dumps({
        '0:r1': [dict(sim_s=39.7, after='ARRIVED')],
        '0:r2': [dict(sim_s=39.9, after='ARRIVED')]}))
    (run / 'contact-ledger.json').write_text(json.dumps(dict(
        contacts_available=True, contact_pairs_total=0,
        base_boxes={r: dict(geom=r + '__base_lower_collision',
                            size=[0.11, 0.09, 0.05], local_pos=[0.0, 0.0, 0.0])
                    for r in L.ROBOTS})))
    (run / 'llm_ledger.json').write_text(json.dumps(
        [dict(robot='r1', usage=dict(prompt_tokens=1000, completion_tokens=20)),
         dict(robot='r2', usage=dict(prompt_tokens=1000, completion_tokens=20))]))
    (run / 'messages.json').write_text(json.dumps([dict(world=0, events=[
        dict(sender='r1', recipients=['r2'], body={'act': 'claim_slot', 'slot': 'left'},
             sim_s=0.0)])]))
    (run / 'slot-decisions.json').write_text(json.dumps(allocation(
        decisions={'r1': 'left', 'r2': 'right'},
        constraints={'r1': 'left', 'r2': None}, utterances=4, rounds=2)))
    report = E.evaluate_run(run)
    assert report['success'] is True
    assert report['status'] == 'NAV_ARRIVAL_UNVERIFIED'
    assert report['aux']['completion_sim_s'] == 39.9
    assert report['aux']['llm']['calls'] == 2
    assert report['aux']['min_center_distance_m'] is not None
    assert report['aux']['min_body_gap_m'] is not None
    assert report['aux']['min_body_gap_m'] < report['aux']['min_center_distance_m']
    assert report['aux']['hallucination']['count'] == 0


# ---------------------------------------------------------------------------
# Runner wiring (mocked physics/transport/planner; no world, no HTTP)


class FakeWorld:
    def __init__(self, nq=30):
        self.model = type('Model', (), dict(ngeom=0))()
        self.data = type('Data', (), dict(qpos=np.zeros(nq)))()
        self.scene_xml = '<xml/>'


class FakeContext(dict):
    """The runner reads contexts as mappings (``context['world']`` etc.)."""

    def __init__(self, nq=30):
        super().__init__(
            scene=type('Scene', (), dict(scene=dict(params=dict(scenario_setup=dict(
                orders=[dict(order_id='pair', destination_zone='B',
                             required_robots=2)])))))(),
            world=FakeWorld(nq),
            static_map=dict(map_id='fake', regions={}),
            no_cargo=True)


class FakeHooks:
    def __init__(self):
        self.m = type('M', (), dict(opt=type('Opt', (), dict(noslip_iterations=0))))()
        self.wm = self.m
        self.seconds = {}

    def initialize(self, contexts):
        pass

    def capture(self, world, context, robot):
        return b'fake-jpeg'

    def step(self, contexts, mask):
        pass

    def save_states(self):
        pass


class FakePlanner:
    """Records image-bearing calls; replays one candidate id per robot call."""

    scripts = {}

    def __init__(self, url, root, static, *, run_id, world_id, robot):
        self.static, self.world_id, self.robot = static, world_id, robot
        self.rows, self.calls = [], 0
        class FakeHealth:
            def check(self, now):
                return None
        self.health = FakeHealth()

    def body(self, frame, dynamic):
        return dict(messages=[dict(role='system', content='fake')], dynamic=dynamic)

    def decide(self, frame, dynamic):
        self.calls += 1
        script = FakePlanner.scripts.get((self.world_id, self.robot)) or []
        act = script.pop(0)
        self.rows.append(dict(call_id=f'fake:{self.robot}:{self.calls}',
                              sim_s=frame.sim_s, status=200, connected=True,
                              image_count=1, image_sha256='0' * 64,
                              request_sha256='1' * 64,
                              usage=dict(prompt_tokens=100, completion_tokens=10),
                              accepted=True, upstream=dict(attempts=[dict(status=200)])))
        return dict(act=act, message=None), None


class FakeTask:
    statics = []

    def __init__(self, robot, static, components):
        self.robot, self.static = robot, static
        FakeTask.statics.append((robot, copy.deepcopy(static)))
        self.component = type('Component', (), {})()
        self.component.events = []
        self.component.phase = 'TASK'
        self.component.needs_decision = True
        self.component.complete = False
        self.command_history = []

    def candidates(self):
        return [dict(id='order_' + str(index), skill='carry_pair', order=order)
                for index, order in enumerate(self.static['orders'])]

    def select(self, candidate, now, *, reason=None):
        self.component.events.append(dict(sim_s=now, after='NAVIGATE', reason=reason))
        self.component.phase = 'NAVIGATE'
        self.component.needs_decision = False

    def observe(self, frame):
        return dict(phase=self.component.phase, own_navigation={},
                    physical_success_available=False)

    def receive(self, rows):
        pass

    def take_inbox(self):
        return []

    def command(self, now):
        return dict(t=now, wheels=[0.0] * 4, duration_s=[0.0] * 4, pwm={'1': 1500})

    @property
    def complete(self):
        return False


def fake_args(tmp_path, condition='no_comm', seed=603):
    return type('Args', (), dict(
        mode='nav', nav_solo_robot=None, seed=seed, condition=condition,
        nworld=1, output=tmp_path / 'run', nav_sim_budget_s=0.5,
        components=None, relay_url='http://127.0.0.1:1/v1/chat/completions',
        map_keyframe_admission='off', round=1, e2e_warp_batch='on_v1',
        arrival_odom_residual=False, arrival_ground_distance_m=None,
        arrival_odom_projection=True, command=['fake-run']))()


def fake_queue(condition='no_comm', seed=603):
    return dict(sim_budget_s=0.5, stack_values=dict(contact_profile='fake'),
                stack_deviations=[], host=dict(instance='fake'),
                map_keyframe_admission='off', dependency_status='fake',
                seed=seed, condition=condition, enabled=True)


def install_fake_runner(monkeypatch, scripts):
    import sys
    import types
    from scripts import run_e2e_warp as R
    fake = types.ModuleType('scripts.e2e_warp_physics')
    fake.build_context = lambda seed, out, stack, **kwargs: FakeContext()
    fake.transport = lambda contexts, out, sha, stack: FakeHooks()
    fake.issue = lambda context, robot, command: None
    fake.own_map = lambda frame, state, keyframe_policy='off': {}
    monkeypatch.setitem(sys.modules, 'scripts.e2e_warp_physics', fake)
    FakePlanner.scripts = scripts
    FakeTask.statics = []
    monkeypatch.setattr(R, 'Planner', FakePlanner)
    monkeypatch.setattr(R, 'NavRobot', FakeTask)
    monkeypatch.setattr(R, 'nav_all_arrived', lambda tasks: False)
    monkeypatch.setattr(R, 'head', lambda: 'a' * 40)
    monkeypatch.setattr(R, 'admit', lambda a, q: (dict(upstream='fake'), dict(host='fake')))
    monkeypatch.setattr(R, 'require_navigation', lambda *a, **k: {'navigation_factory': 'fake'})
    monkeypatch.setattr(R, 'nav_validate_queue', lambda *a, **k: None)
    monkeypatch.setattr(R, 'nav_validate_gate_queue', lambda *a, **k: None)
    monkeypatch.setattr(R, 'nav_validate_calibration', lambda *a, **k: None)
    monkeypatch.setattr(R.l1lite, 'validate_queue', lambda *a, **k: None)
    os.environ['E2EWARP_NAV_L1LITE'] = 'on_v1'
    return R


def test_runner_binds_the_llm_slot_before_building_the_adapter(tmp_path, monkeypatch):
    R = install_fake_runner(monkeypatch, {(0, 'r1'): ['slot_left'],
                                          (0, 'r2'): ['slot_right']})
    args = fake_args(tmp_path)
    result = R.run(args, fake_queue())
    assert result['status'] == 'cap_end'
    assert result['E2E_success'] is False and result['research_result'] is False
    record = json.loads((args.output / 'slot-decisions.json').read_text())
    assert record['decisions'] == {'r1': 'left', 'r2': 'right'}
    assert record['constraint_table_sha256'] == L.constraint_table_digest()
    assert json.loads((args.output / 'messages.json').read_text()) == [
        dict(world=0, events=[])]
    decisions = json.loads((args.output / 'decisions.json').read_text())
    assert [row['phase'] for row in decisions] == ['allocation', 'allocation']
    nav_events = json.loads((args.output / 'nav-events.json').read_text())
    assert all('L1-lite' in (row.get('reason') or '')
               for rows in nav_events.values() for row in rows)
    ledger = json.loads((args.output / 'llm_ledger.json').read_text())
    assert len(ledger) == 2 and all(row['image_count'] == 1 for row in ledger)
    assert result['slot_allocation']['decisions'] == {'r1': 'left', 'r2': 'right'}
    assert result['slot_allocation']['success_eligible'] is True


def test_runner_records_a_named_allocation_failure(tmp_path, monkeypatch):
    R = install_fake_runner(monkeypatch, {(0, 'r1'): ['slot_centre']})
    args = fake_args(tmp_path)
    result = R.run(args, fake_queue())
    assert result['status'] == 'L1LITE_ALLOCATION_FAILED'
    assert 'L1LITE_INVALID_SLOT' in result['error']
    assert result['E2E_success'] is False
    record = json.loads((args.output / 'slot-decisions.json').read_text())
    assert record['errors'] == ['L1LITE_INVALID_SLOT']
    assert record['fatal'] is True
    assert result['slot_allocation']['fatal'] is True
    assert result['slot_allocation']['failure']['code'] == 'L1LITE_INVALID_SLOT'
    assert not (args.output / 'evaluation-state.npz').exists()


def test_runner_default_path_still_uses_the_fixed_r5_slot_mapping(tmp_path, monkeypatch):
    os.environ[gate.GATE_MODE_ENV] = gate.GATE_MODE_V230_R5
    os.environ[gate.ARRIVAL_ENV] = 'odom_projection'
    R = install_fake_runner(monkeypatch, {(0, 'r1'): ['order_0'],
                                          (0, 'r2'): ['order_0']})
    os.environ.pop('E2EWARP_NAV_L1LITE')
    args = fake_args(tmp_path)
    result = R.run(args, fake_queue())
    assert result['status'] == 'cap_end'
    assert not (args.output / 'slot-decisions.json').exists()
    assert 'slot_allocation' not in result
    decisions = json.loads((args.output / 'decisions.json').read_text())
    assert len(decisions) == 2 and all(row['act'] == 'order_0' for row in decisions)
    assert not any(row.get('phase') == 'allocation' for row in decisions)
    for robot, static in FakeTask.statics:
        assert static['slots'] == gate.SLOT_BY_ROBOT
        assert 'own_constraint' not in static


def test_dev_seeds_are_separate_from_test_seeds():
    assert L.DEV_SEEDS == (701, 702)
    assert not set(L.DEV_SEEDS) & set(L.TABLE_SEEDS)
    assert L.seed_split(701) == 'dev' and L.seed_split(601) == 'test'
    assert L.default_slot(701, 'r1') == L.default_slot(701, 'r2')   # collision
    assert L.default_slot(702, 'r1') != L.default_slot(702, 'r2')   # split
    dev = L.dev_constraint_table()
    dev[701]['slot'] = 'left'
    assert L.all_constraints(701)['r1'] == 'right'
