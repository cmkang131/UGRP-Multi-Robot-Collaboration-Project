"""Locked, finite ABBA replay of saved own commands; no controller or model calls.

Four unprofiled runs and one cProfile run, same seed/input/physics. Original
evaluation, camera, command logs and an every-step integration-state hash chain
are compared as raw bytes. This bounded prefix is not full-task acceptance.
"""
import argparse
import cProfile
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import shutil
import subprocess
import time
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def source_check(expected):
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert actual == expected, 'SOURCE_CHANGED'
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip(), 'DIRTY_SOURCE'


def run_one(output, source, mode, duration, profile=False):
    import mujoco
    import numpy as np
    from sim.own_map_closed_loop import PhysicsBackend
    from sim.v7_exact_speedups import install
    output.mkdir()
    bundle = json.loads((source/'bundle.json').read_text())
    commands = rows(source/'robots/r3/commands.jsonl')
    frames = rows(source/'robots/r3/frames.jsonl')
    start = frames[0]['sim_time']
    chosen = [f for f in frames if f['sim_time'] <= start+duration+1e-8]
    assert len(chosen) == round(duration*5)+1 and chosen[-1]['sim_time'] == round(start+duration, 9)
    schedule = {}
    for command in commands:
        if command['kind'] != 'initial_servo_command' and command['t'] <= start+duration+1e-8:
            schedule.setdefault(command['t'], []).append({k:v for k,v in command.items() if k != 't'})
    backend = None
    counts = Counter()
    forward_callers = Counter()
    forward_seconds = Counter()
    chain = hashlib.sha256()
    original_forward = mujoco.mj_forward
    import sys

    def forward(model, data):
        frame = sys._getframe(1)
        key = f'{Path(frame.f_code.co_filename).name}:{frame.f_code.co_firstlineno}:{frame.f_code.co_name}'
        before = time.perf_counter()
        try:
            return original_forward(model, data)
        finally:
            forward_callers[key] += 1
            forward_seconds[key] += time.perf_counter()-before

    # Includes the GL owner thread. No mj_forward call is skipped or changed.
    mujoco.mj_forward = forward
    load_start = os.getloadavg()
    construction_started = time.perf_counter()
    prof = cProfile.Profile() if profile else None
    try:
        backend = PhysicsBackend(bundle, output, seed=bundle['task']['seed'])
        receipt = install(backend, mode)
        backend.reset(5.)
        assert backend.now == start
        backend.set_deadline(round(start+duration, 9))
        construction_s = time.perf_counter()-construction_started
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(backend.world.model, spec))
        original_step = backend.world._physics_step_for

        def step(*a, **kw):
            result = original_step(*a, **kw)
            mujoco.mj_getState(backend.world.model, backend.world.data, state, spec)
            chain.update(state.tobytes())
            counts['steps'] += 1
            return result
        backend.world._physics_step_for = step
        forward_callers.clear()
        forward_seconds.clear()
        if prof:
            prof.enable()
        started = time.perf_counter()
        for i, frame in enumerate(chosen):
            t = frame['sim_time']
            backend.advance_to(t)
            if i == 0:
                for action in schedule.get(t, []):
                    backend.issue('r3', action)
            backend.capture()
            if i:
                for action in schedule.get(t, []):
                    backend.issue('r3', action)
            backend.eval_sample()
        wall_s = time.perf_counter()-started
        if prof:
            prof.disable()
        assert counts['steps'] == round(duration/backend.dt)
        mujoco.mj_getState(backend.world.model, backend.world.data, state, spec)
        write(output/'state-chain.json', dict(steps=counts['steps'], initial_sim_s=start, final_sim_s=backend.now,
            timestep_s=backend.dt,
            state_spec=int(spec), state_size=len(state), chain_sha256=chain.hexdigest(),
            final_sha256=hashlib.sha256(state.tobytes()).hexdigest()))
        # Evaluation result has no runtime/provenance fields; compare it in full.
        from sim.solo_cyan_v106 import evaluate
        write(output/'judgement.json', evaluate(backend.eval_rows, backend.scene.config['static_map'], bundle['task']['destination']))
        info = dict(mode=mode, profile=profile, sim_s=duration, wall_s=wall_s, wall_per_sim=wall_s/duration,
            construction_and_reset_s=construction_s, load_start=load_start, load_end=os.getloadavg(), nice=os.getpriority(os.PRIO_PROCESS,0),
            receipt=receipt, steps=counts['steps'], frames=len(chosen), forward_callers=dict(forward_callers),
            forward_seconds=dict(forward_seconds), scope='saved-command prefix; full physics/render/evaluation, no online controller')
        if hasattr(backend, '_v7_exact_speedups'):
            info['cache'] = backend._v7_exact_speedups.cache_info()
        if prof:
            prof.dump_stats(output.parent/'physics.prof')
            stats = pstats.Stats(prof)
            info['profile_total_s'] = stats.total_tt
            info['top10'] = [dict(function=f'{k[0]}:{k[1]}:{k[2]}', calls=v[1], self_s=v[2],
                cumulative_s=v[3], percent=100*v[2]/stats.total_tt)
                for k,v in sorted(stats.stats.items(), key=lambda item:item[1][2], reverse=True)[:10]]
        return info
    finally:
        if prof:
            prof.disable()
        if backend is not None:
            backend.close()
        mujoco.mj_forward = original_forward


def compare(a, b):
    def inventory(root):
        return {str(p.relative_to(root)): {'sha256':sha(p),'bytes':p.stat().st_size}
                for p in sorted(root.rglob('*')) if p.is_file()}
    left, right = inventory(a), inventory(b)
    required = {'scene.xml', 'judgement.json', 'state-chain.json', 'eval_only/trajectory.jsonl',
                'eval_only/contacts.jsonl', 'robots/r3/commands.jsonl', 'robots/r3/frames.jsonl'}
    assert required <= left.keys() and required <= right.keys(), 'MISSING_EVIDENCE'
    for root in (a, b):
        state = json.loads((root/'state-chain.json').read_text())
        frames = rows(root/'robots/r3/frames.jsonl')
        duration = state['final_sim_s']-state['initial_sim_s']
        assert duration > 0 and state['steps'] == round(duration/state['timestep_s']) > 0
        assert len(frames) == round(duration*5)+1
        assert frames[0]['sim_time'] == state['initial_sim_s'] and frames[-1]['sim_time'] == state['final_sim_s']
        assert all(sha(root/f['path']) == f['sha256'] for f in frames), 'FRAME_HASH_MISMATCH'
        assert len(rows(root/'eval_only/trajectory.jsonl')) == len(frames)
        assert len(rows(root/'eval_only/contacts.jsonl')) == len(frames)
    delta = sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k))
    return dict(a=a.name,b=b.name,files=len(left),bytes_identical=not delta,differences=delta,inventory=left)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('--sim-seconds', type=float, default=4.)
    parser.add_argument('--wait-seconds', type=float, default=0.)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    assert 0 < args.sim_seconds <= 12 and abs(args.sim_seconds*5-round(args.sim_seconds*5)) < 1e-9
    source_check(args.expected_source_sha)
    assert not args.output.exists()
    assert args.output.resolve().is_relative_to(Path('/Users/changmin/projects/ugrp/outputs'))
    assert shutil.disk_usage(args.output.parent).free >= 10*1024**3
    if not args.execute:
        print('preflight only; no physics')
        return
    from scripts.agent_lock import DEFAULT_ROOT, status, acquire, release
    until = time.monotonic()+args.wait_seconds
    while True:
        if status(DEFAULT_ROOT) is None:
            try:
                lock = acquire(DEFAULT_ROOT,owner='codex',branch='codex/sim-speed-egomap53',
                    purpose='simspeed bounded ABBA (research first)',pid=os.getpid(),expected_minutes=5,timing_sensitive=True)
                break
            except RuntimeError:
                pass
        if time.monotonic() >= until:
            raise RuntimeError('TIMING_LOCK_OCCUPIED; no simulation started')
        print('Waiting for research lock', flush=True)
        time.sleep(min(15, max(0,until-time.monotonic())))
    try:
        source_check(args.expected_source_sha)
        assert os.getpriority(os.PRIO_PROCESS,0) == 0
        args.output.mkdir()
        write(args.output/'lock.json',lock)
        receipts = {n:sha(args.source/n) for n in ('bundle.json','robots/r3/commands.jsonl','robots/r3/frames.jsonl')}
        measurements = []
        for name, mode, profile in [('profile','off',True),('A1','off',False),('B1','relay-cache-buffered-v1',False),
                                   ('B2','relay-cache-buffered-v1',False),('A2','off',False)]:
            print('Starting', name, mode, flush=True)
            info = run_one(args.output/name,args.source,mode,args.sim_seconds,profile)
            info['name'] = name
            measurements.append(info)
            write(args.output/'measurements.json',measurements)
            print(json.dumps(info),flush=True)
        comparisons = [compare(args.output/'A1',args.output/n) for n in ('A2','B1','B2')]
        unchanged = all(sha(args.source/n)==h for n,h in receipts.items())
        write(args.output/'comparison.json',dict(source_sha=args.expected_source_sha,input=str(args.source),
            input_hashes=receipts,input_unchanged=unchanged,python=platform.python_version(),platform=platform.platform(),
            comparisons=comparisons,all_bytes_identical=all(c['bytes_identical'] for c in comparisons)))
        assert unchanged and all(c['bytes_identical'] for c in comparisons), 'BYTE_DIFFERENCE'
    finally:
        release(DEFAULT_ROOT,owner='codex')


if __name__ == '__main__':
    main()
