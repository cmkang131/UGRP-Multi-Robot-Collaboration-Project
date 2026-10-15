"""CPU gcp2-only saved-trace reward audit. No physics, training or new success.

The selected ACT15 failures have full evaluation/command traces; the teacher
success has different fields and includes release. Do not fabricate missing
image-instance masks or teacher alignment/done labels to compare total return.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.rl_act_reward import Heuristics, StableLift, TrainingTruth, reward_transition
from scripts.simalt_host import gcp2_identity


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(root, name, sources):
    path = root / name
    if not path.exists():
        path = root / (name + '.zst')
    packed = path.read_bytes()
    data = (subprocess.check_output(['zstd', '-dc', str(path)])
            if path.suffix == '.zst' else packed)
    sources.append(dict(path=str(path), bytes=len(packed), sha256=digest(packed),
                        decoded_sha256=digest(data)))
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def write_trace(path, rows):
    # Permanent text ledger; compress large JSONL losslessly and verify decode.
    data = ''.join(json.dumps(row, allow_nan=False)+'\n' for row in rows).encode()
    if len(data) > 65536:
        path = path.with_suffix(path.suffix + '.zst')
        packed = subprocess.check_output(['zstd', '-q', '-c'], input=data)
        path.write_bytes(packed)
        if subprocess.check_output(['zstd', '-dc', str(path)]) != data:
            raise RuntimeError('reward ledger compression mismatch')
    else:
        path.write_bytes(data)
        packed = data
    return dict(path=str(path), bytes=len(packed), sha256=digest(packed), decoded_sha256=digest(data))


def failure(seed, out, sources):
    root = Path(f'/home/ugrp/ugrp-sim/runs/act16a-gcp2-{seed}-b4db8ba2/raw')
    evaluations = read(root, 'eval-only.jsonl', sources)
    commands = read(root, 'commands.jsonl', sources)
    if len(evaluations) != len(commands):
        raise ValueError('unaligned evaluation/issued rows')
    score, states = StableLift(), []
    for ev, command in zip(evaluations, commands):
        if abs(ev['t']-command['command']['t']) > 1e-5:
            raise ValueError('saved clock mismatch')
        score.add(ev['t'], **{k: ev[k] for k in ('clearance', 'tilt', 'forces', 'weld')})
        states.append(TrainingTruth(ev['station_error_m'], ev['yaw_error_rad'], None, score.success))
    ledger, latched = [], False
    # Audit scale only: initial distance, NOT a fitted training distance p95.
    scale = states[0].distance_m
    for i, (before, after) in enumerate(zip(states, states[1:])):
        first_done = commands[i]['done_requested'] and not latched
        latched |= commands[i]['done_requested']
        reward = reward_transition(before, after, distance_p95=scale,
            first_done=first_done, terminal=i == len(states)-2,
            heuristics=Heuristics(h2_false_done_v1=True, h3_alignment_v1=True))
        # None is unknown, not a made-up screen-loss measurement.
        reward['counterfactual_terms']['h1_center_v1'] = None
        ledger.append(dict(t=commands[i]['command']['t'], first_done=first_done,
                           stable_lift_before=before.stable_lift, **reward))
    return dict(seed=seed, backend='c_mujoco', saved_only=True, new_rl_rollouts=0,
        steps=len(ledger), stable_lift=score.success, h1_actual='unmeasured: no instance masks',
        h1_undiscounted_bounds=[-len(ledger)/900., len(ledger)/900.],
        h2_first_done_events=[r['t'] for r in ledger if r['first_done']],
        h2_sum=sum(r['heuristic_terms']['h2_false_done_v1'] for r in ledger),
        h3_sum=sum(r['heuristic_terms']['h3_alignment_v1'] for r in ledger),
        h3_discounted_sum=sum(.995**i*r['heuristic_terms']['h3_alignment_v1'] for i,r in enumerate(ledger)),
        success_bonus=sum(r['success_reward'] for r in ledger),
        distance_scale_basis='saved audit initial distance, not pilot normalization',
        artifact=write_trace(out/f'failure-{seed}.jsonl', ledger))


def teacher(out, sources):
    root = Path('/home/ugrp/ugrp-sim/runs/act16a-teacher-91434-b4db8ba2/raw')
    evaluations = read(root, 'eval-only.jsonl', sources)
    score, first_success_t, annotations = StableLift(), None, 0
    for ev in evaluations:
        if 'min_z' not in ev:
            if ev.get('kind') != 'lookaround_view':
                raise ValueError('unknown teacher evaluation row schema')
            annotations += 1
            continue
        old = score.success
        score.add(ev['t'], ev['min_z']-ev['support_z'], ev['tilt_deg'],
                  ev['finger_forces'], ev['weld_active'])
        if score.success and not old:
            first_success_t = ev['t']
    return dict(seed=91434, role='teacher', backend='c_mujoco', saved_only=True,
        includes_release=True, stable_lift=score.success, first_success_t=first_success_t,
        success_bonus=10. if score.success else 0.,
        max_stable_s=score.max_stable_s, skipped_lookaround_annotations=annotations,
        h1_actual='unmeasured: no target-instance masks',
        h1_undiscounted_bounds=[-(len(evaluations)-annotations)/900., (len(evaluations)-annotations)/900.],
        h2='not applicable: teacher has no student done token',
        h3='unmeasured: exact station/yaw trace unavailable in this ledger',
        total_return_comparison='not computable without missing annotations; no imputation')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    host = gcp2_identity()
    if host['instance'] != 'ugrp-sim-gcp2':
        p.error('saved analysis on CPU gcp2 only')
    a.output.mkdir(parents=True, exist_ok=False)
    lease = Path('/home/ugrp/ugrp-sim/leases/rl1b.json')
    token = dict(task='rl1b', pid=os.getpid(), started_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        expected_end_utc=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=10)).isoformat(),
        purpose='saved reward audit only; no GPU/physics/training', reserved_output_bytes=10*1024**2)
    with lease.open('x') as f:
        json.dump(token, f)
    sources = []
    try:
        failures = [failure(seed, a.output, sources) for seed in (91427, 91439)]
        success = teacher(a.output, sources)
        report = dict(schema='ugrp.rl1b.saved-reward-audit.v1', host=host,
            source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            failures=failures, teacher_success=success, sources=sources,
            physics_runs=0, training_runs=0, gpu_seconds=0,
            interpretation='reward plumbing audit only; no new-start or policy improvement evidence',
            missing=['h1 target-instance masks', 'teacher exact alignment trace',
                     'teacher ACT done label', 'independent heuristic policy ablations'])
        (a.output/'saved-reward-audit.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps({k: v for k,v in report.items() if k != 'sources'}), flush=True)
    except BaseException as error:
        (a.output/'analysis-error.json').write_text(json.dumps(dict(status='ANALYSIS_ERROR',
            error_type=type(error).__name__, error=str(error), sources=sources,
            physics_runs=0, training_runs=0, gpu_seconds=0), indent=2)+'\n')
        raise
    finally:
        if lease.exists() and json.loads(lease.read_text()) == token:
            lease.unlink()


if __name__ == '__main__':
    main()
