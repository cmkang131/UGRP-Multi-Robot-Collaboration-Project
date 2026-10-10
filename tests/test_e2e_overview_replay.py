import json

import pytest

from scripts.replay_e2e_overview import Timeline, audit_tape, stage_label


def put(p, value, *, lines=False):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(''.join(json.dumps(r)+'\n' for r in value) if lines else json.dumps(value))


def fixture(raw):
    put(raw/'robots/r1/frames.jsonl', [dict(sim_time=2.35)], lines=True)
    put(raw/'result.json', dict(check_sim_s=.05))
    for rid in ('r1', 'r2', 'r3'):
        commands = [dict(t=1., kind='initial_servo_command', pulses={'1':2000})]
        if rid=='r1':
            commands += [dict(t=2.35, kind='hold'), dict(t=2.35, kind='hold')]
        put(raw/f'robots/{rid}/commands.jsonl', commands, lines=True)


def test_replay_keeps_duplicate_holds_and_own_command_order(tmp_path):
    fixture(tmp_path)
    start, end, grouped = audit_tape(tmp_path)
    assert (start, end)==(2.35, 2.4)
    assert len(grouped[0])==2
    assert all(r['robot_id']=='r1' and r['action']=={'kind':'hold'} for r in grouped[0])


def test_ambiguous_coupled_grip_transition_is_rejected(tmp_path):
    fixture(tmp_path)
    p=tmp_path/'robots/r1/commands.jsonl'
    with p.open('a') as f:
        f.write(json.dumps(dict(t=2.35, kind='arm', servo_id=1, pulse=1500))+'\n')
    p=tmp_path/'robots/r2/commands.jsonl'
    with p.open('a') as f:
        f.write(json.dumps(dict(t=2.35, kind='mecanum', forward=.05, left=0., turn=0., duration_s=.1))+'\n')
    with pytest.raises(ValueError, match='ambiguous cross-robot'):
        audit_tape(tmp_path)


def test_stage_caption_uses_current_record_and_keeps_async_states():
    timeline=Timeline([dict(t=3.,robots={'r1':dict(state='align'),'r2':dict(state='grasp')}),
                       dict(t=4.,robots={'r1':dict(state='lower'),'r2':dict(state='wait_open')})])
    assert timeline.at(2.99) is None
    assert stage_label(timeline.at(3.)['robots'])=='r1 정렬 · r2 집기'
    assert stage_label(timeline.at(4.)['robots'])=='내려놓기'
    assert stage_label({'r1':dict(state='align')},finished_single=True)=='내려놓기 (완료)'
