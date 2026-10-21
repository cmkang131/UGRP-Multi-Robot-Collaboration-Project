"""A-r1 pre-training check: aggregation helpers on small synthetic arrays (no model, no dataset)."""
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import act18_carry_r1 as r1
import act18_r1_gate_precheck as g
from harness import grasp_act_contract as c


def enc(pwm):
    return (np.asarray(pwm, np.float64) - 1500.) / 1000.


def action_rows(pwm1_list, done=None):
    action = np.zeros((len(pwm1_list), 14), np.float32)
    action[:, 8:13] = enc(1500)
    action[:, 8] = enc(pwm1_list)
    if done is not None:
        action[:, -1] = done
    return action


def state_with_history(history_pwm1, se=0.):
    """Raw contract state: history entry k has pwm1 = history_pwm1[k], other servos 1500."""
    state = np.zeros(c.CONTEXT_DIM, np.float32)
    columns = r1.pwm_columns().reshape(r1.HISTORY, r1.SERVOS)
    state[columns] = enc(1500)
    state[columns[:, 0]] = enc(history_pwm1)
    state[-2] = se / 120.
    return state


def test_layout_and_bins():
    assert c.CONTEXT_DIM == r1.HISTORY * r1.ENTRY + 28
    out = g.bin_counts([0, 0, 1, 2, 3, 9, 10, 19, 20, 489])
    assert {k: out[k] for k in ('0', '1-2', '3-9', '10-19', '>=20')} == \
        {'0': 2, '1-2': 2, '3-9': 2, '10-19': 2, '>=20': 2}
    assert out['total'] == 10 and out['fractions']['0'] == .2


def test_segments_split_on_gap_and_skill():
    skills = ['grasp', 'release', 'release', 'release', 'release', 'grasp']
    t = [0., .1, .2, .5, .6, .7]
    assert g.contiguous_segments(skills, t, 'release') == [(1, 3), (3, 5)]


def test_teacher_release_deltas_hold_or_large_jump():
    skills = ['grasp', 'release', 'release', 'release', 'release']
    t = [0., .1, .2, .3, .4]
    action = action_rows([1520, 1520, 1520, 2009, 2009])
    delta = g.teacher_release_pwm_deltas(action, skills, t)
    assert delta.shape == (3, 5)
    assert sorted(delta[:, 0].tolist()) == [0, 0, 489]
    bins = g.bin_counts(delta)
    assert bins['3-9'] == 0 and bins['>=20'] == 1 and bins['0'] == 14


def test_release_mass_and_done_labels():
    episodes = [dict(skill=['grasp', 'grasp', 'release', 'release'], t=np.array([0., .1, .2, .3])),
                dict(skill=['grasp', 'release'], t=np.array([0., .1]))]
    out = g.release_mass_summary(episodes, 3.)
    masses = out.pop('masses')
    # uniform: ep1 release .5*.5, ep2 .5*.5 -> .5 ; weighted: ep1 6/8*.5, ep2 3/4*.5 -> .75
    assert out['release_rows'] == 3 and out['release_entry_rows'] == 2
    assert out['release_mass_uniform_episode'] == pytest.approx(.5)
    assert out['release_mass_release_weighted'] == pytest.approx(.75)
    episodes[0]['action0'] = action_rows([2000] * 4, done=[0, 1, 0, 1])
    episodes[1]['action0'] = action_rows([2000] * 2, done=[1, 0])
    labels = g.done_label_summary(episodes, masses)
    assert labels['grasp']['rows'] == 3 and labels['grasp']['done_rows'] == 2
    assert labels['release']['done_row_fraction'] == pytest.approx(1 / 3)
    # weighted release: ep1 rows .1875 each (done at row 3), ep2 row .375 (not done)
    assert labels['release']['done_mass_fraction_weighted'] == pytest.approx(.1875 / .75)
    episodes[1]['action0'][0, -1] = .5
    with pytest.raises(SystemExit):
        g.done_label_summary(episodes, masses)


def test_augmentation_stats_dither_and_dropout():
    states = np.stack([state_with_history([1520] * 16) for _ in range(40)])
    out = g.augmentation_summary(states, 1, dither_max_pwm=6, dither_prob=1., dropout_prob=.5)
    before = out['history_delta_before']
    assert before['0'] == before['total'] == 40 * 15 * 5
    assert out['dither_entries_changed_fraction'] == 1.
    assert 1 <= out['dither_injected_max'] <= 6
    inj = out['dither_injected_abs']
    assert inj['>=20'] == 0 and inj['10-19'] == 0 and inj['total'] == 40 * 80
    after = out['history_delta_after_dither']
    assert after['3-9'] + after['1-2'] + after['10-19'] > 0 and after['>=20'] == 0
    assert 0 < out['dropout_rows_applied'] < 40
    # prob 0 dither changes nothing; dropout on constant history cannot be seen either
    none = g.augmentation_summary(states, 1, dither_max_pwm=6, dither_prob=1e-12, dropout_prob=.5)
    assert none['dither_entries_changed_fraction'] == 0. and none['dropout_rows_applied'] == 0


def test_history_deltas_and_teacher_open():
    state = state_with_history([1500 + 20 * k for k in range(16)], se=4.5)
    assert g.history_pwm(state).shape == (1, 16, 5)
    delta = g.history_pwm_deltas(state)
    assert np.all(delta[0, :, 0] == 20) and np.all(delta[0, :, 1:] == 0)
    episode = dict(seed=1, skill=['grasp', 'release', 'release'], action0=action_rows([2000, 1520, 2009]),
                   state=np.stack([state] * 3), t=np.array([0., .1, .2]))
    out = g.teacher_open_summary([episode])
    assert out['episodes_open'] == 1 and out['open_skill_elapsed_s']['median'] == pytest.approx(4.5, abs=1e-4)
    assert g.teacher_open_index(['grasp', 'release'], [2000, 1520]) is None


def test_first_chunk_open_and_episode_view():
    assert g.first_chunk_open([[1520] * 8, [1520, 1520, 1950] + [1520] * 5], [0., .1]) == (.1, 2)
    assert g.first_chunk_open([[1520] * 8], [0.]) == (None, None)
    skills = ['grasp'] * 3 + ['release'] * 12
    t = np.round(np.arange(15) * .1, 6)
    teacher = np.array([2000, 1520, 1520] + [1520] * 7 + [2009] * 5)   # teacher opens at row 10
    closed = [1520] * 8
    clean = [closed] * 15
    dither = {i: closed for i in range(3, 15)}
    dither[8] = [1520] * 5 + [1930, 1520, 1520]                         # row 8: 0.2 s before open
    te = [1950, 1520, 1930] + [1520] * 12                                # grasp: row 0 teacher open, row 2 early
    view = g.episode_gate_view(7, skills, t, teacher, clean, te, dither_chunk_pwm1=dither)
    assert view['teacher_open_tau'] == pytest.approx(.7)
    assert view['g_r4_clean_hit'] is False and view['g_r4_dither_hit'] is True
    assert view['first_chunk_open_clean']['tau'] is None
    first = view['first_chunk_open_dither']
    assert first['tau'] == pytest.approx(.5) and first['row'] == 5
    assert first['predicted_open_tau'] == pytest.approx(1.) and first['lead_vs_teacher_open_s'] == pytest.approx(.2)
    assert view['g_r6_grasp_te_open_ticks'] == 2 and view['g_r6_grasp_te_open_ticks_teacher_closed'] == 1
    # outside +-0.5 s does not count
    far = {i: closed for i in range(3, 15)}
    far[4] = [1930] * 8
    assert g.episode_gate_view(7, skills, t, teacher, clean, te, far)['g_r4_dither_hit'] is False


def test_temporal_ensemble_dilutes_single_open_chunk():
    closed = np.tile(np.r_[np.zeros(8), enc([1520, 1500, 1500, 1500, 1500]), 0.], (8, 1))
    opened = closed.copy()
    opened[:, 8] = enc(2009)
    t = np.round(np.arange(4) * .1, 6)
    assert g.temporal_ensemble_pwm1([closed] * 4, t) == [1520] * 4
    series = g.temporal_ensemble_pwm1([closed, closed, closed, opened], t)
    assert series[:3] == [1520] * 3 and 1520 < series[3] < g.OPEN_PWM1
    assert g.temporal_ensemble_pwm1([opened], [0.]) == [2009]
    # a gap resets the ensemble
    assert g.temporal_ensemble_pwm1([closed, opened], [0., .5]) == [1520, 2009]


def test_done_rates_and_summary():
    rates = g.done_rates([.7, .6, .9, .1, .66], [1, 1, 0, 0, 0])
    assert rates['recall'] == .5 and rates['false_done'] == pytest.approx(2 / 3)
    views = [dict(seed=1, release_rows=3, teacher_open_tau=.4, g_r4_clean_hit=False, g_r4_dither_hit=True,
                  first_chunk_open_clean=dict(tau=None, row=None, predicted_open_tau=None, lead_vs_teacher_open_s=None),
                  first_chunk_open_dither=dict(tau=.3, row=1, predicted_open_tau=.4, lead_vs_teacher_open_s=.1),
                  g_r6_grasp_te_open_ticks=2, g_r6_grasp_te_open_ticks_teacher_closed=0,
                  grasp_rows=5, grasp_rows_teacher_closed=3),
             dict(seed=2, release_rows=3, teacher_open_tau=None, g_r4_clean_hit=None, g_r4_dither_hit=None,
                  g_r6_grasp_te_open_ticks=0, g_r6_grasp_te_open_ticks_teacher_closed=0,
                  grasp_rows=2, grasp_rows_teacher_closed=2)]
    skills = ['grasp', 'grasp', 'release', 'release']
    out = g.summarize_gate(views, skills, [1, 0, 1, 0], [.9, .1, .2, .7], [.1, .3, .2, .4])
    assert out['G-r1']['recall'] == 1. and out['G-r1']['false_done'] == 0.
    assert out['G-r2']['recall'] == 0. and out['G-r2']['false_done'] == 1.
    assert out['G-r3']['normalized_action_l1_h0_mean'] == pytest.approx(.25)
    assert out['G-r4']['dither'] == dict(episodes=1, episodes_hit=1, fraction=1.)
    assert out['G-r4']['clean']['episodes_hit'] == 0 and out['G-r4']['episodes_without_teacher_open'] == [2]
    assert out['G-r5']['status'] == 'not_computed'
    assert out['G-r6']['teacher_grasp_te_open_ticks'] == 2
    assert out['G-r6']['teacher_grasp_te_open_ticks_where_teacher_closed'] == 0
    first = out['raw_chunk_open_first_appearance']
    assert first['dither']['episodes_with_open'] == 1 and first['dither']['chunk_row_counts'] == {'1': 1}
    assert first['clean']['episodes_with_open'] == 0


def test_c4b_v0_summary(tmp_path):
    replay = dict(worlds=[dict(outcome='failure', arms=dict(V0=dict(open_tau=None, chunk_open_tau=1.2))),
                          dict(outcome='failure', arms=dict(V0=dict(open_tau=None, chunk_open_tau=None))),
                          dict(outcome='success', arms=dict(V0=dict(open_tau=3.4, chunk_open_tau=3.0)))])
    path = tmp_path / 'replay.json'
    path.write_text(json.dumps(replay))
    out = g.c4b_v0_summary(path)
    assert out['failure'] == dict(worlds=2, te_open=0, chunk_open=1)
    assert out['success'] == dict(worlds=1, te_open=1, chunk_open=1)


def test_run_root_only_new_precheck_root(tmp_path):
    with pytest.raises(SystemExit):
        g.prepare_run_root(tmp_path / 'runs' / 'other-20261021T000000', 'x.json')
    with pytest.raises(SystemExit):
        g.prepare_run_root(tmp_path / 'elsewhere' / 'act18-r1-gate-precheck-20261021T000000', 'x.json')
    root = tmp_path / 'runs' / 'act18-r1-gate-precheck-20261021T000000'
    target = g.prepare_run_root(root, 'data-stats.json')
    assert json.loads((root / g.RUN_MARKER).read_text())['label'] == g.LABEL
    g.write_output(target, dict(label=g.LABEL))
    with pytest.raises(SystemExit):
        g.prepare_run_root(root, 'data-stats.json')
    assert g.prepare_run_root(root, 'baseline-gate.json').name == 'baseline-gate.json'
    unmarked = tmp_path / 'runs' / 'act18-r1-gate-precheck-20261021T000001'
    unmarked.mkdir()
    with pytest.raises(SystemExit):
        g.prepare_run_root(unmarked, 'x.json')


def test_default_off():
    with pytest.raises(SystemExit):
        g.main(['data-stats', '--dataset', 'x', '--run-root', 'runs/act18-r1-gate-precheck-20261021T000000'])


def synthetic_dataset(root):
    """Tiny manifest + tensors.npz + samples.json in the v7 layout (no images)."""
    root.mkdir()
    (root / 'norm.json').write_text('{}')
    episodes = []
    for number, split in enumerate(('train', 'train', 'validation')):
        folder = root / ('ep%d' % number)
        folder.mkdir()
        skills = ['grasp'] * 3 + ['release'] * 5
        pwm1 = [2000, 1520, 1520, 1520, 1520, 2009, 2009, 2009]
        done = [0, 0, 1, 0, 0, 0, 0, 1]
        state = np.stack([state_with_history([1520] * 16, se=.1 * i) for i in range(8)])
        action = action_rows(pwm1, done=done)[:, None, :].repeat(8, axis=1)
        np.savez(folder / 'tensors.npz', state=state, action=action)
        (folder / 'samples.json').write_text(json.dumps(
            [dict(skill=s, t=round(.1 * i, 6), seed=100 + number) for i, s in enumerate(skills)]))
        episodes.append(dict(seed=100 + number, split=split, path='ep%d' % number,
                             files={name: g.sha256(folder / name) for name in ('tensors.npz', 'samples.json')}))
    (root / 'manifest.json').write_text(json.dumps(dict(
        episodes=episodes, normalization=dict(path='norm.json', sha256=g.sha256(root / 'norm.json')))))
    return root


def test_data_stats_end_to_end_read_only(tmp_path):
    dataset = synthetic_dataset(tmp_path / 'dataset')
    before = {p: g.sha256(p) for p in dataset.rglob('*') if p.is_file()}
    run_root = tmp_path / 'runs' / 'act18-r1-gate-precheck-20261021T000000'
    assert g.main(['data-stats', '--enabled', '--dataset', str(dataset), '--run-root', str(run_root)]) == 0
    assert {p: g.sha256(p) for p in dataset.rglob('*') if p.is_file()} == before
    out = json.loads((run_root / 'data-stats.json').read_text())
    assert out['label'] == g.LABEL and out['verdict'] is None
    assert out['dataset']['manifest_matches_registered'] is False
    train = out['splits']['train']
    assert train['episodes'] == 2
    assert train['teacher_release_pwm_delta']['dither_3_9_zero'] is True
    assert train['release']['release_entry_rows'] == 2
    assert train['release']['release_mass_uniform_episode'] == pytest.approx(5 / 8)
    assert train['release']['release_mass_release_weighted'] == pytest.approx(15 / 18)
    assert train['done_labels']['grasp']['done_row_fraction'] == pytest.approx(1 / 3)
    assert train['teacher_open']['open_skill_elapsed_s']['median'] == pytest.approx(.5, abs=1e-4)
    aug = train['history_augmentation_release_rows']
    assert aug['rows'] == 10 and aug['history_delta_before']['0'] == aug['history_delta_before']['total']
    assert out['splits']['validation']['episodes'] == 1
