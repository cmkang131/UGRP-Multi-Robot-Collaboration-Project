"""pairact-r1 dry-run: write a SYNTHETIC convert-input tree (pipeline plumbing only).

SYNTHETIC_DRYRUN: not collected data, not a judgement, not a teacher demonstration.
No simulator, teacher or physics runs here. The files follow exactly the input
format that ``harness.grasp_act_data.convert`` reads (RUNBOOK §1-8 layout):

    <out>/protocol.json
    <out>/SYNTHETIC_MANIFEST.json
    <out>/seed-<seed>/{SOURCE_SHA, EXIT, SYNTHETIC.json,
                       raw/{plan.json, result.json, student-camera.json,
                            student-r1.jsonl, teacher-r1.jsonl,
                            student-r2.jsonl, teacher-r2.jsonl, rgb/<robot>/<n>.jpg}}

Two seeds (one train, one validation) in an explicit synthetic range, two
robots (r1 teal / r2 blue on one long_beam), a teacher-phase sequence that
covers all eight pairact-r1 stages (approach, alignment, recover, ready,
execute, carry, place, complete), own 640x480 JPEGs (flat colour + seeded
noise), v6 contract issued commands (wheels in beamact3's {-.35, 0, .35}) and
v7 own clocks (``DeadbandIssuedClock(2)``). Output is byte-deterministic for a
given seed pair. ``SOURCE_SHA`` / ``teacher_sha`` carry a synthetic marker
string instead of a git SHA (convert only compares the strings).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import grasp_act_contract as c
from harness import pairact_r1 as p

LABEL = 'SYNTHETIC_DRYRUN — 수집 데이터 아님 · 판정 아님 · teacher 시연 아님'
MARK = {'label': LABEL, 'synthetic': True}
SCHEMA = 'ugrp.pairact_r1.dryrun.synthetic.v1'
SYNTH_SHA = 'SYNTHETIC-DRYRUN-not-a-teacher-sha'
TRAIN_SEED, VALIDATION_SEED = 9990001, 9990002
SEEDS_JSON = ROOT / 'experiments/2026-10-21-pairact-r1/seeds.json'
ROBOTS = (('r1', 'teal'), ('r2', 'blue'))
OBJECT_KIND = 'long_beam'
WHEEL = .35          # beamact3 WHEEL_VALUES = (-.35, 0., .35)
PULSE = .1           # pulse width for a moving wheel (contract: <= .15 s)
BASE_PWM = {'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500}

# (skill, destination, teacher_phase, rows, wheel sign pattern, pwm override)
# grasp skill phases come from the P3 recorder vocabulary, release-skill phases
# from the P2 carry teacher (``carry:<phase>``). All map through
# harness.pairact_r1.TEACHER_PHASE_TO_STAGE; nothing new is invented.
SCRIPT = (
    ('grasp', 'none', 'start', 3, (0, 0, 0, 0), {}),
    ('grasp', 'none', 'approach', 5, (1, 1, 1, 1), {}),
    ('grasp', 'none', 'align', 5, (1, -1, 1, -1), {'1': 1450}),
    ('grasp', 'none', 'relook', 3, (-1, -1, -1, -1), {'1': 1450}),
    ('grasp', 'none', 'align', 3, (-1, 1, -1, 1), {'1': 1400}),
    ('grasp', 'none', 'ready', 3, (0, 0, 0, 0), {'1': 1400, '3': 1300}),
    ('grasp', 'none', 'wait_go', 3, (0, 0, 0, 0), {'1': 1400, '3': 1300}),
    ('grasp', 'none', 'pick', 3, (0, 0, 0, 0), {'1': 1400, '3': 1200, '4': 1700}),
    ('grasp', 'none', 'close', 3, (0, 0, 0, 0), {'1': 1400, '3': 1200, '4': 1700, '6': 2000}),
    ('grasp', 'none', 'lift', 3, (0, 0, 0, 0), {'1': 1400, '3': 1400, '4': 1600, '6': 2000}),
    ('grasp', 'none', 'hold', 4, (0, 0, 0, 0), {'1': 1400, '3': 1400, '4': 1600, '6': 2000}),
    ('release', 'B', 'carry:carry_hold', 3, (0, 0, 0, 0), {'1': 1400, '3': 1400, '4': 1600, '6': 2000}),
    ('release', 'B', 'carry:to_west_staging', 4, (1, 1, 1, 1), {'1': 1400, '3': 1400, '4': 1600, '6': 2000}),
    ('release', 'B', 'carry:door_pass', 4, (1, 1, 1, 1), {'1': 1400, '3': 1400, '4': 1600, '6': 2000}),
    ('release', 'B', 'carry:to_zone', 4, (1, -1, 1, -1), {'1': 1400, '3': 1400, '4': 1600, '6': 2000}),
    ('release', 'B', 'carry:lower', 3, (0, 0, 0, 0), {'1': 1400, '3': 1200, '4': 1700, '6': 2000}),
    ('release', 'B', 'carry:open', 3, (0, 0, 0, 0), {'1': 1400, '3': 1200, '4': 1700, '6': 1500}),
    ('release', 'B', 'carry:retreat', 3, (-1, -1, -1, -1), {'1': 1400, '3': 1400, '4': 1600}),
    ('release', 'B', 'carry:done', 4, (0, 0, 0, 0), {'1': 1500}),
)
STAGE_COLOR = {'approach': (40, 90, 160), 'alignment': (60, 160, 90), 'recover': (160, 60, 60),
               'ready': (200, 200, 60), 'execute': (200, 120, 40), 'carry': (120, 60, 160),
               'place': (60, 160, 160), 'complete': (90, 90, 90)}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def write_json(path, value):
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n')


def seed_ranges(spec):
    """Every first/last range named in seeds.json: splits, extensions, pilot, known ranges."""
    out = [(f'splits.{k}', v) for k, v in spec.get('splits', {}).items()]
    out += [(k, v) for k, v in spec.items() if isinstance(v, dict) and {'first', 'last'} <= set(v)]
    out += [(f'known_ranges:{r.get("source", "?")}', r) for r in spec.get('known_ranges', [])]
    return out


def seed_overlap(seeds, spec):
    """List every seeds.json range that contains one of ``seeds`` (empty = no overlap)."""
    return [dict(seed=s, range=name, first=r['first'], last=r['last'])
            for s in seeds for name, r in seed_ranges(spec) if r['first'] <= s <= r['last']]


def phase_rows():
    rows = []
    for skill, dest, phase, n, signs, pwm in SCRIPT:
        p.stage_from_phase(phase)          # unmapped phase -> ValueError, never guessed
        rows += [(skill, dest, phase, signs, pwm)] * n
    return rows


def command_at(t, signs, pwm, jitter):
    wheels = [WHEEL * s if s else 0. for s in signs]
    duration = [PULSE if w else 0. for w in wheels]
    values = {k: int(min(2500, max(500, v + jitter.get(k, 0)))) for k, v in {**BASE_PWM, **pwm}.items()}
    return c.command({'t': t, 'wheels': wheels, 'duration_s': duration, 'pwm': values})


def jpeg(stage, rng):
    base = np.array(STAGE_COLOR[stage], np.int16)
    noise = rng.integers(-12, 13, size=(60, 80, 3), dtype=np.int16)
    small = np.clip(base + noise, 0, 255).astype(np.uint8)
    image = Image.fromarray(small).resize((640, 480), Image.Resampling.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=85, optimize=False, progressive=False)
    return buffer.getvalue()


def write_robot(raw, seed, robot_index, robot, role, episode_id):
    rng = np.random.default_rng([seed, robot_index])
    rows = phase_rows()
    initial = command_at(0., (0, 0, 0, 0), {}, {})
    issued = [initial] * c.HISTORY
    clock = p.DeadbandIssuedClock(2)
    refs, students, teachers = [], [], []
    for i, (skill, dest, phase, signs, pwm) in enumerate(rows):
        t = round(i * c.PERIOD_S, 3)
        stage = p.stage_from_phase(phase)
        data = jpeg(stage, rng)
        rel = f'rgb/{robot}/{i:06d}.jpg'
        (raw / rel).parent.mkdir(parents=True, exist_ok=True)
        (raw / rel).write_bytes(data)
        refs.append({'path': rel, 'sha256': sha256_bytes(data), 't': t, 'robot_id': robot})
        instruction = (skill, OBJECT_KIND, role, dest)
        clocks = clock.observe(instruction, t, issued[-1]['pwm'])
        sample_id = f'{episode_id}:{i}:{robot}'
        obs = {'schema': c.SCHEMA, 'robot_id': robot, 'sample_id': sample_id, 't': t, 'skill': skill,
               'object_kind': OBJECT_KIND, 'role': role, 'destination_zone': dest,
               'rgb': c.image_history(refs, t), 'issued': list(issued[-c.HISTORY:]), **clocks}
        c.validate_observation(obs)
        jitter = {k: int(v) for k, v in zip(BASE_PWM, rng.integers(-2, 3, size=len(BASE_PWM)))}
        target = command_at(t, signs, pwm, jitter)
        last_of_skill = i + 1 == len(rows) or rows[i + 1][0] != skill
        teachers.append({'sample_id': sample_id, 'skill': skill, 'object_kind': OBJECT_KIND,
                         'teacher_phase': phase, 'local_skill_sample': True, 'done': last_of_skill,
                         'terminal_reason': 'command_sequence_complete' if last_of_skill else None,
                         'clean_teacher_command': target, 'perturbation_interval': False, 'synthetic': True})
        students.append(obs)
        issued.append(target)
    write_text(raw / f'student-{robot}.jsonl', ''.join(canonical(r) + '\n' for r in students))
    write_text(raw / f'teacher-{robot}.jsonl', ''.join(canonical(r) + '\n' for r in teachers))
    return len(rows)


def protocol(train_seed, validation_seed):
    return {**MARK, 'schema': SCHEMA, 'train_seeds': [train_seed], 'validation_seeds': [validation_seed],
            'run_pattern': 'seed-{seed}', 'teacher_sha': SYNTH_SHA, 'done_label': 'teacher_v1',
            'run_class': 'dev',
            'admission': 'SYNTHETIC_DRYRUN plumbing only; no teacher admission, no physics, no judgement'}


def generate(out, *, train_seed=TRAIN_SEED, validation_seed=VALIDATION_SEED, seeds_json=SEEDS_JSON):
    out = Path(out)
    seeds = [train_seed, validation_seed]
    if len(set(seeds)) != 2:
        raise ValueError('distinct train/validation seeds required')
    overlap = seed_overlap(seeds, json.loads(Path(seeds_json).read_text())) if seeds_json else []
    if overlap:
        raise ValueError(f'synthetic seeds overlap registered ranges: {overlap}')
    out.mkdir(parents=True, exist_ok=False)
    camera = {**MARK, 'schema': c.SCHEMA, 'width': 640, 'height': 480, 'period_s': c.PERIOD_S, 'hz': 10.,
              'camera': 'robot_cam', 'sources': {'harness/grasp_act_contract.py': sha256_file(c.__file__)}}
    rows = {}
    for seed in seeds:
        run, episode_id = out / f'seed-{seed}', f'synthetic-dryrun-{seed}'
        raw = run / 'raw'
        raw.mkdir(parents=True)
        write_text(run / 'SOURCE_SHA', SYNTH_SHA + '\n')
        write_text(run / 'EXIT', '0\n')
        write_json(run / 'SYNTHETIC.json', {**MARK, 'seed': seed, 'note': 'SOURCE_SHA is a synthetic marker'})
        write_json(raw / 'plan.json', {**MARK, 'seed': seed, 'episode_id': episode_id, 'object_kind': OBJECT_KIND,
                                       'roles': dict(ROBOTS)})
        write_json(raw / 'student-camera.json', camera)
        for k, (robot, role) in enumerate(ROBOTS):
            rows[f'{seed}-{robot}'] = write_robot(raw, seed, k, robot, role, episode_id)
        write_json(raw / 'result.json', {**MARK, 'status': 'complete', 'source_sha': SYNTH_SHA, 'seed': seed,
            'physical_success': True, 'training_rgb': True, 'student_execution': False,
            'recording_mode': 'training',
            'note': 'physical_success/training_rgb are placeholders required by convert; no physics ran'})
    write_json(out / 'protocol.json', protocol(train_seed, validation_seed))
    files = {str(f.relative_to(out)): sha256_file(f) for f in sorted(out.rglob('*')) if f.is_file()}
    manifest = {**MARK, 'schema': SCHEMA, 'train_seeds': [train_seed], 'validation_seeds': [validation_seed],
                'robots': dict(ROBOTS), 'rows_per_robot': rows,
                'phases': [s[2] for s in SCRIPT], 'stages_covered': sorted({p.stage_from_phase(s[2]) for s in SCRIPT}),
                'seed_overlap_checked_against': str(seeds_json) if seeds_json else None, 'seed_overlap': overlap,
                'generator_sha256': sha256_file(__file__), 'files': files}
    write_json(out / 'SYNTHETIC_MANIFEST.json', manifest)
    return manifest


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument('--out', type=Path, required=True, help='new directory (must not exist)')
    a.add_argument('--train-seed', type=int, default=TRAIN_SEED)
    a.add_argument('--validation-seed', type=int, default=VALIDATION_SEED)
    a.add_argument('--seeds-json', type=Path, default=SEEDS_JSON)
    args = a.parse_args(argv)
    m = generate(args.out, train_seed=args.train_seed, validation_seed=args.validation_seed,
                 seeds_json=args.seeds_json)
    print(json.dumps({k: m[k] for k in ('label', 'synthetic', 'train_seeds', 'validation_seeds',
                                        'rows_per_robot', 'stages_covered', 'seed_overlap')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
