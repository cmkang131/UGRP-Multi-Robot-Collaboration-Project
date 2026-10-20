"""ACT18 C4b — offline counterfactual replay of the C2c release window (CPU only).

Replays the frozen R8 step-100000 ACT policy over the *recorded* C2c observations of
the release skill, replacing exactly one policy input at a time, and records the
deployed temporal-ensemble pwm1 output. No physics, no simulator, no training, no
GPU. The recorded observations make the replay deterministic: every variant tick
keeps the original observations except for the one substituted input.

Default OFF (``--enabled`` required). The pre-registration JSON must be written and
committed before results; the replay verifies the registered world table against
the C2c originals and fails closed on any mismatch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from harness import grasp_act_contract as contract  # noqa: E402

WINDOW_S = 8.0
PE_SUCCESS = 14.5
SE_TEACHER_OPEN = 4.45
KIND_ORDER = ('cyan', 'green', 'red', 'yellow')
TE_COEFF = .01
OPEN_PWM1 = 1900
ARMS = ('V0', 'V-pe', 'V-se', 'V-img-same', 'V-img-cross', 'V-hist')
CONTROL_ARMS = ARMS[1:]
CHECKPOINT_SHA256 = 'e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a'
RECOVERED_MANIFEST_SHA256 = '6515c3c9be1be026da7ac9eb331def3c937959f99867479b8ed1c9758358f2d2'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def kind_of(item_id):
    """Recorded item id (e.g. cyan_1) -> the policy's object_kind token."""
    kind = str(item_id).rsplit('_', 1)[0]
    if kind not in KIND_ORDER:
        raise ValueError('unregistered kind: %r' % (item_id,))
    return kind


def cohort_of(stage):
    return {'R8-diag': 'HO4', 'R8-train': 'TRAIN4'}[stage]


def world_label(run, group, world):
    return '%s/%s/world-%03d' % (run, group, world)


def c2c_worlds(run_root):
    """All 24 C2c worlds from the published summaries, with seed/kind/outcome."""
    worlds = []
    for run in sorted(p for p in Path(run_root).iterdir()
                      if p.is_dir() and p.name.startswith('C2c-')):
        for stage in sorted(p for p in run.iterdir() if p.is_dir()):
            for group in sorted(p for p in stage.iterdir() if p.is_dir()):
                evaluation = group / 'evaluation'
                summary = evaluation / 'summary.json'
                if not summary.is_file():
                    continue
                scores = json.loads(summary.read_text())['student_scores']
                for world in range(len(scores)):
                    score = scores[world]
                    owner = json.loads((evaluation / 'owner' / ('world-%03d' % world) /
                                        'result.json').read_text())['evaluation']
                    if owner['seed'] != score['seed'] or owner['world'] != world:
                        raise ValueError('owner/score seed mismatch')
                    kind = kind_of(score['assigned_item_id'])
                    success = bool(score['release_success'])
                    entered = bool(score.get('grasp_done_requested'))
                    if success:
                        outcome = 'success'
                    elif entered and score['failure_reason'] == 'release_done_not_requested':
                        outcome = 'failure'
                    else:
                        outcome = 'excluded:' + str(score['failure_reason'])
                    worlds.append(dict(label=world_label(run.name, group.name, world),
                                       run=run.name, stage=stage.name, group=group.name,
                                       world=world, seed=int(score['seed']), kind=kind,
                                       cohort=cohort_of(stage.name), outcome=outcome,
                                       release_success=success,
                                       assigned_item_id=score['assigned_item_id']))
    return worlds


def world_inputs(run_root, world):
    """Recorded observations and issued commands for one world."""
    evaluation = (Path(run_root) / world['run'] / world['stage'] / world['group'] / 'evaluation')
    observations = [row for row in read_rows(evaluation / 'actor-inputs.jsonl')
                    if row['world'] == world['world']]
    issued = [row for row in read_rows(evaluation / 'owner' / 'issued-commands.jsonl')
              if row['world'] == world['world']]
    observations.sort(key=lambda row: row['observation']['t'])
    issued.sort(key=lambda row: row['t'])
    if len(observations) != len(issued):
        raise ValueError('observation/issued row count mismatch')
    for observation, command in zip(observations, issued):
        if abs(observation['observation']['t'] - command['t']) > 1e-9:
            raise ValueError('observation/issued tick mismatch')
    return observations, issued


def release_window(observations):
    """Release-entry tick and the pre-registered [0, 8) s window."""
    release = [row for row in observations if row['observation']['skill'] == 'release']
    if not release:
        raise ValueError('no release rows')
    t0 = release[0]['observation']['t']
    window = [row for row in release
              if 0. <= row['observation']['t'] - t0 < WINDOW_S - 1e-9]
    return t0, window


def recorded_open_tau(issued):
    """First issued pwm1 >= 1900 during release, release-relative; None if never."""
    release = [row for row in issued if row['skill'] == 'release']
    if not release:
        return None
    t0 = release[0]['t']
    for row in release:
        if row['action']['command']['pwm']['1'] >= OPEN_PWM1:
            return round(row['t'] - t0, 6)
    return None


def reference_map(successes, targets):
    """Deterministic same-kind and cross-kind reference world for every target.

    Same-kind: the lexicographically first success of the target's kind that is not
    the target itself; a success world with no same-kind alternative references
    itself (then V-img-same is byte-identical to V0 and is reported as such).
    Cross-kind: the first success of the next kind in fixed cyan->green->red->yellow
    rotation.
    """
    by_kind = {kind: sorted((w for w in successes if w['kind'] == kind),
                            key=lambda w: w['label']) for kind in KIND_ORDER}
    missing = [kind for kind in KIND_ORDER if not by_kind[kind]]
    if missing:
        raise ValueError('no success world for kind(s): %s' % ','.join(missing))
    base = {kind: by_kind[kind][0]['label'] for kind in KIND_ORDER}
    same, cross = {}, {}
    for world in targets:
        alternatives = [w for w in by_kind[world['kind']] if w['label'] != world['label']]
        same[world['label']] = (alternatives or [world])[0]['label']
        cross[world['label']] = base[KIND_ORDER[(KIND_ORDER.index(world['kind']) + 1) %
                                                len(KIND_ORDER)]]
    return base, same, cross


def build_registration(run_root, recovered_root, checkpoint, release_note):
    worlds = c2c_worlds(run_root)
    failures = [w for w in worlds if w['outcome'] == 'failure']
    successes = [w for w in worlds if w['outcome'] == 'success']
    excluded = [w for w in worlds if w['outcome'].startswith('excluded:')]
    if len(failures) != 10 or len(successes) != 9:
        raise ValueError('registered selection expects 10 failure / 9 success worlds, got %d/%d'
                         % (len(failures), len(successes)))
    base, same, cross = reference_map(successes, failures + successes)
    lookup = {w['label']: w for w in worlds}
    for world in failures + successes:
        observations, issued = world_inputs(run_root, world)
        t0, window = release_window(observations)
        if len(window) != 80:
            raise ValueError('expected 80 window ticks, got %d for %s' % (len(window), world['label']))
        world['release_entry_t'] = t0
        world['window_ticks'] = len(window)
        world['recorded_open_tau'] = recorded_open_tau(issued)
    for label in list(same) + list(cross):
        if label not in lookup:
            raise ValueError('reference target not a registered world')
        for reference in (same[label], cross[label]):
            if reference not in lookup:
                raise ValueError('reference label not a registered world')
    registration = {
        'schema': 'ugrp.act18.c4_counterfactual_prereg.v1',
        'experiment': 'C4b',
        'created_utc': release_note['created_utc'],
        'question': ('C2c release world 10 failure / 9 success: does replacing exactly one '
                     'policy input during the first 8 s after release entry produce the open '
                     'command (pwm1 >= 1900) that the failure worlds never issued?'),
        'source': {
            'c2c_run_root': 'outputs/runs/act18-c2c-v7clock-20261019T2315Z',
            'c2c_analysis_sha256': release_note['c2c_analysis_sha256'],
            'c2c_summaries': release_note['c2c_summaries'],
            'checkpoint': str(checkpoint),
            'checkpoint_model_sha256': CHECKPOINT_SHA256,
            'rgb_recovered_root': 'outputs/runs/act18-c4a-recovered-20261020T0451Z',
            'rgb_files': 27783,
            'rgb_manifest_sha256': RECOVERED_MANIFEST_SHA256,
            'contract_sha256': sha256(ROOT / 'harness' / 'grasp_act_contract.py'),
        },
        'selection': {
            'failure': ('release skill entered (grasp issued done) and release_done_not_requested; '
                        'this is the C2c diagnostics 1.3 category (b): 10 worlds'),
            'success': 'release_success == true (C2c diagnostics 1.2): 9 worlds',
            'cohort': ('only the C2c (v7 deadband-2 clock) arm is replayed; the 12 B0 worlds '
                       'are a different clock arm and are not part of this cohort'),
            'excluded': [dict(label=w['label'], reason=w['outcome'][len('excluded:'):])
                         for w in excluded],
        },
        'window': {
            'definition': 'skill == release and 0 <= t - release_entry_t < 8.0 s',
            'release_entry': 'first recorded release observation of the world',
            'ticks_per_world': 80,
            'period_s': 0.1,
        },
        'inputs_replaced': {
            'V0': 'none (baseline fidelity replay)',
            'V-pe': 'pwm_elapsed_s := 14.5 on every window tick',
            'V-se': 'skill_elapsed_s := 4.45 on every window tick',
            'V-img-same': ('the four own-RGB references of every tick := the same-kind success '
                           'world tick at the same release-relative time; times shifted so the '
                           'newest reference equals the target tick'),
            'V-img-cross': ('the four own-RGB references of every tick := the next-kind success '
                            'world tick (cyan->green->red->yellow->cyan) at the same '
                            'release-relative time; times shifted as for V-img-same'),
            'V-hist': ('the 16 issued-command contents := the same-kind success world history at '
                       'the same release-relative time; the target timestamps are kept so only '
                       'the command contents change'),
        },
        'reference_worlds': {
            'kind_base': base,
            'img_same': same,
            'img_cross': cross,
            'alignment': 'release-relative tick index; missing reference tick is a hard error',
        },
        'targets': {
            'failure': failures,
            'success': successes,
        },
        'metrics': {
            'primary': ('te_pwm1 = deployed temporal-ensemble command (coefficient 0.01, '
                        'n_action_steps 1, skill transition resets the buffer) decoded with '
                        'contract.decode_action; open = any window tick with te_pwm1 >= 1900'),
            'open_tau': 'release-relative time of the first open tick',
            'secondary': ('raw_pwm1 = chunk row 0 before ensembling; done_freeze = the executor '
                          'stop rule of harness.grasp_act_policy.ChunkExecutor'),
        },
        'fidelity': {
            'check': ('V0 te_pwm1 must reproduce the recorded owner issued pwm1 for every window '
                      'tick; open status must match 19/19'),
            'max_abs_diff': 1,
            'exact_fraction_min': 0.95,
            'open_status': '19/19',
            'abort_on_failure': True,
        },
        'decision_rules': [
            'n_recovered[V] = number of failure worlds (n=10) with open=True under V and '
            'open=False under V0',
            'single cause: exactly one of V-pe/V-se/V-img-same/V-img-cross/V-hist has '
            'n_recovered >= 6',
            'multiple: two or more variants reach >= 6; report both, no single-cause attribution',
            'kind-specific visual generalisation: only V-img-cross reaches >= 6',
            'no recovery: no variant reaches >= 6 -> model capacity/data, not a single input',
            'success control (n=9) is descriptive only: V0 must keep open 9/9; variant open '
            'counts are reported but do not enter the failure decision',
        ],
        'exclusions_and_limits': [
            'offline replay: outputs are not executed, no physics, not a closed-loop result',
            'the recorded observation sequence is fixed; a counterfactual command does not '
            'change later observations (no re-simulation)',
            'failure 10 is the C2c category (b) subset only; the 2 drop_detected and 3 '
            'grasp_done_not_requested worlds are not replayed',
            'HO4 is a diagnostic holdout (gate_eligible=false); no pooling with VAL8/FINAL40',
            'kind is fixed per seed and fully confounded with scene placement in the C2c cohort',
        ],
        'registered_before_results': True,
    }
    if not registration['fidelity']['abort_on_failure']:
        raise ValueError('fidelity gate must abort')
    return registration


class TemporalEnsemble:
    """Exact copy of harness.grasp_act_policy.ChunkExecutor's ensemble arithmetic."""

    def __init__(self, coeff=TE_COEFF):
        self.coeff = coeff
        self.chunks = []
        self.done_requested = False

    def reset(self):
        self.chunks = []
        self.done_requested = False

    def step(self, prediction):
        values = np.asarray(prediction, dtype=float)
        self.chunks.append(values)
        weights = np.exp(-self.coeff * np.arange(len(self.chunks)))
        averaged = np.average([chunk[0] for chunk in self.chunks], axis=0, weights=weights)
        action = contract.decode_action(averaged)
        self.chunks = [chunk[1:] for chunk in self.chunks if len(chunk) > 1]
        self.done_requested = bool(action['done'])
        return action, averaged


def held_command(observation):
    """ChunkExecutor stop rule: hold the last issued command with zero wheels."""
    value = dict(observation['issued'][-1], wheels=[0.] * 4, duration_s=[0.] * 4)
    return {'wheels': value['wheels'], 'duration_s': value['duration_s'],
            'pwm': dict(value['pwm']), 'done': True}


def replace_clocks(observation, *, pe=None, se=None):
    changed = dict(observation)
    if pe is not None:
        changed['pwm_elapsed_s'] = float(pe)
    if se is not None:
        changed['skill_elapsed_s'] = float(se)
    return changed


def replace_images(observation, reference_row, reference_robot='r1'):
    """Substitute the own-RGB history with the reference world's, times shifted."""
    source = reference_row['observation']
    delta = observation['t'] - source['t']
    refs = [dict(path=ref['path'], sha256=ref['sha256'], t=ref['t'] + delta,
                 robot_id=observation['robot_id']) for ref in source['rgb']]
    changed = dict(observation)
    changed['rgb'] = refs
    return changed


def replace_history(observation, reference_row):
    """Substitute issued-command contents, keeping the target issue timestamps."""
    source = reference_row['observation']['issued']
    if len(source) != len(observation['issued']):
        raise ValueError('issued history length mismatch')
    issued = [dict(t=orig['t'], wheels=list(src['wheels']),
                   duration_s=list(src['duration_s']), pwm=dict(src['pwm']))
              for orig, src in zip(observation['issued'], source)]
    changed = dict(observation)
    changed['issued'] = issued
    return changed


def apply_variant(arm, observation, *, same_row, cross_row):
    """One-input substitution; everything else stays recorded."""
    if arm == 'V0':
        return observation
    if arm == 'V-pe':
        return replace_clocks(observation, pe=PE_SUCCESS)
    if arm == 'V-se':
        return replace_clocks(observation, se=SE_TEACHER_OPEN)
    if arm == 'V-img-same':
        return replace_images(observation, same_row)
    if arm == 'V-img-cross':
        return replace_images(observation, cross_row)
    if arm == 'V-hist':
        return replace_history(observation, same_row)
    raise ValueError('unknown arm: %r' % (arm,))


def open_tau(series, threshold=OPEN_PWM1):
    for tau, pwm1 in series:
        if pwm1 >= threshold:
            return tau
    return None


def decide(recovered):
    """Apply the pre-registered failure decision rules; counts is arm -> n_recovered."""
    hit = [arm for arm in CONTROL_ARMS if recovered[arm] >= 6]
    if not hit:
        return dict(verdict='no_recovery', arms=[], text='모델 용량/데이터')
    if len(hit) == 1:
        arm = hit[0]
        if arm == 'V-img-cross':
            return dict(verdict='kind_specific_visual', arms=hit,
                        text='V-img-cross만 회복 -> kind 특이 시각 일반화')
        return dict(verdict='single_input_cause', arms=hit, text='단일 입력 원인: ' + arm)
    return dict(verdict='multiple_inputs', arms=hit, text='복수 입력 변형이 기준 이상')


def rindex(observations, t0, tick):
    """Reference row at the same release-relative 0.1 s tick index."""
    target = t0 + tick * contract.PERIOD_S
    best = None
    for row in observations:
        if row['observation']['skill'] != 'release':
            continue
        offset = abs(row['observation']['t'] - target)
        if offset <= 1e-6:
            return row
        if best is None or offset < best[0]:
            best = (offset, row)
    if best is None or best[0] > .05 + 1e-9:
        raise ValueError('missing reference tick %d' % tick)
    return best[1]


def load_jpegs(base, refs, cache):
    data = []
    for ref in refs:
        key = (str(base), ref['path'])
        value = cache.get(key)
        if value is None:
            path = Path(base) / ref['path']
            if not path.is_file():
                raise FileNotFoundError(str(path))
            value = path.read_bytes()
            if hashlib.sha256(value).hexdigest() != ref['sha256']:
                raise ValueError('recovered RGB hash mismatch: %s' % path)
            cache[key] = value
        data.append(value)
    return data


def replay_world(world, arms, run_root, recovered_root, actor, checkpoint_sha):
    """Replay one world: all arms share one tick loop and one JPEG cache."""
    observations, issued = world_inputs(run_root, world)
    t0, window = release_window(observations)
    if len(window) != world['window_ticks']:
        raise ValueError('window tick count changed')
    evaluation = (Path(run_root) / world['run'] / world['stage'] / world['group'] /
                  'evaluation')
    recovered = Path(recovered_root) / world['run'] / world['stage'] / world['group'] / 'evaluation'
    own_base = recovered / 'actor-inputs' / ('world-%03d' % world['world'])
    same_label = world['reference_same']
    cross_label = world['reference_cross']
    same_world = world['reference_worlds'][same_label]
    cross_world = world['reference_worlds'][cross_label]
    same_obs, _ = world_inputs(run_root, same_world)
    cross_obs, _ = world_inputs(run_root, cross_world)
    same_t0, _ = release_window(same_obs)
    cross_t0, _ = release_window(cross_obs)
    same_base = (Path(recovered_root) / same_world['run'] / same_world['stage'] /
                 same_world['group'] / 'evaluation' / 'actor-inputs' /
                 ('world-%03d' % same_world['world']))
    cross_base = (Path(recovered_root) / cross_world['run'] / cross_world['stage'] /
                  cross_world['group'] / 'evaluation' / 'actor-inputs' /
                  ('world-%03d' % cross_world['world']))
    cache = {}
    ensembles = {arm: TemporalEnsemble() for arm in arms}
    series = {arm: [] for arm in arms}
    forward_times = {arm: 0. for arm in arms}
    done_tau = {arm: None for arm in arms}
    for index, row in enumerate(window):
        observation = row['observation']
        same_row = rindex(same_obs, same_t0, index)
        cross_row = rindex(cross_obs, cross_t0, index)
        for arm in arms:
            ensemble = ensembles[arm]
            if ensemble.done_requested:
                action = held_command(observation)
                raw = None
                averaged = None
            else:
                changed = apply_variant(arm, observation, same_row=same_row, cross_row=cross_row)
                if arm == 'V-img-same':
                    jpegs = load_jpegs(same_base, changed['rgb'], cache)
                elif arm == 'V-img-cross':
                    jpegs = load_jpegs(cross_base, changed['rgb'], cache)
                else:
                    jpegs = load_jpegs(own_base, changed['rgb'], cache)
                started = time.perf_counter()
                prediction = np.asarray(actor.predict(changed, jpegs), dtype=float)
                forward_times[arm] += time.perf_counter() - started
                action, averaged = ensemble.step(prediction)
                raw = contract.decode_action(prediction[0])
            tau = round(observation['t'] - t0, 6)
            if action['done'] and done_tau[arm] is None:
                done_tau[arm] = tau
            series[arm].append(dict(tau=tau,
                                    te_pwm1=int(action['pwm']['1']),
                                    raw_pwm1=None if raw is None else int(raw['pwm']['1']),
                                    te_done=None if averaged is None else round(
                                        float(averaged[-1]), 6)))
    result = dict(label=world['label'], seed=world['seed'], kind=world['kind'],
                  cohort=world['cohort'], outcome=world['outcome'],
                  window_ticks=len(window), release_entry_t=t0,
                  recorded_open_tau=world['recorded_open_tau'],
                  reference_same=world['reference_same'],
                  reference_cross=world['reference_cross'], arms={})
    for arm in arms:
        te_series = [(item['tau'], item['te_pwm1']) for item in series[arm]]
        raw_series = [(item['tau'], item['raw_pwm1']) for item in series[arm]
                      if item['raw_pwm1'] is not None]
        result['arms'][arm] = dict(
            open_tau=open_tau(te_series),
            te_pwm1_max=max(value for _, value in te_series),
            raw_open_tau=open_tau(raw_series) if raw_series else None,
            raw_pwm1_max=max((value for _, value in raw_series), default=None),
            done_tau=done_tau[arm],
            forwards=int(sum(1 for item in series[arm] if item['raw_pwm1'] is not None)),
            forward_wall_s=round(forward_times[arm], 3),
            series=series[arm])
    result['recorded'] = [
        dict(tau=round(row['t'] - t0, 6), issued_pwm1=int(row['action']['command']['pwm']['1']))
        for row in issued if 0. <= row['t'] - t0 < WINDOW_S - 1e-9]
    return result


def fidelity_check(replay):
    """V0 must reproduce the recorded issued pwm1 and the recorded open status."""
    exact = 0
    total = 0
    worst = 0
    status_ok = 0
    details = []
    for world in replay:
        recorded = world['recorded']
        baseline = world['arms']['V0']['series']
        if len(recorded) != len(baseline):
            raise ValueError('recorded/replay window length mismatch')
        diffs = [abs(item['te_pwm1'] - ref['issued_pwm1'])
                 for item, ref in zip(baseline, recorded)]
        world_exact = sum(1 for diff in diffs if diff == 0)
        exact += world_exact
        total += len(diffs)
        worst = max(worst, max(diffs))
        recorded_open = open_tau([(ref['tau'], ref['issued_pwm1']) for ref in recorded])
        replay_open = world['arms']['V0']['open_tau']
        same = (recorded_open is None) == (replay_open is None)
        status_ok += int(same)
        details.append(dict(label=world['label'], ticks=len(diffs),
                            exact=world_exact, max_abs_diff=max(diffs),
                            recorded_open_tau=recorded_open, replay_open_tau=replay_open,
                            open_status_match=same))
    return dict(ticks=total, exact=exact, exact_fraction=exact / total,
                max_abs_diff=worst, open_status=f'{status_ok}/{len(replay)}',
                open_status_ok=status_ok, worlds=len(replay), details=details)


def summarize(replay, checkpoint_sha):
    failures = [world for world in replay if world['outcome'] == 'failure']
    successes = [world for world in replay if world['outcome'] == 'success']
    table = {}
    for arm in ARMS:
        table[arm] = dict(
            failure_open=sum(1 for world in failures if world['arms'][arm]['open_tau'] is not None),
            success_open=sum(1 for world in successes if world['arms'][arm]['open_tau'] is not None),
            failure_raw_open=sum(1 for world in failures
                                 if world['arms'][arm]['raw_open_tau'] is not None),
            failure_done=sum(1 for world in failures if world['arms'][arm]['done_tau'] is not None),
            failure_te_pwm1_max=[world['arms'][arm]['te_pwm1_max'] for world in failures])
    recovered = {}
    for arm in CONTROL_ARMS:
        recovered[arm] = sum(1 for world in failures
                             if world['arms'][arm]['open_tau'] is not None
                             and world['arms']['V0']['open_tau'] is None)
    return dict(checkpoint_sha256=checkpoint_sha,
                failure_n=len(failures), success_n=len(successes),
                table=table, recovered=recovered, decision=decide(recovered))


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--c2c-root', type=Path, required=True)
    parser.add_argument('--recovered-root', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--prereg', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--emit-prereg', type=Path)
    parser.add_argument('--arms', default=','.join(ARMS))
    parser.add_argument('--worlds', default='')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--created-utc', default='')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_arguments(argv)
    if not args.enabled:
        raise SystemExit('C4b replay is default OFF; pass --enabled')
    if sha256(args.checkpoint / 'model.safetensors') != CHECKPOINT_SHA256:
        raise SystemExit('unexpected checkpoint hash')
    manifest = Path(args.recovered_root) / 'remote-rgb-sha256.txt'
    if sha256(manifest) != RECOVERED_MANIFEST_SHA256:
        raise SystemExit('unexpected C4a recovered manifest hash')
    arms = tuple(part.strip() for part in args.arms.split(',') if part.strip())
    for arm in arms:
        if arm not in ARMS:
            raise SystemExit('unknown arm %r' % (arm,))
    if args.emit_prereg:
        note = dict(created_utc=args.created_utc or time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                                 time.gmtime()),
                    c2c_analysis_sha256=sha256(Path(args.c2c_root) / 'analysis.json'),
                    c2c_summaries={str(path.relative_to(args.c2c_root)):
                                   sha256(path) for path in
                                   sorted(Path(args.c2c_root).glob('C2c-*/R8-*/group-*/evaluation/summary.json'))})
        registration = build_registration(args.c2c_root, args.recovered_root,
                                          args.checkpoint, note)
        write_json(args.emit_prereg, registration)
        print('registered %d failure + %d success worlds -> %s'
              % (len(registration['targets']['failure']),
                 len(registration['targets']['success']), args.emit_prereg))
        return 0
    if args.prereg is None:
        raise SystemExit('--prereg is required for a replay')
    registration = json.loads(Path(args.prereg).read_text())
    if registration.get('schema') != 'ugrp.act18.c4_counterfactual_prereg.v1':
        raise SystemExit('unregistered prereg schema')
    if registration['source']['checkpoint_model_sha256'] != CHECKPOINT_SHA256:
        raise SystemExit('prereg checkpoint hash mismatch')
    if registration['source']['rgb_manifest_sha256'] != RECOVERED_MANIFEST_SHA256:
        raise SystemExit('prereg recovered manifest mismatch')
    worlds = {world['label']: world for world in
              registration['targets']['failure'] + registration['targets']['success']}
    order = ([world['label'] for world in registration['targets']['failure']] +
             [world['label'] for world in registration['targets']['success']])
    selected = [label.strip() for label in args.worlds.split(',') if label.strip()] or order
    unknown = [label for label in selected if label not in worlds]
    if unknown:
        raise SystemExit('unregistered world(s): %s' % ','.join(unknown))
    # Validate the registered table against the C2c originals before any inference.
    current = {world['label']: world for world in c2c_worlds(args.c2c_root)}
    for label, world in worlds.items():
        live = current[label]
        for key in ('run', 'stage', 'group', 'world', 'seed', 'kind', 'cohort', 'outcome'):
            if live[key] != world[key]:
                raise SystemExit('registered %s mismatch on %s' % (label, key))
    reference_labels = registration['reference_worlds']
    all_worlds = {world['label']: world for world in c2c_worlds(args.c2c_root)}
    if len(all_worlds) != 24:
        raise SystemExit('expected 24 C2c worlds')
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    import torch
    torch.set_num_threads(max(1, args.threads))
    from act18_policy import Actor
    started = time.time()
    actor = Actor.load(str(args.checkpoint), device='cpu')
    cache = {}
    replay = []
    for number, label in enumerate(selected, 1):
        world = dict(worlds[label])
        world['reference_same'] = reference_labels['img_same'][label]
        world['reference_cross'] = reference_labels['img_cross'][label]
        world['reference_worlds'] = {world['reference_same']: all_worlds[world['reference_same']],
                                     world['reference_cross']: all_worlds[world['reference_cross']]}
        world_started = time.time()
        result = replay_world(world, arms, args.c2c_root, args.recovered_root, actor,
                              CHECKPOINT_SHA256)
        replay.append(result)
        print('[%d/%d] %s %s %s ticks=%d wall=%.1fs V0_open=%s V-pe=%s V-se=%s '
              'same=%s cross=%s hist=%s' % (
                  number, len(selected), label, result['kind'], result['outcome'],
                  result['window_ticks'], time.time() - world_started,
                  result['arms'].get('V0', {}).get('open_tau'),
                  result['arms'].get('V-pe', {}).get('open_tau'),
                  result['arms'].get('V-se', {}).get('open_tau'),
                  result['arms'].get('V-img-same', {}).get('open_tau'),
                  result['arms'].get('V-img-cross', {}).get('open_tau'),
                  result['arms'].get('V-hist', {}).get('open_tau')), flush=True)
        write_json(out / 'replay.json', dict(worlds=replay))
    wall = time.time() - started
    fidelity = fidelity_check(replay)
    summary = summarize(replay, CHECKPOINT_SHA256)
    receipt = dict(schema='ugrp.act18.c4b_counterfactual.v1',
                   prereg=str(args.prereg), prereg_sha256=sha256(args.prereg),
                   args=vars(args) | dict(c2c_root=str(args.c2c_root),
                                          recovered_root=str(args.recovered_root),
                                          checkpoint=str(args.checkpoint), out=str(args.out)),
                   checkpoint_sha256=CHECKPOINT_SHA256,
                   recovered_manifest_sha256=RECOVERED_MANIFEST_SHA256,
                   arms=list(arms), worlds=len(replay), wall_s=round(wall, 1),
                   forwards=sum(world['arms'][arm]['forwards'] for world in replay for arm in arms),
                   created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                   fidelity=fidelity, summary=summary)
    write_json(out / 'summary.json', receipt)
    print(json.dumps(dict(fidelity={key: fidelity[key] for key in
                                    ('ticks', 'exact', 'exact_fraction', 'max_abs_diff',
                                     'open_status')},
                          table={arm: dict(failure_open=summary['table'][arm]['failure_open'],
                                           success_open=summary['table'][arm]['success_open'])
                                 for arm in arms},
                          recovered=summary['recovered'],
                          decision=summary['decision'], wall_s=round(wall, 1)), indent=1))
    if (fidelity['exact_fraction'] < registration['fidelity']['exact_fraction_min']
            or fidelity['max_abs_diff'] > registration['fidelity']['max_abs_diff']
            or fidelity['open_status'] != registration['fidelity']['open_status']):
        print('FIDELITY_GATE_FAILED', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
