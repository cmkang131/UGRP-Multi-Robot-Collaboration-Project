"""E1/C2: R8 teacher-state or student-rollout temporal-ensemble replay.

Default OFF (``--enabled`` required). This is an offline CPU replay: it reads
recorded student observations, calls ``Actor.predict`` once per tick, runs the
same temporal ensemble as ``harness.grasp_act_policy.ChunkExecutor`` and writes
per-tick decoded commands. No simulator, rollout, teacher command execution or
physics is involved. Counterfactuals change only whitelisted fields and must
still pass ``validate_observation``.

Modes:
  --experiment E1  (default) teacher-state replay V0-V3, prereg E1_TSREPLAY_PREREG.json.
  --experiment C2a teacher-state replay V0+V4 plus ``--pe-sweep`` at the pilot
                   hold end tick, prereg C2_DONECLOCK_PREREG.json (spec §3 C2a).
  --experiment C2b ``--source student-rollout`` S0-S4 replay of recorded
                   finish-r3/repro actor inputs, same prereg (spec §3 C2b).

Spec: outputs/reports/claude-arch-parallel-20261019/act-student-failure-design.md
§3 E1 and act-C2-R3-spec.md §3 C2a/C2b. Prereg: E1_TSREPLAY_PREREG.json (E1),
C2_DONECLOCK_PREREG.json (C2a/C2b).
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

VARIANTS = ('V0', 'V1', 'V2', 'V3', 'V4')
STUDENT_VARIANTS = ('S0', 'S1', 'S2', 'S3', 'S4')
TE_COEFF = .01                 # act18_evaluate.py Executor: temporal_ensemble_coeff=.01
DONE_THRESHOLD = .65           # frozen done-head threshold
WINDOW_TAIL_S = 1.0            # lookback_return start + 1 s
PWM_CLOCK_CAP = .3             # V1: min(pwm_elapsed_s, .3)
SKILL_CLOCK_OFFSET = 40.      # V2: skill_elapsed_s += 40
DONE_LOW = .05                 # C2 rule in design §3 E1
ONSET_TOLERANCE = 5            # |delta| <= 5 ticks
ONSET_DELAY = 15               # V1 more than 15 ticks late counts as affected
PREREG_PATH = ROOT / 'experiments/2026-10-17-act18/E1_TSREPLAY_PREREG.json'
C2_PREREG_PATH = ROOT / 'experiments/2026-10-17-act18/C2_DONECLOCK_PREREG.json'
PILOT_ROOT = Path('/home/ubuntu/UGRP/outputs/reports/act-chunk8-pilot/act-chunk8-pilot')
EVIDENCE_TAR = Path('/home/ubuntu/UGRP/outputs/reports/act-chunk8-pilot/act-chunk8-pilot-evidence.tar.gz')
OUTPUT_RUNS = Path('/home/ubuntu/UGRP/outputs/runs')
EXPECTED_MODEL_SHA = 'e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a'
EXPECTED_CHUNK = 8
TARGET_HOLD_END_PE = 11.25     # C2a V4: pwm_elapsed_s += 11.25 - pilot hold end pe
SWEEP_DEFAULT = (9.0, 10.0, 10.5, 10.8, 11.0, 11.1, 11.2, 11.3, 11.4, 11.6, 12.0, 13.0)
SWEEP_PASS = .5                # C2a a3: raw h=0 >= .5 interval inside [10.8, 11.8]
SWEEP_TARGET = (10.8, 11.8)
DETERMINISM_TOLERANCE = 1e-6   # C2a: V0 chunk per tick |diff| <= 1e-6 vs E1
C2B_WINDOW_BEFORE_S = 1.0      # C2b: lift onset - 1.0 s
C2B_WINDOW_AFTER_S = 14.0      # C2b: lift onset + 14.0 s
C2B_LIFT_CLEARANCE_M = .012    # physical lift onset: min_z >= lift clearance
C2B_GRASP_FORCE_N = .5         # non-lift fallback anchor: finger force >= .5 N
C2B_BACKWARD_TICKS = 5         # b2: four negative wheels for >= 5 consecutive ticks
C2B_DONE_PE_RANGE = (10.3, 12.0)  # C2b done-path PASS: fire pe in [10.3, 12.0]


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


def mutate_observation(observation, variant, delta_s=None):
    """Change only whitelisted clock values; the result must revalidate.

    V4 (C2a) shifts ``pwm_elapsed_s`` by the preregistered per-world delta so
    that the pilot hold end reaches ``TARGET_HOLD_END_PE``. The delta must come
    from the prereg; it is never derived from model output.
    """
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
    if variant == 'V4':
        if delta_s is None or not math.isfinite(delta_s) or delta_s < 0:
            raise ValueError('V4 requires a finite nonnegative preregistered delta')
        recorded = float(row['pwm_elapsed_s'])
        if not math.isfinite(recorded) or recorded < 0:
            raise ValueError('finite nonnegative recorded pwm clock required')
        row['pwm_elapsed_s'] = recorded + float(delta_s)
    c.validate_observation(row)
    return row


def parse_sweep(text):
    """Parse ``--pe-sweep 9.0,10.0,...`` into a strictly increasing tuple."""
    if text in (None, '', 'off'):
        return ()
    if isinstance(text, (list, tuple)):
        values = [float(item) for item in text]
    else:
        values = [float(item) for item in str(text).split(',') if item.strip()]
    if not values:
        raise ValueError('empty pe sweep')
    for value in values:
        if not math.isfinite(value) or value < 0:
            raise ValueError('pe sweep points must be finite nonnegative seconds')
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError('pe sweep points must be strictly increasing')
    return tuple(values)


def sweep_interval(points, threshold=SWEEP_PASS):
    """Largest contiguous sweep run with raw h=0 >= threshold.

    ``points`` is an iterable of ``(pe, raw_done_score)`` sorted by pe; the
    sweep grid is fixed in the prereg, so "contiguous" means adjacent grid
    points, not an interpolated curve. Returns None when nothing reaches the
    threshold.
    """
    ordered = sorted(points)
    best = []
    run = []
    for pe, raw in ordered:
        if raw >= threshold:
            run.append((pe, raw))
            if len(run) > len(best):
                best = list(run)
        else:
            run = []
    if not best:
        return None
    return {'pe_min': best[0][0], 'pe_max': best[-1][0],
            'pe_points': [pe for pe, _ in best], 'width_s': best[-1][0] - best[0][0],
            'peak_pe': max(best, key=lambda item: item[1])[0],
            'peak_raw': max(raw for _, raw in best)}


def sweep_half_max(points):
    """FWHM of the raw h=0 sweep curve (descriptive; not a verdict rule)."""
    ordered = sorted(points)
    if not ordered:
        return None
    peak = max(raw for _, raw in ordered)
    if peak <= 0:
        return None
    half = peak / 2.
    above = [pe for pe, raw in ordered if raw >= half]
    if not above:
        return None
    return {'pe_min': min(above), 'pe_max': max(above),
            'width_s': max(above) - min(above), 'peak_raw': peak,
            'half_max': half}


def compare_replay_rows(rows, reference, tolerance=DETERMINISM_TOLERANCE):
    """Per-tick chunk comparison against a reference replay (C2a determinism)."""
    if len(rows) != len(reference):
        raise ValueError(f'determinism row count mismatch: {len(rows)} != {len(reference)}')
    worst_chunk = 0.
    worst_tick = None
    worst_done = 0.
    worst_wheels = 0.
    for row, expected in zip(rows, reference):
        if row['index'] != expected['index']:
            raise ValueError(f'determinism index mismatch at {row["index"]}')
        chunk = np.asarray(row['chunk'], dtype=float)
        other = np.asarray(expected['chunk'], dtype=float)
        if chunk.shape != other.shape:
            raise ValueError('determinism chunk shape mismatch')
        delta = float(np.max(np.abs(chunk - other)))
        if delta > worst_chunk:
            worst_chunk, worst_tick = delta, row['index']
        worst_done = max(worst_done, abs(float(row['te']['done_score'])
                                         - float(expected['te']['done_score'])))
        worst_wheels = max(worst_wheels, float(np.max(np.abs(
            np.asarray(row['te']['wheels'], dtype=float)
            - np.asarray(expected['te']['wheels'], dtype=float)))))
    return {'ticks': len(rows), 'max_abs_chunk_diff': worst_chunk,
            'max_abs_chunk_diff_tick': worst_tick,
            'max_abs_te_done_diff': worst_done, 'max_abs_te_wheel_diff': worst_wheels,
            'tolerance': tolerance, 'passed': worst_chunk <= tolerance}


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


def verify_c2_prereg(prereg, args, experiment):
    """C2 prereg gate: hashes, sweep grid and (C2a) world deltas must match."""
    c2 = prereg.get('c2') or {}
    key = 'c2a' if experiment == 'C2a' else 'c2b'
    section = c2.get(key)
    if not isinstance(section, dict):
        raise ValueError(f'prereg has no c2.{key} section')
    if prereg['checkpoint']['model_sha256'] != EXPECTED_MODEL_SHA:
        raise ValueError('prereg checkpoint sha changed')
    if experiment == 'C2a':
        evidence = prereg['inputs']['evidence_tar']
        if sha256(args.evidence_tar) != evidence['sha256']:
            raise ValueError('evidence tar sha mismatch')
        if abs(float(section['target_hold_end_pe']) - TARGET_HOLD_END_PE) > 1e-12:
            raise ValueError('prereg target hold end pe changed')
        for world in section['worlds']:
            student = args.pilot_root / world['student_r1_jsonl']
            teacher = args.pilot_root / world['teacher_r1_jsonl']
            if sha256(student) != world['student_r1_sha256'] or sha256(teacher) != world['teacher_r1_sha256']:
                raise ValueError(f"input hash mismatch: {world['group']}/{world['world']}")
            delta = float(world['v4_delta_pwm_s'])
            if not math.isfinite(delta) or delta < 0:
                raise ValueError('invalid prereg v4 delta')
        expected = tuple(float(value) for value in section['sweep_points'])
        if parse_sweep(args.pe_sweep) != expected:
            raise ValueError('pe sweep points differ from prereg')
        if not args.determinism_e1:
            raise ValueError('C2a requires --determinism-e1 (E1 V0 reference)')
    else:
        if args.source != 'student-rollout':
            raise ValueError('C2b requires --source student-rollout')
        if not args.rollout_root:
            raise ValueError('C2b requires --rollout-root')
        if not section.get('runs'):
            raise ValueError('prereg c2b has no runs')
        for run in section['runs']:
            evaluation = Path(args.rollout_root) / run['root'] / run['group'] / 'evaluation'
            if not (evaluation / 'actor-inputs.jsonl').is_file():
                raise ValueError(f"missing actor inputs: {evaluation}")
            if not (evaluation / 'owner' / 'evaluation-only.jsonl').is_file():
                raise ValueError(f"missing evaluation-only truth: {evaluation}")
    return {'section': section, 'prereg_path': str(args.prereg),
            'prereg_sha256': sha256(args.prereg)}


def c2a_world_delta(section, group, world):
    for entry in section['worlds']:
        if entry['group'] == group and entry['world'] == world:
            return float(entry['v4_delta_pwm_s']), entry
    raise ValueError(f'no prereg V4 delta for {group}/{world}')


def sweep_world(actor, student_row, points, images):
    """C2a a3: hold end tick, pe only, raw h=0 done score per sweep point."""
    rows = []
    for pe in points:
        mutated = dict(student_row)
        mutated['pwm_elapsed_s'] = float(pe)
        c.validate_observation(mutated)
        chunk = chunk_prediction(actor, mutated, images)
        first = np.asarray(chunk[0], dtype=float)
        action = c.decode_action(first)
        rows.append({'pe': float(pe), 'raw_done_score': action['done_score'],
                     'raw_done': action['done'], 'wheels': action['wheels'],
                     'pwm': action['pwm'], 'chunk_first_row': first.tolist()})
    return rows


def compare_v0_to_e1(rows, e1_file):
    reference = read_rows(e1_file)
    return compare_replay_rows(rows, reference)


def reconstruct_clock(rows, deadband):
    """Recompute pwm_elapsed_s from the issued history.

    ``deadband=1`` reproduces the recorded v6 clock (any servo change resets) and
    is used as a fail-closed check. ``deadband=3`` is the C2b S2/S3/S4 v7 clock
    (spec §3 C2b S2: reset only when a servo changes by >= 3 PWM).
    """
    if deadband < 1:
        raise ValueError('deadband must be >= 1')
    changed = None
    previous = None
    values = {}
    for row in rows:
        observation = row['observation']
        now = float(observation['t'])
        pwm = observation['issued'][-1]['pwm']
        if previous is not None and any(
                abs(pwm[str(servo)] - previous[str(servo)]) >= deadband for servo in c.SERVOS):
            changed = now
        if changed is None:
            changed = now
        values[round(now, 6)] = now - changed
        previous = pwm
    return values


def stabilize_history(observation, stabilized, lift_onset_t):
    """S3: after lift onset, replace issued PWM jitter with the last >=3 step value."""
    row = dict(observation)
    issued = []
    for entry in row['issued']:
        command = dict(entry)
        pwm = dict(entry['pwm'])
        if float(entry['t']) >= lift_onset_t - 1e-9:
            reference = stabilized.get(round(float(entry['t']), 6))
            if reference is not None:
                pwm = {str(servo): int(reference[str(servo)]) for servo in c.SERVOS}
        command['pwm'] = pwm
        issued.append(command)
    row['issued'] = issued
    c.validate_observation(row)
    return row


def stabilized_commands(rows):
    """Per-tick stabilized own command PWM: keep a command only when a servo moved >= 3."""
    stabilized = {}
    previous = None
    current = None
    for row in rows:
        observation = row['observation']
        now = round(float(observation['t']), 6)
        pwm = observation['issued'][-1]['pwm']
        if current is None:
            current = {str(servo): int(pwm[str(servo)]) for servo in c.SERVOS}
        elif any(abs(pwm[str(servo)] - current[str(servo)]) >= 3 for servo in c.SERVOS):
            current = {str(servo): int(pwm[str(servo)]) for servo in c.SERVOS}
        stabilized[now] = dict(current)
        previous = pwm
    return stabilized


def teacher_alignment(teacher_root, seed):
    """Same-seed pilot teacher: lift start/end, aligned skill clock, lift posture."""
    import glob
    matches = []
    for phase_file in sorted(Path(teacher_root).glob('group-*/world-*/teacher-r1.jsonl')):
        world_dir = phase_file.parent
        student_file = world_dir / 'student-r1.jsonl'
        labels = read_rows(phase_file)
        students = read_rows(student_file)
        seed_value = None
        for item in students:
            sample = item.get('sample_id', '')
            parts = sample.split('-')
            if len(parts) > 1 and parts[1].isdigit():
                seed_value = int(parts[1])
                break
        if seed_value == seed:
            matches.append((world_dir, labels, students))
    if len(matches) != 1:
        raise ValueError(f'expected exactly one pilot teacher world for seed {seed}, got {len(matches)}')
    world_dir, labels, students = matches[0]
    phases = [item['teacher_phase'] for item in labels]
    lift_start = phases.index('lift')
    lift_end = phases.index('lift_settle') if 'lift_settle' in phases else lift_start
    posture = {str(servo): int(labels[lift_end]['teacher_command']['pwm'][str(servo)])
               for servo in (3, 4, 5)}
    return {'world_dir': str(world_dir), 't': [float(item['t']) for item in labels],
            'skill_elapsed_s': [float(item['skill_elapsed_s']) for item in students],
            'lift_start_t': float(labels[lift_start]['t']),
            'lift_end_t': float(labels[lift_end]['t']), 'lift_posture': posture,
            'lift_end_skill_elapsed_s': float(students[lift_end]['skill_elapsed_s'])}


def aligned_skill_elapsed(teacher, now):
    """Piecewise teacher skill clock shifted by the lift-onset alignment."""
    times = teacher['t']
    values = teacher['skill_elapsed_s']
    if now <= times[0]:
        return values[0]
    if now >= times[-1]:
        return values[-1] + (now - times[-1])
    low, high = 0, len(times) - 1
    while low < high - 1:
        middle = (low + high) // 2
        if times[middle] <= now:
            low = middle
        else:
            high = middle
    span = times[high] - times[low]
    if span <= 0:
        return values[high]
    share = (now - times[low]) / span
    return values[low] + share * (values[high] - values[low])


def rollout_anchor(truth):
    """C2b anchor: physical lift onset, else grasp onset (non-lift control)."""
    for row in truth:
        if float(row.get('min_z') or 0.) >= C2B_LIFT_CLEARANCE_M:
            return float(row['t']), 'lift_clearance'
    for row in truth:
        forces = row.get('finger_forces') or [0., 0.]
        if max(float(value) for value in forces) >= C2B_GRASP_FORCE_N:
            return float(row['t']), 'grasp_force_fallback'
    raise ValueError('no physical lift or grasp anchor in evaluation-only truth')


def c2b_truth(evaluation, world):
    rows = [row for row in read_rows(Path(evaluation) / 'owner' / 'evaluation-only.jsonl')
            if row.get('world') == world and row.get('speed') is not None]
    rows.sort(key=lambda row: float(row['t']))
    if not rows:
        raise ValueError(f'no evaluation-only physics rows for world {world}')
    return rows


def c2b_inputs(evaluation, world):
    rows = [row for row in read_rows(Path(evaluation) / 'actor-inputs.jsonl')
            if row['world'] == world]
    rows.sort(key=lambda row: float(row['observation']['t']))
    if not rows:
        raise ValueError(f'no actor inputs for world {world}')
    return rows


def load_rollout_images(evaluation, world, rows):
    """Verify every JPEG referenced inside the replay window and return bytes."""
    base = Path(evaluation) / 'actor-inputs' / f'world-{world:03d}'
    refs = {}
    for row in rows:
        for ref in row['observation']['rgb']:
            refs[ref['path']] = ref['sha256']
    images = {}
    for rel, digest in sorted(refs.items()):
        path = (base / rel).resolve()
        if not path.is_relative_to(base.resolve()) or not path.is_file():
            raise ValueError(f'missing recovered JPEG: {rel}')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'JPEG hash mismatch: {rel}')
        images[rel] = data
    manifest = hashlib.sha256('\n'.join(f'{path} {refs[path]}' for path in sorted(refs)).encode()).hexdigest()
    return images, {'files': len(refs), 'sha256': manifest, 'base': str(base)}


def backward_onset(rows, anchor_t, minimum=C2B_BACKWARD_TICKS):
    """First tick after the anchor starting >= minimum consecutive four-negative-wheel ticks."""
    run_start = None
    run = 0
    for row in rows:
        if row['t'] < anchor_t - 1e-9:
            continue
        negative = all(wheel < 0 for wheel in row['te']['wheels'])
        if negative:
            run += 1
            if run == 1:
                run_start = row['t']
            if run >= minimum:
                return {'t': run_start, 'ticks': minimum, 'satisfied': True}
        else:
            run = 0
            run_start = None
    return {'t': None, 'ticks': run, 'satisfied': False}


def first_done_fire(rows, anchor_t):
    for row in rows:
        if row['t'] < anchor_t - 1e-9:
            continue
        if row['te']['done']:
            return row
    return None


def run_student_replay(args):
    prereg = json.loads(args.prereg.read_text())
    verified = verify_c2_prereg(prereg, args, 'C2b')
    section = verified['section']
    source_sha = git(['rev-parse', 'HEAD'])
    dirty = git(['status', '--porcelain'])
    if dirty and not args.allow_dirty:
        raise ValueError('clean committed source required (--allow-dirty only for diagnostics)')
    checkpoint = verify_checkpoint(args.checkpoint)
    out = Path(args.out)
    if not args.allow_outside_output and not out.resolve().is_relative_to(OUTPUT_RUNS.resolve()):
        raise ValueError('output root must be a new root under /home/ubuntu/UGRP/outputs/runs')
    out.mkdir(parents=True, exist_ok=False)
    variants = list(STUDENT_VARIANTS)
    sweep_points = parse_sweep(args.pe_sweep)
    started = utc_now()
    launch = {
        'schema': 'ugrp.act18.c2b_replay.launch.v1', 'experiment': 'C2b',
        'argv': sys.argv, 'cwd': str(Path.cwd()), 'started_utc': started,
        'source_sha': source_sha, 'source_dirty': bool(dirty),
        'git_status': dirty.splitlines() if dirty else [],
        'prereg': verified, 'checkpoint': checkpoint, 'variants': variants,
        'rollout_root': str(args.rollout_root), 'teacher_root': str(args.teacher_root),
        'sweep_points': list(sweep_points),
        'window': {'before_s': C2B_WINDOW_BEFORE_S, 'after_s': C2B_WINDOW_AFTER_S,
                   'lift_clearance_m': C2B_LIFT_CLEARANCE_M,
                   'grasp_force_fallback_n': C2B_GRASP_FORCE_N},
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
    sweeps = {}
    started_monotonic = time.monotonic()
    try:
        for run in section['runs']:
            label = run['label']
            evaluation = Path(args.rollout_root) / run['root'] / run['group'] / 'evaluation'
            world = int(run['world'])
            inputs = c2b_inputs(evaluation, world)
            truth = c2b_truth(evaluation, world)
            anchor_t, anchor_kind = rollout_anchor(truth)
            if bool(run.get('lift_expected')) and anchor_kind != 'lift_clearance':
                raise ValueError(f'{label}: prereg expects a lift but no clearance anchor')
            if not bool(run.get('lift_expected')) and anchor_kind != 'grasp_force_fallback':
                raise ValueError(f'{label}: prereg expects a non-lift control but found a lift anchor')
            first_t = anchor_t - C2B_WINDOW_BEFORE_S
            last_t = anchor_t + C2B_WINDOW_AFTER_S
            selected = [row for row in inputs
                        if first_t - 1e-9 <= float(row['observation']['t']) <= last_t + 1e-9]
            if len(selected) < 100:
                raise ValueError(f'{label}: replay window too short ({len(selected)} ticks)')
            indices = [row['observation']['sample_id'] for row in selected]
            images, rgb_manifest = load_rollout_images(evaluation, world, selected)
            recorded = reconstruct_clock(inputs, 1)
            v7 = reconstruct_clock(inputs, 3)
            worst_recorded = 0.
            for row in selected:
                observation = row['observation']
                now = round(float(observation['t']), 6)
                worst_recorded = max(worst_recorded,
                                     abs(recorded[now] - float(observation['pwm_elapsed_s'])))
            if worst_recorded > 1e-6:
                raise ValueError(f'{label}: recorded clock reconstruction mismatch {worst_recorded}')
            stabilized = stabilized_commands(inputs)
            teacher = teacher_alignment(args.teacher_root, int(run['seed']))
            alignment = anchor_t - teacher['lift_start_t']
            print(f'[{label}] window {first_t:.1f}..{last_t:.1f} ticks={len(selected)} '
                  f'anchor={anchor_t:.1f} ({anchor_kind}) alignment={alignment:+.1f}s', flush=True)
            buffers = {variant: [] for variant in variants}
            ensembles = {variant: TemporalEnsemble() for variant in variants}
            world_started = time.monotonic()
            for offset, row in enumerate(selected):
                observation = row['observation']
                now = round(float(observation['t']), 6)
                base = {variant: dict(observation) for variant in variants}
                base['S0'] = observation
                base['S1'] = observation
                base['S2']['pwm_elapsed_s'] = v7[now]
                base['S3']['pwm_elapsed_s'] = v7[now]
                base['S4']['pwm_elapsed_s'] = v7[now]
                for variant in ('S3', 'S4'):
                    base[variant] = stabilize_history(base[variant], stabilized, anchor_t)
                posture = teacher['lift_posture']
                issued = []
                for entry in base['S4']['issued']:
                    command = dict(entry)
                    pwm = dict(entry['pwm'])
                    for servo in ('3', '4', '5'):
                        pwm[servo] = posture[servo]
                    command['pwm'] = pwm
                    issued.append(command)
                base['S4']['issued'] = issued
                base['S4']['skill_elapsed_s'] = aligned_skill_elapsed(
                    teacher, float(observation['t']) - alignment)
                for variant in variants:
                    if variant == 'S1':
                        continue
                    mutated = dict(base[variant])
                    c.validate_observation(mutated)
                    chunk = chunk_prediction(actor, mutated, images)
                    action = ensembles[variant].step(chunk)
                    buffers[variant].append({
                        'schema': 'ugrp.act18.c2b_replay.row.v1',
                        'variant': variant, 'label': label, 'group': run['group'],
                        'world': world, 'seed': int(run['seed']),
                        'sample_id': observation['sample_id'], 'index': offset,
                        't': float(observation['t']), 'anchor_t': anchor_t,
                        'anchor_kind': anchor_kind, 'skill': observation['skill'],
                        'skill_elapsed_s': mutated['skill_elapsed_s'],
                        'pwm_elapsed_s': mutated['pwm_elapsed_s'],
                        'chunk': chunk.tolist(), 'te': action,
                        'onset': bool(all(wheel < 0 for wheel in action['wheels'])),
                    })
                if (offset + 1) % 50 == 0 or offset + 1 == len(selected):
                    wall = time.monotonic() - world_started
                    print(f'  {label} {offset + 1}/{len(selected)} wall={wall:.1f}s', flush=True)
            for variant in variants:
                if variant == 'S1':
                    continue
                rows = buffers[variant]
                after = [row for row in rows if row['t'] >= anchor_t - 1e-9]
                fire = first_done_fire(rows, anchor_t)
                peak = max(rows, key=lambda row: row['te']['done_score'])
                backward = backward_onset(rows, anchor_t)
                metrics[variant][label] = {
                    'schema': 'ugrp.act18.c2b_replay.metrics.v1',
                    'group': run['group'], 'world': world, 'seed': int(run['seed']),
                    'lift_expected': bool(run.get('lift_expected')),
                    'anchor_t': anchor_t, 'anchor_kind': anchor_kind,
                    'window_first_t': float(selected[0]['observation']['t']),
                    'window_last_t': float(selected[-1]['observation']['t']),
                    'ticks': len(rows), 'post_anchor_ticks': len(after),
                    'first_done_t': None if fire is None else fire['t'],
                    'first_done_pe': None if fire is None else fire['pwm_elapsed_s'],
                    'first_done_skill_elapsed_s': None if fire is None else fire['skill_elapsed_s'],
                    'done_fire': fire is not None,
                    'peak_done_score': peak['te']['done_score'],
                    'peak_done_t': peak['t'],
                    'post_anchor_max_pe': max((row['pwm_elapsed_s'] for row in after), default=None),
                    'backward_onset_t': backward['t'],
                    'backward_onset': backward['satisfied'],
                    'teacher_lift_start_t': teacher['lift_start_t'],
                    'teacher_lift_end_t': teacher['lift_end_t'],
                    'teacher_alignment_s': alignment,
                    'input_manifest_sha256': rgb_manifest['sha256'],
                    'rgb_files': rgb_manifest['files'],
                }
                target = out / variant / f'{label}.jsonl'
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('x') as stream:
                    for item in rows:
                        stream.write(json.dumps(item) + '\n')
            if sweep_points:
                after = [row for row in selected if float(row['observation']['t']) >= anchor_t - 1e-9]
                anchor_row = max(after, key=lambda row: float(row['observation']['pwm_elapsed_s']))
                sweeps[label] = {
                    'anchor_t': float(anchor_row['observation']['t']),
                    'anchor_pe': float(anchor_row['observation']['pwm_elapsed_s']),
                    'points': sweep_world(actor, anchor_row['observation'], sweep_points, images),
                }
                target = out / 'S1' / f'{label}.jsonl'
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('x') as stream:
                    for item in sweeps[label]['points']:
                        stream.write(json.dumps({'label': label, **item}) + '\n')
            del images
            print(f'[{label}] done wall={time.monotonic() - world_started:.1f}s', flush=True)
        for variant in variants:
            if variant == 'S1':
                continue
            write_json(out / variant / 'metrics.json', {
                'schema': 'ugrp.act18.c2b_replay.metrics.v1', 'variant': variant,
                'source_sha': source_sha, 'runs': metrics[variant],
                'definitions': {
                    'first_done_t': 'first TE decoded done (>= .65) tick at or after the anchor',
                    'first_done_pe': 'pwm_elapsed_s fed to the policy at that tick',
                    'backward_onset_t': 'first tick of >= 5 consecutive four-negative-wheel TE ticks',
                },
            })
        if sweeps:
            write_json(out / 'S1' / 'metrics.json', {
                'schema': 'ugrp.act18.c2b_sweep.metrics.v1',
                'source_sha': source_sha, 'runs': sweeps,
                'definition': 'raw h=0 done score at the max recorded pe tick after the anchor',
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


def run_replay(args):
    if args.experiment == 'C2b':
        return run_student_replay(args)
    prereg = json.loads(args.prereg.read_text())
    if args.experiment == 'C2a':
        verified = verify_c2_prereg(prereg, args, 'C2a')
        section = verified['section']
        hashes = {'prereg_path': verified['prereg_path'],
                  'prereg_sha256': verified['prereg_sha256'],
                  'evidence_tar': str(args.evidence_tar),
                  'evidence_sha256': prereg['inputs']['evidence_tar']['sha256']}
    else:
        if args.source != 'teacher-pilot':
            raise ValueError('E1 replay only accepts --source teacher-pilot')
        hashes = verify_prereg(prereg, args)
        section = None
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
    if args.experiment == 'C2a':
        if 'V4' not in variants or 'V0' not in variants:
            raise ValueError('C2a requires both V0 and V4 variants')
        if any(variant in variants for variant in ('V1', 'V2', 'V3')):
            raise ValueError('C2a replays only V0 and V4')
    sweep_points = parse_sweep(args.pe_sweep)
    if args.experiment == 'C2a' and not sweep_points:
        raise ValueError('C2a requires --pe-sweep')
    if args.experiment == 'E1' and sweep_points:
        raise ValueError('--pe-sweep belongs to C2a only')
    worlds = prereg['inputs']['worlds']
    if args.diagnostic_world:
        worlds = [w for w in worlds
                  if f"{w['group']}/{w['world']}" == args.diagnostic_world]
        if not worlds:
            raise ValueError('unknown diagnostic world')
    started = utc_now()
    launch = {
        'schema': 'ugrp.act18.e1_tsreplay.launch.v1', 'experiment': args.experiment,
        'argv': sys.argv, 'cwd': str(Path.cwd()), 'started_utc': started,
        'source_sha': source_sha, 'source_dirty': bool(dirty),
        'git_status': dirty.splitlines() if dirty else [],
        'prereg': hashes, 'checkpoint': checkpoint,
        'variants': variants, 'worlds': [f"{w['group']}/{w['world']}" for w in worlds],
        'diagnostic': bool(args.diagnostic_world or args.diagnostic_max_ticks),
        'limits': {'diagnostic_world': args.diagnostic_world,
                   'diagnostic_max_ticks': args.diagnostic_max_ticks},
        'sweep_points': list(sweep_points),
        'determinism_e1': str(args.determinism_e1) if args.determinism_e1 else None,
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
    sweeps = {}
    determinism = {}
    started_monotonic = time.monotonic()
    try:
        for world in worlds:
            name = f"{world['group']}/{world['world']}"
            world_dir = args.pilot_root / world['group'] / world['world']
            student, teacher = aligned_world(world_dir)
            bounds = window_bounds(teacher)
            images, rgb_manifest = load_world_images(world_dir, student)
            delta = None
            if args.experiment == 'C2a':
                delta, entry = c2a_world_delta(section, world['group'], world['world'])
                hold_pe = float(student[bounds['hold_end_tick']]['pwm_elapsed_s'])
                expected = float(entry['hold_end_pe_recorded'])
                if abs(hold_pe - expected) > 1e-9:
                    raise ValueError(f'{name}: hold end pe {hold_pe} != prereg {expected}')
                if abs((hold_pe + delta) - TARGET_HOLD_END_PE) > 1e-9:
                    raise ValueError(f'{name}: prereg delta does not reach the target hold end pe')
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
                    mutated = mutate_observation(observation, variant, delta)
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
                    repeat = chunk_prediction(actor, mutate_observation(observation, variants[0], delta), images)
                    launch.setdefault('determinism_first_tick_equal', {})[name] = bool(
                        np.array_equal(np.asarray(repeat), np.asarray(buffers[variants[0]][0]['chunk'])))
                    determinism_checked = True
                if (offset + 1) % 25 == 0 or offset + 1 == len(indices):
                    wall = time.monotonic() - world_started
                    print(f'  {name} {offset + 1}/{len(indices)} wall={wall:.1f}s '
                          f'({wall / (offset + 1):.2f}s/tick)', flush=True)
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
            if args.determinism_e1 and 'V0' in variants:
                reference = (Path(args.determinism_e1) / 'V0'
                             / f'world-{world["group"]}-{world["world"]}.jsonl')
                if reference.is_file():
                    comparison = compare_v0_to_e1(buffers['V0'], reference)
                    determinism[name] = comparison
                    launch['determinism_e1'] = determinism
                    write_json(out / 'launch.json', launch)
                    print(f'[{name}] determinism chunk_max={comparison["max_abs_chunk_diff"]:.3e} '
                          f'passed={comparison["passed"]}', flush=True)
                    if not comparison['passed']:
                        raise ValueError(f'{name}: determinism check failed against E1 V0')
            if sweep_points:
                hold_index = bounds['hold_end_tick']
                hold_row = student[hold_index]
                points = sweep_world(actor, hold_row, sweep_points, images)
                sweeps[f"{world['group']}-{world['world']}"] = {
                    'sample_id': hold_row['sample_id'], 'index': hold_index,
                    't': hold_row['t'], 'recorded_pe': hold_row['pwm_elapsed_s'],
                    'teacher_phase': teacher[hold_index]['teacher_phase'],
                    'points': points,
                }
                target = out / 'sweep' / f'world-{world["group"]}-{world["world"]}.jsonl'
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('x') as stream:
                    for item in points:
                        stream.write(json.dumps({'group': world['group'], 'world': world['world'],
                                                 'sample_id': hold_row['sample_id'],
                                                 'index': hold_index, **item}) + '\n')
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
        if sweeps:
            write_json(out / 'sweep' / 'metrics.json', {
                'schema': 'ugrp.act18.c2a_sweep.metrics.v1', 'source_sha': source_sha,
                'points': list(sweep_points), 'worlds': sweeps,
                'definition': 'raw h=0 done score at the pilot hold end tick, pe only',
            })
        launch['finished_utc'] = utc_now()
        launch['wall_s'] = time.monotonic() - started_monotonic
        launch['status'] = 'complete'
        launch['determinism_e1'] = determinism
        write_json(out / 'launch.json', launch)
        print(f'REPLAY_COMPLETE out={out} wall={launch["wall_s"]:.1f}s', flush=True)
    except BaseException as error:
        launch['finished_utc'] = utc_now()
        launch['wall_s'] = time.monotonic() - started_monotonic
        launch['status'] = 'HOST_ERROR'
        launch['error'] = repr(error)
        write_json(out / 'launch.json', launch)
        raise


def c2a_decision(world_names, rows):
    """Preregistered C2a verdict from a1/a3 per-world metrics."""
    a1_ok = sum(1 for world in world_names if rows[world]['a1_ge_065'])
    a3_ok = sum(1 for world in world_names if rows[world]['a3_interval_inside_10_8_11_8'])
    fail_a1 = sum(1 for world in world_names
                  if (rows[world]['a1_done_max_hold_pm10'] or 0.) < DONE_LOW)
    fail_sweep = sum(1 for world in world_names
                     if all(raw < DONE_LOW for _, raw in rows[world]['a3_sweep_points']))
    passed = a1_ok >= 3 and a3_ok >= 3
    failed = fail_a1 >= 3 and fail_sweep >= 3
    verdict = 'PASS' if passed else ('FAIL' if failed else 'INCONCLUSIVE')
    return {
        'a1_worlds_done_ge_065': a1_ok,
        'a3_worlds_interval_inside_target': a3_ok,
        'verdict': verdict,
        'fingerprint_confirmed': passed,
        'D11_condition_i_met': passed,
        'fail_a1_worlds_below_005': fail_a1,
        'fail_sweep_worlds_all_below_005': fail_sweep,
        'next_action': ('PASS -> C2b v7 counterfactual (and C2c only if C2b done path passes)'
                        if passed else
                        ('FAIL -> D11 not established; cancel C2c; R3 uses clock-independent R3-B'
                         if failed else
                         'INCONCLUSIVE -> C2b proceeds; C2c only via C2b S2')),
    }


def analyze_c2a(args, launch, prereg, prereg_sha):
    out = Path(args.out)
    section = prereg['c2']['c2a']
    variants = launch['variants']
    tables = {variant: json.loads((out / variant / 'metrics.json').read_text())['worlds']
              for variant in variants}
    sweep_metrics = json.loads((out / 'sweep' / 'metrics.json').read_text())['worlds']
    world_names = [f"{world['group']}-{world['world']}" for world in section['worlds']]
    rows = {}
    for world in world_names:
        v0, v4 = tables['V0'][world], tables['V4'][world]
        points = [(item['pe'], item['raw_done_score'])
                  for item in sweep_metrics[world]['points']]
        interval = sweep_interval(points)
        half = sweep_half_max(points)
        inside = (interval is not None
                  and interval['pe_min'] >= SWEEP_TARGET[0] - 1e-9
                  and interval['pe_max'] <= SWEEP_TARGET[1] + 1e-9)
        reference = read_rows(out / 'V4' / f'world-{world}.jsonl')
        hold_end = v4['window']['hold_end_tick']
        achieved = next(float(row['pwm_elapsed_s']) for row in reference if row['index'] == hold_end)
        fire = v4['done_fire_tick']
        rows[world] = {
            'seed': v4['seed'],
            'hold_end_tick': hold_end,
            'achieved_hold_end_pe': achieved,
            'a1_done_max_hold_pm10': v4['done_max_hold_pm10'],
            'a1_ge_065': v4['done_ge_065'],
            'a2_first_fire_tick': fire,
            'a2_delta_vs_hold_end_ticks': None if fire is None else fire - hold_end,
            'a3_sweep_interval': interval,
            'a3_interval_inside_10_8_11_8': inside,
            'a3_half_max': half,
            'a3_sweep_points': points,
            'a4_v0_onset_tick': v0['onset_tick'],
            'a4_v4_onset_tick': v4['onset_tick'],
            'a4_same_as_v0': (v4['onset_tick'] is not None
                              and v4['onset_tick'] == v0['onset_tick']),
            'a4_v4_delta_vs_lookback_ticks': v4['delta_vs_lookback_ticks'],
        }
    decisions = c2a_decision(world_names, rows)
    summary = {
        'schema': 'ugrp.act18.c2a_doneclock.summary.v1',
        'experiment': '2026-10-17-act18', 'phase': 'C2a',
        'generated_utc': utc_now(),
        'labels': ['engineering-only', 'sim', 'gate 비대상', 'pooling 금지'],
        'source_sha': launch['source_sha'], 'source_dirty': launch['source_dirty'],
        'environment': launch['environment'],
        'prereg': {'path': str(args.prereg), 'sha256': prereg_sha},
        'checkpoint': launch['checkpoint'],
        'inputs': section['worlds'],
        'target_hold_end_pe': TARGET_HOLD_END_PE,
        'sweep_points': section['sweep_points'],
        'te': {'coefficient': TE_COEFF, 'chunk': c.CHUNK, 'done_threshold': DONE_THRESHOLD},
        'worlds': rows,
        'decisions': decisions,
        'determinism_e1': launch.get('determinism_e1'),
        'replay_wall_s': launch.get('wall_s'),
        'scope': 'teacher-state offline replay only; no rollout, no physical success claim',
    }
    write_json(out / 'summary.json', summary)
    print(json.dumps(decisions, indent=2, ensure_ascii=False))
    print(f'ANALYZE_COMPLETE out={out}')


def c2b_decision(per_variant, lift, control):
    """Preregistered C2b done-path verdict plus backward attribution."""
    s2_lift_fire = sum(1 for label in lift if per_variant['S2'][label]['fire_pe_in_10_3_12_0'])
    s3_lift_fire = sum(1 for label in lift if per_variant['S3'][label]['fire_pe_in_10_3_12_0'])
    s2_any_fire = sum(1 for label in lift if per_variant['S2'][label]['done_fire'])
    s3_any_fire = sum(1 for label in lift if per_variant['S3'][label]['done_fire'])
    pass_done = s2_lift_fire >= 4
    fail_done = s2_any_fire <= 1 and s3_any_fire <= 1
    verdict = 'PASS' if pass_done else ('FAIL' if fail_done else 'INCONCLUSIVE')
    onset_counts = {variant: sum(1 for label in lift if per_variant[variant][label]['backward_onset'])
                    for variant in ('S0', 'S2', 'S3', 'S4')}
    attribution = None
    for variant in ('S2', 'S3', 'S4'):
        if onset_counts[variant] >= 4:
            attribution = variant
            break
    false_positive = {variant: [label for label in control
                                if per_variant[variant][label]['done_fire']]
                      for variant in ('S0', 'S2', 'S3', 'S4')}
    return {
        'b1_S2_lift_fires_pe_in_range': s2_lift_fire,
        'b1_S2_lift_fires_any': s2_any_fire,
        'b1_S3_lift_fires_pe_in_range': s3_lift_fire,
        'b1_S3_lift_fires_any': s3_any_fire,
        'done_path_verdict': verdict,
        'D11_condition_ii_confirmed': pass_done,
        'b2_backward_onset_counts_lift': onset_counts,
        'b2_single_variant_attribution': attribution,
        'b3_false_positive_control_fires': false_positive,
        'next_action': ('PASS -> C2c ready (off-peak, requires 창민 v7 approval)'
                        if pass_done else
                        ('FAIL -> C2c cancelled; R3-B clock-independent' if fail_done else
                         'INCONCLUSIVE -> C2c only via C2b S2 review')),
    }


def analyze_c2b(args, launch, prereg, prereg_sha):
    out = Path(args.out)
    section = prereg['c2']['c2b']
    labels = [run['label'] for run in section['runs']]
    tables = {variant: json.loads((out / variant / 'metrics.json').read_text())['runs']
              for variant in ('S0', 'S2', 'S3', 'S4')}
    sweeps = json.loads((out / 'S1' / 'metrics.json').read_text())['runs']
    lift = [run['label'] for run in section['runs'] if run.get('lift_expected')]
    control = [run['label'] for run in section['runs'] if not run.get('lift_expected')]
    per_variant = {}
    for variant in ('S0', 'S2', 'S3', 'S4'):
        per_variant[variant] = {}
        for label in labels:
            item = tables[variant][label]
            pe = item['first_done_pe']
            in_range = (pe is not None
                        and C2B_DONE_PE_RANGE[0] - 1e-9 <= pe <= C2B_DONE_PE_RANGE[1] + 1e-9)
            per_variant[variant][label] = {
                'lift_expected': item['lift_expected'],
                'done_fire': item['done_fire'],
                'first_done_t': item['first_done_t'],
                'first_done_pe': pe,
                'fire_pe_in_10_3_12_0': bool(item['done_fire'] and in_range),
                'peak_done_score': item['peak_done_score'],
                'post_anchor_max_pe': item['post_anchor_max_pe'],
                'backward_onset': item['backward_onset'],
                'backward_onset_t': item['backward_onset_t'],
            }
    decisions = c2b_decision(per_variant, lift, control)
    summary = {
        'schema': 'ugrp.act18.c2b_doneclock.summary.v1',
        'experiment': '2026-10-17-act18', 'phase': 'C2b',
        'generated_utc': utc_now(),
        'labels': ['engineering-only', 'sim', 'gate 비대상', 'pooling 금지'],
        'source_sha': launch['source_sha'], 'source_dirty': launch['source_dirty'],
        'environment': launch['environment'],
        'prereg': {'path': str(args.prereg), 'sha256': prereg_sha},
        'checkpoint': launch['checkpoint'],
        'rollout_root': launch.get('rollout_root'),
        'teacher_root': launch.get('teacher_root'),
        'window': launch.get('window'),
        'runs': section['runs'],
        'te': {'coefficient': TE_COEFF, 'chunk': c.CHUNK, 'done_threshold': DONE_THRESHOLD},
        'sweep_S1': sweeps,
        'variants': per_variant,
        'decisions': decisions,
        'replay_wall_s': launch.get('wall_s'),
        'scope': ('student-rollout offline replay only; S4 is a diagnostic teacher-posture '
                  'counterfactual, not a deployable input; no rollout'),
    }
    write_json(out / 'summary.json', summary)
    print(json.dumps(decisions, indent=2, ensure_ascii=False))
    print(f'ANALYZE_COMPLETE out={out}')


def analyze(args):
    out = Path(args.out)
    launch = json.loads((out / 'launch.json').read_text())
    prereg = json.loads(args.prereg.read_text())
    prereg_sha = sha256(args.prereg)
    experiment = launch.get('experiment', 'E1')
    if experiment == 'C2a':
        return analyze_c2a(args, launch, prereg, prereg_sha)
    if experiment == 'C2b':
        return analyze_c2b(args, launch, prereg, prereg_sha)
    return analyze_e1(args, launch, prereg, prereg_sha)


def analyze_e1(args, launch, prereg, prereg_sha):
    out = Path(args.out)
    variants = launch['variants']
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
    parser = argparse.ArgumentParser(description='E1/C2 teacher-state TE replay (default OFF)')
    parser.add_argument('--enabled', action='store_true',
                        help='required safety gate; the script is inert without it')
    parser.add_argument('--experiment', choices=['E1', 'C2a', 'C2b'], default='E1')
    parser.add_argument('--variant', nargs='+', choices=[*VARIANTS, 'all'], default=['all'])
    parser.add_argument('--source', choices=['teacher-pilot', 'student-rollout'],
                        default='teacher-pilot',
                        help='C2b requires student-rollout (recorded actor inputs)')
    parser.add_argument('--rollout-root', type=Path,
                        help='C2b recovered finish-r3/repro tree root')
    parser.add_argument('--teacher-root', type=Path, default=PILOT_ROOT,
                        help='C2b S4 teacher alignment source (same seed pilot world)')
    parser.add_argument('--pe-sweep', default='off',
                        help='C2a/C2b S1 comma-separated pe sweep points, default off')
    parser.add_argument('--determinism-e1', type=Path,
                        help='C2a: E1 run root for the V0 per-tick determinism check')
    parser.add_argument('--checkpoint', type=Path,
                        help='R8 checkpoint directory (model.safetensors/config/adapter/SHA256)')
    parser.add_argument('--out', type=Path, required=False,
                        help='new run root; per-variant subdirs and summary.json')
    parser.add_argument('--prereg', type=Path,
                        help='prereg JSON (default: E1 for --experiment E1, C2 otherwise)')
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
    if args.prereg is None:
        args.prereg = PREREG_PATH if args.experiment == 'E1' else C2_PREREG_PATH
    if args.torch_threads != 2:
        raise ValueError('E1/C2 CPU budget is exactly 2 torch threads')
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
        if args.experiment == 'C2b' and args.variant != ['all']:
            raise ValueError('C2b variants are fixed to S0-S4')
    return args


def main(argv=None):
    args = parse(argv)
    if args.analyze:
        analyze(args)
    else:
        run_replay(args)


if __name__ == '__main__':
    main()
