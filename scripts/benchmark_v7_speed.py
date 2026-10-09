"""Finite, locked ABBA replay through pinned S2/S3/egomap physical backends.

Saved commands only: no controller, provider calls, or new mission success claim.
Adapter code is exported from Git, never merged into this branch or edited in its
worktree. Four core modules are overlaid, matching the proposed main merge.
"""
from __future__ import annotations
import argparse
import cProfile
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import pstats
import shutil
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ('sim.v7_exact_speedups', 'scripts.run_final_environment_checks',
           'sim.final_environment_checks', 'sim.masterpi_drive_friction_v7')
PROVENANCE = {'v7-speedups.json', 'runtime-bundle.json'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def source_check(expected):
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == expected
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip(), 'DIRTY_SOURCE'


def inventory(root):
    return {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


def export_adapter(revision, output):
    """Tracked source/assets only. Exclude historical heavy experimental media."""
    assert len(revision) == 40 and all(c in '0123456789abcdef' for c in revision)
    output.mkdir()
    proc = subprocess.Popen(['git', 'archive', revision, 'sim', 'harness', 'scripts',
                             'configs', 'maps', 'experiments'], cwd=ROOT, stdout=subprocess.PIPE)
    heavy = {'.png', '.jpg', '.jpeg', '.mp4', '.zip', '.gz', '.npz', '.npy', '.pdf'}
    with tarfile.open(fileobj=proc.stdout, mode='r|') as archive:
        for member in archive:
            p = Path(member.name)
            if not member.isfile():
                continue
            if p.parts[0] == 'experiments' and p.suffix in heavy and not (
                    '2026-10-07-wall-parallax-texture/assets' in member.name):
                continue
            assert not p.is_absolute() and '..' not in p.parts
            dest = output/p
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as src, dest.open('xb') as dst:
                shutil.copyfileobj(src, dst)
    assert proc.wait() == 0
    return inventory(output)


def load_adapter(root):
    # Fresh child interpreter: all adapter dependencies from its immutable export.
    sys.path.insert(0, str(root))
    for package in ('sim', 'scripts', 'harness'):
        importlib.import_module(package).__path__ = [str(root/package)]
    for name in OVERLAY:
        parent_name, _, leaf = name.rpartition('.')
        parent = importlib.import_module(parent_name)
        path = ROOT/(name.replace('.', '/')+'.py')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        setattr(parent, leaf, module)


def backend_factory(kind, bundle):
    if kind == 'egomap':
        from sim.own_map_closed_loop import PhysicsBackend
        return PhysicsBackend
    if kind == 's3':
        from sim.zone_s3_no_prior import PhysicsBackend
        return PhysicsBackend
    if kind != 's2':
        raise ValueError(kind)
    # The exact backend composition in run_s2_landmarks_dev.run (v141 stack).
    from sim import s2_realism
    from sim.s2_servo_stiffness import transform_xml
    from sim.s2_pulse_cal import backend_class
    from sim.s2_eval_wall_contacts import backend_class as wall_backend
    class Backend(wall_backend(backend_class())):
        def __init__(self, *args, **kwargs):
            original = s2_realism.make_scene
            def scene_factory(*a, **kw):
                scene = original(*a, **kw)
                transform = scene.robot_transform
                scene.robot_transform = lambda xml, **k: transform_xml(
                    transform(xml, **k), servo_stiffness=bundle['options']['servo_stiffness'])
                return scene
            try:
                s2_realism.make_scene = scene_factory
                super().__init__(*args, **kwargs)
            finally:
                s2_realism.make_scene = original
    return Backend


def scene_receipt(actual, reference):
    """Relocated Git exports change asset path spelling, never their bytes."""
    import xml.etree.ElementTree as ET
    a, b = ET.fromstring(actual.read_bytes()), ET.fromstring(reference.read_bytes())
    assets = []
    for node in a.iter():
        if node.get('file'):
            path = Path(node.get('file'))
            digest = sha(path)
            assets.append({'name': node.get('name'), 'sha256': digest})
            node.set('file', 'sha256:'+digest)
    for node in b.iter():
        if node.get('file'):
            node.set('file', 'sha256:'+sha(Path(node.get('file'))))
    assert ET.tostring(a) == ET.tostring(b), 'ADAPTER_SCENE_DIFF'
    return {'identical_after_asset_path_relocation': True, 'assets': assets}


def worker(args):
    held = json.loads((args.output.parent/'lock.json').read_text())
    # Parent owns the exclusive lock; workers are strictly serial direct children.
    assert held['pid'] == os.getppid() and held['owner'] == 'codex'
    load_adapter(args.adapter_root)
    from scripts.agent_lock import DEFAULT_ROOT, status
    assert status(DEFAULT_ROOT)['pid'] == os.getppid()
    import mujoco
    import numpy as np
    os.environ['UGRP_V7_EXACT_SPEEDUPS'] = args.mode
    bundle = json.loads((args.source/'bundle.json').read_text())
    kind = args.path_kind
    robots = ('r1', 'r2', 'r3') if kind == 's3' else ('r3',)
    seed = bundle['seed'] if kind == 's3' else bundle['task']['seed']
    frames = {r: rows(args.source/f'robots/{r}/frames.jsonl') for r in robots}
    start = frames[robots[0]][0]['sim_time']
    period = .2 if kind == 'egomap' else .05
    times = [round(start+i*period, 9) for i in range(round(args.sim_seconds/period)+1)]
    for r in robots:
        assert [f['sim_time'] for f in frames[r][:len(times)]] == times, 'INCOMPLETE_SOURCE_FRAMES'
    schedule = {}
    for r in robots:
        for action in rows(args.source/f'robots/{r}/commands.jsonl'):
            if action['kind'] != 'initial_servo_command' and action['t'] <= times[-1]+1e-8:
                assert round(action['t'], 9) in times
                schedule.setdefault(round(action['t'], 9), []).append((r, {k:v for k,v in action.items() if k != 't'}))
    args.output.mkdir()
    backend = None
    undo = None
    if str(bundle.get('speedups', '')).startswith('v98-exact-v6'):
        from harness.zone_pair_highpose_exact_speedups import install
        _, undo = install('v98-exact-v6')
    profile = cProfile.Profile() if args.profile else None
    initial_load = os.getloadavg()
    try:
        backend = backend_factory(kind, bundle)(bundle, args.output, seed=seed)
        backend.reset(5.)
        assert backend.now == start
        write(args.output/'scene-proof.json', scene_receipt(args.output/'scene.xml', args.source/'scene.xml'))
        backend.set_deadline(times[-1])
        if kind == 's2':
            # Replay the recorded command-derived release flag; never infer it from GT.
            supervision = {round(x['t'], 9): x['release_allowed'] for x in rows(args.source/'eval_only/supervisor.jsonl')}
        state_spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(backend.world.model, state_spec))
        chain = hashlib.sha256()
        step_count = 0
        original = backend.world._physics_step_for
        def step(*a, **kw):
            nonlocal step_count
            result = original(*a, **kw)
            mujoco.mj_getState(backend.world.model, backend.world.data, state, state_spec)
            chain.update(state.tobytes())
            for rid in sorted(backend.world.drive_input_state):
                chain.update(backend.world.drive_input_state[rid].tobytes())
            step_count += 1
            return result
        backend.world._physics_step_for = step
        if profile: profile.enable()
        started = time.perf_counter()
        for i, t in enumerate(times):
            backend.advance_to(t)
            if kind == 's2': backend.release_allowed = supervision[t]
            if kind != 'egomap': backend.eval_sample()
            if kind == 'egomap' and i == 0:
                for rid, action in schedule.get(t, []): backend.issue(rid, action)
            backend.capture()
            if kind != 'egomap' or i:
                for rid, action in schedule.get(t, []): backend.issue(rid, action)
            if kind == 'egomap': backend.eval_sample()
        wall = time.perf_counter()-started
        if profile: profile.disable()
        assert step_count == round(args.sim_seconds/backend.dt)
        mujoco.mj_getState(backend.world.model, backend.world.data, state, state_spec)
        write(args.output/'state-chain.json', dict(steps=step_count, start=start, end=backend.now,
            dt=backend.dt, sim_s=args.sim_seconds, period=period, robots=robots, frames=len(times),
            state_spec=int(state_spec), chain_sha256=chain.hexdigest(), final_sha256=hashlib.sha256(state.tobytes()).hexdigest()))
        if kind == 's3':
            from harness.zone_s3_no_prior_contract import inputs
            # Same post-loop referee as the original host.
            orders = inputs()[2]['orders']
            judgment = backend.evaluate(orders, backend.scene.config['static_map'])
        else:
            from sim.solo_cyan_v106 import evaluate
            judgment = evaluate(backend.eval_rows, backend.scene.config['static_map'], bundle['task']['destination'])
        write(args.output/'judgement.json', judgment)
        info = dict(mode=args.mode, seed=seed, kind=kind, sim_s=args.sim_seconds, wall_s=wall,
            wall_per_sim=wall/args.sim_seconds, load_start=initial_load, load_end=os.getloadavg(),
            nice=os.getpriority(os.PRIO_PROCESS, 0), steps=step_count, frames=len(times),
            receipt=backend.world.v7_speedups_record, profile=args.profile)
        if hasattr(backend.world.drive_parameters, 'cache_info'):
            info['cache'] = backend.world.drive_parameters.cache_info()
        if profile:
            profile.dump_stats(str(args.output)+'.prof')
            stats = pstats.Stats(profile)
            info['profile_total_s'] = stats.total_tt
            info['top10_python'] = [dict(function=f'{k[0]}:{k[1]}:{k[2]}', calls=v[1], self_s=v[2],
                cumulative_s=v[3], percent=100*v[2]/stats.total_tt)
                for k,v in sorted(((k,v) for k,v in stats.stats.items() if k[0] != '~'), key=lambda x:x[1][2], reverse=True)[:10]]
        write(Path(str(args.output)+'.measurement.json'), info)
    finally:
        if profile: profile.disable()
        if backend: backend.close()
        if undo: undo()


def validate(root):
    data = json.loads((root/'state-chain.json').read_text())
    assert all(len(data[k]) == 64 and all(c in '0123456789abcdef' for c in data[k])
               for k in ('chain_sha256', 'final_sha256'))
    assert data['sim_s'] > 0 and data['steps'] == round(data['sim_s']/data['dt'])
    assert abs(data['end']-data['start']-data['sim_s']) < 1e-8
    assert data['frames'] == round(data['sim_s']/data['period'])+1
    assert (root/'scene.xml').stat().st_size > 0 and (root/'judgement.json').is_file()
    contacts = rows(root/'eval_only/contacts.jsonl')
    assert len(contacts) == data['frames']
    for r in data['robots']:
        frames = rows(root/f'robots/{r}/frames.jsonl')
        assert [x['sim_time'] for x in frames] == [round(data['start']+i*data['period'],9) for i in range(data['frames'])]
        assert all(sha(root/x['path']) == x['sha256'] for x in frames)
        assert rows(root/f'robots/{r}/commands.jsonl')[0]['kind'] == 'initial_servo_command'
    for name in PROVENANCE:
        assert (root/name).is_file()
    return data


def compare(left, right):
    assert validate(left) == validate(right)
    a, b = inventory(left), inventory(right)
    assert a.keys() == b.keys()
    delta = [n for n in a if n not in PROVENANCE and (left/n).read_bytes() != (right/n).read_bytes()]
    return dict(left=left.name, right=right.name, identical=not delta, differences=delta,
                compared_files=len(a)-len(PROVENANCE), explicit_provenance_files=sorted(PROVENANCE), inventory=a)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite', type=Path)
    p.add_argument('--expected-source-sha')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sim-seconds', type=float, default=30.)
    p.add_argument('--wait-seconds', type=float, default=0.)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--source', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--adapter-root', type=Path, help=argparse.SUPPRESS)
    p.add_argument('--path-kind', choices=('s2','s3','egomap'), help=argparse.SUPPRESS)
    p.add_argument('--mode', choices=('off','relay-cache-v1'), help=argparse.SUPPRESS)
    p.add_argument('--profile', action='store_true')
    args = p.parse_args()
    if args.worker:
        worker(args)
        return
    source_check(args.expected_source_sha)
    assert 0 < args.sim_seconds <= 30 and abs(args.sim_seconds*5-round(args.sim_seconds*5)) < 1e-8
    assert args.output.is_absolute() and not args.output.exists()
    assert args.output.resolve().is_relative_to(Path('/Users/changmin/projects/ugrp/outputs'))
    suite = json.loads(args.suite.read_text())
    assert {r['kind'] for r in suite} == {'s2','s3','egomap'}
    if not args.execute:
        print('preflight only; no model construction')
        return
    assert shutil.disk_usage(args.output.parent).free >= 10*1024**3
    from scripts.agent_lock import DEFAULT_ROOT, acquire, release, status
    until = time.monotonic()+args.wait_seconds
    while True:
        if status(DEFAULT_ROOT) is None:
            try:
                lock = acquire(DEFAULT_ROOT, owner='codex', branch='codex/sim-speed-core',
                    purpose='simspeed2 3-path 30s ABBA; research queue cleared', pid=os.getpid(),
                    expected_minutes=20, timing_sensitive=True)
                break
            except RuntimeError: pass
        if time.monotonic() >= until: raise RuntimeError('LOCK_WAIT_EXPIRED; no physics')
        print('waiting for agent_lock', flush=True)
        time.sleep(min(15, max(0, until-time.monotonic())))
    try:
        source_check(args.expected_source_sha)
        assert os.getpriority(os.PRIO_PROCESS, 0) == 0
        args.output.mkdir()
        write(args.output/'lock.json', lock)
        write(args.output/'suite.json', suite)
        for row in suite:
            case = args.output/row['kind']; case.mkdir()
            # Worker sees the same parent lock for each case.
            write(case/'lock.json', lock)
            source = Path(row['source'])
            snapshot = case/'adapter'
            adapter_before = export_adapter(row['adapter_sha'], snapshot)
            write(case/'adapter-manifest.json', adapter_before)
            inputs_before = {str(f.relative_to(source)):sha(f) for f in [source/'bundle.json', source/'scene.xml',
                *sorted(source.glob('robots/*/commands.jsonl')), *sorted(source.glob('robots/*/frames.jsonl'))]}
            sequence = [('A1','off'),('B1','relay-cache-v1'),('B2','relay-cache-v1'),('A2','off')]
            if args.profile and row['kind'] == 'egomap': sequence += [('profile-off','off'),('profile-on','relay-cache-v1')]
            for name, mode in sequence:
                cmd = [sys.executable, str(Path(__file__)), '--worker', '--output', str(case/name),
                       '--source', str(source), '--adapter-root', str(snapshot), '--path-kind', row['kind'],
                       '--mode', mode, '--sim-seconds', str(args.sim_seconds)]
                if name.startswith('profile'): cmd.append('--profile')
                print('starting', row['kind'], name, flush=True)
                subprocess.run(cmd, check=True, cwd=snapshot, timeout=900)
                print((Path(str(case/name)+'.measurement.json')).read_text(), flush=True)
            assert inventory(snapshot) == adapter_before, 'ADAPTER_CHANGED'
            assert all(sha(source/n) == h for n,h in inputs_before.items()), 'INPUT_CHANGED'
            comparisons = [compare(case/'A1',case/n) for n in ('A2','B1','B2')]
            write(case/'comparison.json', dict(comparisons=comparisons, input_hashes=inputs_before,
                  source_sha=args.expected_source_sha, adapter_sha=row['adapter_sha'], inputs_unchanged=True))
            assert all(r['identical'] for r in comparisons), 'BYTE_DIFFERENCE'
    finally:
        write(args.output/'released.json', release(DEFAULT_ROOT, owner='codex'))


if __name__ == '__main__':
    main()
