import copy
import pytest

from harness.grasp_act_contract import (
    SCHEMA, RGB_HISTORY, HISTORY, CONTEXT_DIM, context, validate_observation,
    encode_action, decode_action, training_windows,
)


def command(t=0):
    return {'t': t, 'drive': [0., 0., 0.], 'duration_s': 0.,
            'pwm': {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}}


def observation(t=0, skill='grasp'):
    return {'schema': SCHEMA, 'sample_id': f'ep001:{t}:r1', 'robot_id': 'r1',
            't': t, 'object_kind':'long_beam','skill': skill, 'role': 'teal',
            'rgb': [{'path': 'rgb/a.jpg', 'sha256': 'a'*64, 't': t, 'robot_id': 'r1'} for _ in range(RGB_HISTORY)],
            'issued': [command(t)] * HISTORY}


@pytest.mark.parametrize('key', ['pose', 'qpos', 'contact', 'held', 'teacher_phase', 'peer_state'])
def test_privileged_fields_rejected(key):
    x = observation(); x[key] = 0
    with pytest.raises(ValueError, match='whitelist'):
        validate_observation(x)


def test_peer_and_future_images_rejected():
    x = observation(); x['rgb'][1]['robot_id'] = 'r2'
    with pytest.raises(ValueError): validate_observation(x)
    x = observation(); x['rgb'][1]['t'] = .1
    with pytest.raises(ValueError): validate_observation(x)
    x = observation(); x['issued'][0] = command(2)
    with pytest.raises(ValueError): validate_observation(x)


def test_context_is_owned_commands_and_task_only():
    x = observation()
    assert len(context(x)) == CONTEXT_DIM
    y = copy.deepcopy(x); y['issued'][-1]['pwm']['6'] = 1600
    assert context(x) != context(y)


def test_action_roundtrip_and_bounded_done():
    x = command(); x.update(drive=[-.35, 0., 0.], duration_s=.15)
    d = decode_action(encode_action(x))
    assert d['drive'] == x['drive'] and d['pwm'] == x['pwm'] and d['duration_s'] == .15
    d = decode_action(encode_action(x, done=True))
    assert d['done'] and d['drive'] == [0., 0., 0.]
    with pytest.raises(ValueError): decode_action([float('nan')]*10)


def test_chunk_masks_end_of_skill_and_timeout_is_not_done():
    obs = [observation(0), observation(.1), observation(.2, 'release')]
    labels = [{'sample_id': x['sample_id'], 'object_kind':'long_beam','skill': x['skill'], 'done': i == 1,
               'terminal_reason': 'skill_success' if i == 1 else None,
               'clean_teacher_command': command(x['t'])} for i, x in enumerate(obs)]
    windows = training_windows(obs, labels, chunk=4)
    assert windows[0]['action_is_pad'] == [False, False, True, True]
    assert windows[1]['action_is_pad'] == [False, True, True, True]
    labels[1]['terminal_reason'] = 'timeout'
    with pytest.raises(ValueError, match='successful'):
        training_windows(obs, labels)


def test_cross_actor_sequence_rejected():
    obs = [observation(0), observation(.1)]
    obs[1]['robot_id'] = 'r2'
    for ref in obs[1]['rgb']: ref['robot_id'] = 'r2'
    labels = [{'sample_id': x['sample_id'], 'object_kind':'long_beam','skill': x['skill'], 'done': False,
               'terminal_reason': None, 'clean_teacher_command': command(x['t'])} for x in obs]
    with pytest.raises(ValueError, match='crosses'):
        training_windows(obs, labels)


def test_continuous_diagonal_roundtrip_and_joint_wheel_bound():
    from harness.grasp_act_contract import command as check, wheel_mix
    x=command();x.update(drive=[.27,-.12,.07],duration_s=.15)
    assert decode_action(encode_action(check(x)))['drive']==x['drive']
    d=decode_action([4.,3.,2.,1.,0.,0.,0.,0.,0.,0.])
    assert max(map(abs,wheel_mix(d['drive'])))<=1.+1e-9
    x['drive']=[1.,1.,0.]
    with pytest.raises(ValueError,match='wheel range'):check(x)


def test_native_feedforward_uses_only_issued_command_signs():
    from sim.grasp_act_port import native_wheels
    start=native_wheels([.02,0.,0.],[0.]*4)
    assert start==(.35,)*4
    moving=native_wheels([.02,0.,0.],start)
    assert moving==pytest.approx((.02+1./12.,)*4)
    assert native_wheels([0.,0.,0.],moving)==(0.,)*4


def test_history_covers_measured_blind_interval_without_privileged_selection():
    from harness.grasp_act_contract import image_history,RGB_LAGS_S,MEMORY_S
    refs=[{'t':i*.1,'path':str(i)} for i in range(701)]
    sampled=image_history(refs,70.)
    assert [round(70.-r['t'],1) for r in sampled]==list(RGB_LAGS_S)
    assert MEMORY_S>=57.6 and (HISTORY-1)*.1>=57.6
    assert image_history(refs[:1],0.)==[refs[0]]*RGB_HISTORY
    x=observation();x['schema']='ugrp.grasp_act.student.v3'
    with pytest.raises(ValueError,match='whitelist'):validate_observation(x)
