"""Finite Oracle x86 ABBA, frozen experiment adapters, no Mac execution."""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time
import traceback
from scripts.profile_controller_replay import interruptible

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = {'s3': '4e19382d59a9bb2bbf351a7fca1356cdf480e8a0',
            'ego': '2cfe8852ba3b8db8045bb946d45d5f678d134e86'}
ORDER = ('eager', 'lazy-v1', 'lazy-v1', 'eager')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def archive_fingerprint(path):
    files = {str(p.relative_to(path)): sha(p) for folder in ('sim', 'harness', 'scripts')
             for p in sorted((path/folder).rglob('*.py'))}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def host_guard(expected):
    if (platform.system() != 'Linux' or platform.machine() != 'x86_64'
            or os.getenv('UGRP_EXECUTION_HOST') != 'oracle-x86'
            or os.getenv('MUJOCO_GL') != 'osmesa'):
        raise RuntimeError('ORACLE_X86_ONLY_NO_MAC_PHYSICS')
    if ROOT.name != expected or len(expected) != 40:
        raise ValueError('COMMITTED_ARCHIVE_REQUIRED')
    if os.getpriority(os.PRIO_PROCESS, 0) != 0:
        raise ValueError('NICE_ZERO_REQUIRED')
    if os.getenv('LP_NUM_THREADS') != '4':
        raise ValueError('FIXED_LP_NUM_THREADS_4_REQUIRED')


def run_one(args):
    from sim import lazy_camera  # our committed implementation before adapter routing
    adapter = ROOT.parent/ADAPTERS[args.kind]
    before = archive_fingerprint(adapter)
    for name in ('sim', 'harness', 'scripts'):
        package = importlib.import_module(name)
        package.__path__ = [str(adapter/name), str(ROOT/name)]
    os.environ[lazy_camera.ENV] = args.render_mode
    undo = lazy_camera.install_adapter()
    out = args.output
    if out.exists(): raise ValueError('PRESERVE_EXISTING_OUTPUT')
    samples = []
    done = threading.Event()
    def sample():
        while not done.is_set():
            samples.append(dict(wall=time.time(), load=list(os.getloadavg())))
            done.wait(1.)
    thread = threading.Thread(target=sample, daemon=True); thread.start()
    started = time.monotonic()
    counters = {'physics_s': 0., 'physics_calls': 0, 'render_s': 0., 'render_calls': 0}
    from sim.multi_masterpi_production import MultiMasterPiProductionV2 as World
    originals = {}
    for name, category in (('_physics_step_for', 'physics'), ('_render_rgb_for', 'render')):
        original = getattr(World, name); originals[name] = original
        def timed(*a, _original=original, _category=category, **kw):
            start = time.perf_counter()
            try: return _original(*a, **kw)
            finally:
                counters[_category+'_s'] += time.perf_counter()-start
                counters[_category+'_calls'] += 1
        setattr(World, name, timed)
    result = None
    failure = None
    try:
        if args.kind == 's3':
            from scripts import run_s3_coarse_fine_probe as probe
            from harness.zone_pair_highpose_exact_speedups import install
            _, undo_exact = install('v98-exact-v6')
            try:
                b = probe.bundle(ADAPTERS['s3'], 'cyan', 0, 'stopped_base_arm_v1', args.sim_s)
                result = probe.run(b, out)
            finally: undo_exact()
        else:
            from scripts import run_own_route_particle_stages as stage
            from scripts import run_goal_route_motion_audit as motion
            from harness.active_camera import bind
            from types import SimpleNamespace
            def bundle(seed, source, profile, mode):
                b = motion.bundle(seed, source)
                b['case_cap_s'] = args.sim_s
                b['options']['wall_asset_numeric'] = 'libm_ulps_v1'
                b.update(stage_diagnostic=True, admission='speedctrl3 same-seed finite DEV camera comparison')
                return b
            b = bundle(55001, ADAPTERS['ego'], 'baseline', 'speedctrl_stage')
            result = bind(stage.run, bundle=bundle)(SimpleNamespace(output=out,
                seed=55001, profile='baseline', mode='speedctrl_stage', checkpoint=None))
    except BaseException:
        failure = traceback.format_exc()
        raise
    finally:
        elapsed = time.monotonic()-started
        done.set(); thread.join()
        for name, original in originals.items(): setattr(World, name, original)
        undo()
        unchanged = before == archive_fingerprint(adapter)
        sim = (result or {}).get('check_sim_s')
        if sim is None and result and result.get('total_sim_s') is not None:
            sim = result['total_sim_s']-result.get('start_sim_s', 0.)
        write(out/'measurement.json', dict(schema='ugrp.lazy_camera_measurement.v1',
            implementation_sha=args.expected_source_sha, adapter_sha=ADAPTERS[args.kind],
            adapter_fingerprint=before, adapter_unchanged=unchanged,
            kind=args.kind, mode=args.render_mode, requested_sim_s=args.sim_s,
            sim_s=sim, wall_s=elapsed, wall_per_sim=elapsed/sim if sim else None,
            load_mean=[sum(row['load'][i] for row in samples)/len(samples) for i in range(3)],
            samples=samples, timers=counters, result_status=(result or {}).get('status'),
            failure=failure, source_module_sha256=sha(Path(lazy_camera.__file__)),
            physics_host=platform.node(), environment={key: os.environ.get(key) for key in
                ('LP_NUM_THREADS','OMP_NUM_THREADS','MUJOCO_GL','UGRP_EXECUTION_HOST')}))
    return int(result.get('status') == 'HOST_ERROR')


def behavior_files(path, kind):
    # Direct original bytes, including every retained JPEG. No float rounding,
    # canonicalization or timing-key removal from the control ledgers.
    files = {str(p.relative_to(path)) for p in (path/'robots').rglob('*') if p.is_file()}
    names = ('student_record.json', 'stage-states.json') if kind == 's3' else (
        'own-controller.jsonl', 'own-contacts.jsonl', 'frontend-covariances.jsonl',
        'online-maps.jsonl', 'route-map.json', 'utility-events.json', 'frontend-grid.json',
        'frontend-ledger.json', 'decisions.json', 'heading-decisions.json')
    for name in names:
        if not (path/name).is_file(): raise ValueError('MISSING_BEHAVIOR:'+name)
        files.add(name)
    return files


def equal_bytes(a, b):
    if a.stat().st_size != b.stat().st_size: return False
    with a.open('rb') as x, b.open('rb') as y:
        while True:
            left, right = x.read(1024*1024), y.read(1024*1024)
            if left != right: return False
            if not left: return True


def compare(paths, kind):
    rows = [json.loads((p/'measurement.json').read_text()) for p in paths]
    files = [behavior_files(p, kind) for p in paths]
    mismatches = []
    same_names = all(f == files[0] for f in files)
    for name in sorted(set.union(*files)):
        if not all(name in f for f in files) or not all(equal_bytes(paths[0]/name, p/name) for p in paths[1:]):
            mismatches.append(name)
    loads = [r['load_mean'][0] for r in rows]
    def comparable(a,b): return abs(a-b) <= max(.5, .25*min(a,b))
    a_load, b_load = (loads[0]+loads[3])/2, (loads[1]+loads[2])/2
    load_ok = comparable(loads[0],loads[1]) and comparable(loads[3],loads[2]) and comparable(a_load,b_load)
    valid = all(r['adapter_unchanged'] and r['failure'] is None and r['sim_s'] == r['requested_sim_s']
                and r['result_status'] in ('DEV_STAGE_FINISHED','RECORDED') for r in rows)
    identities = ('implementation_sha','adapter_sha','adapter_fingerprint','source_module_sha256','environment')
    same_source = all(all(r[k] == rows[0][k] for r in rows) for k in identities)
    a = (rows[0]['wall_per_sim']+rows[3]['wall_per_sim'])/2
    b = (rows[1]['wall_per_sim']+rows[2]['wall_per_sim'])/2
    return dict(kind=kind, complete=valid, same_source=same_source,
        byte_identical=same_names and not mismatches, compared_files=len(files[0]), mismatches=mismatches,
        frame_proof='all retained JPEGs and original frame-ledger bytes; superset of consumed frames',
        load_means=loads, load_comparable=load_ok, eager_wall_per_sim=a, lazy_wall_per_sim=b,
        reduction_fraction=1-b/a if valid and same_source and load_ok and not mismatches else None,
        rows=rows, camera=[json.loads((p/'camera-render.json').read_text()) for p in paths])


def cohort(args):
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for kind in ('s3','ego'):
        paths = []
        for i, mode in enumerate(ORDER, 1):
            # Remote peers use their own slots. Do not stop them. Wait for an
            # idle host before each arm; a finite deadline prevents a daemon.
            deadline = time.monotonic()+3600
            while True:
                available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))*1024
                processes = subprocess.check_output(['ps','-eo','pid,ppid,args'], text=True).splitlines()
                peers = [line for line in processes if ' -m scripts.run_' in line and 'python' in line]
                if not peers and available >= 6*2**30: break
                if time.monotonic() >= deadline: raise TimeoutError('HOST_BUSY_NO_MEASUREMENT')
                time.sleep(10)
            if shutil.disk_usage(args.output).free < 2*2**30: raise OSError('REMOTE_DISK_RESERVE_2GIB')
            path = args.output/f'{kind}-{i}-{mode}'; paths.append(path)
            cmd = [sys.executable, '-m', 'scripts.benchmark_lazy_camera', '--kind', kind,
                   '--output', str(path), '--render-mode', mode, '--sim-s', str(args.sim_s),
                   '--expected-source-sha', args.expected_source_sha]
            with (args.output/f'{kind}-{i}.log').open('x') as log:
                from scripts.benchmark_controller_replay import run_owned_command
                run_owned_command(cmd, cwd=ROOT, log=log, timeout=1800)
            write(args.output/'progress.json', dict(kind=kind, arm=i, mode=mode))
        result = compare(paths, kind); results.append(result)
        write(args.output/(kind+'-comparison.json'), result)
    write(args.output/'comparison.json', dict(schema='ugrp.lazy_camera_abba.v1', source=args.expected_source_sha,
        order=ORDER, results=results, adopted=False, default='eager'))
    return 0


@interruptible
def main():
    p = argparse.ArgumentParser(); p.add_argument('--kind', choices=('s3','ego','abba'), required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--render-mode', choices=ORDER[:2], default='eager')
    p.add_argument('--sim-s', type=float, choices=(5.,60.), default=60.)
    args = p.parse_args(); host_guard(args.expected_source_sha)
    if args.kind != 'abba': return run_one(args)
    from scripts import agent_lock
    lock_root = ROOT.parent.parent/'agent-locks'
    held = agent_lock.acquire(lock_root, owner='codex', branch='codex/sim-speed-ctrl2',
        purpose='speedctrl3 Oracle camera ABBA after S3 research', pid=os.getpid(),
        expected_minutes=90, timing_sensitive=True)
    try:
        return cohort(args)
    finally:
        write(args.output/'lock.json', held)
        current = agent_lock.status(lock_root)
        if current and all(current[k] == held[k] for k in ('owner','pid','branch','acquired_unix')):
            agent_lock.release(lock_root, owner='codex')


if __name__ == '__main__': raise SystemExit(main())
