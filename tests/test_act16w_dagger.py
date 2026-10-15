from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from scripts.act16w_dagger import OracleHoldBoundary, prepare_single_step


def fixture():
    # Injectable contract keeps this scientific target-boundary test independent
    # of simulator/torch imports and the external frozen library checkout.
    contract = SimpleNamespace(CHUNK=8, ACTION_DIM=14,
        validate_observation=lambda x: None, command=lambda x: x,
        encode_action=lambda x, done: np.full(14, x['value'], dtype=np.float32))
    obs = [dict(sample_id=f'episode:{i}:r1', t=i*.1, issued=[{'own_command':i}]) for i in range(3)]
    labels = [dict(sample_id=o['sample_id'], t=o['t'], teacher_phase='align', phase_after='align',
                   label_valid=True, teacher_command=dict(t=o['t'],value=i+1)) for i,o in enumerate(obs)]
    audit = dict(invisible_measurements=0, held_world_reads=0, teacher_actions_executed=0)
    return contract, obs, labels, audit


def test_successive_student_queries_are_not_a_future_expert_chunk():
    contract, obs, labels, audit = fixture()
    original = deepcopy(obs)
    rows, report = prepare_single_step(obs, labels, contract=contract, audit=audit)
    assert len(rows) == 3
    assert np.all(rows[0]['action'][0] == 1)
    assert np.all(rows[0]['action'][1:] == 0)
    assert rows[0]['action_is_pad'].tolist() == [False] + [True]*7
    assert obs == original  # Oracle proposals never replace student's own history.
    assert report['future_student_path_borrowed_as_expert_chunk'] is False


def test_invalid_or_post_hover_labels_are_counted_and_excluded():
    contract, obs, labels, audit = fixture()
    labels[1]['teacher_phase'] = 'close'
    labels[2]['phase_after'] = 'failed'
    rows, report = prepare_single_step(obs, labels, contract=contract, audit=audit)
    assert len(rows) == 1
    assert sum(r['count'] for r in report['rejections']) == 2


def test_hidden_reads_executed_teacher_or_misaligned_pair_cannot_admit():
    contract, obs, labels, audit = fixture()
    for key in audit:
        with pytest.raises(ValueError):
            prepare_single_step(obs, labels, contract=contract, audit={**audit, key:1})
    labels[0]['sample_id'] = 'different-state'
    with pytest.raises(ValueError):
        prepare_single_step(obs, labels, contract=contract, audit=audit)


def test_potential_hold_never_calls_oracle_even_if_student_reopens():
    initial = {'pwm': {'1': 2000}}
    boundary = OracleHoldBoundary(initial)
    assert boundary.query([initial], lambda: 'allowed') == 'allowed'
    def forbidden():
        raise AssertionError('must not measure held cargo truth for labels')
    closing = {'pwm': {'1': 1999}}
    assert boundary.query([closing], forbidden)['query_blocked_by_hold_boundary']
    assert boundary.query([initial], forbidden)['query_blocked_by_hold_boundary']
    assert initial == {'pwm': {'1': 2000}} and closing == {'pwm': {'1': 1999}}
