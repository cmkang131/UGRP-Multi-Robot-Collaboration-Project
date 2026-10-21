"""A-r1 pre-training check: data statistics and a *current R8* G-r1..G-r6 baseline.

PRE_TRAIN_BASELINE. Not a verdict, not collected data. Nothing here decides whether
A-r1 opens (that stays with the owner-plan tournament rule); it checks that the G-r
measurement runs and records where the current R8 checkpoint sits before training.

Sub-commands (both default OFF, ``--enabled`` required):

``data-stats``  (CPU) reads the v7 dataset (manifest, tensors.npz, samples.json) read-only:
    teacher release PWM change distribution (0 / 1-2 / 3-9 / 10-19 / >=20), release
    entry rows and release mass before/after the registered release oversampling,
    grasp/release done-label ratios (rows and sampler mass), and the issued-history
    PWM change distribution before/after the registered history dither/dropout
    (``act18_carry_r1.history_dither`` / ``history_dropout``, unchanged).

``baseline-gate`` (GPU) runs the R8 step-100000 checkpoint forward only (no training,
    no physics) on the teacher validation episodes without VAL8 and computes G-r1..G-r6
    as written in ``experiments/2026-10-17-act18/CARRY_RETRAIN_R1_DRAFT.md`` section 3.
    The branch holds no gate *code*, only that table, so each G-r is implemented here
    literally from the table; operationalisation choices are recorded in the output
    (``operationalisation``) rather than silently fixed. Also aggregates the first raw
    chunk position predicting open (pwm1 >= 1900, the C4b ``chunk_open`` rule).

Outputs go only to a new run root ``runs/act18-r1-gate-precheck-<TS>/``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import act18_carry_r1 as r1  # noqa: E402
from act18_gripper_state import GRIPPER_ACTION_DIM, GRIPPER_OPEN_PWM  # noqa: E402

LABEL = 'PRE_TRAIN_BASELINE — 학습 전 점검, 판정 아님, 수집 데이터 아님'
SCHEMA = 'ugrp.act18.r1_gate_precheck.v1'
POLICY = 'learned (R8 step-100000, 재학습 전)'
DATA = 'teacher 데모 (act17-v7 dataset-r1, recorded teacher commands; no closed-loop student data)'
R8_MODEL_SHA256 = 'e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a'
DATASET_MANIFEST_SHA256 = '44c1c46073aa08ea028324ffe924b67d862a2f01b56f4db11afad17000a9b198'
RUN_PREFIX = 'act18-r1-gate-precheck-'
RUN_MARKER = 'PRECHECK_RUN.json'
OPEN_PWM1 = GRIPPER_OPEN_PWM            # 1900, sim "clearly open"; C4b OPEN_PWM1
DONE_THRESHOLD = .65                    # harness.grasp_act_contract.decode_action
TE_COEFF = .01                          # protocol.json inference.temporal_ensemble_coeff
PERIOD_S = .1
G_R4_WINDOW_S = .5
PWM_BINS = (('0', 0, 0), ('1-2', 1, 2), ('3-9', 3, 9), ('10-19', 10, 19), ('>=20', 20, None))
DRAFT_THRESHOLDS = {  # CARRY_RETRAIN_R1_DRAFT.md section 3; reference only, never applied here
    'G-r1': 'grasp done recall@.65 >= R8 - 2%p; grasp false-done <= R8',
    'G-r2': 'release done recall@.65 >= R8 - 2%p; release false-done <= R8',
    'G-r3': 'normalised h0 action L1 <= R8 * 1.10',
    'G-r4': 'raw chunk pwm1 >= 1900 within teacher open tick +-0.5 s in >= 90% episodes (dither history)',
    'G-r5': 'C4b V0 TE pwm1 >= 1900 in >= 6/10 failure worlds, success 9/9 kept',
    'G-r6': 'grasp TE pwm1 >= 1900 count 0 (teacher grasp rows and C2c grasp replay)',
}


# ----------------------------------------------------------------------------- helpers

def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def pwm_counts(encoded):
    """(pwm-1500)/1000 encoded values -> integer PWM counts."""
    return np.rint(np.asarray(encoded, np.float64) * 1000. + 1500.).astype(np.int64)


def bin_counts(abs_delta):
    """Counts of |dPWM| in the registered bins 0 / 1-2 / 3-9 / 10-19 / >=20."""
    values = np.asarray(abs_delta, np.int64).ravel()
    out = {}
    for name, low, high in PWM_BINS:
        mask = values >= low if high is None else (values >= low) & (values <= high)
        out[name] = int(mask.sum())
    out['total'] = int(values.size)
    out['fractions'] = {name: (out[name] / values.size if values.size else None)
                        for name, _, _ in PWM_BINS}
    return out


def contiguous_segments(skills, t, skill):
    """[start, stop) row ranges of consecutive ``skill`` rows spaced by one period."""
    segments, start = [], None
    for index, name in enumerate(skills):
        joined = (start is not None and name == skill
                  and abs(float(t[index]) - float(t[index - 1]) - PERIOD_S) < 1e-5)
        if name == skill and not joined:
            if start is not None:
                segments.append((start, index))
            start = index
        elif name != skill and start is not None:
            segments.append((start, index))
            start = None
    if start is not None:
        segments.append((start, len(skills)))
    return segments


def teacher_release_pwm_deltas(action0, skills, t):
    """|dPWM| between consecutive teacher h0 commands inside release segments (5 servos)."""
    pwm = pwm_counts(np.asarray(action0)[:, 8:13])
    deltas = [np.abs(np.diff(pwm[a:b], axis=0)) for a, b in contiguous_segments(skills, t, 'release')
              if b - a > 1]
    return np.concatenate(deltas) if deltas else np.zeros((0, r1.SERVOS), np.int64)


def history_pwm(states):
    """(N, 16, 5) integer issued-PWM history from raw contract states."""
    states = np.atleast_2d(np.asarray(states, np.float32))
    return pwm_counts(states[:, r1.pwm_columns()]).reshape(len(states), r1.HISTORY, r1.SERVOS)


def history_pwm_deltas(states):
    """|dPWM| between consecutive history entries, (N, 15, 5)."""
    return np.abs(np.diff(history_pwm(states), axis=1))


def teacher_open_index(skills, pwm1):
    """First release row whose teacher h0 pwm1 >= 1900, else None."""
    for index, (name, value) in enumerate(zip(skills, pwm1)):
        if name == 'release' and value >= OPEN_PWM1:
            return index
    return None


def first_chunk_open(chunk_pwm1, taus):
    """C4b ``chunk_open`` rule: first tick whose raw chunk has any row pwm1 >= 1900.

    Returns (tau, row) or (None, None)."""
    for tau, rows in zip(taus, chunk_pwm1):
        for row, value in enumerate(rows):
            if value >= OPEN_PWM1:
                return float(tau), int(row)
    return None, None


def temporal_ensemble_pwm1(chunks, t, coeff=TE_COEFF):
    """Deployed ChunkExecutor ensemble arithmetic (n_action_steps 1, k=.01) over decoded chunks.

    ``chunks`` is (T, chunk, 14) in decoded action units; resets on any gap != one period.
    Done-freeze is not modelled (teacher-forced offline view). Returns TE pwm1 per tick."""
    from harness import grasp_act_contract as contract
    out, pending, last = [], [], None
    for values, now in zip(chunks, t):
        if last is not None and abs(float(now) - float(last) - PERIOD_S) > 1e-5:
            pending = []
        last = now
        pending.append(np.asarray(values, np.float64))
        weights = np.exp(-coeff * np.arange(len(pending)))
        averaged = np.average([chunk[0] for chunk in pending], axis=0, weights=weights)
        out.append(int(contract.decode_action(averaged)['pwm']['1']))
        pending = [chunk[1:] for chunk in pending if len(chunk) > 1]
    return out


def done_rates(probability, label, threshold=DONE_THRESHOLD):
    probability = np.asarray(probability, np.float64)
    label = np.asarray(label, np.float64)
    positive, negative = label == 1, label == 0
    fire = probability >= threshold
    return dict(rows=int(len(label)), positive_rows=int(positive.sum()), negative_rows=int(negative.sum()),
                recall=(float(fire[positive].mean()) if positive.any() else None),
                false_done=(float(fire[negative].mean()) if negative.any() else None),
                threshold=threshold)


def quantiles(values):
    values = np.asarray([v for v in values if v is not None], np.float64)
    if not values.size:
        return None
    return dict(n=int(values.size), min=float(values.min()), p10=float(np.quantile(values, .1)),
                median=float(np.median(values)), p90=float(np.quantile(values, .9)),
                max=float(values.max()))


def source_sha():
    try:
        return subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def prepare_run_root(run_root, output_name):
    """Only a ``runs/act18-r1-gate-precheck-<TS>/`` root; never overwrite an output."""
    run_root = Path(run_root)
    if not re.fullmatch(re.escape(RUN_PREFIX) + r'\d{8}T\d{6}Z?', run_root.name) \
            or run_root.parent.name != 'runs':
        raise SystemExit('run root must be runs/%s<YYYYMMDDTHHMMSS[Z]>' % RUN_PREFIX)
    if run_root.exists():
        if not (run_root / RUN_MARKER).is_file():
            raise SystemExit('existing run root without %s; refuse to write' % RUN_MARKER)
    else:
        run_root.mkdir(parents=True)
        (run_root / RUN_MARKER).write_text(json.dumps(dict(schema=SCHEMA, label=LABEL), ensure_ascii=False) + '\n')
    target = run_root / output_name
    if target.exists():
        raise SystemExit('%s exists; outputs are never overwritten' % target)
    return target


def write_output(target, value):
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(target)


# ----------------------------------------------------------------------------- data-stats

def dataset_receipt(dataset, verify_files=True):
    dataset = Path(dataset)
    manifest = read_json(dataset / 'manifest.json')
    norm = manifest['normalization']
    receipt = dict(path=str(dataset), manifest_sha256=sha256(dataset / 'manifest.json'),
                   manifest_sha256_registered=DATASET_MANIFEST_SHA256,
                   normalization_sha256=sha256(dataset / norm['path']))
    receipt['manifest_matches_registered'] = receipt['manifest_sha256'] == DATASET_MANIFEST_SHA256
    if receipt['normalization_sha256'] != norm['sha256']:
        raise SystemExit('normalization hash mismatch')
    if verify_files:
        for episode in manifest['episodes']:
            for name, digest in episode['files'].items():
                if sha256(dataset / episode['path'] / name) != digest:
                    raise SystemExit('episode file hash mismatch: %s/%s' % (episode['path'], name))
        receipt['episode_files_verified'] = True
    return manifest, receipt


def load_episodes(dataset, manifest, splits=('train', 'validation')):
    """Read-only: state, h0 action, skill, t, seed per episode (no images)."""
    rows = []
    for episode in manifest['episodes']:
        if episode['split'] not in splits:
            continue
        folder = Path(dataset) / episode['path']
        with np.load(folder / 'tensors.npz') as archive:
            state = np.asarray(archive['state'], np.float32)
            action0 = np.asarray(archive['action'][:, 0, :], np.float32)
        metadata = read_json(folder / 'samples.json')
        if len(metadata) != len(state):
            raise SystemExit('metadata/state length mismatch in %s' % episode['path'])
        rows.append(dict(seed=episode['seed'], split=episode['split'], state=state, action0=action0,
                         skill=[m['skill'] for m in metadata], t=np.asarray([m['t'] for m in metadata])))
    return rows


def release_mass_summary(episodes, release_weight):
    """Release-row mass under uniform_episode_v1 and the carry-r1 release-weighted sampler."""
    from act18_policy import weighted_sampler_mass
    metadata, episode_indices, offset = [], [], 0
    for episode in episodes:
        n = len(episode['skill'])
        metadata.extend(dict(skill=s) for s in episode['skill'])
        episode_indices.append(np.arange(offset, offset + n, dtype=np.int64))
        offset += n
    release = np.asarray([m['skill'] == 'release' for m in metadata])
    uniform = weighted_sampler_mass(episode_indices, np.ones(len(metadata)))
    weighted = weighted_sampler_mass(episode_indices, r1.release_row_weights(metadata, release_weight))
    entries = sum(len(contiguous_segments(e['skill'], e['t'], 'release')) for e in episodes)
    return dict(rows=int(len(metadata)), release_rows=int(release.sum()),
                release_row_fraction=float(release.mean()) if len(release) else None,
                release_entry_rows=int(entries),
                episodes_with_release=int(sum(1 for e in episodes if 'release' in e['skill'])),
                release_mass_uniform_episode=float(uniform[release].sum()),
                release_mass_release_weighted=float(weighted[release].sum()),
                release_weight=release_weight,
                masses=dict(uniform=uniform, weighted=weighted))


def done_label_summary(episodes, masses):
    out = {}
    skills = np.asarray([s for e in episodes for s in e['skill']])
    done = np.concatenate([e['action0'][:, -1] for e in episodes]) if episodes else np.zeros(0)
    if not np.isin(done, (0., 1.)).all():
        raise SystemExit('binary h0 done label required')
    for skill in ('grasp', 'release'):
        mask = skills == skill
        entry = dict(rows=int(mask.sum()), done_rows=int(done[mask].sum()),
                     done_row_fraction=float(done[mask].mean()) if mask.any() else None)
        for name, mass in masses.items():
            total = float(mass[mask].sum())
            entry['done_mass_fraction_' + name] = float((mass[mask] * done[mask]).sum() / total) if total else None
        out[skill] = entry
    return out


def augmentation_summary(states, seed, *, dither_max_pwm, dither_prob, dropout_prob):
    """History change distribution before/after the registered dither and dropout."""
    states = np.atleast_2d(np.asarray(states, np.float32))
    rng = np.random.default_rng(seed)
    before = history_pwm(states)
    dithered = np.stack([r1.history_dither(s, rng, dither_max_pwm, dither_prob) for s in states]) \
        if len(states) else states.copy()
    after_dither = history_pwm(dithered)
    dropped = np.stack([r1.history_dropout(s, rng, dropout_prob) for s in dithered]) \
        if len(states) else states.copy()
    after_both = history_pwm(dropped)
    injected = np.abs(after_dither - before)
    dropout_rows = np.any(~np.isclose(dropped, dithered), axis=1)
    return dict(rows=int(len(states)), seed=seed,
                options=dict(dither_max_pwm=dither_max_pwm, dither_prob=dither_prob, dropout_prob=dropout_prob),
                dither_entries_changed_fraction=float((injected > 0).mean()) if injected.size else None,
                dither_injected_abs=bin_counts(injected[injected > 0]),
                dither_injected_max=int(injected.max()) if injected.size else None,
                dropout_rows_applied=int(dropout_rows.sum()),
                dropout_rows_fraction=float(dropout_rows.mean()) if len(states) else None,
                history_delta_before=bin_counts(np.abs(np.diff(before, axis=1))),
                history_delta_after_dither=bin_counts(np.abs(np.diff(after_dither, axis=1))),
                history_delta_after_dither_dropout=bin_counts(np.abs(np.diff(after_both, axis=1))))


def teacher_open_summary(episodes):
    """Teacher open tick inside release: skill-elapsed clock (state[-2] * 120 s)."""
    se, missing = [], []
    for episode in episodes:
        pwm1 = pwm_counts(episode['action0'][:, GRIPPER_ACTION_DIM])
        index = teacher_open_index(episode['skill'], pwm1)
        if index is None:
            if 'release' in episode['skill']:
                missing.append(episode['seed'])
            continue
        se.append(float(episode['state'][index, -2]) * 120.)
    return dict(open_skill_elapsed_s=quantiles(se), episodes_open=len(se),
                episodes_release_without_open=missing)


def data_stats(episodes, *, seed, options):
    out = {}
    for split in ('train', 'validation'):
        group = [e for e in episodes if e['split'] == split]
        if not group:
            continue
        deltas = np.concatenate([teacher_release_pwm_deltas(e['action0'], e['skill'], e['t']) for e in group])
        per_servo = {str(s): bin_counts(deltas[:, i]) for i, s in enumerate((1, 3, 4, 5, 6))} if len(deltas) else {}
        mass = release_mass_summary(group, options['release_weight'])
        masses = mass.pop('masses')
        release_states = np.concatenate([e['state'][[s == 'release' for s in e['skill']]] for e in group])
        all_states = np.concatenate([e['state'] for e in group])
        out[split] = dict(
            episodes=len(group),
            teacher_release_pwm_delta=dict(all_servos=bin_counts(deltas), per_servo=per_servo,
                                           dither_3_9_zero=bool(bin_counts(deltas)['3-9'] == 0),
                                           nonzero_below_20=int(((deltas > 0) & (deltas < 20)).sum())),
            teacher_open=teacher_open_summary(group),
            release=mass,
            done_labels=done_label_summary(group, masses),
            history_augmentation_release_rows=augmentation_summary(
                release_states, seed, dither_max_pwm=options['dither_max_pwm'],
                dither_prob=options['dither_prob'], dropout_prob=options['dropout_prob']),
            history_augmentation_all_rows=augmentation_summary(
                all_states, seed, dither_max_pwm=options['dither_max_pwm'],
                dither_prob=options['dither_prob'], dropout_prob=options['dropout_prob']),
        )
    return out


# ----------------------------------------------------------------------------- baseline-gate

def episode_gate_view(seed, skills, t, teacher_pwm1, chunk_pwm1, te_pwm1, dither_chunk_pwm1=None):
    """Per-episode G-r4 / open-first-appearance / G-r6 view from forward outputs.

    All arrays are row-aligned for one episode. ``dither_chunk_pwm1`` maps a row index to
    the chunk pwm1 list of the dither-history forward (release rows only)."""
    skills = list(skills)
    t = np.asarray(t, np.float64)
    open_index = teacher_open_index(skills, teacher_pwm1)
    release_rows = [i for i, s in enumerate(skills) if s == 'release']
    entry_t = float(t[release_rows[0]]) if release_rows else None
    view = dict(seed=seed, release_rows=len(release_rows),
                teacher_open_tau=(None if open_index is None or entry_t is None else round(float(t[open_index]) - entry_t, 6)))

    def window_hit(rows_pwm1):
        if open_index is None:
            return None
        rows = [i for i in release_rows if abs(float(t[i]) - float(t[open_index])) <= G_R4_WINDOW_S + 1e-9]
        return bool(any(max(rows_pwm1[i]) >= OPEN_PWM1 for i in rows if rows_pwm1.get(i) is not None))

    clean = {i: chunk_pwm1[i] for i in release_rows}
    view['g_r4_clean_hit'] = window_hit(clean)
    if dither_chunk_pwm1 is not None:
        view['g_r4_dither_hit'] = window_hit(dither_chunk_pwm1)
    for name, rows_pwm1 in (('clean', clean), ('dither', dither_chunk_pwm1)):
        if rows_pwm1 is None or not release_rows:
            continue
        taus = [round(float(t[i]) - entry_t, 6) for i in release_rows]
        tau, row = first_chunk_open([rows_pwm1[i] for i in release_rows], taus)
        view['first_chunk_open_' + name] = dict(
            tau=tau, row=row,
            predicted_open_tau=None if tau is None else round(tau + row * PERIOD_S, 6),
            lead_vs_teacher_open_s=(None if tau is None or view['teacher_open_tau'] is None
                                    else round(view['teacher_open_tau'] - tau, 6)))
    grasp_rows = [i for i, s in enumerate(skills) if s == 'grasp']
    view['g_r6_grasp_te_open_ticks'] = int(sum(1 for i in grasp_rows if te_pwm1[i] >= OPEN_PWM1))
    view['g_r6_grasp_te_open_ticks_teacher_closed'] = int(
        sum(1 for i in grasp_rows if te_pwm1[i] >= OPEN_PWM1 and teacher_pwm1[i] < OPEN_PWM1))
    view['grasp_rows'] = len(grasp_rows)
    view['grasp_rows_teacher_closed'] = int(sum(1 for i in grasp_rows if teacher_pwm1[i] < OPEN_PWM1))
    return view


def summarize_gate(views, skills, done_label, done_prob, l1_h0, c4b=None):
    skills = np.asarray(skills)
    g = {}
    for gate, skill in (('G-r1', 'grasp'), ('G-r2', 'release')):
        mask = skills == skill
        g[gate] = dict(skill=skill, **done_rates(np.asarray(done_prob)[mask], np.asarray(done_label)[mask]))
    g['G-r3'] = dict(normalized_action_l1_h0_mean=float(np.mean(l1_h0)) if len(l1_h0) else None,
                     per_skill={s: float(np.mean(np.asarray(l1_h0)[skills == s]))
                                for s in sorted(set(skills.tolist())) if (skills == s).any()},
                     rows=int(len(l1_h0)))
    with_open = [v for v in views if v['teacher_open_tau'] is not None]
    for name in ('clean', 'dither'):
        key = 'g_r4_%s_hit' % name
        hits = [v[key] for v in with_open if v.get(key) is not None]
        g.setdefault('G-r4', {})[name] = dict(
            episodes=len(hits), episodes_hit=int(sum(hits)),
            fraction=(sum(hits) / len(hits) if hits else None))
    g['G-r4']['window_s'] = G_R4_WINDOW_S
    g['G-r4']['episodes_without_teacher_open'] = [v['seed'] for v in views
                                                  if v['teacher_open_tau'] is None and v['release_rows']]
    g['G-r5'] = c4b if c4b is not None else dict(
        status='not_computed',
        note='G-r5 = C4b V0 replay of the C2c worlds; for R8 this is the C4b-GPU V0 arm '
             '(origin/dsh/act18-c4-counterfactual). Pass --c4b-replay <replay.json> to attach. [확인 필요]')
    g['G-r6'] = dict(
        teacher_grasp_te_open_ticks=int(sum(v['g_r6_grasp_te_open_ticks'] for v in views)),
        teacher_grasp_te_open_ticks_where_teacher_closed=int(
            sum(v['g_r6_grasp_te_open_ticks_teacher_closed'] for v in views)),
        episodes_with_any_teacher_closed_te_open=int(
            sum(1 for v in views if v['g_r6_grasp_te_open_ticks_teacher_closed'])),
        grasp_rows=int(sum(v['grasp_rows'] for v in views)),
        grasp_rows_teacher_closed=int(sum(v['grasp_rows_teacher_closed'] for v in views)),
        c2c_grasp_replay=dict(status='not_computed',
                              note='no C2c grasp-window replay tool on this branch (C4b covers the '
                                   'release window only). [확인 필요]'))
    first = {}
    for name in ('clean', 'dither'):
        items = [v.get('first_chunk_open_' + name) for v in views if v.get('first_chunk_open_' + name)]
        found = [x for x in items if x['tau'] is not None]
        rows = {}
        for x in found:
            rows[str(x['row'])] = rows.get(str(x['row']), 0) + 1
        first[name] = dict(episodes=len(items), episodes_with_open=len(found),
                           first_tau_s=quantiles([x['tau'] for x in found]),
                           predicted_open_tau_s=quantiles([x['predicted_open_tau'] for x in found]),
                           lead_vs_teacher_open_s=quantiles([x['lead_vs_teacher_open_s'] for x in found]),
                           chunk_row_counts=rows)
    g['raw_chunk_open_first_appearance'] = first
    return g


def c4b_v0_summary(path):
    """G-r5 from an existing C4b replay.json (V0 arm), no new forward."""
    replay = read_json(path)
    worlds = replay['worlds']
    out = dict(source=str(path), sha256=sha256(path), status='attached')
    for outcome in ('failure', 'success'):
        group = [w for w in worlds if w['outcome'] == outcome and 'V0' in w['arms']]
        out[outcome] = dict(worlds=len(group),
                            te_open=int(sum(1 for w in group if w['arms']['V0']['open_tau'] is not None)),
                            chunk_open=int(sum(1 for w in group if w['arms']['V0'].get('chunk_open_tau') is not None)))
    return out


def baseline_gate(args):
    import torch
    from harness import grasp_act_contract as contract
    from act18_policy import Actor, ReferenceDataset
    checkpoint = Path(args.checkpoint)
    model_sha = sha256(checkpoint / 'model.safetensors')
    if model_sha != R8_MODEL_SHA256:
        raise SystemExit('R8 step-100000 checkpoint required (model sha256 mismatch)')
    _, data_receipt = dataset_receipt(args.dataset, verify_files=False)
    protocol = read_json(args.protocol)
    val8 = set(protocol['validation8_seeds'])
    if args.device == 'cuda' and not torch.cuda.is_available():
        raise SystemExit('cuda requested but unavailable')
    target = prepare_run_root(args.run_root, 'baseline-gate.json')
    started = time.time()
    actor = Actor.load(checkpoint, device=args.device)
    data = ReferenceDataset(args.dataset, 'validation', chunk=actor.chunk)  # verifies episode hashes
    for key in ('state_mean', 'state_std', 'action_mean', 'action_std'):
        if not np.array_equal(np.asarray(actor.stats[key], np.float32), np.asarray(data.stats[key], np.float32)):
            raise SystemExit('checkpoint and dataset normalisation differ: ' + key)
    state_mean = np.asarray(data.stats['state_mean'], np.float32)
    state_std = np.asarray(data.stats['state_std'], np.float32)
    selected = [i for i, m in enumerate(data.metadata) if m['seed'] not in val8]
    if args.limit_rows:
        selected = selected[:args.limit_rows]
    rng = np.random.default_rng(args.dither_seed)
    n = len(selected)
    chunks = np.zeros((n, actor.chunk, contract.ACTION_DIM), np.float32)
    l1 = np.zeros(n, np.float64)
    dither_chunks = {}
    forwards = 0
    for offset in range(0, n, args.batch):
        part = selected[offset:offset + args.batch]
        items = [data[i] for i in part]
        batch = {k: torch.from_numpy(np.stack([np.asarray(x[k]) for x in items])).to(args.device)
                 for k in items[0] if k.startswith('observation.')}
        with torch.inference_mode():
            raw = actor.policy.predict_action_chunk(batch).float().cpu().numpy()
        forwards += len(part)
        target_norm = np.stack([np.asarray(x['action'])[0] for x in items])
        l1[offset:offset + len(part)] = np.abs(raw[:, 0, :13] - target_norm[:, :13]).mean(axis=1)
        chunks[offset:offset + len(part)] = actor.decode(raw)
        release = [j for j, i in enumerate(part) if data.metadata[i]['skill'] == 'release']
        if release:
            dithered = []
            for j in release:
                shard, row = data.index[part[j]]
                raw_state = r1.history_dither(data.shards[shard]['state'][row], rng,
                                              r1.REGISTERED['dither_max_pwm'], r1.REGISTERED['dither_prob'])
                dithered.append((raw_state - state_mean) / state_std)
            sub = {k: v[release] for k, v in batch.items()}
            sub['observation.state'] = torch.from_numpy(np.stack(dithered).astype(np.float32)).to(args.device)
            with torch.inference_mode():
                values = actor.decode(actor.policy.predict_action_chunk(sub).float().cpu().numpy())
            forwards += len(release)
            for j, value in zip(release, values):
                dither_chunks[offset + j] = [int(contract.decode_action(r)['pwm']['1']) for r in value]
        print('rows %d/%d forwards=%d wall=%.0fs' % (min(offset + args.batch, n), n, forwards,
                                                     time.time() - started), flush=True)
    chunk_pwm1 = [[int(contract.decode_action(r)['pwm']['1']) for r in c] for c in chunks]
    meta = [data.metadata[i] for i in selected]
    teacher = np.stack([data.shards[data.index[i][0]]['action'][data.index[i][1], 0] for i in selected])
    teacher_pwm1 = pwm_counts(teacher[:, GRIPPER_ACTION_DIM])
    done_label = teacher[:, -1]
    done_prob = chunks[:, 0, -1]
    views = []
    for seed in sorted({m['seed'] for m in meta}):
        rows = [k for k, m in enumerate(meta) if m['seed'] == seed]
        t = [meta[k]['t'] for k in rows]
        te = temporal_ensemble_pwm1(chunks[rows], t)
        local_dither = {a: dither_chunks[k] for a, k in enumerate(rows) if k in dither_chunks}
        views.append(episode_gate_view(seed, [meta[k]['skill'] for k in rows], t, teacher_pwm1[rows],
                                       [chunk_pwm1[k] for k in rows], te, dither_chunk_pwm1=local_dither))
    c4b = c4b_v0_summary(args.c4b_replay) if args.c4b_replay else None
    gates = summarize_gate(views, [m['skill'] for m in meta], done_label, done_prob, l1, c4b)
    report = dict(
        schema=SCHEMA, label=LABEL, subcommand='baseline-gate', verdict=None,
        policy=POLICY, data=DATA,
        checkpoint=dict(path=str(checkpoint), model_sha256=model_sha, registered_r8_sha256=R8_MODEL_SHA256),
        dataset=data_receipt, protocol=dict(path=str(args.protocol), sha256=sha256(args.protocol)),
        source_sha=source_sha(), device=dict(name=args.device, torch=torch.__version__,
                                             gpu=torch.cuda.get_device_name(0) if args.device == 'cuda' else None),
        episodes=len(views), rows=n, release_rows_dither_forward=len(dither_chunks), forwards=forwards,
        val8_excluded=sorted(val8), limit_rows=args.limit_rows, dither_seed=args.dither_seed,
        dither_rule=dict(fn='act18_carry_r1.history_dither', max_pwm=r1.REGISTERED['dither_max_pwm'],
                         prob=r1.REGISTERED['dither_prob']),
        operationalisation=dict(
            done_probability='decoded h0 done (sigmoid of the done logit), threshold .65 = decode_action',
            false_done='fraction of done-label-0 rows of the skill with h0 done probability >= .65',
            action_l1='mean |pred - target| over normalised action dims 0..12 at h0 (done dim excluded) [확인 필요]',
            open='pwm1 >= 1900 after contract.decode_action (C4b OPEN_PWM1)',
            teacher_open_tick='first release row whose teacher h0 pwm1 >= 1900',
            g_r4='any raw chunk row pwm1 >= 1900 at a release tick within +-0.5 s of the teacher open tick',
            g_r6=('TE = ChunkExecutor ensemble (k=.01, n_action_steps 1) over teacher-forced chunks, reset at '
                  'skill entry/gap, no done freeze; literal count over all grasp rows and the count restricted '
                  'to rows where the teacher itself is closed (pwm1 < 1900). Which one the draft means by '
                  '"조기 open" is [확인 필요]: teacher grasp starts with an open gripper.')),
        draft_thresholds_reference_only=DRAFT_THRESHOLDS,
        gates=gates, episodes_detail=views, wall_s=round(time.time() - started, 1),
        created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), argv=sys.argv)
    write_output(target, report)
    print(json.dumps(dict(out=str(target), label=LABEL, gates={k: v for k, v in gates.items()
                                                               if k != 'raw_chunk_open_first_appearance'}),
                     ensure_ascii=False, indent=1, default=str))
    return 0


def run_data_stats(args):
    manifest, receipt = dataset_receipt(args.dataset, verify_files=True)
    target = prepare_run_root(args.run_root, 'data-stats.json')
    started = time.time()
    episodes = load_episodes(args.dataset, manifest)
    options = dict(dither_max_pwm=r1.REGISTERED['dither_max_pwm'], dither_prob=r1.REGISTERED['dither_prob'],
                   dropout_prob=r1.REGISTERED['dropout_prob'], release_weight=r1.REGISTERED['release_weight'])
    report = dict(schema=SCHEMA, label=LABEL, subcommand='data-stats', verdict=None,
                  policy='none (data only)', data=DATA, dataset=receipt, source_sha=source_sha(),
                  registered_options=options, augmentation_seed=args.seed,
                  splits=data_stats(episodes, seed=args.seed, options=options),
                  wall_s=None, created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), argv=sys.argv)
    report['wall_s'] = round(time.time() - started, 1)
    write_output(target, report)
    print(json.dumps(dict(out=str(target), label=LABEL), ensure_ascii=False))
    return 0


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    stats = sub.add_parser('data-stats')
    gate = sub.add_parser('baseline-gate')
    for p in (stats, gate):
        p.add_argument('--enabled', action='store_true')
        p.add_argument('--dataset', type=Path, required=True)
        p.add_argument('--run-root', type=Path, required=True)
    stats.add_argument('--seed', type=int, default=r1.REGISTERED['seed'])
    gate.add_argument('--checkpoint', type=Path, required=True)
    gate.add_argument('--protocol', type=Path, required=True)
    gate.add_argument('--device', choices=('cuda', 'cpu'), default='cuda')
    gate.add_argument('--batch', type=int, default=8)
    gate.add_argument('--dither-seed', type=int, default=r1.REGISTERED['seed'])
    gate.add_argument('--limit-rows', type=int, default=0, help='smoke only; full run uses 0')
    gate.add_argument('--c4b-replay', type=Path, help='existing C4b-GPU replay.json (V0 arm) for G-r5')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_arguments(argv)
    if not args.enabled:
        raise SystemExit('pre-check is default OFF; pass --enabled')
    return run_data_stats(args) if args.command == 'data-stats' else baseline_gate(args)


if __name__ == '__main__':
    raise SystemExit(main())
