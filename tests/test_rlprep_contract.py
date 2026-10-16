"""Three non-physics boundary tests. No Torch, MuJoCo, Warp or subprocesses."""
from copy import deepcopy
import hashlib
import json

import pytest

from scripts.rl_act_reward import potential, shaped_reward
from scripts.rlprep_contract import (CountBudget, PreparationBatchEnv, WARP3_CONTROLLER,
                                     WARP3_SOURCE, inspect_warp3_marker, start_training)


class Backend:
    def __init__(self, truth_offset=0):
        self.truth_offset, self.steps, self.reads = truth_offset, 0, 0

    def reset(self, plans, indices):
        self.indices = indices

    def step(self, actions):
        self.steps += 1
        return [False, False]

    def read_actor(self, i):
        return {'own_rgb': ['r%d.jpg' % i], 'issued': [self.steps], 'skill': 'grasp'}, (b'own-jpeg',)

    def read_training(self, i):
        self.reads += 1
        # Actual warp3 API returns a private dict, unlike PR530's old owner.
        return dict(distance_m=1. + self.truth_offset, alignment_rad=.2,
                    target_xy=None, stable_lift=False), (float(self.truth_offset),)


def validate_obs(row):
    # Stand-in for the exact frozen ACT validator, which has nested whitelists.
    assert set(row) == {'own_rgb', 'issued', 'skill'}


def validate_command(row):
    assert set(row) == {'issued_command'}


def wrapper(backend, **kw):
    return PreparationBatchEnv(backend, validate_obs, validate_command,
        budget=CountBudget(2, 2), rlprep_batch_v1=True, **kw)


def test_actor_transcript_unchanged_by_truth_and_eval_reads_zero():
    transcripts, private = [], []
    actions = [{'command': {'issued_command': 1}, 'done': False}] * 2
    for offset in (0, 19):
        env = wrapper(Backend(offset), training=True)
        initial = env.reset([{}, {}])
        actors, terminal = env.step(actions)
        transcripts.append(repr((initial, actors, terminal)))
        private.append(env.training_output())
        # Training critic is separate and cannot mutate the actor result.
        copied = deepcopy(actors)
        env.training_output()[0].reward['reward'] = 123
        assert actors == copied
        env.reset([{}], indices=(1,))
        assert env.env.previous[0] is not None  # untouched world history retained
        with pytest.raises(RuntimeError, match='no current'):
            env.training_output()
    assert transcripts[0] == transcripts[1]
    assert private[0][0].critic != private[1][0].critic
    ev_backend = Backend()
    ev = wrapper(ev_backend)
    ev.reset([{}, {}]); ev.step(actions)
    assert ev_backend.reads == 0
    with pytest.raises(RuntimeError, match='unavailable'):
        ev.training_output()
    # Poisoned backend data must fail validation, including in training.
    ev_backend.read_actor = lambda i: ({'own_rgb': [], 'issued': [], 'skill': 'grasp', 'qpos': [1]}, ())
    with pytest.raises(AssertionError):
        ev.env.actor_inputs()


def test_count_cap_stops_before_backend_and_shaping_telescopes(tmp_path):
    backend = Backend()
    with pytest.raises(ValueError, match='default OFF'):
        PreparationBatchEnv(backend, validate_obs, validate_command)
    for kwargs in ({}, {'enabled': True, 'act_beats_persistence': True}):
        with pytest.raises(RuntimeError, match='design-only'):
            start_training(**kwargs)
    env = wrapper(backend)
    env.reset([{}, {}])
    actions = [{'command': {'issued_command': 1}, 'done': False}] * 2
    env.step(actions)
    with pytest.raises(RuntimeError, match='cap_end'):
        env.step(actions)
    assert backend.steps == 1 and env.transitions == 2
    assert env.audit[-1]['cap_end'] is True
    assert env.audit[-1]['category'] and env.audit[-1]['blocking_object']
    assert env.audit[-1]['minimum_gap_m'] is None
    env.write_audit(tmp_path / 'audit.jsonl')
    assert len((tmp_path / 'audit.jsonl').read_text().splitlines()) == 2
    # Ng1999 potential shaping: a finite terminal has Phi=0. Collector cuts do not.
    p = [potential(1, .4, 1), potential(.6, .2, 1), potential(.8, .3, 1)]
    gamma = .995  # unchanged PR530 per-0.1SIM discount
    rewards = [shaped_reward(p[i], p[i+1], first_success=False,
                             terminal=i == 1, gamma=gamma)['reward'] for i in range(2)]
    assert rewards[0] + gamma * rewards[1] == pytest.approx(-p[0])
    repeated = Backend()
    repeated.read_training = lambda i: (dict(distance_m=1., alignment_rad=.2,
        target_xy=None, stable_lift=repeated.steps % 2 == 1), (0.,))
    train = PreparationBatchEnv(repeated, validate_obs, validate_command,
        budget=CountBudget(2, 6), rlprep_batch_v1=True, training=True)
    train.reset([{}, {}])
    bonuses = []
    for _ in range(3):
        train.step(actions)
        bonuses.append(train.training_output()[0].reward['success_reward'])
    assert bonuses == [10., 0., 0.]  # no second bonus for drop/regrasp


def test_real_warp3_marker_shape_and_missing_proof_rejected(tmp_path):
    # Same shape as the supplied marker: proofs, not invented backend/gate keys.
    row = dict(status='RECORD_API_READY', ready=True, source_sha=WARP3_SOURCE,
               controller_source=WARP3_CONTROLLER, centre_mask_annotation_supported=False,
               proofs={key: {'path': '/raw/' + key, 'sha256': 'a' * 64}
                       for key in ('gate', 'reset_pause', 'native_recording', 'actual_actor')})
    path = tmp_path / 'RECORD_API_READY.json'
    path.write_text(json.dumps(row))
    report = inspect_warp3_marker(path)
    assert report['marker_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report['proofs_retrieved_this_task'] is False
    del row['proofs']['actual_actor']
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match='actual_actor'):
        inspect_warp3_marker(path)
