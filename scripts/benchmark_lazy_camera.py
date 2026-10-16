"""Finite Oracle x86 paired/ABBA runs, frozen adapters, no Mac execution."""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import resource
import signal
import statistics
import contextlib
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
    temporary = path.with_name(path.name+f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    os.replace(temporary,path)


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


def verify_archive(args, source):
    """Compare a sender-pinned Git tree manifest to actual archive source bytes."""
    if sha(args.archive_manifest) != args.archive_manifest_sha256:
        raise ValueError('ARCHIVE_MANIFEST_CHANGED')
    manifest = json.loads(args.archive_manifest.read_text())
    files = manifest['archives'][source]
    root = ROOT.parent/source
    actual_python = {str(p.relative_to(root)) for folder in ('sim','harness','scripts')
                     for p in (root/folder).rglob('*.py')}
    expected_python = {p for p in files if p.endswith('.py') and p.split('/')[0] in ('sim','harness','scripts')}
    if actual_python != expected_python:
        raise ValueError('ARCHIVE_PYTHON_FILE_SET_CHANGED')
    for name, blob in files.items():
        path = root/name
        data = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
        digest = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if digest != blob: raise ValueError('ARCHIVE_GIT_BLOB_CHANGED:'+name)
    return args.archive_manifest_sha256


def observe_append(host):
    """Inspect issued commands independently of the adapter's buffered writers."""
    if hasattr(host, '_speed4_append_observer'): return
    original = host._append
    counts = dict(frames=0,commands=0,translating_commands=0,arm_commands=0,command_kinds={})
    host._speed4_append_observer = counts
    last = [-float('inf')]
    def append(name, row):
        result = original(name,row)
        if name.startswith('robots/') and name.endswith('/commands.jsonl'):
            counts['commands'] += 1
            key = row['kind']; counts['command_kinds'][key] = counts['command_kinds'].get(key,0)+1
            counts['translating_commands'] += int(abs(row.get('forward',0.))+abs(row.get('left',0.))>0.)
            counts['arm_commands'] += int(key in ('arm','servo','look'))
        if name.startswith('robots/') and name.endswith('/frames.jsonl'):
            counts['frames'] += 1
            t = row['sim_time']
            if t-last[0] >= 1.-1e-8:
                last[0] = t
                write(host.out/'command-progress.json',dict(**counts,sim_time=t,
                    semantics='evaluation-only observer of original append calls; original buffering unchanged'))
        return result
    host._append = append


def run_one(args):
    from sim import lazy_camera  # our committed implementation before adapter routing
    # Ignore an adapter's old pyc files; no untracked cached code in the proof.
    import tempfile
    sys.pycache_prefix = tempfile.mkdtemp(prefix='speedctrl3-pycache-')
    sys.dont_write_bytecode = True
    adapter = ROOT.parent/ADAPTERS[args.kind]
    verify_archive(args, args.expected_source_sha)
    verify_archive(args, ADAPTERS[args.kind])
    before = archive_fingerprint(adapter)
    for name in ('sim', 'harness', 'scripts'):
        package = importlib.import_module(name)
        package.__path__ = [str(adapter/name), str(ROOT/name)]
    os.environ[lazy_camera.ENV] = args.render_mode
    undo = lazy_camera.install_adapter()
    if args.parent_batch:
        from sim.solo_cyan_v106 import PhysicsBackend as Solo
        from sim.zone_s3_host import PhysicsBackend as Team
        for cls in (Solo,Team):
            capture = cls.capture
            def observed(host, _capture=capture):
                observe_append(host)
                return _capture(host)
            cls.capture = observed
    out = args.output
    if out.exists(): raise ValueError('PRESERVE_EXISTING_OUTPUT')
    if args.start_barrier:
        write(args.start_barrier.parent/(out.name+'-ready.json'), dict(pid=os.getpid(), source=args.expected_source_sha))
        deadline = time.monotonic()+120
        while not args.start_barrier.exists():
            if time.monotonic()>deadline: raise TimeoutError('BATCH_START_BARRIER_TIMEOUT')
            time.sleep(.1)
    samples = []
    done = threading.Event()
    def sample():
        while not done.is_set():
            samples.append(dict(wall=time.time(), load=list(os.getloadavg())))
            done.wait(1.)
    thread = threading.Thread(target=sample, daemon=True); thread.start()
    started_at = time.time()
    started = time.monotonic()
    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    evaluated_motion = {}
    last_progress = [-float("inf")]
    counters = {'physics_s': 0., 'physics_calls': 0, 'render_s': 0., 'render_calls': 0}
    from sim.multi_masterpi_production import MultiMasterPiProductionV2 as World
    originals = {}
    for name, category in (('_physics_step_for', 'physics'), ('_render_rgb_for', 'render')):
        original = getattr(World, name); originals[name] = original
        def timed(*a, _original=original, _category=category, **kw):
            start = time.perf_counter()
            try:
                if _category == 'render':
                    world = a[0]
                    t = float(world.data.time)
                    if t-last_progress[0] >= 1.-1e-8:
                        last_progress[0] = t
                        for rid, robot in world.controllers.items():
                            values = [float(x) for x in (*robot.base_xyz(), *robot.base_rpy(), *robot.site_xyz('grip_site'))]
                            initial = evaluated_motion.setdefault(rid, dict(initial=values, latest=values, max_position_delta_m=0.))
                            initial['latest'] = values
                            initial['max_position_delta_m'] = max(initial['max_position_delta_m'],
                                max(sum((values[i+j]-initial['initial'][i+j])**2 for j in range(3))**.5 for i in (0,6)))
                        # Evaluation-only sidecar. Never returned to the controller.
                        write(out/'evaluation-progress.json', dict(sim_time=t, wall=time.time(), robots=evaluated_motion,
                            semantics='base and grip positions; evaluation only; no feedback'))
                return _original(*a, **kw)
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
            from scripts import run_goal_route_motion_audit as motion_adapter
            from harness.active_camera import bind
            from types import SimpleNamespace
            def bundle(seed, source, profile, mode):
                b = motion_adapter.bundle(seed, source)
                b['case_cap_s'] = args.sim_s
                b['options']['wall_asset_numeric'] = 'libm_ulps_v1'
                b.update(stage_diagnostic=True, admission='speedctrl3 same-seed finite DEV camera comparison')
                return b
            b = bundle(55001, ADAPTERS['ego'], 'baseline', 'speedctrl_stage')
            # The parent admission replaces the frozen eight-slot limiter for this
            # explicitly authorized concurrent batch; robot behavior is unchanged.
            bindings = dict(bundle=bundle)
            if args.parent_batch: bindings['server_slot'] = lambda: contextlib.nullcontext('speed4-batch')
            result = bind(stage.run, **bindings)(SimpleNamespace(output=out,
                seed=55001, profile='baseline', mode='speedctrl_stage', checkpoint=None))
    except BaseException:
        failure = traceback.format_exc()
        raise
    finally:
        elapsed = time.monotonic()-started
        finished_at = time.time()  # same interval, before receipt/source verification
        cpu_end = resource.getrusage(resource.RUSAGE_SELF)
        cpu_user = cpu_end.ru_utime-cpu_start.ru_utime
        cpu_sys = cpu_end.ru_stime-cpu_start.ru_stime
        done.set(); thread.join()
        for name, original in originals.items(): setattr(World, name, original)
        undo()
        unchanged = before == archive_fingerprint(adapter)
        try:
            verify_archive(args, args.expected_source_sha)
            verify_archive(args, ADAPTERS[args.kind])
        except Exception:
            unchanged = False
            failure = traceback.format_exc()
        sim = (result or {}).get('check_sim_s')
        if sim is None and result and result.get('total_sim_s') is not None:
            sim = result['total_sim_s']-result.get('start_sim_s', 0.)
        write(out/'measurement.json', dict(schema='ugrp.lazy_camera_measurement.v1',
            implementation_sha=args.expected_source_sha, adapter_sha=ADAPTERS[args.kind],
            archive_manifest_sha256=args.archive_manifest_sha256,
            adapter_fingerprint=before, adapter_unchanged=unchanged,
            kind=args.kind, mode=args.render_mode, requested_sim_s=args.sim_s,
            sim_s=sim, started_at=started_at, ended_at=finished_at, wall_s=elapsed,
            wall_per_sim=elapsed/sim if sim else None, cpu_user_s=cpu_user, cpu_sys_s=cpu_sys,
            cpu_per_sim=(cpu_user+cpu_sys)/sim if sim else None,
            cpu_scope="RUSAGE_SELF including all in-process renderer threads; same interval as wall",
            load_start=samples[0]['load'], load_end=samples[-1]['load'],
            load_mean=[sum(row['load'][i] for row in samples)/len(samples) for i in range(3)],
            samples=samples, timers=counters,
            timer_coverage={key: ('measured' if counters[key+'_calls'] else 'unmeasured_hook_not_called')
                            for key in ('physics', 'render')},
            result_status=(result or {}).get('status'),
            failure=failure, source_module_sha256=sha(Path(lazy_camera.__file__)),
            physics_host=platform.node(), environment={key: os.environ.get(key) for key in
                ('LP_NUM_THREADS','OMP_NUM_THREADS','MUJOCO_GL','UGRP_EXECUTION_HOST')}))
    return int(result.get('status') == 'HOST_ERROR')


def behavior_files(path, kind):
    # Direct original bytes, including every retained JPEG. No float rounding,
    # canonicalization or timing-key removal from the control ledgers.
    files = {str(p.relative_to(path)) for p in (path/'robots').rglob('*') if p.is_file()}
    names = ('bundle.json', 'student_record.json', 'stage-states.json') if kind == 's3' else (
        'bundle.json',
        'own-controller.jsonl', 'own-contacts.jsonl', 'frontend-covariances.jsonl',
        'online-maps.jsonl', 'route-map.json', 'utility-events.json', 'frontend-grid.json',
        'frontend-ledger.json', 'decisions.json', 'heading-decisions.json')
    for name in names:
        if not (path/name).is_file(): raise ValueError('MISSING_BEHAVIOR:'+name)
        files.add(name)
    if not any(name.endswith('.jpg') for name in files):
        raise ValueError('MISSING_CAMERA_FRAMES')
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
    identities = ('implementation_sha','adapter_sha','adapter_fingerprint','source_module_sha256','environment','archive_manifest_sha256')
    same_source = all(all(r[k] == rows[0][k] for r in rows) for k in identities)
    a = (rows[0]['wall_per_sim']+rows[3]['wall_per_sim'])/2
    b = (rows[1]['wall_per_sim']+rows[2]['wall_per_sim'])/2
    return dict(kind=kind, complete=valid, same_source=same_source,
        byte_identical=same_names and not mismatches, compared_files=len(files[0]), mismatches=mismatches,
        frame_proof='all retained JPEGs and original frame-ledger bytes; superset of consumed frames',
        load_means=loads, load_comparable=load_ok, eager_wall_per_sim=a, lazy_wall_per_sim=b,
        reduction_fraction=1-b/a if valid and same_source and load_ok and not mismatches else None,
        rows=rows, camera=[json.loads((p/'camera-render.json').read_text()) for p in paths])


def host_sample():
    available = int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:')))*1024
    processes = subprocess.check_output(['ps','-eo','pid,ppid,args'], text=True).splitlines()
    peers = [line for line in processes if ' -m scripts.run_' in line and 'python' in line]
    return dict(at=time.time(), available_bytes=available, peers=peers, load=list(os.getloadavg()))


def wait_for_idle(receipt):
    """Use the same low-load admission for every arm, including load decay."""
    deadline = time.monotonic()+3600
    samples = []
    ready = False
    try:
        while True:
            row = host_sample(); samples.append(row)
            remaining = deadline-time.monotonic()
            if remaining <= 0: raise TimeoutError('HOST_BUSY_NO_MEASUREMENT')
            ready = not row['peers'] and row['available_bytes'] >= 6*2**30 and row['load'][0] <= 2.
            if ready: return
            time.sleep(min(10, remaining))
    finally:
        write(receipt, dict(ready=ready, samples=samples,
            rule='no peer workers, MemAvailable >=6GiB, 1min load <=2.0 before every arm'))


def cohort(args):
    results = []
    for kind in ('s3','ego'):
        paths = []
        for i, mode in enumerate(ORDER, 1):
            # Remote peers use their own slots. Do not stop them. Wait for an
            # idle host before each arm; a finite deadline prevents a daemon.
            wait_for_idle(args.output/f'{kind}-{i}-admission.json')
            if shutil.disk_usage(args.output).free < 2*2**30: raise OSError('REMOTE_DISK_RESERVE_2GIB')
            path = args.output/f'{kind}-{i}-{mode}'; paths.append(path)
            cmd = [sys.executable, '-m', 'scripts.benchmark_lazy_camera', '--kind', kind,
                   '--output', str(path), '--render-mode', mode, '--sim-s', str(args.sim_s),
                   '--parent-lease-pid', str(os.getpid()),
                   '--archive-manifest', str(args.archive_manifest),
                   '--archive-manifest-sha256', args.archive_manifest_sha256,
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


# These six provider summaries contain measured inference latency, not inputs or
# decisions. Keep the sample count and every other value. JSON object key order
# has no semantic meaning; arrays and numeric values are never rounded/reordered.
LATENCY_PATHS = tuple(tuple(p.split('/')) for p in (
    'pair/robots/r1/provider/provider/inference_wall_ms',
    'pair/robots/r2/provider/provider/inference_wall_ms',
    'solo/provider/provider/inference_wall_ms',
    'localizers/r1/provider/provider/inference_wall_ms',
    'localizers/r2/provider/provider/inference_wall_ms',
    'localizers/r3/provider/provider/inference_wall_ms'))


def behavior_projection(path):
    value = json.loads(path.read_text())
    removed = {}
    if path.name == 'student_record.json':
        for parts in LATENCY_PATHS:
            node = value
            for part in parts:
                if not isinstance(node, dict) or part not in node:
                    raise ValueError('MISSING_REGISTERED_LATENCY:'+ '/'.join(parts))
                node = node[part]
            if set(node) != {'n','p50','p90','max'}:
                raise ValueError('UNKNOWN_LATENCY_SUMMARY')
            for key in ('p50','p90','max'):
                removed['/'+ '/'.join((*parts,key))] = node.pop(key)
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest(), removed


def compare_pair(a, b, kind):
    rows = [json.loads((p/'measurement.json').read_text()) for p in (a,b)]
    files = [behavior_files(p, kind) for p in (a,b)]
    raw_mismatches, behavior_mismatches, proofs = [], [], {}
    for name in sorted(set.union(*files)):
        if any(name not in f for f in files):
            raw_mismatches.append(name); behavior_mismatches.append(name); continue
        raw = equal_bytes(a/name, b/name)
        if not raw: raw_mismatches.append(name)
        # Only these two JSON objects are projected. Ledgers, SIM timestamps,
        # command arrays and every retained JPEG remain strict original bytes.
        if name in ('bundle.json','student_record.json'):
            projected = [behavior_projection(p/name) for p in (a,b)]
            same = projected[0][0] == projected[1][0]
            proofs[name] = dict(raw_sha256=[sha(p/name) for p in (a,b)],
                behavior_sha256=[v[0] for v in projected],
                excluded_latency_fields=[v[1] for v in projected])
        else: same = raw
        if not same: behavior_mismatches.append(name)
    identities = ('implementation_sha','adapter_sha','adapter_fingerprint',
                  'source_module_sha256','environment','archive_manifest_sha256')
    complete = all(r['adapter_unchanged'] and not r['failure'] and
                   r['sim_s'] == r['requested_sim_s'] and
                   r['result_status'] in ('RECORDED','DEV_STAGE_FINISHED') for r in rows)
    source_same = all(rows[0][k] == rows[1][k] for k in identities)
    overlap = max(0., min(r['ended_at'] for r in rows)-max(r['started_at'] for r in rows))
    eligible = complete and source_same and not behavior_mismatches and overlap > 0
    return dict(kind=kind, paths=[str(a),str(b)], complete=complete, same_source=source_same,
        raw_byte_identical=not raw_mismatches, raw_mismatches=raw_mismatches,
        behavior_byte_identical=not behavior_mismatches, behavior_mismatches=behavior_mismatches,
        compared_files=len(files[0]), proofs=proofs, eligible=eligible,
        start_skew_s=abs(rows[0]['started_at']-rows[1]['started_at']), overlap_s=overlap,
        wall_ratio_b_over_a=rows[1]['wall_per_sim']/rows[0]['wall_per_sim'] if eligible else None,
        cpu_ratio_b_over_a=rows[1]['cpu_per_sim']/rows[0]['cpu_per_sim'] if eligible else None,
        rows=rows, camera=[json.loads((p/'camera-render.json').read_text()) for p in (a,b)])


def validate_parent_batch(args):
    receipt = json.loads(args.parent_batch.read_text())
    if not (receipt['pid'] == os.getppid() and receipt['source'] == args.expected_source_sha
            and any(r['kind'] == args.kind and r['mode'] == args.render_mode
                    and r['output'] == str(args.output) for r in receipt['runs'])):
        raise ValueError('LIVE_REGISTERED_BATCH_PARENT_REQUIRED')
    os.kill(receipt['pid'], 0)
    if args.start_barrier != args.parent_batch.parent/'start.json':
        raise ValueError('REGISTERED_START_BARRIER_REQUIRED')


def admit_concurrent():
    row = host_sample()
    if row['available_bytes'] < 6*2**30: raise RuntimeError('BATCH_MEMORY_RETRY_REQUIRED')
    if row['load'][0] >= 51: raise RuntimeError('BATCH_LOAD_RETRY_REQUIRED')
    return row


def early_state(path, kind, log):
    errors = 'Traceback (most recent call last)' in log.read_text()
    progress = json.loads((path/'evaluation-progress.json').read_text()) if (path/'evaluation-progress.json').exists() else {}
    frames, commands = [], []
    def lines(p):
        text = p.read_text()
        # A concurrently growing line-buffered ledger can end in an unfinished
        # row. Inspect only newline-terminated records, never repair originals.
        return [json.loads(line) for line in text.split('\n')[:-1] if line]
    for p in (path/'robots').glob('*/frames.jsonl'):
        frames.extend(lines(p))
    for p in (path/'robots').glob('*/commands.jsonl'):
        commands.extend(lines(p))
    moving = max((v['max_position_delta_m'] for v in progress.get('robots',{}).values()), default=0.)
    translating = [r for r in commands if abs(r.get('forward',0.))+abs(r.get('left',0.)) > 0]
    arm_actions = [r for r in commands if r.get('kind') in ('arm','servo','look')]
    observed_path = path/'command-progress.json'
    observed = json.loads(observed_path.read_text()) if observed_path.exists() else {}
    frame_count = max(len(frames), observed.get('frames',0))
    command_count = max(len(commands), observed.get('commands',0))
    translation_count = max(len(translating),observed.get('translating_commands',0))
    arm_count = max(len(arm_actions),observed.get('arm_commands',0))
    own = path/'own-controller.jsonl'
    controller = lines(own) if own.exists() else []
    stages = sorted({r.get('stage','unknown') for r in controller})
    # Initial egomap sensor_sweep is a registered exploration observation phase;
    # rotation there is intentional. Once it exits, require translational commands.
    sweeping = bool(controller) and all(r.get('status') == 'sensor_sweep' for r in controller)
    command_ok = command_count>0 and (translation_count>0 or (kind == 's3' and arm_count>0) or
                                    (kind == 'ego' and sweeping and progress.get('sim_time',0.) <= 20.))
    stage_ok = bool(stages) if kind == 'ego' else bool(frame_count and arm_count)
    ok = not errors and frame_count>2 and moving>1e-5 and command_ok and stage_ok
    return dict(ok=ok, traceback=errors, frames=frame_count, sim_time=progress.get('sim_time'),
        motion_delta_m=moving, commands=command_count, translating_commands=translation_count,
        command_kinds=sorted({r['kind'] for r in commands}|set(observed.get('command_kinds',{}))), stages=stages,
        buffered_append_observer=observed,
        stage_evidence='own controller stage' if kind=='ego' else 'S3 camera control and arm commands',
        initial_sensor_sweep=sweeping, evaluation=progress)


def stop_owned(process):
    # Every subprocess is a new session created by this parent. Never select a
    # process by name, and never signal a peer run or the common server.
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=15)


def spawn_registered(children, row, cmd, log):
    """Defer interruption across OS spawn -> handle -> ownership registration."""
    watched = (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)
    previous = {s:signal.getsignal(s) for s in watched}
    pending = []
    def defer(signum,frame): pending.append((signum,frame))
    try:
        for signum in watched: signal.signal(signum,defer)
        with log.open('x') as stream:
            proc = subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            children.append((row,proc,log))
    finally:
        for signum,handler in previous.items(): signal.signal(signum,handler)
    if pending:
        signum,frame = pending[0]
        handler = previous[signum]
        if callable(handler): handler(signum,frame)
        raise InterruptedError('HOST_INTERRUPTED:'+signal.Signals(signum).name)
    return proc


def cleanup_children(children, output):
    """Attempt every owned stop before writing any receipt; collect all errors."""
    errors = []
    watched = (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)
    previous = {s:signal.getsignal(s) for s in watched}
    try:
        for signum in watched: signal.signal(signum,signal.SIG_IGN)
        for row,proc,_ in children:
            try: stop_owned(proc)
            except BaseException as e: errors.append(dict(pid=proc.pid,operation='stop',error=repr(e)))
        for row,proc,_ in children:
            try: write(output/(Path(row['output']).name+'-EXIT.json'),dict(pid=proc.pid,EXIT=proc.returncode))
            except BaseException as e: errors.append(dict(pid=proc.pid,operation='receipt',error=repr(e)))
    finally:
        for signum,handler in previous.items(): signal.signal(signum,handler)
    if errors:
        print(json.dumps(dict(cleanup_errors=errors)),file=sys.stderr,flush=True)
        if sys.exc_info()[0] is None: raise RuntimeError('CHILD_CLEANUP_FAILED')


def paired_cohort(args):
    runs, children = [], []
    initial = admit_concurrent()
    if shutil.disk_usage(args.output).free < 2*2**30: raise OSError('REMOTE_DISK_RESERVE_2GIB')
    for pair in range(4):
        for kind in ('s3','ego'):
            for mode in (ORDER[:2] if pair%2 == 0 else ORDER[:2][::-1]):
                name = f'{kind}-p{pair+1}-{mode}'
                runs.append(dict(kind=kind, pair=pair+1, mode=mode, output=str(args.output/name)))
    receipt = args.output/'batch.json'; barrier = args.output/'start.json'
    write(receipt, dict(pid=os.getpid(),source=args.expected_source_sha,runs=runs,
        admission=initial, authorization='2026-10-10 speed4 concurrent pairs; no exclusive lease',
        frozen_ego_slot_override='parent resource admission replaces eight-slot wrapper only'))
    try:
        for row in runs:
            admission = admit_concurrent()
            name = Path(row['output']).name
            cmd = [sys.executable,'-m','scripts.benchmark_lazy_camera','--kind',row['kind'],
                '--output',row['output'],'--render-mode',row['mode'],'--sim-s',str(args.sim_s),
                '--parent-batch',str(receipt),'--start-barrier',str(barrier),
                '--archive-manifest',str(args.archive_manifest),
                '--archive-manifest-sha256',args.archive_manifest_sha256,
                '--expected-source-sha',args.expected_source_sha]
            log = args.output/(name+'.log')
            proc = spawn_registered(children,row,cmd,log)
            write(args.output/(name+'-launch.json'),dict(pid=proc.pid,admission=admission,command=cmd))
        ready_deadline = time.monotonic()+120
        while not all((args.output/(Path(r['output']).name+'-ready.json')).exists() for r in runs):
            if any(p.poll() is not None for _,p,_ in children): raise RuntimeError('CHILD_FAILED_BEFORE_BARRIER')
            if time.monotonic()>ready_deadline: raise TimeoutError('PARENT_BARRIER_TIMEOUT')
            time.sleep(.5)
        write(barrier, dict(released_at=time.time(),admission=host_sample()))
        started = time.monotonic(); checked = set(); early = {}
        while any(p.poll() is None for _,p,_ in children):
            for row,proc,log in children:
                name = Path(row['output']).name
                if name not in checked and (time.monotonic()-started >= 180 or proc.poll() is not None):
                    state = early_state(Path(row['output']),row['kind'],log)
                    state.update(checked_at=time.time(),elapsed_since_barrier_s=time.monotonic()-started)
                    if not state['ok']:
                        stop_owned(proc); state['EXIT'] = proc.returncode
                    early[name]=state; checked.add(name)
                    write(args.output/'early-check.json',early)
            if time.monotonic()-started > 1800: raise TimeoutError('FINITE_BATCH_BUDGET')
            time.sleep(1.)
        pairs = []; failures=[]
        for kind in ('s3','ego'):
            for i in range(1,5):
                try: pairs.append(compare_pair(args.output/f'{kind}-p{i}-eager',args.output/f'{kind}-p{i}-lazy-v1',kind))
                except Exception as e: failures.append(dict(kind=kind,pair=i,error=str(e)))
        summaries = {}
        for kind in ('s3','ego'):
            valid = [r for r in pairs if r['kind']==kind and r['eligible']]
            summaries[kind] = dict(n=len(valid),N=4)
            for metric in ('wall','cpu'):
                ratios = [r[metric+'_ratio_b_over_a'] for r in valid]
                summaries[kind][metric] = dict(median=statistics.median(ratios) if ratios else None,
                    range=[min(ratios),max(ratios)] if ratios else None,ratios=ratios)
        write(args.output/'comparison.json',dict(schema='ugrp.lazy_camera_paired.v1',source=args.expected_source_sha,
            cases=summaries,pairs=pairs,failures=failures,early_checks=early,
            exit_codes={Path(r['output']).name:p.returncode for r,p,_ in children},
            projection='JSON key order and only 18 registered measured inference quantiles; raw proofs retained',
            adopted=False,default='eager'))
        return int(bool(failures) or any(not r['eligible'] for r in pairs) or any(not v['ok'] for v in early.values()))
    finally:
        cleanup_children(children,args.output)


@interruptible
def main():
    p = argparse.ArgumentParser(); p.add_argument('--kind', choices=('s3','ego','abba','paired'), required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--render-mode', choices=ORDER[:2], default='eager')
    p.add_argument('--sim-s', type=float, choices=(5.,60.), default=60.)
    p.add_argument('--parent-lease-pid', type=int)
    p.add_argument('--parent-batch', type=Path)
    p.add_argument('--start-barrier', type=Path)
    p.add_argument('--archive-manifest', type=Path, required=True)
    p.add_argument('--archive-manifest-sha256', required=True)
    args = p.parse_args(); host_guard(args.expected_source_sha)
    if args.output.exists(): raise ValueError('PRESERVE_EXISTING_OUTPUT')
    from scripts import agent_lock
    lock_root = ROOT.parent.parent/'agent-locks'
    if args.kind == 'paired':
        args.output.mkdir(parents=True, exist_ok=False)
        return paired_cohort(args)
    if args.kind != 'abba':
        if args.parent_batch:
            validate_parent_batch(args)
            return run_one(args)
        held = agent_lock.status(lock_root)
        if not (held and held['pid_alive'] and held['timing_sensitive'] and
                held['owner'] == 'codex' and held['branch'] == 'codex/sim-speed-ctrl2' and
                held['pid'] == args.parent_lease_pid == os.getppid()):
            raise ValueError('LIVE_PARENT_LEASE_REQUIRED')
        return run_one(args)
    # Atomic admission before acquiring a lease; no finally may write into an
    # existing run, even if a competing invocation races for the same path.
    args.output.mkdir(parents=True, exist_ok=False)
    held = agent_lock.acquire(lock_root, owner='codex', branch='codex/sim-speed-ctrl2',
        purpose='speedctrl3 Oracle camera ABBA after S3 research', pid=os.getpid(),
        expected_minutes=90, timing_sensitive=True)
    try:
        return cohort(args)
    finally:
        try:
            write(args.output/'lock.json', held)
        finally:
            current = agent_lock.status(lock_root)
            if current and all(current[k] == held[k] for k in ('owner','pid','branch','acquired_unix')):
                agent_lock.release(lock_root, owner='codex')


if __name__ == '__main__': raise SystemExit(main())
