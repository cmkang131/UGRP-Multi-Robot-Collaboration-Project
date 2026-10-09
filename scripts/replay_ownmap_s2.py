"""Sealed fixed-frame/command S2 map-swap replay; evaluator data is never read."""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time

import cv2
import numpy as np

from harness import ownmap_s2 as adapter
from harness import zone_solo_cyan_contract_v106 as contract
from harness import zone_pair_highpose_frame_gate as gate
from harness.zone_pair_highpose_exact_speedups import install

PLAN = Path(__file__).resolve().parents[1]/'experiments/2026-10-09-ownmap-s2/registration.json'
FIELDS = ('t_est', 'x', 'y', 'yaw', 'std_xy_m', 'std_yaw_rad', 'last_fix_t')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()


def rows(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines()]


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n')


def inputs(pair):
    for p, digest in pair['hashes'].items():
        if sha(p) != digest:
            raise ValueError('REGISTERED_INPUT_CHANGED: '+p)
    own = Path(pair['map_raw'])
    last = None
    with (own/'online-maps.jsonl').open() as f:
        for line in f:
            last = json.loads(line)
    grid = read(own/'frontend-grid.json')
    if last is None or any(last['grid'][k] != grid[k] for k in ('frame', 'resolution_m', 'cells')):
        raise ValueError('FINAL_ONLINE_GRID_DIFFERS_FROM_FRONTEND')
    return adapter.convert(last['grid'], read(own/'remembered-goal.json'), option=adapter.OPTION)


def run(pair, option, output):
    dest = output/pair['id']/option
    dest.mkdir(parents=True, exist_ok=False)
    raw = Path(pair['raw']); static_own = inputs(pair)
    write(dest/'own-map.json', static_own)
    bundle = read(raw/'bundle.json'); old = read(raw/'student_record.json')
    frames = rows(raw/'robots/r3/frames.jsonl')
    if not frames:
        raise ValueError('NO_FRAMES')
    by_time = {}
    for cmd in old['commands']:
        by_time.setdefault(round(cmd['t'], 6), []).append(cmd)
    initial = by_time[round(frames[0]['sim_time'], 6)].pop(0)
    if initial['kind'] != 'initial_servo_command':
        raise ValueError('INITIAL_COMMAND_REQUIRED')
    if set(by_time)-{round(f['sim_time'], 6) for f in frames}:
        raise ValueError('COMMAND_WITHOUT_FRAME_TIME')
    reference = {round(p['t'], 6): p for p in old['poses']}
    _, undo = install('v98-exact-v6')
    runtime = None
    start = time.monotonic()
    try:
        static = contract.hp.resolve(contract.MAP_ID)[0] if option == 'off' else static_own
        runtime = adapter.build_runtime(bundle, static, contract.ROOT/contract.CALIBRATION,
                                        contract.CALIBRATION_SHA, option=option)
        runtime.initial_commands(initial['t'], {'r3': {int(k): v for k, v in initial['pulses'].items()}})
        maximum = 0.; mismatch = None; count = 1; pred_hash = hashlib.sha256(); ref_hash = hashlib.sha256()
        pf = runtime.pose.provider.loc._pf
        with (dest/'poses.jsonl').open('w') as f:
            for i, frame in enumerate(frames):
                now = frame['sim_time']; data = (raw/frame['path']).read_bytes()
                if hashlib.sha256(data).hexdigest() != frame['sha256']:
                    raise ValueError('RGB_CHANGED: '+frame['path'])
                rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), 1), cv2.COLOR_BGR2RGB)
                verdict, _ = gate.gate().assess({**frame, 'image': base64.b64encode(data).decode()}, 'r3', now, ob=False)
                report = runtime.pose.on_frame(now, rgb if verdict == gate.VALID else None)
                q = adapter.report_row(report, now)
                # The recorded drive schedule is fixed. Warnings are evaluated
                # later at its original times, without calling a controller.
                q['pose_uncertain'] = adapter.warned(q)
                q['particle_count'] = pf.n
                f.write(json.dumps(q, allow_nan=False)+'\n')
                a = {k: q[k] for k in FIELDS}; z = {k: reference[round(now, 6)][k] for k in FIELDS}
                pred_hash.update(json.dumps(a).encode()); ref_hash.update(json.dumps(z).encode())
                delta = max(abs(a[k]-z[k]) if a[k] is not None and z[k] is not None else
                            float(a[k] != z[k]) for k in FIELDS)
                maximum = max(maximum, delta)
                if delta > 1e-9 and mismatch is None:
                    mismatch = dict(t=now, maximum_field_delta=delta)
                for cmd in by_time.get(round(now, 6), []):
                    runtime.on_command('r3', now, {k: v for k, v in cmd.items() if k != 't'})
                    count += 1
                if i % 1000 == 0:
                    print(pair['id'], option, i, '/', len(frames), flush=True)
        write(dest/'measurements.json', runtime.landmark_audit)
        write(dest/'amcl.json', runtime.amcl_audit)
        result = dict(schema='ugrp.ownmaps2a.prediction.v1', pair_id=pair['id'], option=option,
            source_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            registration_sha256=sha(PLAN), raw=str(raw), map_raw=pair['map_raw'],
            status='complete', physics_runs=0, model_calls=0, gt_inputs=False, commands_fixed=True,
            frames=len(frames), commands=count, total_recorded_commands=len(old['commands']),
            frame_sha256_verified=len(frames), started_load_average=os.getloadavg(),
            wall_s=time.monotonic()-start, wall_scope='replay processing only, not speed comparison',
            python=platform.python_version(), numpy=np.__version__, opencv=cv2.__version__,
            recorded_pose_max_delta=maximum, recorded_pose_first_mismatch=mismatch,
            recorded_pose_sha256=ref_hash.hexdigest(), replay_pose_sha256=pred_hash.hexdigest(),
            baseline_identity=maximum <= 1e-9 if option == 'off' else None,
            input_hashes=pair['hashes'], outputs={p.name: sha(p) for p in dest.iterdir() if p.is_file()})
        if count != len(old['commands']):
            raise ValueError('COMMAND_COUNT_MISMATCH')
        write(dest/'prediction.json', result)
        print(pair['id'], option, 'SEALED', 'baseline_identity', result['baseline_identity'], flush=True)
        return result
    finally:
        if runtime is not None:
            runtime.close()
        undo()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pair')
    parser.add_argument('--option', choices=('off', adapter.OPTION))
    args = parser.parse_args()
    if not args.output.is_absolute() or args.output.exists():
        raise ValueError('NEW_ABSOLUTE_OUTPUT_REQUIRED')
    if os.getpriority(os.PRIO_PROCESS, 0) != 0:
        raise ValueError('NICE_ZERO_REQUIRED; do not renice')
    args.output.mkdir(parents=True)
    plan = read(PLAN); results = []
    for pair in plan['pairs']:
        if args.pair and pair['id'] != args.pair:
            continue
        for option in ([args.option] if args.option else ['off', adapter.OPTION]):
            try:
                results.append(run(pair, option, args.output))
            except Exception as exc:
                import traceback
                result = dict(pair_id=pair['id'], option=option, status='HOST_ERROR',
                              error=repr(exc), traceback=traceback.format_exc(), physics_runs=0)
                results.append(result)
                write(args.output/pair['id']/option/'error.json', result)
                print(result['traceback'], flush=True)
        write(args.output/'replay-index.json', results)
    if not results:
        raise ValueError('NO_REGISTERED_PAIRS_SELECTED')
    return int(any(r['status'] != 'complete' or r.get('baseline_identity') is False for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
