"""E1: R8 teacher-state temporal-ensemble replay and clock counterfactuals.

Default OFF (``--enabled`` required). This is an offline CPU replay: it reads
recorded student observations, calls ``Actor.predict`` once per tick, runs the
same temporal ensemble as ``harness.grasp_act_policy.ChunkExecutor`` and writes
per-tick decoded commands. No simulator, rollout, teacher command execution or
physics is involved. Counterfactuals change only the two whitelisted clock
fields and must still pass ``validate_observation``.

Spec: outputs/reports/claude-arch-parallel-20261019/act-student-failure-design.md
§3 E1. Prereg: experiments/2026-10-17-act18/E1_TSREPLAY_PREREG.json.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))

from harness import grasp_act_contract as c  # noqa: E402

VARIANTS = ('V0', 'V1', 'V2', 'V3')
TE_COEFF = .01                 # act18_evaluate.py Executor: temporal_ensemble_coeff=.01
DONE_THRESHOLD = .65           # frozen done-head threshold
WINDOW_TAIL_S = 1.0            # lookback_return start + 1 s
PWM_CLOCK_CAP = .3             # V1: min(pwm_elapsed_s, .3)
SKILL_CLOCK_OFFSET = 40.      # V2: skill_elapsed_s += 40
DONE_LOW = .05                 # C2 rule in design §3 E1
ONSET_TOLERANCE = 5            # |delta| <= 5 ticks
ONSET_DELAY = 15               # V1 more than 15 ticks late counts as affected
PREREG_PATH = ROOT / 'experiments/2026-10-17-act18/E1_TSREPLAY_PREREG.json'
PILOT_ROOT = Path('/home/ubuntu/UGRP/outputs/reports/act-chunk8-pilot/act-chunk8-pilot')
EVIDENCE_TAR = Path('/home/ubuntu/UGRP/outputs/reports/act-chunk8-pilot/act-chunk8-pilot-evidence.tar.gz')
OUTPUT_RUNS = Path('/home/ubuntu/UGRP/outputs/runs')
EXPECTED_MODEL_SHA = 'e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a'
EXPECTED_CHUNK = 8


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False, sort_keys=False) + '\n')


def git(args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def require_enabled(args):
    """Default-off gate: refuse before any input, checkpoint or device access."""
    if not getattr(args, 'enabled', False):
        raise SystemExit('act18 E1 replay is default OFF; pass --enabled to run')


def mutate_observation(observation, variant):
    """Change only whitelisted clock values; the result must revalidate."""
    if variant not in VARIANTS:
        raise ValueError('unknown variant')
    row = dict(observation)
    if variant in ('V1', 'V3'):
        recorded = float(row['pwm_elapsed_s'])
        if not math.isfinite(recorded) or recorded < 0:
            raise ValueError('finite nonnegative recorded pwm clock required')
        row['pwm_elapsed_s'] = min(recorded, PWM_CLOCK_CAP)
    if variant in ('V2', 'V3'):
        recorded = float(row['skill_elapsed_s'])
        if not math.isfinite(recorded) or recorded < 0:
            raise ValueError('finite nonnegative recorded skill clock required')
        row['skill_elapsed_s'] = recorded + SKILL_CLOCK_OFFSET
    c.validate_observation(row)
    return row


class TemporalEnsemble:
    """Bit-for-bit numpy copy of harness/grasp_act_policy.py:182-188.

    ``n_action_steps=1`` predicts every tick, so the chunk list receives one row
    per tick. ChunkExecutor stops returning after done; this class keeps
    replaying because the diagnostic needs hold-end done scores after any fire.
    """

    def __init__(self, coeff=TE_COEFF):
        if not math.isfinite(coeff) or coeff < 0:
            raise ValueError('nonnegative finite ensemble coefficient required')
        self.coeff = coeff
        self.chunks = []
        self.ticks = 0
        self.done_tick = None

    def step(self, chunk):
        values = np.asarray(chunk, dtype=float)
        if values.shape != (c.CHUNK, c.ACTION_DIM) or not np.isfinite(values).all():
            raise ValueError('invalid 8x14 chunk')
        self.chunks.append(values)
        weights = np.exp(-self.coeff * np.arange(len(self.chunks)))
        averaged = np.average([item[0] for item in self.chunks], axis=0, weights=weights)
        action = c.decode_action(averaged)
        self.chunks = [item[1:] for item in self.chunks if len(item) > 1]
        self.ticks += 1
        if action['done'] and self.done_tick is None:
            self.done_tick = self.ticks - 1
        return action


def window_bounds(teacher_rows):
    """Preregistered window and reference ticks (evaluation-side labels only)."""
    phases = [row['teacher_phase'] for row in teacher_rows]
    times = [row['t'] for row in teacher_rows]
    close = phases.index('close')
    lookback = phases.index('lookback')
    lookback_return = phases.index('lookback_return')
    tail = times[lookback_return] + WINDOW_TAIL_S
    after = [i for i, t in enumerate(times) if t <= tail + 1e-9]
    if not after or after[-1] < lookback_return:
        raise ValueError('window tail truncated')
    end = after[-1]
    hold = [i for i, phase in enumerate(phases) if phase == 'hold']
    if not hold:
        raise ValueError('hold phase required for M1.2')
    settle = [i for i in range(close, end + 1) if phases[i] == 'lift_settle']
    return {'close_tick': close, 'end_tick': end, 'lookback_tick': lookback,
            'lookback_return_tick': lookback_return, 'hold_end_tick': hold[-1],
            'lift_settle_ticks': settle, 'ticks': end - close + 1}


def aligned_world(world_dir):
    world_dir = Path(world_dir)
    student = read_rows(world_dir / 'student-r1.jsonl')
    teacher = read_rows(world_dir / 'teacher-r1.jsonl')
    if not student or len(student) != len(teacher):
        raise ValueError(f'{world_dir}: student/teacher row count mismatch')
    for index, (obs, label) in enumerate(zip(student, teacher)):
        if obs['sample_id'] != label['sample_id'] or abs(obs['t'] - label['t']) > 1e-6:
            raise ValueError(f'{world_dir}: student/teacher misaligned at row {index}')
    return student, teacher


def load_world_images(world_dir, student):
    """Verify every referenced JPEG once and return path -> bytes for the window."""
    world_dir = Path(world_dir)
    refs = {}
    for row in student:
        for ref in row['rgb']:
            refs[ref['path']] = ref['sha256']
    images = {}
    for rel, digest in sorted(refs.items()):
        path = (world_dir / rel).resolve()
        if not path.is_relative_to(world_dir.resolve()) or not path.is_file():
            raise ValueError(f'missing in-episode JPEG: {rel}')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'JPEG hash mismatch: {rel}')
        images[rel] = data
    manifest = hashlib.sha256('\n'.join(f'{p} {refs[p]}' for p in sorted(refs)).encode()).hexdigest()
    return images, {'files': len(refs), 'sha256': manifest}


def verify_checkpoint(root, expected_model_sha=EXPECTED_MODEL_SHA, expected_chunk=EXPECTED_CHUNK):
    root = Path(root)
    hashes = json.loads((root / 'SHA256.json').read_text())
    if set(hashes) != {'model.safetensors', 'config.json', 'adapter.json'}:
        raise ValueError('checkpoint inventory mismatch')
    for name, digest in hashes.items():
        actual = sha256(root / name)
        if actual != digest:
            raise ValueError(f'checkpoint artifact hash mismatch: {name}')
    model_sha = hashes['model.safetensors']
    if model_sha != expected_model_sha:
        raise ValueError('checkpoint model.safetensors differs from the preregistered R8 sha')
    meta = json.loads((root / 'adapter.json').read_text())
    if (meta.get('schema') != 'ugrp.act18.adapter.v1' or meta.get('chunk') != expected_chunk
            or meta.get('done_mode') != 'balanced_bce_v1'
            or meta.get('image_mode') != 'current_full_v1'):
        raise ValueError('R8 adapter contract mismatch (chunk 8 required)')
    return {'dir': str(root), 'model_sha256': model_sha,
            'adapter_sha256': hashes['adapter.json'], 'config_sha256': hashes['config.json'],
            'chunk': meta['chunk'], 'schema': meta['schema'],
            'source_sha': (meta.get('provenance') or {}).get('source_sha'),
            'step': (meta.get('provenance') or {}).get('step'),
            'candidate': (meta.get('provenance') or {}).get('candidate')}


def verify_prereg(prereg, args):
    checkpoint = prereg['checkpoint']
    if checkpoint['model_sha256'] != EXPECTED_MODEL_SHA:
        raise ValueError('prereg checkpoint sha changed')
    evidence = prereg['inputs']['evidence_tar']
    if sha256(args.evidence_tar) != evidence['sha256']:
        raise ValueError('evidence tar sha mismatch')
    for world in prereg['inputs']['worlds']:
        student = args.pilot_root / world['student_r1_jsonl']
        teacher = args.pilot_root / world['teacher_r1_jsonl']
        if sha256(student) != world['student_r1_sha256'] or sha256(teacher) != world['teacher_r1_sha256']:
            raise ValueError(f"input hash mismatch: {world['group']}/{world['world']}")
    return {'prereg_path': str(args.prereg), 'prereg_sha256': sha256(args.prereg),
            'evidence_tar': str(args.evidence_tar), 'evidence_sha256': evidence['sha256']}


def world_metrics(rows, bounds, lookback_tick):
    """M1.1-M1.3 from one variant/world replay, global tick indices."""
    onset_rows = [row for row in rows if row['onset']]
    onset_tick = onset_rows[0]['index'] if onset_rows else None
    delta = None if onset_tick is None else onset_tick - lookback_tick
    band = [row for row in rows
            if bounds['hold_end_tick'] - 10 <= row['index'] <= bounds['hold_end_tick'] + 10]
    done_max = max((row['te']['done_score'] for row in band), default=None)
    done_fire = next((row['index'] for row in rows if row['te']['done']), None)
    done_fire_band = next((row['index'] for row in band if row['te']['done']), None)
    settle = [row for row in rows if row['teacher_phase'] == 'lift_settle']
    pairs = ticks_with_change = 0
    for previous, current in zip(settle, settle[1:]):
        changed = False
        for servo in c.SERVOS:
            step = abs(current['te']['pwm'][str(servo)] - previous['te']['pwm'][str(servo)])
            if 1 <= step <= 3:
                pairs += 1
                changed = True
        ticks_with_change += int(changed)
    return {
        'ticks': len(rows),
        'onset_tick': onset_tick,
        'onset_window_tick': None if onset_tick is None else onset_tick - bounds['close_tick'],
        'delta_vs_lookback_ticks': delta,
        'capability_hit': onset_tick is not None and abs(delta) <= ONSET_TOLERANCE,
        'done_max_hold_pm10': done_max,
        'done_ge_065': done_max is not None and done_max >= DONE_THRESHOLD,
        'done_fire_tick': done_fire,
        'done_fire_hold_pm10': done_fire_band,
        'lift_settle_ticks': len(settle),
        'jitter_pairs_1to3': pairs,
        'jitter_pairs_denominator': max(0, (len(settle) - 1) * len(c.SERVOS)),
        'jitter_ticks_1to3': ticks_with_change,
    }


def chunk_prediction(actor, observation, images):
    jpegs = [images[ref['path']] for ref in observation['rgb']]
    values = actor.predict(observation, jpegs)
    chunk = np.asarray(values, dtype=float)
    if chunk.shape != (c.CHUNK, c.ACTION_DIM) or not np.isfinite(chunk).all():
        raise ValueError('Actor.predict did not return finite 8x14')
    return chunk


def run_replay(args):
    prereg = json.loads(args.prereg.read_text())
    hashes = verify_prereg(prereg, args)
    source_sha = git(['rev-parse', 'HEAD'])
    dirty = git(['status', '--porcelain'])
    if dirty and not args.allow_dirty:
        raise ValueError('clean committed source required (--allow-dirty only for diagnostics)')
    checkpoint = verify_checkpoint(args.checkpoint)
    out = Path(args.out)
    if not args.allow_outside_output and not out.resolve().is_relative_to(OUTPUT_RUNS.resolve()):
        raise ValueError('output root must be a new root under /home/ubuntu/UGRP/outputs/runs')
    out.mkdir(parents=True, exist_ok=False)

    variants = list(VARIANTS) if 'all' in args.variant else list(dict.fromkeys(args.variant))
    worlds = prereg['inputs']['worlds']
    if args.diagnostic_world:
        worlds = [w for w in worlds
                  if f"{w['group']}/{w['world']}" == args.diagnostic_world]
        if not worlds:
            raise ValueError('unknown diagnostic world')
    started = utc_now()
    launch = {
        'schema': 'ugrp.act18.e1_tsreplay.launch.v1',
        'argv': sys.argv, 'cwd': str(Path.cwd()), 'started_utc': started,
        'source_sha': source_sha, 'source_dirty': bool(dirty),
        'git_status': dirty.splitlines() if dirty else [],
        'prereg': hashes, 'checkpoint': checkpoint,
        'variants': variants, 'worlds': [f"{w['group']}/{w['world']}" for w in worlds],
        'diagnostic': bool(args.diagnostic_world or args.diagnostic_max_ticks),
        'limits': {'diagnostic_world': args.diagnostic_world,
                   'diagnostic_max_ticks': args.diagnostic_max_ticks},
        'environment': {
            'python': platform.python_version(), 'machine': platform.machine(),
            'system': platform.system(), 'cpu_count': os.cpu_count(),
            'torch': importlib.metadata.version('torch'),
            'torchvision': importlib.metadata.version('torchvision'),
            'numpy': importlib.metadata.version('numpy'),
            'lerobot': importlib.metadata.version('lerobot'),
            'torch_threads': args.torch_threads,
        },
        'labels': ['engineering-only', 'sim', 'gate 비대상', 'pooling 금지'],
        'status': 'running',
    }
    write_json(out / 'launch.json', launch)

    import torch
    from act18_policy import Actor
    torch.set_num_threads(args.torch_threads)
    torch.manual_seed(0)
    actor = Actor.load(args.checkpoint, device='cpu')

    metrics = {variant: {} for variant in variants}
    started_monotonic = time.monotonic()
    try:
        for world in worlds:
            name = f"{world['group']}/{world['world']}"
            world_dir = args.pilot_root / world['group'] / world['world']
            student, teacher = aligned_world(world_dir)
            bounds = window_bounds(teacher)
            images, rgb_manifest = load_world_images(world_dir, student)
            indices = list(range(bounds['close_tick'], bounds['end_tick'] + 1))
            if args.diagnostic_max_ticks:
                indices = indices[:args.diagnostic_max_ticks]
            print(f'[{name}] ticks={len(indices)} window={bounds["close_tick"]}..{bounds["end_tick"]} '
                  f'lookback={bounds["lookback_tick"]} hold_end={bounds["hold_end_tick"]}', flush=True)
            buffers = {variant: [] for variant in variants}
            ensembles = {variant: TemporalEnsemble() for variant in variants}
            world_started = time.monotonic()
            determinism_checked = False
            for offset, index in enumerate(indices):
                observation = student[index]
                for variant in variants:
                    mutated = mutate_observation(observation, variant)
                    chunk = chunk_prediction(actor, mutated, images)
                    action = ensembles[variant].step(chunk)
                    onset = bool(all(wheel < 0 for wheel in action['wheels']))
                    buffers[variant].append({
                        'schema': 'ugrp.act18.e1_tsreplay.row.v1',
                        'variant': variant, 'group': world['group'], 'world': world['world'],
                        'sample_id': observation['sample_id'],
                        'index': index, 'tick': index - bounds['close_tick'], 't': observation['t'],
                        'teacher_phase': teacher[index]['teacher_phase'],
                        'phase_after': teacher[index].get('phase_after'),
                        'skill_elapsed_s': mutated['skill_elapsed_s'],
                        'pwm_elapsed_s': mutated['pwm_elapsed_s'],
                        'chunk': chunk.tolist(),
                        'te': action,
                        'onset': onset,
                    })
                if not determinism_checked:
                    repeat = chunk_prediction(actor, mutate_observation(observation, variants[0]), images)
                    launch.setdefault('determinism_first_tick_equal', {})[name] = bool(
                        np.array_equal(np.asarray(repeat), np.asarray(buffers[variants[0]][0]['chunk'])))
                    determinism_checked = True
                if (offset + 1) % 25 == 0 or offset + 1 == len(indices):
                    wall = time.monotonic() - world_started
                    print(f'  {name} {offset + 1}/{len(indices)} wall={wall:.1f}s '
                          f'({wall / (offset + 1):.2f}s/tick/4variants)', flush=True)
            for variant in variants:
                rows = buffers[variant]
                metrics[variant][f"{world['group']}-{world['world']}"] = {
                    **world_metrics(rows, bounds, bounds['lookback_tick']),
                    'seed': world['seed'], 'window': bounds,
                    'input_manifest_sha256': rgb_manifest['sha256'],
                    'rgb_files': rgb_manifest['files'],
                    'student_r1_sha256': world['student_r1_sha256'],
                    'teacher_r1_sha256': world['teacher_r1_sha256'],
                }
                target = out / variant / f'world-{world["group"]}-{world["world"]}.jsonl'
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('x') as stream:
                    for row in rows:
                        stream.write(json.dumps(row) + '\n')
            del images
            print(f'[{name}] done wall={time.monotonic() - world_started:.1f}s', flush=True)
        for variant in variants:
            write_json(out / variant / 'metrics.json', {
                'schema': 'ugrp.act18.e1_tsreplay.metrics.v1', 'variant': variant,
                'source_sha': source_sha, 'worlds': metrics[variant],
                'definitions': {
                    'onset': 'first TE-decoded tick with all four decoded wheels < 0',
                    'delta_vs_lookback_ticks': 'TE onset global index - first lookback phase index',
                    'done_max_hold_pm10': 'max TE done_score within hold end +/-10 ticks',
                    'jitter_pairs_1to3': 'consecutive lift_settle tick pairs x 5 servos with |dPWM| in 1..3',
                },
            })
        launch['finished_utc'] = utc_now()
        launch['wall_s'] = time.monotonic() - started_monotonic
        launch['status'] = 'complete'
        write_json(out / 'launch.json', launch)
        print(f'REPLAY_COMPLETE out={out} wall={launch["wall_s"]:.1f}s', flush=True)
    except BaseException as error:
        launch['finished_utc'] = utc_now()
        launch['wall_s'] = time.monotonic() - started_monotonic
        launch['status'] = 'HOST_ERROR'
        launch['error'] = repr(error)
        write_json(out / 'launch.json', launch)
        raise


def analyze(args):
    out = Path(args.out)
    launch = json.loads((out / 'launch.json').read_text())
    prereg = json.loads(args.prereg.read_text())
    prereg_sha = sha256(args.prereg)
    variants = launch['variants']
    if launch.get('diagnostic'):
        raise ValueError('diagnostic replay cannot be analyzed as an E1 result')
    tables = {}
    for variant in variants:
        metrics = json.loads((out / variant / 'metrics.json').read_text())
        tables[variant] = metrics['worlds']
    world_names = [f"{w['group']}-{w['world']}" for w in prereg['inputs']['worlds']]

    def value(variant, world, key):
        return tables[variant][world][key]

    v0 = tables['V0']
    capability = [w for w in world_names if v0[w]['capability_hit']]
    done_ok = [w for w in world_names if v0[w]['done_ge_065']]
    onset_worlds = [w for w in world_names if v0[w]['onset_tick'] is not None]
    affected = []
    for world in onset_worlds:
        v1_onset = tables['V1'][world]['onset_tick']
        if v1_onset is None or v1_onset - v0[world]['onset_tick'] > ONSET_DELAY:
            affected.append(world)
    capability_ok = len(capability) >= 3
    done_ok_flag = len(done_ok) >= 3
    h1_primary = (len(onset_worlds) > 0 and
                  len(affected) >= math.ceil(.75 * len(onset_worlds)))
    competence_failure = len(capability) <= 1
    c2_confirmed = all((v0[w]['done_max_hold_pm10'] or 0.) < DONE_LOW for w in world_names)
    decisions = {
        'M1_capability_ok': capability_ok,
        'M1_done_head_ok': done_ok_flag,
        'H1_model_level_supported': h1_primary,
        'H1_affected_onset_worlds': affected,
        'H1_onset_worlds': onset_worlds,
        'H1_onset_subset_fraction': (len(affected) / len(onset_worlds)) if onset_worlds else None,
        'H1_all_world_fraction': len(affected) / 4,
        'ability_failure_V0_onset_le_1_of_4': competence_failure,
        'C2_confirmed_V0_done_lt_005_all4': c2_confirmed,
        'next_action': ('ability failure: hold E2 and move to training-side designs'
                        if competence_failure else
                        ('H1 model-level supported -> E2 PWM deadband A/B eligible'
                         if h1_primary else 'H1 not supported at model level')),
    }
    summary = {
        'schema': 'ugrp.act18.e1_tsreplay.summary.v1',
        'experiment': '2026-10-17-act18', 'phase': 'E1',
        'generated_utc': utc_now(),
        'labels': ['engineering-only', 'sim', 'gate 비대상', 'pooling 금지'],
        'source_sha': launch['source_sha'], 'source_dirty': launch['source_dirty'],
        'environment': launch['environment'],
        'prereg': {'path': str(args.prereg), 'sha256': prereg_sha},
        'evidence_tar': launch['prereg']['evidence_tar'],
        'evidence_tar_sha256': launch['prereg']['evidence_sha256'],
        'checkpoint': launch['checkpoint'],
        'inputs': [{'group': w['group'], 'world': w['world'], 'seed': w['seed'],
                    'student_r1_sha256': w['student_r1_sha256'],
                    'teacher_r1_sha256': w['teacher_r1_sha256']}
                   for w in prereg['inputs']['worlds']],
        'te': {'coefficient': TE_COEFF, 'chunk': c.CHUNK, 'action_dim': c.ACTION_DIM,
               'done_threshold': DONE_THRESHOLD,
               'formula': 'weights=exp(-k*arange(len(chunks))); average first rows; grasp_act_contract.decode_action'},
        'worlds': {world: {variant: tables[variant][world] for variant in variants}
                   for world in world_names},
        'decisions': decisions,
        'replay_wall_s': launch.get('wall_s'),
        'determinism_first_tick_equal': launch.get('determinism_first_tick_equal'),
        'scope': 'teacher-state offline replay only; no rollout, no physical success claim, no student closed-loop claim',
    }
    write_json(out / 'summary.json', summary)
    print(json.dumps(decisions, indent=2, ensure_ascii=False))
    print(f'ANALYZE_COMPLETE out={out}')


def parse(argv=None):
    parser = argparse.ArgumentParser(description='E1 teacher-state TE replay (default OFF)')
    parser.add_argument('--enabled', action='store_true',
                        help='required safety gate; the script is inert without it')
    parser.add_argument('--variant', nargs='+', choices=[*VARIANTS, 'all'], default=['all'])
    parser.add_argument('--checkpoint', type=Path,
                        help='R8 checkpoint directory (model.safetensors/config/adapter/SHA256)')
    parser.add_argument('--out', type=Path, required=False,
                        help='new run root; per-variant subdirs and summary.json')
    parser.add_argument('--prereg', type=Path, default=PREREG_PATH)
    parser.add_argument('--pilot-root', type=Path, default=PILOT_ROOT)
    parser.add_argument('--evidence-tar', type=Path, default=EVIDENCE_TAR)
    parser.add_argument('--torch-threads', type=int, default=2)
    parser.add_argument('--analyze', action='store_true', help='write summary.json from replay outputs')
    parser.add_argument('--allow-dirty', action='store_true', help='diagnostics only')
    parser.add_argument('--allow-outside-output', action='store_true', help='diagnostics only')
    parser.add_argument('--diagnostic-world', help='diagnostics only: group-000/world-000')
    parser.add_argument('--diagnostic-max-ticks', type=int, help='diagnostics only')
    args = parser.parse_args(argv)
    require_enabled(args)
    if args.out is None:
        parser.error('--out is required')
    if args.torch_threads != 2:
        raise ValueError('E1 CPU budget is exactly 2 torch threads')
    if args.analyze:
        if args.checkpoint is not None:
            raise ValueError('--analyze does not take a checkpoint')
    else:
        if args.checkpoint is None:
            parser.error('--checkpoint is required for replay')
        if not args.checkpoint.is_dir():
            parser.error('--checkpoint must be a directory')
        if not args.prereg.is_file():
            parser.error('--prereg must exist')
        if args.diagnostic_max_ticks is not None and not (
                args.allow_dirty and args.allow_outside_output):
            raise ValueError('diagnostic flags require --allow-dirty --allow-outside-output')
    return args


def main(argv=None):
    args = parse(argv)
    if args.analyze:
        analyze(args)
    else:
        run_replay(args)


if __name__ == '__main__':
    main()
