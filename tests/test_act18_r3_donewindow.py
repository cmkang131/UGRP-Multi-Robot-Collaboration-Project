"""R3 done-window and clock-jitter probe (default OFF) contract tests.

Spec: outputs/reports/claude-arch-parallel-20261019/act-C2-R3-spec.md section 4.
The five tests below are the pre-registered CPU checks for R3-A/R3-B:
  1. flags 0/None keep data, prior and targets byte identical
  2. K=10 makes exactly 200*10 grasp rows positive (200*9 added)
  3. the window never crosses an episode or skill boundary
  4. the policy input whitelist and shapes are unchanged
  5. R3-B jitter changes only verify_lift/hold clock inputs
"""
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from act18_policy import (DONE_CLOCK_JITTER_PHASES, ReferenceDataset, expand_done_window,
                          extend_targets, registered_pilot_checkpoint)
from act18_train import validate_probe_options
from harness import grasp_act_contract as contract
from harness.grasp_act_data import TRAIN_KEYS


def _jpeg_bytes():
    """One real 640x480 JPEG so Dataset.__getitem__ can decode the current frame."""
    from io import BytesIO
    from PIL import Image
    buffer = BytesIO()
    Image.new('RGB', (640, 480), (12, 34, 56)).save(buffer, format='JPEG', quality=60)
    return buffer.getvalue()


def _fixture(tmp_path, *, episodes=2, seed_base=99000):
    import hashlib
    root = tmp_path / 'dataset'
    root.mkdir(parents=True)
    frame = root / 'frame.jpg'
    frame.write_bytes(_jpeg_bytes())
    frame_sha = hashlib.sha256(frame.read_bytes()).hexdigest()
    manifest = dict(schema='ugrp.act17.jpeg_dataset.v1', complete=True, cohort='test',
                    normalization=None, episodes=[], eligible_train_seeds=[])
    for episode in range(episodes):
        seed = seed_base + episode
        stages = ['approach', 'approach', 'alignment', 'alignment'] + ['grasp'] * 12 + ['release'] * 3
        phases = ['start', 'fold', 'align', 'align'] + (
            ['hover', 'descent', 'close'] + ['lift', 'lift_settle', 'lookback_pose', 'lookback',
                                             'lookback_settle', 'verify_lift', 'hold', 'hold',
                                             'hold', 'hold', 'hold', 'hold'])[:12] + ['backoff'] * 3
        skills = ['grasp'] * 16 + ['release'] * 3
        rows = len(stages)
        states = np.zeros((rows, contract.CONTEXT_DIM), np.float32)
        for index in range(rows):
            states[index] = np.linspace(0., 1., contract.CONTEXT_DIM, dtype=np.float32)
            states[index, -2:] = np.array([min(120., index * .1) / 120.,
                                           min(120., index * .1) / 120.], np.float32)
        actions = np.zeros((rows, 1, contract.ACTION_DIM), np.float32)
        actions[:, 0, 0] = .35
        grasp_positive = 15  # last grasp row (hold)
        release_positive = rows - 1  # last release row
        actions[grasp_positive, 0, -1] = 1.
        actions[release_positive, 0, -1] = 1.
        samples = [dict(seed=seed, sample_id=f'{seed}:{index}:r1', t=.1 * index,
                        skill=skills[index], stage=stages[index], teacher_phase=phases[index])
                   for index in range(rows)]
        folder = root / str(seed)
        folder.mkdir()
        tensors = folder / 'tensors.npz'
        np.savez_compressed(tensors, state=states, action=actions,
                            action_is_pad=np.zeros((rows, 1), bool),
                            image_index=np.zeros((rows, 1), np.int64))
        frames = folder / 'frames.json'
        frames.write_text(json.dumps([dict(path=str(frame), sha256=frame_sha)]))
        (folder / 'samples.json').write_text(json.dumps(samples))
        files = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                 for name in ('tensors.npz', 'frames.json', 'samples.json')}
        manifest['episodes'].append(dict(seed=seed, split='train', path=str(seed),
                                         files=files, rows=rows))
        manifest['eligible_train_seeds'].append(seed)
    normalization = dict(schema='ugrp.grasp_act.dataset.v1', train_seeds=manifest['eligible_train_seeds'],
                         rows=sum(ep['rows'] for ep in manifest['episodes']),
                         state_mean=[0.] * contract.CONTEXT_DIM,
                         state_std=[1.] * contract.CONTEXT_DIM,
                         action_mean=[0.] * contract.ACTION_DIM,
                         action_std=[1.] * contract.ACTION_DIM)
    norm = root / 'normalization.json'
    norm.write_text(json.dumps(normalization))
    manifest['normalization'] = dict(path='normalization.json',
                                     sha256=hashlib.sha256(norm.read_bytes()).hexdigest())
    (root / 'manifest.json').write_text(json.dumps(manifest))
    return root


def test_zero_flags_are_byte_identical_and_explicit_zero_matches_default(tmp_path):
    root = _fixture(tmp_path)
    default = ReferenceDataset(root, 'train', chunk=8)
    explicit = ReferenceDataset(root, 'train', chunk=8, done_window_ticks=0, done_clock_jitter_s=None)
    for left, right in zip(default.shards, explicit.shards):
        assert np.array_equal(left['action'], right['action'])
        assert np.array_equal(left['action_is_pad'], right['action_is_pad'])
    assert default.completion_priors('uniform_episode_v1') == explicit.completion_priors('uniform_episode_v1')
    # The default path is the untouched parent implementation, including state.
    assert np.array_equal(default[0]['observation.state'], explicit[0]['observation.state'])
    # extend_targets without the flag returns the historical chunks.
    shard = default.shards[0]
    meta = default.metadata[:len(shard['state'])]
    rebuilt, pad = extend_targets(shard['action'][:, 0], meta, 8)
    assert np.array_equal(rebuilt, shard['action'])
    assert np.array_equal(pad, shard['action_is_pad'])


def test_k10_makes_exactly_200x10_grasp_rows_positive():
    episodes, rows = 200, 16
    actions = np.zeros((episodes * rows, 14), np.float32)
    metadata = []
    for episode in range(episodes):
        for index in range(rows):
            position = episode * rows + index
            metadata.append(dict(sample_id=f'{episode}:{index}:r1', t=.1 * index,
                                 skill='grasp' if index < 12 else 'release'))
        actions[episode * rows + 11, -1] = 1.  # grasp hold end
        actions[episode * rows + 15, -1] = 1.  # release backoff end
    expanded, receipt = expand_done_window(actions, metadata, 10)
    grasp = np.asarray([row['skill'] == 'grasp' for row in metadata])
    assert int(expanded[grasp, -1].sum()) == 200 * 10
    assert receipt['positive_rows'] == 200
    assert receipt['window_rows'] == 2000
    assert receipt['added_rows'] == 1800
    # Release positives are a different skill and are not expanded.
    assert int(expanded[~grasp, -1].sum()) == 200
    assert int(expanded[:, -1].sum()) == 2200
    # Every grasp episode has 10 consecutive window rows including the anchor.
    first = expanded[:rows, -1]
    assert first.tolist() == [0., 0.] + [1.] * 10 + [0.] * 3 + [1.]


def test_window_stops_at_episode_skill_and_time_gaps():
    actions = np.zeros((10, 14), np.float32)
    actions[5, -1] = 1.
    metadata = [dict(sample_id=('ep:0:r1' if i < 7 else 'next:0:r1'), t=.1 * i,
                     skill=('grasp' if i == 5 else 'release')) for i in range(7)]
    metadata += [dict(sample_id='other:0:r1', t=.1 * i, skill='grasp') for i in range(3)]
    actions[9, -1] = 1.
    expanded, receipt = expand_done_window(actions, metadata, 10)
    # Row 5 is positive; rows 4 is a different skill, so the window stops there.
    assert expanded[5, -1] == 1. and expanded[4, -1] == 0.
    # The second positive at row 9 belongs to another episode prefix: only rows
    # 7,8,9 share it, so at most 3 rows are positive (not 10).
    assert int(expanded[7:, -1].sum()) == 3
    assert receipt['stopped_by_boundary'] >= 1
    # A missing 0.1 s observation also stops the walk.
    actions = np.zeros((6, 14), np.float32)
    actions[5, -1] = 1.
    metadata = [dict(sample_id='ep:0:r1', t=t, skill='grasp') for t in (.1, .2, .3, .5, .6, .7)]
    expanded, receipt = expand_done_window(actions, metadata, 4)
    assert expanded[3:, -1].tolist() == [1., 1., 1.] and expanded[2, -1] == 0.


def test_input_whitelist_and_shapes_are_unchanged(tmp_path):
    root = _fixture(tmp_path)
    window = ReferenceDataset(root, 'train', chunk=8, done_window_ticks=10)
    item = window[0]
    assert set(item) == set(TRAIN_KEYS)
    assert item['observation.state'].shape == (contract.CONTEXT_DIM,)
    assert item['action'].shape == (8, contract.ACTION_DIM)
    assert item['action_is_pad'].shape == (8,)
    assert contract.CONTEXT_DIM == contract.HISTORY * 14 + len(contract.SKILLS) + len(contract.KINDS) \
        + len(contract.ROLES) + len(contract.DESTINATIONS) + 2
    # The window changes only the completion column of the target, never inputs.
    base = ReferenceDataset(root, 'train', chunk=8)
    assert np.array_equal(window[0]['observation.state'], base[0]['observation.state'])
    valid = ~window[0]['action_is_pad']
    assert not np.any(valid & base[0]['action_is_pad'])  # window only truncates
    assert np.array_equal(window[0]['action'][valid, :13], base[0]['action'][valid, :13])


def test_r3b_jitter_targets_only_verify_lift_and_hold_clocks(tmp_path):
    root = _fixture(tmp_path, episodes=2)
    base = ReferenceDataset(root, 'train', chunk=8)
    jittered = ReferenceDataset(root, 'train', chunk=8, done_window_ticks=10, done_clock_jitter_s=1.0)
    assert jittered.clock_jitter_rows == sum(
        row['teacher_phase'] in DONE_CLOCK_JITTER_PHASES for row in base.metadata)
    assert jittered.clock_jitter_rows > 0
    state_std = np.asarray(base.stats['state_std'], np.float32)
    state_mean = np.asarray(base.stats['state_mean'], np.float32)
    changed = 0
    for index, row in enumerate(base.metadata):
        before = base[index]['observation.state']
        after = jittered[index]['observation.state']
        delta_s = (after[-2:].astype(np.float64) - before[-2:]) * state_std[-2:]
        if row['teacher_phase'] in DONE_CLOCK_JITTER_PHASES:
            # The recorded clock dims are min(120 s, elapsed)/120, so a
            # U(-1,+1) s offset adds offset_s/120 before normalization.
            assert np.all(delta_s <= 1. / 120. + 1e-6) and np.all(delta_s >= -1. / 120. - 1e-6)
            assert np.all(after[-2:] >= (0. - state_mean[-2:]) / state_std[-2:] - 1e-6)
            changed += int(np.any(np.abs(delta_s) > 0))
            if np.any(np.abs(delta_s) > 1e-7):
                assert np.allclose(delta_s * 120., jittered.clock_jitter_offsets_s[index], atol=1e-4)
        else:
            assert np.array_equal(after, before)
        repeat = jittered[index]['observation.state']
        assert np.array_equal(after, repeat)  # static per-row offsets, not per-access RNG
    assert changed > 0
    offsets = jittered.clock_jitter_offsets_s
    assert np.all(offsets[~np.asarray([row['teacher_phase'] in DONE_CLOCK_JITTER_PHASES
                                       for row in base.metadata])] == 0.)
    # Strong evidence against an accidental constant shift: signed mean near 0.
    eligible = np.asarray([row['teacher_phase'] in DONE_CLOCK_JITTER_PHASES
                           for row in base.metadata])
    assert abs(offsets[eligible].mean()) < .35


def test_r3dw_options_and_probe_registration():
    assert validate_probe_options('act18-r3dw', Path('ckpt'), 10000, None, None, .5,
                                  None, False, False, 10, None) == 10000
    assert validate_probe_options('act18-r3dw', Path('ckpt'), 10000, None, None, .5,
                                  None, False, False, 10, 1.0) == 10000
    with pytest.raises(ValueError, match='requires --done-window-ticks'):
        validate_probe_options('act18-r3dw', Path('ckpt'), 10000, None, None, .5)
    with pytest.raises(ValueError, match='requires --init-checkpoint'):
        validate_probe_options('act18-r3dw', None, 10000, None, None, .5,
                               None, False, False, 10, None)
    with pytest.raises(ValueError, match='act18-r3dw'):
        validate_probe_options('act18-tune', Path('ckpt'), 2000, None, None, None,
                               None, False, False, 10, None)
    with pytest.raises(ValueError, match=r'\[1, 20\]'):
        validate_probe_options('act18-r3dw', Path('ckpt'), 10000, None, None, .5,
                               None, False, False, 0, None)
    with pytest.raises(ValueError, match='requires --done-window-ticks'):
        validate_probe_options('act18-r3dw', Path('ckpt'), 10000, None, None, .5,
                               None, False, False, None, 1.0)
    with pytest.raises(ValueError, match=r'\(0, 2\]'):
        validate_probe_options('act18-r3dw', Path('ckpt'), 10000, None, None, .5,
                               None, False, False, 10, 2.5)
    provenance = dict(candidate='act18-r3dw', cohort='act18-v7-reference', training_complete=True,
                      step=10000, protocol_sha256='a' * 64,
                      probe=dict(kind='done_window_finetune_v1', steps_override=10000,
                                 packaging_eligible=False,
                                 init_checkpoint=dict(model_sha256='b' * 64)))
    assert registered_pilot_checkpoint(provenance, 'a' * 64) is True
    provenance['probe']['packaging_eligible'] = True
    assert registered_pilot_checkpoint(provenance, 'a' * 64) is False
    provenance['probe']['packaging_eligible'] = False
    provenance['candidate'] = 'act18-tune'
    assert registered_pilot_checkpoint(provenance, 'a' * 64) is False
