"""Input-boundary, diagnostic-denominator and approval regressions; no training."""
import json

import numpy as np
import pytest

from harness import grasp_act_contract as c
from harness.grasp_act_data import IMAGE_KEYS, history_image, normalized_image
from harness.grasp_act_input import drop_command_history, validate_history_dropout
from scripts.analyze_grasp_act_memory import change_metrics, intervene, lag_metrics, visibility_summary
from scripts.grasp_act_training_guard import authorize_main
from scripts.queue_grasp_act_act5 import build_queue


def test_dropout_off_is_identity_and_does_not_advance_rng():
    torch = pytest.importorskip('torch')
    batch = {'observation.state': torch.ones(4, c.CONTEXT_DIM)}
    before = torch.get_rng_state().clone()
    assert drop_command_history(batch) is batch
    assert torch.equal(before, torch.get_rng_state())


def test_dropout_only_history_and_resume_rng_exact():
    torch = pytest.importorskip('torch')
    state = torch.arange(32*c.CONTEXT_DIM, dtype=torch.float32).reshape(32, -1)+1
    batch = {'observation.state': state, 'action': torch.ones(32, 8, 14),
             'action_is_pad': torch.zeros(32, 8, dtype=torch.bool), IMAGE_KEYS[0]: torch.ones(32, 3, 2, 2)}
    before = state.clone()
    rng = torch.get_rng_state().clone()
    dropped = drop_command_history(batch, .5)
    torch.set_rng_state(rng)
    restored = drop_command_history(batch, .5)
    assert torch.equal(dropped['observation.state'], restored['observation.state'])
    changed = (dropped['observation.state'][:, :224] == 0).all(1)
    assert changed.any() and not changed.all()
    assert torch.equal(dropped['observation.state'][~changed], state[~changed])
    assert torch.equal(dropped['observation.state'][:, 224:], state[:, 224:])
    assert torch.equal(state, before)
    for key in ('action', 'action_is_pad', IMAGE_KEYS[0]):
        assert dropped[key] is batch[key]
    all_dropped = drop_command_history(batch, 1.)
    assert (all_dropped['observation.state'][:, :224] == 0).all()


@pytest.mark.parametrize('value', [-.01, 1.01, float('nan'), float('inf'), True, '.2'])
def test_dropout_rejects_invalid_probability(value):
    with pytest.raises(ValueError):
        validate_history_dropout(value)


def test_raw_zero_and_training_mean_are_distinct_and_keep_instructions():
    batch = {'observation.state': np.ones(c.CONTEXT_DIM, np.float32),
             IMAGE_KEYS[0]: np.ones((3, 480, 640), np.float32)}
    stats = {'state_mean': [2.]*c.CONTEXT_DIM, 'state_std': [.5]*c.CONTEXT_DIM}
    zero, mean = (intervene(batch, variant, stats) for variant in ('commands_zero', 'commands_mean'))
    assert (zero['observation.state'][:224] == -4).all()
    assert (mean['observation.state'][:224] == 0).all()
    for b in (zero, mean):
        assert (b['observation.state'][224:] == 1).all()
        assert np.array_equal(b[IMAGE_KEYS[0]], batch[IMAGE_KEYS[0]])
    assert (batch['observation.state'] == 1).all()


def test_image_ablation_preserves_current_tile_location_and_normalization():
    frames = [np.full((3, 240, 320), v, np.uint8) for v in (30, 60, 90, 120)]
    original = history_image(frames)
    b = {IMAGE_KEYS[0]: original, 'observation.state': np.ones(c.CONTEXT_DIM)}
    only = intervene(b, 'current_rgb_only', {})[IMAGE_KEYS[0]]
    oldest = intervene(b, 'oldest_rgb_blank', {})[IMAGE_KEYS[0]]
    black = normalized_image(np.zeros_like(frames[0]))
    assert np.array_equal(only[:, :240, :320], black)
    assert np.array_equal(only[:, 240:, :320], black)
    assert np.array_equal(only[:, 240:, 320:], original[:, 240:, 320:])
    assert np.array_equal(oldest[:, 240:, :], original[:, 240:, :])
    assert np.array_equal(original, history_image(frames))


def test_sensitivity_signs_exclude_decoded_stationary_baseline():
    base = np.zeros((1, 14)); base[0, :4] = .1; base[0, 4:8] = 1
    pred = base.copy(); pred[0, :4] = .35
    result = change_metrics(pred, base)
    assert result['direction']['raw_forward']['moving_target_N'] == 1
    assert result['direction']['decoded_forward']['moving_target_N'] == 0
    assert result['direction']['decoded_forward']['rate'] is None
    assert result['direction']['decoded_forward']['activated_from_stationary_n'] == 1


def test_lag_excludes_gaps_and_reports_constant_as_undefined():
    a = np.zeros((4, 14)); a[:, :4] = .35; a[:, 4:8] = .5
    result = lag_metrics(a, [0, .1, 5., 5.1])
    assert result['pairs_N'] == 2
    assert result['axes']['forward']['pearson'] is None
    assert result['axes']['forward']['same_sign_n'] == 2
    assert lag_metrics(a, [0, .1, .2, .3], selected=[False, False, True, False])['pairs_N'] == 1


def test_current_absence_does_not_imply_history_absence():
    pixels = [{'sample_id': str(i), 'elapsed_s': i*.1,
        'full': {'pixels': 100 if i == 0 else 0, 'center': [.9, .5]},
        'tile': {'pixels': 25 if i == 0 else 0, 'center': [.9, .5]}} for i in range(3)]
    observations = [{'sample_id': str(i), 'rgb': [{'path': '0'}]*3+[{'path': str(i)}]} for i in range(3)]
    result = visibility_summary(pixels, observations)
    assert result['all_four_history_frames_absent_N'] == 0
    assert result['current_absent_intervals'][0]['frames_N'] == 2
    assert result['matched_visible_frames_N'] == 1
    with pytest.raises(ValueError, match='alignment'):
        visibility_summary(pixels[::-1], observations)


def test_dropout_needs_exact_main_approval_and_legacy_defaults_remain(tmp_path):
    file = tmp_path/'approval.json'
    approval = {'approved': True, 'stage': 'main', 'source_sha': 'a'*40,
        'dataset_manifest_sha256': 'd', 'smoke_summary_sha256': 's', 'steps': 10000,
        'blank_images': False, 'gate_promotion_authorized_if_all_conditions_pass': False}
    kwargs = dict(source='a'*40, dataset_hash='d', smoke_hash='s', steps=10000, blank=False)
    file.write_text(json.dumps(approval))
    authorize_main(file, **kwargs)
    with pytest.raises(ValueError, match='dropout'):
        authorize_main(file, **kwargs, command_history_dropout=.2)
    approval['command_history_dropout'] = .2; file.write_text(json.dumps(approval))
    authorize_main(file, **kwargs, command_history_dropout=.2)
    with pytest.raises(ValueError, match='dropout'):
        authorize_main(file, **kwargs)


def test_combined_queue_is_disabled_and_uses_matched_control():
    q = build_queue('a'*40)
    assert q['approved'] is False and q['enabled'] is False
    assert q['remote_execution_started'] is False
    jobs = {j['stage']: j for j in q['jobs']}
    assert len(jobs) == 12
    assert all(j['approved'] is False and j['enabled'] is False for j in jobs.values())
    for arm, value in (('act4-control', '0.0'), ('act5-dropout', '0.2')):
        smoke = jobs[arm+'/smoke']; main = jobs[arm+'/main']
        assert 'memory-review-receipt' in smoke['depends_on']
        assert smoke['command'][-2:] == ['--command-history-dropout', value]
        assert main['command'][-2:] == ['--command-history-dropout', value]
        assert '--done-loss' in smoke['command'] and 'balanced_bce_v1' in smoke['command']
        assert jobs[arm+'/closed-loop']['command'] is None
        assert q['main_approval_templates'][arm]['approved'] is False
    assert q['budgets']['training_max_wall_s_total'] == 46800
