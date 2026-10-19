"""R3 offline gate g1-g5 (default OFF, CPU only, no simulator).

The spec (act-C2-R3-spec.md section 4) forbids GPU evaluation unless every gate
passes. This tool prepares and runs the CPU gates on Oracle:

  pilot  g1/g2/g3: teacher-state temporal-ensemble replay of the 4 pilot worlds
                   (same TE coefficient, .65 threshold and window definitions
                   as E1; no simulator, no teacher command execution)
  c2b    g4:       C2b S2(v7) student stop-state done firing (reads the C2b
                   owner's adapter summary; never re-infers on Oracle)
  e0     g5:       E0 open-loop TRAIN4 teacher terminal rows (either evaluates
                   an existing frames.jsonl.gz or runs CPU positive-row
                   inference from the full dataset + checkpoint)
  report:          combines the three receipts; PASS = g1..g5 all true

R8 is the validation checkpoint for this tool: with R8, g1 must fail (done head
is the known C2 defect), g2/g3 must pass, and the E0 frames evaluator must read
4/4. The R3 checkpoint is normally absent at prep time.
"""
from __future__ import annotations

import argparse
import gzip
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from harness import grasp_act_contract as c

TE_COEFF = .01
DONE_THRESHOLD = .65
ONSET_TOLERANCE = 5
WINDOW_TAIL_S = 1.0
TRAIN4_SEEDS = (88600, 88601, 88602, 88603)
EXPECTED_R8_SHA = 'e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a'
DEFAULT_PILOT_ROOT = Path('/home/ubuntu/UGRP/outputs/reports/act-chunk8-pilot/act-chunk8-pilot')
DEFAULT_EVIDENCE_TAR = Path('/home/ubuntu/UGRP/outputs/reports/act-chunk8-pilot/act-chunk8-pilot-evidence.tar.gz')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def read_json(path):
    return json.loads(Path(path).read_text())


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def require_enabled(args):
    if not args.enabled:
        raise SystemExit('R3 offline gate is default OFF; pass --enabled')


class TemporalEnsemble:
    """Numpy copy of the frozen evaluation-time ensemble (coeff .01)."""

    def __init__(self, coeff=TE_COEFF):
        if not math.isfinite(coeff) or coeff < 0:
            raise ValueError('nonnegative finite ensemble coefficient required')
        self.coeff = coeff
        self.chunks = []

    def step(self, chunk):
        values = np.asarray(chunk, dtype=float)
        if values.shape != (c.CHUNK, c.ACTION_DIM) or not np.isfinite(values).all():
            raise ValueError('invalid 8x14 chunk')
        self.chunks.append(values)
        weights = np.exp(-self.coeff * np.arange(len(self.chunks)))
        averaged = np.average([item[0] for item in self.chunks], axis=0, weights=weights)
        action = c.decode_action(averaged)
        self.chunks = [item[1:] for item in self.chunks if len(item) > 1]
        return action


def window_bounds(teacher_rows):
    phases = [row['teacher_phase'] for row in teacher_rows]
    times = [row['t'] for row in teacher_rows]
    close = phases.index('close')
    lookback = phases.index('lookback')
    lookback_return = phases.index('lookback_return')
    tail = times[lookback_return] + WINDOW_TAIL_S
    after = [i for i, t in enumerate(times) if t <= tail + 1e-9]
    if not after or after[-1] < lookback_return:
        raise ValueError('window tail truncated')
    hold = [i for i, phase in enumerate(phases) if phase == 'hold']
    verify = [i for i, phase in enumerate(phases) if phase == 'verify_lift']
    if not hold or not verify:
        raise ValueError('hold/verify_lift phases required')
    return {'close_tick': close, 'end_tick': after[-1], 'lookback_tick': lookback,
            'lookback_return_tick': lookback_return, 'hold_end_tick': hold[-1],
            'verify_lift_tick': verify[0], 'ticks': after[-1] - close + 1}


def aligned_world(world_dir):
    world_dir = Path(world_dir)
    student = read_rows(world_dir / 'student-r1.jsonl')
    teacher = read_rows(world_dir / 'teacher-r1.jsonl')
    if not student or len(student) != len(teacher):
        raise ValueError('%s: student/teacher row count mismatch' % world_dir)
    for index, (obs, label) in enumerate(zip(student, teacher)):
        if obs['sample_id'] != label['sample_id'] or abs(obs['t'] - label['t']) > 1e-6:
            raise ValueError('%s: student/teacher misaligned at row %d' % (world_dir, index))
    return student, teacher


def load_world_images(world_dir, student):
    world_dir = Path(world_dir)
    refs = {}
    for row in student:
        for ref in row['rgb']:
            refs[ref['path']] = ref['sha256']
    images = {}
    for rel, digest in sorted(refs.items()):
        path = (world_dir / rel).resolve()
        if not path.is_relative_to(world_dir.resolve()) or not path.is_file():
            raise ValueError('missing in-episode JPEG: %s' % rel)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('JPEG hash mismatch: %s' % rel)
        images[rel] = data
    manifest = hashlib.sha256('\n'.join('%s %s' % (path, refs[path]) for path in sorted(refs)).encode())
    return images, {'files': len(refs), 'sha256': manifest.hexdigest()}


def chunk_prediction(actor, observation, images):
    jpegs = [images[ref['path']] for ref in observation['rgb']]
    values = np.asarray(actor.predict(observation, jpegs), dtype=float)
    if values.shape != (c.CHUNK, c.ACTION_DIM) or not np.isfinite(values).all():
        raise ValueError('Actor.predict did not return finite 8x14')
    return values


def checkpoint_identity(root):
    root = Path(root)
    hashes = read_json(root / 'SHA256.json')
    if set(hashes) != {'model.safetensors', 'config.json', 'adapter.json'}:
        raise ValueError('checkpoint inventory mismatch')
    if any(sha256(root / name) != digest for name, digest in hashes.items()):
        raise ValueError('checkpoint artifact hash mismatch')
    adapter = read_json(root / 'adapter.json')
    provenance = adapter.get('provenance') or {}
    probe = provenance.get('probe') or {}
    if (adapter.get('schema') != 'ugrp.act18.adapter.v1' or adapter.get('chunk') != 8
            or adapter.get('done_mode') != 'balanced_bce_v1'
            or adapter.get('image_mode') != 'current_full_v1'):
        raise ValueError('chunk8 balanced-BCE act18 adapter required')
    if provenance.get('candidate') == 'R8' and provenance.get('step') == 100000:
        kind = 'R8-reference-validation'
    elif (provenance.get('candidate') == 'act18-r3dw'
          and probe.get('kind') == 'done_window_finetune_v1'
          and probe.get('packaging_eligible') is False and provenance.get('training_complete') is True
          and type(provenance.get('step')) is int and 1 <= provenance['step'] <= 20000):
        kind = 'R3-done-window-probe'
    else:
        raise ValueError('only R8 or the registered R3 done-window probe may use this gate')
    return dict(dir=str(root), model_sha256=hashes['model.safetensors'],
                adapter_sha256=hashes['adapter.json'], candidate=provenance.get('candidate'),
                step=provenance.get('step'), kind=kind,
                probe_kind=probe.get('kind'), packaging_eligible=False)


def load_actor(root):
    from act18_policy import Actor
    identity = checkpoint_identity(root)
    return Actor.load(root, device='cpu'), identity


def pilot_metrics(rows, bounds, lookback_tick):
    onset = next((row['index'] for row in rows if row['onset']), None)
    delta = None if onset is None else onset - lookback_tick
    band = [row for row in rows if bounds['hold_end_tick'] - 10 <= row['index'] <= bounds['hold_end_tick'] + 10]
    before = [row for row in rows if row['index'] < bounds['verify_lift_tick']]
    return dict(
        ticks=len(rows), onset_tick=onset, delta_vs_lookback_ticks=delta,
        done_max_hold_pm10=max((row['te']['done_score'] for row in band), default=None),
        done_max_before_verify=max((row['te']['done_score'] for row in before), default=None),
        done_fire_before_verify=any(row['te']['done_score'] >= DONE_THRESHOLD for row in before),
        done_fire_hold_pm10=next((row['index'] for row in band
                                  if row['te']['done_score'] >= DONE_THRESHOLD), None))


def run_pilot(args):
    prereg = read_json(args.prereg)
    gate = prereg['offline_gate']
    pilot = gate['pilot_inputs']
    pilot_root = Path(args.pilot_root or pilot['pilot_root'])
    evidence = Path(args.evidence_tar or DEFAULT_EVIDENCE_TAR)
    if sha256(evidence) != pilot['evidence_tar_sha256']:
        raise ValueError('pilot evidence tar sha mismatch')
    out = Path(args.out)
    if out.exists():
        raise ValueError('gate output root already exists: %s' % out)
    out.mkdir(parents=True)
    actor, identity = load_actor(args.checkpoint)
    worlds = []
    for world in pilot['worlds']:
        world_dir = pilot_root / world['group'] / world['world']
        student_path = world_dir / 'student-r1.jsonl'
        teacher_path = world_dir / 'teacher-r1.jsonl'
        if sha256(student_path) != world['student_r1_sha256'] or sha256(teacher_path) != world['teacher_r1_sha256']:
            raise ValueError('pilot input hash mismatch: %s/%s' % (world['group'], world['world']))
        student, teacher = aligned_world(world_dir)
        bounds = window_bounds(teacher)
        images, rgb = load_world_images(world_dir, student)
        ensemble = TemporalEnsemble()
        rows = []
        started = time.monotonic()
        for index in range(bounds['close_tick'], bounds['end_tick'] + 1):
            observation = student[index]
            chunk = chunk_prediction(actor, observation, images)
            action = ensemble.step(chunk)
            rows.append(dict(index=index, t=observation['t'], teacher_phase=teacher[index]['teacher_phase'],
                             te=action, onset=bool(all(wheel < 0 for wheel in action['wheels']))))
        metrics = pilot_metrics(rows, bounds, bounds['lookback_tick'])
        metrics.update(seed=world['seed'], window=bounds, rgb=rgb,
                       student_r1_sha256=world['student_r1_sha256'],
                       teacher_r1_sha256=world['teacher_r1_sha256'],
                       wall_s=round(time.monotonic() - started, 1))
        worlds.append(dict(group=world['group'], world=world['world'], **metrics))
        with (out / ('rows-%s-%s.jsonl' % (world['group'], world['world']))).open('x') as stream:
            for row in rows:
                stream.write(json.dumps(dict(index=row['index'], t=row['t'],
                                             teacher_phase=row['teacher_phase'],
                                             done_score=round(row['te']['done_score'], 6),
                                             done=row['te']['done'], wheels=row['te']['wheels'],
                                             onset=row['onset'])) + '\n')
        del images
    g1 = sum(1 for world in worlds if (world['done_max_hold_pm10'] or 0.) >= DONE_THRESHOLD) >= 3
    g2 = not any(world['done_fire_before_verify'] for world in worlds)
    g3 = sum(1 for world in worlds
             if world['delta_vs_lookback_ticks'] is not None
             and abs(world['delta_vs_lookback_ticks']) <= ONSET_TOLERANCE) >= 3
    report = dict(schema='ugrp.act18.r3_offline_gate.pilot.v1', generated_utc=utc_now(),
                  checkpoint=identity, prereg=dict(path=str(args.prereg), sha256=sha256(args.prereg)),
                  pilot_root=str(pilot_root), evidence=dict(path=str(evidence), sha256=sha256(evidence)),
                  worlds=worlds, gates=dict(g1=g1, g2=g2, g3=g3),
                  definitions=dict(g1='max TE done in hold end +/-10 >= .65 in >=3/4',
                                   g2='no TE done >= .65 before verify_lift start (0/4)',
                                   g3='|onset - lookback start| <= 5 ticks in >=3/4'),
                  reproduce=sys.argv)
    write_json(out / 'pilot.json', report)
    print(json.dumps(dict(gates=report['gates'], checkpoint=identity['kind']), indent=2))


def run_c2b(args):
    value = read_json(args.c2b_summary)
    if value.get('schema') != 'ugrp.act18.r3_c2b_gate_input.v1':
        raise ValueError('C2b adapter schema required')
    if not isinstance(value.get('source_sha'), str) or len(value['source_sha']) < 7:
        raise ValueError('C2b source sha required')
    if args.checkpoint and value.get('checkpoint_sha256') != args.checkpoint:
        raise ValueError('C2b checkpoint sha does not match the R3 checkpoint')
    worlds = value.get('worlds') or []
    lift = [row for row in worlds if row.get('role') == 'lift']
    control = [row for row in worlds if row.get('role') == 'control']
    if len(lift) != 6 or len(control) != 2:
        raise ValueError('C2b gate expects exactly 6 lift and 2 control worlds')
    if any(type(row.get('done_fired')) is not bool for row in worlds):
        raise ValueError('done_fired must be boolean')
    g4 = sum(row['done_fired'] for row in lift) >= 4 and sum(row['done_fired'] for row in control) <= 1
    report = dict(schema='ugrp.act18.r3_offline_gate.c2b.v1', generated_utc=utc_now(),
                  c2b_summary=dict(path=str(args.c2b_summary), sha256=sha256(args.c2b_summary)),
                  source_sha=value['source_sha'], checkpoint_sha256=value.get('checkpoint_sha256'),
                  lift_fired=sum(row['done_fired'] for row in lift), lift_N=len(lift),
                  control_fired=sum(row['done_fired'] for row in control), control_N=len(control),
                  worlds=worlds, gates=dict(g4=g4),
                  definition='lift fired >=4/6 and control fired <=1/2', reproduce=sys.argv)
    out = Path(args.out)
    if out.exists():
        raise ValueError('gate output root already exists: %s' % out)
    out.mkdir(parents=True)
    write_json(out / 'c2b.json', report)
    print(json.dumps(report['gates'], indent=2))


def e0_from_frames(path):
    rows = []
    with gzip.open(path, 'rt') as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    grouped = {}
    for row in rows:
        grouped.setdefault(int(row['seed']), []).append(row)
    missing = [seed for seed in TRAIN4_SEEDS if seed not in grouped]
    if missing:
        raise ValueError('TRAIN4 seeds missing from open-loop frames: %s' % missing)
    episodes = []
    for seed in TRAIN4_SEEDS:
        grasp = [row for row in grouped[seed] if row['skill'] == 'grasp']
        positives = [row for row in grasp if float(row['teacher'][13]) >= .5]
        if len(positives) != 1:
            raise ValueError('seed %d has %d hold-end done positives (expected 1)' % (seed, len(positives)))
        positive = positives[0]
        probability = float(positive['prediction'][13])
        episodes.append(dict(seed=seed, t=positive['t'],
                             teacher_phase=positive.get('teacher_phase'),
                             done_probability=round(probability, 6),
                             done_ge_065=probability >= DONE_THRESHOLD,
                             rows=len(grouped[seed]), grasp_rows=len(grasp)))
    return dict(mode='existing-frames', rows=len(rows), episodes=episodes)


def e0_from_inference(dataset, checkpoint):
    from act18_policy import ReferenceDataset
    dataset = Path(dataset)
    data = ReferenceDataset(dataset, 'train', chunk=8)
    positives = []
    for seed in TRAIN4_SEEDS:
        indices = [index for index, row in enumerate(data.metadata)
                   if row['seed'] == seed and row['skill'] == 'grasp'
                   and float(data.shards[data.index[index][0]]['action'][data.index[index][1], 0, -1]) == 1.]
        if len(indices) != 1:
            raise ValueError('seed %d has %d grasp completion rows (expected 1)' % (seed, len(indices)))
        positives.append((seed, indices[0]))
    import torch
    torch.set_num_threads(2)
    actor, identity = load_actor(checkpoint)
    episodes = []
    for seed, index in positives:
        meta = data.metadata[index]
        item = data[index]
        batch = {key: torch.from_numpy(np.asarray(value)).unsqueeze(0) for key, value in item.items()
                 if key.startswith('observation.')}
        with torch.inference_mode():
            normalized = actor.policy.predict_action_chunk(batch)[0].cpu().numpy()
        decoded = actor.decode(normalized)
        probability = float(decoded[0, -1])
        episodes.append(dict(seed=seed, t=meta['t'], teacher_phase=meta.get('teacher_phase'),
                             done_probability=round(probability, 6),
                             done_ge_065=probability >= DONE_THRESHOLD,
                             sample_id=meta['sample_id']))
    return dict(mode='cpu-inference', checkpoint=identity, dataset=str(dataset),
                dataset_manifest_sha256=sha256(dataset / 'manifest.json')
                if (dataset / 'manifest.json').is_file() else sha256(dataset / 'manifest.json.zst'),
                episodes=episodes,
                rows=sum(ep.get('rows', 0) for ep in episodes))


def run_e0(args):
    if args.frames is not None:
        if args.dataset is not None or args.checkpoint is not None:
            raise ValueError('e0 takes either --frames or --dataset/--checkpoint')
        result = e0_from_frames(args.frames)
    else:
        if args.dataset is None or args.checkpoint is None:
            raise ValueError('e0 needs --dataset and --checkpoint for CPU inference')
        result = e0_from_inference(args.dataset, args.checkpoint)
    g5 = all(row['done_ge_065'] for row in result['episodes'])
    report = dict(schema='ugrp.act18.r3_offline_gate.e0.v1', generated_utc=utc_now(),
                  frames=dict(path=str(args.frames), sha256=sha256(args.frames)) if args.frames else None,
                  **result, gates=dict(g5=g5),
                  definition='TRAIN4 teacher terminal done probability >= .65 for 4/4',
                  reproduce=sys.argv)
    out = Path(args.out)
    if out.exists():
        raise ValueError('gate output root already exists: %s' % out)
    out.mkdir(parents=True)
    write_json(out / 'e0.json', report)
    print(json.dumps(report['gates'], indent=2))


def run_report(args):
    gate_dir = Path(args.gate_dir)
    paths = dict(pilot=gate_dir / 'pilot' / 'pilot.json',
                 c2b=gate_dir / 'c2b' / 'c2b.json',
                 e0=gate_dir / 'e0' / 'e0.json')
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError('missing gate receipts: %s' % missing)
    receipts = {name: read_json(path) for name, path in paths.items()}
    gates = dict(g1=bool(receipts['pilot']['gates']['g1']),
                 g2=bool(receipts['pilot']['gates']['g2']),
                 g3=bool(receipts['pilot']['gates']['g3']),
                 g4=bool(receipts['c2b']['gates']['g4']),
                 g5=bool(receipts['e0']['gates']['g5']))
    passed = all(gates.values())
    report = dict(schema='ugrp.act18.r3_offline_gate.summary.v1', generated_utc=utc_now(),
                  gates=gates, PASS=passed,
                  rule='PASS = g1 AND g2 AND g3 AND g4 AND g5; any failure closes R3 as FAIL and forbids GPU evaluation',
                  receipts={name: dict(path=str(path), sha256=sha256(path)) for name, path in paths.items()},
                  checkpoint=receipts['pilot']['checkpoint'],
                  reproduce=sys.argv)
    write_json(gate_dir / 'summary.json', report)
    print(json.dumps(dict(gates=gates, PASS=passed), indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('pilot', 'c2b', 'e0', 'report'))
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--prereg', type=Path,
                        default=ROOT / 'experiments/2026-10-17-act18/R3_DONEWINDOW_PREREG.json')
    parser.add_argument('--pilot-root', type=Path)
    parser.add_argument('--evidence-tar', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--c2b-summary', type=Path)
    parser.add_argument('--frames', type=Path)
    parser.add_argument('--dataset', type=Path)
    parser.add_argument('--gate-dir', type=Path)
    args = parser.parse_args(argv)
    require_enabled(args)
    if args.stage != 'report' and args.out is None:
        parser.error('--out is required')
    if args.stage == 'pilot' and args.checkpoint is None:
        parser.error('--checkpoint is required')
    if args.stage == 'pilot':
        run_pilot(args)
    elif args.stage == 'c2b':
        if args.c2b_summary is None:
            parser.error('--c2b-summary is required')
        run_c2b(args)
    elif args.stage == 'e0':
        run_e0(args)
    else:
        if args.gate_dir is None:
            parser.error('--gate-dir is required')
        run_report(args)


if __name__ == '__main__':
    main()
