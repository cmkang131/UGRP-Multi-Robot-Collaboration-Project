"""Short non-physics tests: reward credit, privileged boundary and reset isolation."""
import copy
import math

import pytest

from scripts.rl_act_curriculum import Curriculum, Start
from scripts.rl_act_env import ActorEnv
from scripts.rl_act_reward import (GAMMA, Heuristics, StableLift, TrainingTruth,
                                   potential, reward_transition, shaped_reward,
                                   target_centre_from_own_mask)


def truth(*, distance=1., angle=1., centre=(0., 0.), lifted=False):
    return TrainingTruth(distance, angle, centre, lifted)


def test_off_matches_base_and_h1_h2_h3_have_distinct_credit():
    before, after = truth(), truth(distance=.5, angle=.2)
    flags = dict(distance_p95=1., first_done=True, terminal=False)
    off = reward_transition(before, after, **flags)
    base = shaped_reward(potential(1., 1., 1.), potential(.5, .2, 1.),
                         first_success=False, terminal=False)
    assert off['reward'] == base['reward']
    on = reward_transition(before, after, heuristics=Heuristics(True, True, True), **flags)
    terms = on['heuristic_terms']
    assert terms['h1_center_v1'] > 0
    assert terms['h2_false_done_v1'] == -10
    assert terms['h3_alignment_v1'] > 0
    out = reward_transition(before, truth(centre=None), heuristics=Heuristics(True), **flags)
    assert out['heuristic_terms']['h1_center_v1'] < 0
    lifted = reward_transition(before, truth(lifted=True), heuristics=Heuristics(True, True), **flags)
    assert lifted['success_reward'] == 10 and lifted['heuristic_terms']['h2_false_done_v1'] == -10
    confirmed = reward_transition(truth(lifted=True), truth(lifted=True),
                                 heuristics=Heuristics(True, True), **flags)
    assert confirmed['heuristic_terms']['h2_false_done_v1'] == 0


def test_visible_instance_mask_centre_and_empty_image():
    import numpy as np
    mask = np.zeros((480, 640), dtype=bool)
    assert target_centre_from_own_mask(mask) is None
    mask[239:241, 319:321] = True
    assert target_centre_from_own_mask(mask) == pytest.approx((0., 0.))
    mask[:] = False
    mask[0, 639] = True
    assert target_centre_from_own_mask(mask) == (1., -1.)
    with pytest.raises(ValueError):
        target_centre_from_own_mask(np.zeros((480, 640), dtype='uint8'))


def test_potential_cycle_telescopes_including_terminal():
    values = [truth(angle=.2), truth(angle=1.4), truth(angle=.1), truth(angle=.2)]
    terms = [reward_transition(a, b, distance_p95=1., first_done=False,
                 terminal=i == 2, heuristics=Heuristics(h3_alignment_v1=True))
             for i, (a, b) in enumerate(zip(values, values[1:]))]
    discounted = sum(GAMMA**i * r['heuristic_terms']['h3_alignment_v1'] for i, r in enumerate(terms))
    assert discounted == pytest.approx(.2 / math.pi)


@pytest.mark.parametrize('kwargs', [dict(distance=-1.), dict(angle=float('nan')),
                                   dict(centre=(1.1, 0.)), dict(lifted=1)])
def test_bad_truth_rejected(kwargs):
    with pytest.raises(ValueError):
        truth(**kwargs)


def test_unchanged_lift_requires_bilateral_force_and_full_three_seconds():
    score = StableLift()
    for i in range(31):
        score.add(i * .1, .012, 10., [.5, .49], False)
    assert not score.success
    score = StableLift()
    for i in range(30):
        score.add(i * .1, .012, 10., [.5, .5], False)
    assert not score.success
    assert score.add(3., .012, 10., [.5, .5], False)
    with pytest.raises(ValueError, match='WELD'):
        score.add(3.1, .02, 0., [1., 1.], True)


class Backend:
    def __init__(self):
        self.public = [dict(rgb='own-a', issued=0), dict(rgb='own-b', issued=0)]
        self.private = [truth(), truth()]
        self.private_reads = 0
        self.steps = 0

    def reset(self, plans, *, indices):
        for i, plan in zip(indices, plans):
            self.public[i]['issued'] = plan['seed']

    def read_actor(self, i):
        return self.public[i], (b'own-image',)

    def read_training(self, i):
        self.private_reads += 1
        return self.private[i], (self.private[i].distance_m,)

    def step(self, actions):
        self.steps += 1
        return [False, False]


def validate_observation(row):
    if set(row) != {'rgb', 'issued'}:
        raise ValueError('forbidden observation key')


def validate_command(row):
    if set(row) != {'issued'}:
        raise ValueError('forbidden command key')


def env(backend, **kwargs):
    return ActorEnv(backend, validate_observation, validate_command,
                    nworld=2, enabled=True, **kwargs)


def actions(done=False):
    return [dict(command={'issued': 1}, done=done) for _ in range(2)]


def test_evaluation_never_reads_truth_and_mutation_cannot_change_actor_inputs():
    b = Backend()
    e = env(b)
    with pytest.raises(RuntimeError, match='reset'):
        e.step(actions())
    first = e.reset([{'seed': 1}, {'seed': 2}])
    b.private = [truth(distance=100., lifted=True), truth(distance=50.)]
    inputs, _, training = e.step(actions())
    assert inputs == first and training == (None, None)
    assert b.private_reads == 0
    assert e.training_privileged_reward_reads == 0
    with pytest.raises(RuntimeError, match='unavailable'):
        e._truth(0)
    inputs[0].observation['issued'] = -99
    assert b.public[0]['issued'] == 1


def test_training_false_done_penalty_once_and_partial_reset_isolated():
    b = Backend()
    e = env(b, training=True, heuristics=Heuristics(h2_false_done_v1=True))
    e.reset([{'seed': 1}, {'seed': 2}])
    _, _, first = e.step(actions(True))
    _, _, second = e.step(actions(True))
    assert first[0].reward['heuristic_terms']['h2_false_done_v1'] == -10
    assert second[0].reward['heuristic_terms']['h2_false_done_v1'] == 0
    before = copy.deepcopy(b.public[1]), e.previous[1], e.done_latched[1]
    e.reset([{'seed': 3}], indices=[0])
    assert (b.public[1], e.previous[1], e.done_latched[1]) == before
    assert e.done_latched == [False, True]
    _, _, after = e.step(actions(True))
    assert after[0].reward['heuristic_terms']['h2_false_done_v1'] == -10
    assert after[1].reward['heuristic_terms']['h2_false_done_v1'] == 0


def test_policy_and_action_injection_rejected_before_physics():
    b = Backend()
    e = env(b)
    e.reset([{'seed': 1}, {'seed': 2}])
    b.public[0]['ground_truth'] = 123
    with pytest.raises(ValueError, match='forbidden observation'):
        e.actor_inputs()
    bad = actions()
    bad[0]['command']['contact'] = True
    with pytest.raises(ValueError, match='forbidden command'):
        e.step(bad)
    assert b.steps == 0
    with pytest.raises(ValueError, match='training-only'):
        env(Backend(), heuristics=Heuristics(True))


def test_curriculum_expands_training_only_deterministically_and_copies_plans():
    starts = [Start(i, i / 10, i / 20, {'seed': i}) for i in range(8)]
    kwargs = dict(evaluation_seeds=[90, 91], transition_limit=300, rng_seed=7)
    c = Curriculum(starts, h4_curriculum_v1=True, **kwargs)
    assert [len(c.pool(t)) for t in (0, 99, 100, 199, 200, 300)] == [2, 2, 4, 4, 8, 8]
    assert len(Curriculum(starts, **kwargs).pool(0)) == 8
    other = Curriculum(starts, h4_curriculum_v1=True, **kwargs)
    assert c.sample(0, 5) == other.sample(0, 5)
    c.sample(0, 1)[0]['seed'] = 99
    assert all(s.plan['seed'] == s.seed for s in starts)
    with pytest.raises(ValueError, match='overlap'):
        Curriculum(starts, **{**kwargs, 'evaluation_seeds': [3]})


def test_dependency_watch_does_not_mistake_teacher_transport_for_actor_reset(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'experiments/2026-10-16-rl1/tools/wait_for_warp.py'
    spec = importlib.util.spec_from_file_location('rl1b_watch', path)
    watch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(watch)
    monkeypatch.setattr(watch, 'ALERT', tmp_path / 'ops-alert.md')
    source = 'class WarpTransport:\n    def initialize(self): pass\n    def step(self): pass\n    def sync_render(self): pass\n'

    def git(*args):
        if args[0] == 'rev-parse':
            return (0, 'abc123', '') if args[-1] == 'claude/warp-act' else (1, '', '')
        if args[0] == 'ls-tree':
            return 0, 'scripts/warp_act_backend.py', ''
        if args[0] == 'show':
            return 0, source, ''
        raise AssertionError(args)

    monkeypatch.setattr(watch, 'git', git)
    assert not watch.inspect()['signal']
    source += '    def reset(self): pass\n'
    signalled = watch.inspect()
    assert signalled['signal'] and not signalled['runtime_admitted']
    source = 'class WarpTransport:\n    def step(self): pass\n'
    watch.ALERT.write_text('warp1: FAILED backend pilot\n')
    signalled = watch.inspect()
    assert signalled['signal'] and not signalled['runtime_admitted']
