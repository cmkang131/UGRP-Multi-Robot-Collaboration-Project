import json
from pathlib import Path

import pytest

from scripts.replay_s4_overview import audit_tape, latest_message, message_timeline


def put(path, value, *, lines=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r)+'\n' for r in value) if lines else json.dumps(value))


def fixture(raw):
    tape = [dict(t=2.35, robot_id='r2', action=dict(kind='hold')),
            dict(t=2.35, robot_id='r1', action=dict(kind='arm', servo_id=1, pulse=1600))]
    put(raw/'decision-command-links.json', tape)
    put(raw/'robots/r1/frames.jsonl', [dict(sim_time=2.35)], lines=True)
    put(raw/'result.json', dict(check_sim_s=.05))
    for rid in ('r1', 'r2', 'r3'):
        commands = [dict(t=1., kind='initial_servo_command')]
        commands += [dict(t=r['t'], **r['action']) for r in tape if r['robot_id']==rid]
        put(raw/f'robots/{rid}/commands.jsonl', commands+[dict(t=2.4, kind='hold')], lines=True)
    return tape


def test_preserves_same_tick_cross_robot_order_and_final_hold(tmp_path):
    tape = fixture(tmp_path)
    start, end, grouped = audit_tape(tmp_path)
    assert (start, end) == (2.35, 2.4)
    assert grouped[0] == tape
    p = tmp_path/'robots/r2/commands.jsonl'
    p.write_text('\n'.join(p.read_text().splitlines()[:-1])+'\n')
    with pytest.raises(ValueError, match='does not reproduce r2'):
        audit_tape(tmp_path)


def test_rejects_off_grid_command_before_physics(tmp_path):
    tape = fixture(tmp_path)
    tape[0]['t'] = 2.351
    put(tmp_path/'decision-command-links.json', tape)
    with pytest.raises(ValueError, match='0.05s clock'):
        audit_tape(tmp_path)


def test_captions_use_recorded_acceptance_time_and_keep_rejections(tmp_path):
    put(tmp_path/'llm/actions.json', [dict(kind='claim_order', actor='r1', arguments=dict(order_id='beam', role='leader'),
        accepted=True, submitted_at_sim_s=2.)])
    put(tmp_path/'pair-handshake.json', dict(decisions=[dict(robot_id='r2', at=4., accepted=False,
        action=dict(choice='ack_go', epoch=1000, peer_go_ref='call-1'))]))
    events = message_timeline(tmp_path)
    assert latest_message(events, 1.99) == 'LLM: waiting for claim'
    assert 'claim beam leader' in latest_message(events, 3.99)
    assert latest_message(events, 4.) == 'LLM @4.00s: r2 ACK epoch=1000 -> call-1 [rejected]'
