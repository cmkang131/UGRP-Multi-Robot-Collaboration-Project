"""Small synthetic/offline checks only: no optimization, simulator or renderer."""
import io
import json
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from harness import grasp_act_contract as c
from harness.grasp_act_loss import completion_priors, policy_loss
from harness.grasp_act_policy import ChunkExecutor, GraspActor
from harness.grasp_act_rollout import OwnHistory
from scripts.analyze_grasp_act_predictions import analyze, metrics


def observation():
    stream = io.BytesIO(); Image.new('RGB', (640, 480), 'red').save(stream, 'JPEG')
    initial = {'t': 0., 'wheels': [0.]*4, 'duration_s': [0.]*4, 'pwm': {str(s): 1500 for s in c.SERVOS}}
    history = OwnHistory('r1', 'synthetic', initial)
    obs, jpgs, _ = history.observe(0., stream.getvalue(), skill='grasp', object_kind='cyan', role='west')
    return obs, jpgs


def test_ensemble_matches_pinned_upstream_including_zero_actions_and_expiry():
    torch = pytest.importorskip('torch')
    from lerobot.policies.act.modeling_act import ACTTemporalEnsembler
    rng = np.random.default_rng(3)
    chunks = rng.normal(0, .3, (14, c.CHUNK, c.ACTION_DIM))
    chunks[:, :, 4:8] = .5; chunks[:, :, -1] = 0.
    chunks[0, 1] = 0.  # Valid zero predictions must participate.
    source = iter(chunks)
    executor = ChunkExecutor(lambda *_: next(source), n_action_steps=1, temporal_ensemble_coeff=.01)
    upstream = ACTTemporalEnsembler(.01, c.CHUNK)
    obs, jpgs = observation()
    for i, chunk in enumerate(chunks):
        obs['t'] = i*.1
        for ref in obs['rgb']: ref['t'] = obs['t']
        actual, done = executor.step(obs, jpgs)
        expected = c.decode_action(upstream.update(torch.tensor(chunk[None])).numpy()[0])
        assert actual['wheels'] == pytest.approx(expected['wheels'])
        assert actual['duration_s'] == pytest.approx(expected['duration_s'])
        assert actual['pwm'] == expected['pwm'] and not done
        assert len(executor.chunks) <= c.CHUNK-1


@pytest.mark.parametrize('change', ['skill', 'gap', 'interrupt'])
def test_ensemble_forgets_prior_task_and_interruption(change):
    obs, jpgs = observation()
    chunk = [[.4]*4+[1.]*4+[0.]*5+[0.]]*c.CHUNK
    calls = []
    def predict(*_):
        calls.append(1)
        return chunk if len(calls) == 1 else [[0.]*c.ACTION_DIM]*c.CHUNK
    ex = ChunkExecutor(predict, n_action_steps=1, temporal_ensemble_coeff=.01)
    ex.step(obs, jpgs)
    obs['t'] = .3 if change == 'gap' else .1
    for ref in obs['rgb']: ref['t'] = obs['t']
    if change == 'skill': obs['skill'] = 'release'; obs['destination_zone'] = 'pickup_site'
    value, _ = ex.step(obs, jpgs, interrupt=change == 'interrupt')
    assert value['wheels'] == [0.]*4
    if change == 'interrupt': assert not ex.chunks and len(calls) == 1


def test_ensemble_done_and_invalid_settings():
    obs, jpgs = observation()
    ex = ChunkExecutor(lambda *_: [[0.]*13+[1.]]*c.CHUNK,
                       n_action_steps=1, temporal_ensemble_coeff=.01)
    _, done = ex.step(obs, jpgs)
    assert done and not ex.chunks and not ex.pending
    for kwargs in ({'n_action_steps': 0}, {'n_action_steps': 9},
                   {'temporal_ensemble_coeff': .01},
                   {'n_action_steps': 1, 'temporal_ensemble_coeff': float('nan')}):
        with pytest.raises(ValueError): ChunkExecutor(None, **kwargs)


def test_weighting_uses_unique_rows_not_overlapping_horizons():
    state = np.zeros((10, c.CONTEXT_DIM)); state[:, c.HISTORY*14] = 1
    action = np.zeros((10, c.CHUNK, c.ACTION_DIM)); action[-1, :, -1] = 1
    data = SimpleNamespace(shards=[{'state': state, 'action': action}])
    assert completion_priors(data) == {'grasp': {'positive_n': 1, 'rows_N': 10, 'positive_fraction': .1}}


def test_balanced_completion_replaces_only_done_l1_and_masks_padding():
    torch = pytest.importorskip('torch')
    class Model(torch.nn.Module):
        def forward(self, batch): return batch['prediction'], (None, None)
    class Policy(torch.nn.Module):
        def __init__(self): super().__init__(); self.model = Model()
        def forward(self, batch):
            pred, _ = self.model(batch)
            valid = ~batch['action_is_pad']
            loss = (pred-batch['action']).abs()[valid].mean()
            return loss, {'l1_loss': loss.item()}
    prediction = torch.zeros((2, 8, 14), requires_grad=True)
    target = torch.zeros_like(prediction); target[0, 0, -1] = 1
    pad = torch.ones((2, 8), dtype=torch.bool); pad[:, 0] = False
    state = torch.zeros((2, c.CONTEXT_DIM)); state[:, c.HISTORY*14] = 1
    batch = {'action': target, 'prediction': prediction, 'action_is_pad': pad, 'observation.state': state}
    stats = {'action_mean': [0.]*14, 'action_std': [1.]*14}
    policy = Policy(); legacy, _ = policy_loss(policy, batch)
    assert legacy.item() == pytest.approx(1/28)
    priors = {'grasp': {'positive_fraction': .1}}
    loss, _ = policy_loss(policy, batch, mode='balanced_bce_v1', stats=stats, priors=priors)
    assert loss.item() == pytest.approx(np.log(2)*(.5/.1+.5/.9)/2)
    grad, = torch.autograd.grad(loss, prediction)
    assert grad[0, 0, -1] < 0 and grad[1, 0, -1] > 0
    assert abs(grad[0, 0, -1]/grad[1, 0, -1]) == pytest.approx(9.)
    assert (grad[:, 1:] == 0).all() and not policy.model._forward_hooks


def test_old_and_new_completion_output_cannot_be_confused():
    class Policy:
        def eval(self): return self
    stats = {'action_mean': [0.]*13+[.005], 'action_std': [1.]*13+[.075]}
    values = np.zeros((1, 8, 14)); values[0, 0, -1] = 1000; values[0, 1, -1] = -1000
    old = GraspActor(Policy(), stats).decode_predictions(values)
    new = GraspActor(Policy(), stats, done_mode='balanced_bce_v1').decode_predictions(values)
    assert old[0, 2, -1] == .005 and new[0, 2, -1] == .5
    assert new[0, 0, -1] == 1 and new[0, 1, -1] == 0
    assert np.array_equal(old[..., :-1], new[..., :-1])


@pytest.mark.parametrize('mode', ['legacy_l1', 'balanced_bce_v1'])
def test_checkpoint_roundtrip_preserves_completion_semantics(tmp_path, monkeypatch, mode):
    torch = pytest.importorskip('torch')
    pytest.importorskip('draccus'); pytest.importorskip('safetensors')
    from harness.grasp_act_policy import save_actor
    class Policy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.zeros(14))
            self.config = {'device': 'cpu', 'synthetic_serialization_test': True}
    monkeypatch.setattr('harness.grasp_act_policy.make_policy', lambda **kwargs: Policy())
    stats = {'action_mean': [0.]*14, 'action_std': [1.]*14}
    save_actor(Policy(), tmp_path/'actor', stats, {}, done_mode=mode)
    restored = GraspActor.load(tmp_path/'actor')
    assert restored.done_mode == mode and restored.stats == stats
    meta = json.loads((tmp_path/'actor/adapter.json').read_text())
    if mode == 'legacy_l1': assert 'done_mode' not in meta and meta['schema'].endswith('.v1')
    else: assert meta['done_mode'] == mode and meta['schema'].endswith('.v2')


def test_direction_uses_pulse_impulse_and_excludes_stationary_denominator():
    y = np.zeros((2, 1, 14)); y[0, 0, :4] = [-.35, .35, .35, -.35]; y[:, :, 4:8] = 1
    p = y.copy(); p[0, 0, :4] *= -1
    m = metrics(p, y, np.zeros((2, 1), bool))
    assert m['direction']['raw_lateral'] == {'match_n': 0, 'moving_target_N': 1, 'rate': 0., 'stationary_target_N': 1}
    assert m['direction']['raw_yaw']['moving_target_N'] == 0
    assert m['done']['positive_score_quantiles'] is None


def test_saved_prediction_analysis_rejects_partial_and_duplicate_denominators(tmp_path):
    manifest = tmp_path/'manifest.json'; pred = tmp_path/'predictions.jsonl'
    manifest.write_text(json.dumps({'episodes': [{'seed': 86045, 'split': 'validation', 'rows_selected': 2}]}))
    row = {'sample_id': 'train-86045:0:r1', 'prediction': [[0.]*14]*8,
           'target': [[0.]*14]*8, 'action_is_pad': [False]*8}
    pred.write_text(json.dumps(row)+'\n')
    with pytest.raises(ValueError, match='incomplete'): analyze(pred, manifest, tmp_path/'partial')
    pred.write_text((json.dumps(row)+'\n')*2)
    with pytest.raises(ValueError, match='duplicate'): analyze(pred, manifest, tmp_path/'duplicate')
    second = dict(row, sample_id='train-86045:1:r1')
    pred.write_text(json.dumps(row)+'\n'+json.dumps(second)+'\n')
    report = analyze(pred, manifest, tmp_path/'complete')
    assert report['episodes']['86045']['first_action']['valid_actions'] == 2
    assert report['episodes']['86045']['all_horizons']['valid_actions'] == 16


def test_act4_queue_never_inherits_old_approval_or_starts_before_measurement():
    from scripts.queue_grasp_act_act4 import build_queue
    q = build_queue('b'*40)
    assert not q['approved'] and not q['enabled'] and not q['remote_execution_started']
    assert not q['main_approval_template']['approved']
    assert q['project'] == 'ugrp-act-train-1014'
    assert q['machine']['max_run_duration'] == '8h' and q['machine']['idle_shutdown_s'] == 1200
    assert all(not j['approved'] and not j['enabled'] for j in q['jobs'])
    smoke = next(j for j in q['jobs'] if j['stage'] == 'smoke')
    assert 'measurement-receipt' in smoke['depends_on']
    assert smoke['command'][smoke['command'].index('--done-loss')+1] == 'balanced_bce_v1'
    closed = next(j for j in q['jobs'] if j['stage'] == 'closed-loop')
    assert closed['max_runs'] == 1 and not closed['seed_inventory_verified']
    assert closed['proposed_seed'] == 91101 and '{' not in ' '.join(closed['command'])
    plan = json.loads(__import__('pathlib').Path(closed['command'][closed['command'].index('--plan')+1]).read_text())
    assert plan['seed'] == 91101
