"""pairact-r1 draft: pure checks plus an optional tiny synthetic head/loss check."""
import json
import platform
from pathlib import Path

import numpy as np
import pytest

from harness import grasp_act_contract as c
from harness import pairact_r1 as p

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json'


def test_registered_config_validates_and_deviations_fail():
    cfg = p.load_config(CONFIG)
    assert cfg['steps'] == 20000 and cfg['seed'] == 20261020 and cfg['issued_clock_deadband'] == 2
    assert cfg['selection']['split'] == 'validation'
    for key, value in [('selection', {'split': 'heldout'}), ('issued_clock_deadband', 1),
                       ('base_arm', 'B'), ('steps', 20001), ('sampling', {'mode': 'x'})]:
        bad = json.loads(CONFIG.read_text())
        bad[key] = value
        with pytest.raises(ValueError):
            p.validate_config(bad)


def test_history_dither_matches_act18_and_dropout_min_k_stays_visible():
    rng = np.random.default_rng(0)
    state = np.zeros(c.CONTEXT_DIM, np.float32)
    out = p.history_dither(state, rng, 6, 1.)
    pwm = np.rint(out[p.pwm_columns()] * 1000)
    assert np.all((np.abs(pwm) >= 1) & (np.abs(pwm) <= 6))
    others = np.setdiff1d(np.arange(c.CONTEXT_DIM), p.pwm_columns())
    assert np.all(out[others] == 0)
    state = np.arange(c.CONTEXT_DIM, dtype=np.float32)
    for seed in range(50):
        out = p.history_dropout(state, np.random.default_rng(seed), .999, p.VISIBLE_MIN_K)
        changed = {i // p.ENTRY for i in np.flatnonzero(out != state)}
        # k in 12..15: every event changes at least one entry of the 5 visible ones (11..15)
        assert changed and max(changed) >= 11 and all(e < 15 for e in changed)
        ages = [e * p.ENTRY + 13 for e in range(c.HISTORY)]
        assert np.all(out[ages] == state[ages])
    with pytest.raises(ValueError):
        p.validate_history_options(dropout_min_k=12)


def test_v7_clock_deadband_two_ignores_small_moves_and_zero_matches_contract():
    pwm = {str(s): 1500 for s in c.SERVOS}
    v7, v6, ref = p.DeadbandIssuedClock(2), p.DeadbandIssuedClock(0), c.IssuedClock()
    seq = [0, 2, 1, 3, 3, 0]
    for i, d in enumerate(seq):
        x = dict(pwm, **{'1': 1500 + d})
        a, b, r = v7.observe('grasp', i * .1, x), v6.observe('grasp', i * .1, x), ref.observe('grasp', i * .1, x)
        assert b == r
    assert v7.resets == 1          # only 3->0 (|d|=3) resets; |d|<=2 moves do not
    with pytest.raises(ValueError):
        p.DeadbandIssuedClock(1)


def test_v7_reset_count_exact():
    pwm = {str(s): 1500 for s in c.SERVOS}
    clock = p.DeadbandIssuedClock(2)
    for i, d in enumerate([0, 2, 5, 6, 9]):
        clock.observe('grasp', i * .1, dict(pwm, **{'3': 1500 + d}))
    assert clock.resets == 2      # 2->5 and 6->9


def test_carry_teacher_phases_map_and_unknown_phase_rejected():
    assert p.stage_from_phase('carry:door_pass') == 'carry'
    assert p.stage_from_phase('carry:lower') == 'place'
    assert p.stage_from_phase('carry:done') == 'complete'
    with pytest.raises(ValueError, match='unmapped'):
        p.stage_from_phase('carry:teleport')


def _samples(skills):
    return [dict(sample_id=f's{i}', skill=s, t=round(i * .1, 3)) for i, s in enumerate(skills)]


def test_episode_stage_targets_and_transition_weights():
    skills = ['grasp'] * 6 + ['release'] * 6
    phases = ['align', 'align', 'ready', 'ready', 'grasp', 'grasp',
              'carry:door_pass', 'carry:to_zone', 'carry:lower', 'carry:open', 'carry:done', 'carry:done']
    samples = _samples(skills)
    pad = np.zeros((12, c.CHUNK), bool)
    for i in range(12):
        end = 6 if i < 6 else 12
        pad[i, max(0, end - i):] = True
    targets = p.episode_stage_targets(samples, {s['sample_id']: ph for s, ph in zip(samples, phases)}, pad)
    assert targets[0, 0] == p.stage_index('alignment') and targets[0, 2] == p.stage_index('ready')
    assert targets[5, 1] == p.PAD           # never crosses into the carry segment
    segments = p.segment_ids_from_samples(samples)
    assert segments == [0] * 6 + [1] * 6
    w = p.transition_row_weights(targets[:, 0], segments, window_rows=1, weight=3.)
    # alignment->ready at 2, ready->execute at 4, carry->place at 8, place->complete at 10
    assert w.tolist() == [1, 3, 3, 3, 3, 1, 1, 3, 3, 3, 3, 1]
    with pytest.raises(ValueError, match='without teacher_phase'):
        p.episode_stage_targets(samples, {}, pad)


def test_weighted_completion_priors_use_sampler_mass():
    priors = p.weighted_completion_priors(['grasp'] * 4, [0., 0., 0., 1.], [1., 1., 1., 3.])
    assert priors['grasp']['positive_fraction'] == pytest.approx(.5)
    assert priors['grasp']['positive_n'] == 1 and priors['grasp']['rows_N'] == 4


def test_offline_gate_and_selection():
    target = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 7, 7]
    segments = [0] * 14
    done_t = [0] * 13 + [1]
    clean = p.offline_metrics(target, target, segments, [0.] * 13 + [1.], done_t)
    assert clean['stage_macro_acc'] == 1 and clean['premature_ready'] == 0
    assert all(v['recall'] == 1 for v in clean['transitions'].values())
    ok, why = p.gate(clean, clean)
    assert ok, why
    assert p.gate(clean)[1] == ['G5 dithered-history check missing']
    early = list(target); early[1] = 2          # READY during alignment
    bad = p.offline_metrics(early, target, segments, [0.] * 13 + [1.], done_t)
    assert not p.gate(bad, clean)[0] and any('G2' in r for r in p.gate(bad, clean)[1])
    rows = [dict(step=1000, passed=True, clean=clean), dict(step=2000, passed=True, clean=clean),
            dict(step=3000, passed=False, clean=clean)]
    assert p.select_checkpoint(rows) == 1000
    assert p.select_checkpoint([dict(step=1, passed=False, clean=clean)]) is None


def test_barrier_holds_carry_and_place_until_go():
    b = p.PairActBarrier()
    prev = dict(t=0., wheels=[0.] * 4, duration_s=[0.] * 4, pwm={str(s): 2000 for s in c.SERVOS})
    val = dict(prev, t=.1, wheels=[.35] * 4)
    with pytest.raises(ValueError):
        b.propose(val, False, prev, stage='READY')
    b.propose(val, False, prev, stage='carry')
    out, done = b.issue(.1, prev, val, False, permit=False)
    assert out['wheels'] == [0.] * 4 and not done
    b.propose(val, False, prev, stage='ready')
    out, _ = b.issue(.2, prev, val, False, permit=True)
    assert b.started and out['wheels'] == [.35] * 4
    b.propose(val, False, prev, stage='place')
    out, _ = b.issue(.3, prev, val, False, permit=True)
    assert out['wheels'] == [.35] * 4


def test_place_sync_freezes_until_second_permit():
    b = p.PairActBarrier(place_sync=p.PLACE_SYNC_MODE)
    prev = dict(t=0., wheels=[0.] * 4, duration_s=[0.] * 4, pwm={str(s): 1500 for s in c.SERVOS})
    val = dict(prev, t=.1, wheels=[.35] * 4)
    b.propose(val, False, prev, stage='ready'); b.issue(.1, prev, val, False, permit=True)
    b.propose(val, False, prev, stage='place')
    assert b.place_ready
    out, _ = b.issue(.2, prev, val, False, permit=True, place_permit=False)
    assert out['wheels'] == [0.] * 4
    out, _ = b.issue(.3, prev, val, False, permit=True, place_permit=True)
    assert out['wheels'] == [.35] * 4 and b.place_started


def test_stage_head_loss_has_gradients_and_ignores_stage_as_input():
    if platform.system() != 'Linux':
        pytest.skip('Linux CI synthetic tensors only')
    torch = pytest.importorskip('torch')
    from torch import nn
    from types import SimpleNamespace
    from harness import beamact3

    class Model(nn.Module):
        def __init__(self):
            super().__init__(); self.action_head = nn.Linear(6, 14)
        def forward(self, b):
            assert 'stage_target' not in b
            return self.action_head(b['features']), (None, None)

    class Policy(nn.Module):
        def __init__(self):
            super().__init__(); self.model = Model(); self.config = SimpleNamespace(dim_model=6)
        def forward(self, b):
            y = self.model(b)[0]; loss = (y - b['action']).abs()[~b['action_is_pad']].mean()
            return loss, dict(l1_loss=loss.item())

    stats = dict(action_mean=[0.] * 14, action_std=[1.] * 14)
    torch.manual_seed(3)
    pol = p.install_stage_head(beamact3.install_head(Policy(), stats))
    state = torch.zeros(2, c.CONTEXT_DIM); state[:, c.HISTORY * 14] = 1
    action = torch.zeros(2, c.CHUNK, 14); action[0, :, :4] = .35; action[0, :, -1] = 1
    pad = torch.zeros(2, c.CHUNK, dtype=torch.bool); pad[:, 5:] = True
    target = torch.arange(16).reshape(2, 8) % len(p.STAGES)
    target[pad] = p.PAD
    b = dict(features=torch.randn(2, 8, 6), action=action, action_is_pad=pad, stage_target=target,
             **{'observation.state': state})
    loss, metrics = p.policy_loss(pol, b, mode='balanced_bce_v1', stats=stats,
                                  priors={'grasp': {'positive_fraction': .5}})
    loss.backward()
    assert metrics['stage_ce_loss'] > 0 and pol.model.action_head.stage.weight.grad.abs().sum() > 0
    assert pol.model.action_head.stage.out_features == 8


def test_trainer_pairact_flags_are_default_off_and_validated(tmp_path):
    import subprocess, sys
    base = [sys.executable, str(ROOT / 'scripts/train_grasp_act.py'), '--dataset', str(tmp_path),
            '--output', str(tmp_path / 'out'), '--stage', 'main', '--steps', '20000']
    def run(*extra):
        return subprocess.run(base + list(extra), capture_output=True, text=True, cwd=ROOT)
    r = run('--pairact-r1-config', str(CONFIG))
    assert r.returncode == 2 and 'both --pairact-r1-config' in r.stderr
    targets = tmp_path / 'stage-targets.json'; targets.write_text('{}')
    common = ('--pairact-r1-config', str(CONFIG), '--pairact-r1-stage-targets', str(targets))
    r = run(*common, '--seed', '20261020')
    assert r.returncode == 2 and 'registered base arm' in r.stderr
    r = run(*common, '--seed', '20261020', '--beamact3-v1', 'A', '--done-loss', 'balanced_bce_v1',
            '--execution-host-profile', 'beamact1_gcp2', '--checkpoint-every', '500')
    assert r.returncode == 2 and 'registered steps' in r.stderr


def _synthetic_dataset(tmp_path):
    from harness.grasp_act_data import DATA_SCHEMA, IMAGE_HW, sha256, write_json
    skills = ['grasp'] * 6 + ['release'] * 6
    phases = ['align', 'align', 'ready', 'ready', 'grasp', 'grasp',
              'carry:door_pass', 'carry:to_zone', 'carry:lower', 'carry:open', 'carry:done', 'carry:done']
    n = len(skills)
    data, raw = tmp_path / 'data', tmp_path / 'run' / 'raw'
    (data / '8340000-r1').mkdir(parents=True); raw.mkdir(parents=True)
    samples = [dict(sample_id=f'e:{i}:r1', robot_id='r1', role='teal', object_kind='long_beam', skill=s,
                    t=round(i * .1, 3)) for i, s in enumerate(skills)]
    teacher = raw / 'teacher-r1.jsonl'
    teacher.write_text(''.join(json.dumps(dict(sample_id=s['sample_id'], teacher_phase=ph)) + '\n'
                               for s, ph in zip(samples, phases)))
    state = np.zeros((n, c.CONTEXT_DIM), np.float32)
    for i, s in enumerate(skills):
        state[i, c.HISTORY * 14 + c.SKILLS.index(s)] = 1
    pad = np.zeros((n, c.CHUNK), bool)
    for i in range(n):
        pad[i, max(0, (6 if i < 6 else 12) - i):] = True
    action = np.zeros((n, c.CHUNK, 14), np.float32); action[[5, 11], 0, -1] = 1
    folder = data / '8340000-r1'
    np.savez_compressed(folder / 'tensors.npz', state=state, action=action, action_is_pad=pad,
                        image_index=np.zeros((n, 4), np.int64))
    np.save(folder / 'images.npy', np.zeros((1, 3, *IMAGE_HW), np.uint8))
    write_json(folder / 'samples.json', samples)
    stats = dict(schema=DATA_SCHEMA, train_seeds=[8340000], state_mean=[0.] * c.CONTEXT_DIM,
                 state_std=[1.] * c.CONTEXT_DIM, action_mean=[0.] * 14, action_std=[1.] * 14)
    write_json(data / 'normalization.json', stats)
    manifest = dict(schema=DATA_SCHEMA, complete=True, protocol=dict(train_seeds=[8340000]),
                    normalization=dict(path='normalization.json', sha256=sha256(data / 'normalization.json')),
                    episodes=[dict(path='8340000-r1', seed=8340000, split='train', robot_id='r1',
                                   source_root=str(tmp_path / 'run'),
                                   source_hashes={'raw/teacher-r1.jsonl': sha256(teacher)},
                                   files={f.name: sha256(f) for f in folder.iterdir()})])
    write_json(data / 'manifest.json', manifest)
    return data


def test_sidecar_builder_and_pair_dataset_end_to_end(tmp_path):
    pytest.importorskip('torch')
    from scripts.build_pairact_r1_stage_targets import build
    data = _synthetic_dataset(tmp_path)
    sidecar = build(data, tmp_path / 'targets')
    assert sidecar['missing_stages'] == ['approach', 'recover']
    cfg = p.load_config(CONFIG)
    ds = p.pair_dataset_class()(data, 'train', stage_manifest=tmp_path / 'targets/stage-targets.json',
                                seed=cfg['seed'], history=cfg['history_augmentation'], sampling=cfg['sampling'])
    assert len(ds) == 12 and ds.row_weights.max() == 3.
    clean = ds[0]
    assert clean['stage_target'][0] == p.stage_index('alignment') and set(clean) >= {'observation.state'}
    ds.augment = True
    changed = [not np.array_equal(ds[i]['observation.state'], clean['observation.state']) for i in [0] * 5]
    assert any(changed)
    import torch
    picks = ds.sample(torch.Generator().manual_seed(0), 64)
    assert all(0 <= i < 12 for i in picks)
    priors = ds.completion_priors()
    assert set(priors) == {'grasp', 'release'}
    with pytest.raises(ValueError, match='TRAIN only'):
        p.pair_dataset_class()(data, 'validation', stage_manifest=tmp_path / 'targets/stage-targets.json',
                               history=cfg['history_augmentation'])
    with pytest.raises(FileExistsError):
        build(data, tmp_path / 'targets')


def test_grasp_teacher_vocabulary_is_mapped():
    # P3 recorder table (dsh/pairact-p2-carrypath harness/pair_carry_recorder.py)
    fixed = {'approach': 'approach', 'search': 'approach', 'align': 'alignment', 'relook': 'recover',
             'ready': 'ready', 'pick': 'execute', 'verify': 'execute', 'complete': 'complete', 'done': 'complete'}
    assert {k: p.stage_from_phase(k) for k in fixed} == fixed
