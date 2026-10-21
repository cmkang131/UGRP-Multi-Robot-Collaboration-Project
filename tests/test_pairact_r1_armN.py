"""pairact-r1 arm N (near-field only): config pairing, carry masking, offline scope."""
import json
from pathlib import Path

import numpy as np
import pytest

from harness import grasp_act_contract as c
from harness import pairact_r1 as p

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'experiments/2026-10-21-pairact-r1'
ARM_F = EXP / 'PAIRACT_R1_TRAIN_CONFIG_DRAFT.json'
ARM_N = EXP / 'PAIRACT_R1_TRAIN_CONFIG_ARM_N.json'


def test_arm_configs_pair_and_only_scope_differs():
    f, n = p.load_config(ARM_F), p.load_config(ARM_N)
    assert (p.config_arm(f), p.segment_scope(f)) == ('F', 'full_v1')
    assert (p.config_arm(n), p.segment_scope(n)) == ('N', 'near_only_v1')
    assert n['seed'] == f['seed'] == 20261020 and n['steps'] == f['steps'] == 20000
    assert p.assert_arm_pair(f, n)
    for key, value in (('seed', 1), ('steps', 10000), ('sampling', {'mode': 'off'})):
        changed = dict(n, **{key: value})
        with pytest.raises(ValueError):
            p.assert_arm_pair(f, changed)


def test_arm_scope_must_match_registration():
    n = json.loads(ARM_N.read_text())
    with pytest.raises(ValueError, match='segment scope'):
        p.validate_config(dict(n, segment_scope='full_v1'))
    with pytest.raises(ValueError, match='unknown pairact-r1 arm'):
        p.validate_config(dict(n, arm='X'))
    with pytest.raises(ValueError, match='segment scope'):
        p.validate_config(dict(json.loads(ARM_F.read_text()), segment_scope='near_only_v1'))


def test_near_only_keep_masks_carry_and_padding_only():
    carry, place, execute = (p.stage_index(s) for s in ('carry', 'place', 'execute'))
    target = np.array([[execute, execute, carry, carry], [carry, carry, place, p.PAD]])
    keep = p.near_only_keep(target)
    assert keep.tolist() == [[True, True, False, False], [False, False, True, False]]
    w = p.scoped_row_weights([3., 1.], target, 'near_only_v1')
    assert w.tolist() == [3., 0.]
    assert p.scoped_row_weights([3., 1.], target, 'full_v1').tolist() == [3., 1.]
    with pytest.raises(ValueError):
        p.scoped_row_weights([1., 1.], target, 'other')


def test_carry_teacher_phases_are_the_excluded_rows():
    excluded = [ph for ph, st in p.TEACHER_PHASE_TO_STAGE.items() if st in p.NEAR_EXCLUDED_STAGES]
    carry_phases = ['carry:' + x for x in p.CARRY_TEACHER_PHASES[:9]]
    assert set(carry_phases) <= set(excluded)
    # the 3 s hold (grasp skill 'hold') and the whole place segment stay trained
    for kept in ('hold', 'lift', 'ready', 'align', 'carry:lower', 'carry:open', 'carry:raise', 'carry:retreat'):
        assert p.TEACHER_PHASE_TO_STAGE[kept] not in p.NEAR_EXCLUDED_STAGES


def test_offline_metrics_near_scope_drops_carry_rows_but_keeps_handback_transition():
    st = {s: p.stage_index(s) for s in p.STAGES}
    target = [st['ready'], st['execute'], st['carry'], st['carry'], st['place'], st['place']]
    pred = [st['ready'], st['execute'], st['approach'], st['approach'], st['place'], st['place']]
    seg = [0] * 6
    done_score = [0., 0., .9, .9, 0., 0.]           # carry rows would be done false positives
    done_target = [0., 1., 0., 0., 0., 1.]
    full = p.offline_metrics(pred, target, seg, done_score, done_target)
    near = p.offline_metrics(pred, target, seg, done_score, done_target, scope='near_only_v1')
    assert 'carry' in full['per_stage'] and 'carry' not in near['per_stage']
    assert full['done_false_positive'] > 0 and near['done_false_positive'] == 0
    assert near['scored_rows'] == 4 and near['segment_scope'] == 'near_only_v1'
    assert near['transitions']['carry->place'] == dict(hits=1, total=1, recall=1.)


def test_near_scope_dataset_masks_carry_loss_and_never_samples_carry_rows(tmp_path):
    pytest.importorskip('torch')
    import torch
    from scripts.build_pairact_r1_stage_targets import build
    import importlib.util
    spec = importlib.util.spec_from_file_location("_t_r1", ROOT / "tests/test_pairact_r1.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    _synthetic_dataset = mod._synthetic_dataset
    data = _synthetic_dataset(tmp_path)
    build(data, tmp_path / 'targets')
    cfg = p.load_config(ARM_N)
    manifest = tmp_path / 'targets/stage-targets.json'
    ds = p.pair_dataset_class()(data, 'train', stage_manifest=manifest, seed=cfg['seed'],
                                history=cfg['history_augmentation'], sampling=cfg['sampling'],
                                scope=p.segment_scope(cfg))
    carry = p.stage_index('carry')
    h0 = np.concatenate([t[:, 0] for t in ds.targets])
    assert (ds.row_weights[h0 == carry] == 0).all() and (ds.row_weights[h0 != carry] > 0).all()
    picks = ds.sample(torch.Generator().manual_seed(0), 256)
    assert not any(h0[i] == carry for i in picks)
    for i in range(len(ds)):
        item = ds[i]
        assert not (item['stage_target'] == carry).any()
        assert np.array_equal(item['action_is_pad'], item['stage_target'] == p.PAD)
    # row 5 (grasp end) has a carry-free horizon; row 4's horizon is the same rows -> unchanged
    full = p.pair_dataset_class()(data, 'train', stage_manifest=manifest, seed=cfg['seed'])
    assert np.array_equal(full[0]['action_is_pad'], ds[0]['action_is_pad'])
    with pytest.raises(ValueError, match='TRAIN only'):
        p.pair_dataset_class()(data, 'validation', stage_manifest=manifest, scope='near_only_v1')

