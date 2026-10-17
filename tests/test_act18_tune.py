"""Default-off TUNE probe options: init checkpoint receipt and align..close weighting."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from act16w_runtime import sha256
from act17_compact_records import original_sha256
from act18_policy import align_close_row_weights, weighted_sampler_mass
from act18_train import init_checkpoint_receipt, validate_probe_options


def _fixture(tmp_path, *, training_complete=True, chunk=8, step=100000, protocol_steps=100000):
    dataset = tmp_path / 'dataset'
    dataset.mkdir(parents=True)
    manifest = dataset / 'manifest.json'
    manifest.write_text('{"complete": true}\n')
    protocol = tmp_path / 'protocol.json'
    protocol.write_text('{"schema": "ugrp.act18.protocol.v1", "steps": %d}\n' % protocol_steps)
    checkpoint = tmp_path / 'checkpoint'
    checkpoint.mkdir(parents=True)
    (checkpoint / 'model.safetensors').write_bytes(b'weights')
    (checkpoint / 'config.json').write_text('{"chunk_size": %d}\n' % chunk)
    adapter = dict(schema='ugrp.act18.adapter.v1', chunk=chunk, provenance=dict(
        candidate='R8', step=step, training_complete=training_complete,
        protocol_sha256=sha256(protocol),
        dataset_manifest_sha256=original_sha256(manifest)))
    (checkpoint / 'adapter.json').write_text(__import__('json').dumps(adapter))
    (checkpoint / 'SHA256.json').write_text(__import__('json').dumps(
        {name: sha256(checkpoint / name) for name in ('model.safetensors', 'config.json', 'adapter.json')}))
    return checkpoint, protocol, dataset


def test_completed_matched_init_checkpoint_is_accepted(tmp_path):
    checkpoint, protocol, dataset = _fixture(tmp_path)
    receipt = init_checkpoint_receipt(checkpoint, __import__('json').loads(protocol.read_text()), protocol, dataset, 8)
    assert receipt['step'] == 100000
    assert receipt['model_sha256'] == sha256(checkpoint / 'model.safetensors')


def test_init_checkpoint_rejects_tamper_incomplete_or_wrong_chunk(tmp_path):
    checkpoint, protocol, dataset = _fixture(tmp_path)
    (checkpoint / 'model.safetensors').write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        init_checkpoint_receipt(checkpoint, __import__('json').loads(protocol.read_text()), protocol, dataset, 8)
    checkpoint, protocol, dataset = _fixture(tmp_path / 'second', training_complete=False)
    with pytest.raises(ValueError, match='completed matched'):
        init_checkpoint_receipt(checkpoint, __import__('json').loads(protocol.read_text()), protocol, dataset, 8)
    checkpoint, protocol, dataset = _fixture(tmp_path / 'third', chunk=100)
    with pytest.raises(ValueError, match='completed matched'):
        init_checkpoint_receipt(checkpoint, __import__('json').loads(protocol.read_text()), protocol, dataset, 8)


def test_probe_options_require_tune_candidate_and_bounds():
    assert validate_probe_options('act18-tune', Path('ckpt'), 2000, 4.0, 2.0) == 2000
    assert validate_probe_options('act18-tune', Path('ckpt'), 2000, None, None) == 2000
    with pytest.raises(ValueError, match='requires --init-checkpoint and --steps'):
        validate_probe_options('act18-tune', None, 2000, 4.0, 2.0)
    with pytest.raises(ValueError, match='requires --init-checkpoint and --steps'):
        validate_probe_options('act18-tune', Path('ckpt'), None, None, None)
    with pytest.raises(ValueError, match='tune options require'):
        validate_probe_options('R8', Path('ckpt'), 2000, None, None)
    with pytest.raises(ValueError, match='tune options require'):
        validate_probe_options('R100', None, None, 4.0, None)
    with pytest.raises(ValueError, match=r'\[1, 20000\]'):
        validate_probe_options('act18-tune', Path('ckpt'), 0, None, None)
    with pytest.raises(ValueError, match=r'\[1, 20000\]'):
        validate_probe_options('act18-tune', Path('ckpt'), 20001, None, None)
    with pytest.raises(ValueError, match=r'\[1, 20\]'):
        validate_probe_options('act18-tune', Path('ckpt'), 2000, 0, None)
    with pytest.raises(ValueError, match=r'\[1, 20\]'):
        validate_probe_options('act18-tune', Path('ckpt'), 2000, 20.5, None)
    with pytest.raises(ValueError, match=r'\[1, 20\]'):
        validate_probe_options('act18-tune', Path('ckpt'), 2000, None, 0.5)
    assert validate_probe_options('R8', None, None, None, None) is None


def test_align_close_weights_only_touch_declared_segments():
    metadata = [
        dict(stage='approach', teacher_phase='approach'),
        dict(stage='alignment', teacher_phase='align'),
        dict(stage='grasp', teacher_phase='hover'),
        dict(stage='grasp', teacher_phase='close'),
        dict(stage='grasp', teacher_phase='lift'),
        dict(stage='grasp', teacher_phase='hold'),
        dict(stage='grasp', teacher_phase='verify_lift'),
        dict(stage='release', teacher_phase='lookaround'),
    ]
    weights = align_close_row_weights(metadata, 4.0, 2.0)
    # 2단계 표: post-close(lift/hold/verify_lift)=4, pre-close(hover/close)=2, 나머지=1
    assert weights.tolist() == [1.0, 1.0, 2.0, 2.0, 4.0, 4.0, 4.0, 1.0]
    assert align_close_row_weights(metadata, 4.0, None).tolist() == [1.0, 1.0, 1.0, 1.0, 4.0, 4.0, 4.0, 1.0]
    assert align_close_row_weights(metadata, None, 2.0).tolist() == [1.0, 1.0, 2.0, 2.0, 1.0, 1.0, 1.0, 1.0]
    assert align_close_row_weights(metadata, None, None).tolist() == [1.0] * 8
    with pytest.raises(ValueError, match=r'\[1, 20\]'):
        align_close_row_weights(metadata, 0.5, 2.0)


def test_weighted_sampler_mass_is_episode_uniform_and_row_weighted():
    episodes = [__import__('numpy').array([0, 1]), __import__('numpy').array([2, 3])]
    mass = weighted_sampler_mass(episodes, [1.0, 1.0, 1.0, 3.0])
    assert mass.tolist() == pytest.approx([0.25, 0.25, 0.125, 0.375])
    with pytest.raises(ValueError, match='cover every episode row'):
        weighted_sampler_mass(episodes, [1.0, 1.0, 1.0])
    with pytest.raises(ValueError, match='positive finite'):
        weighted_sampler_mass(episodes, [1.0, 0.0, 1.0, 1.0])
