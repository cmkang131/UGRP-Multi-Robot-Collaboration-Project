"""DEV-ONLY checkpoint / resume for v98 pair stage probes (scripts/run_pair_highpose.py).

Why: an ``align_to_carry`` probe replays the whole route from the dock (about 500 SIM s, 40-90 min wall) while a
fix usually only changes behaviour near the failure. This tool saves the whole run state at loop boundaries and
restarts a probe from a saved mid-route state.

What is saved (one pickle per checkpoint, the whole Python object graph, cloudpickle + reducers):
* the physics owner (``backend``): MuJoCo ``MjModel``/``MjData`` (pickled whole: qpos/qvel/act, ``qacc_warmstart``,
  contact/constraint buffers, ``time``), the world's Python state, the command ports, the frame counter and the
  issued-command table;
* the whole controller runtime of both robots (``runtime``): PF particles/weights/numpy ``Generator`` states,
  command history, status channel, timers, executors, guards, controller logs;
* the host loop state: tick index, ``start``, per-robot command counters, the case ``result`` dict;
* process RNGs: ``random.getstate()`` and the legacy ``np.random`` state;
* the output prefix: byte offset + sha256 of every open jsonl stream and sha256 of every other written file
  (frames are not copied; their sha256 rows are in ``frames.jsonl``).

Not pickled, recreated on load (reducers): thread locks (must be unheld at the loop boundary), the world's
render ``ThreadPoolExecutor`` and both ``mujoco.Renderer`` GL contexts (recreated on the new render thread with the
same model, size and owner rules; the render profile is model-level XML, so nothing renderer-side is lost), open
jsonl streams (prefix copied, sha256-checked, reopened for append), paths under the old case directory (remapped to
the new one). A view into a MuJoCo buffer (ndarray whose base is a PyCapsule) or a pending Future is refused at save
time instead of being silently copied.

Rules (#363 dev speed-up, 2026-10-05):
* Resumed runs are DEV diagnostics: labelled ``resumed_from=<checkpoint sha256>``, cohort
  ``v98-dev-resumed-diagnostic``, never evidence and never pooled. Final validation stays a continuous run.
* Resuming with changed controller code needs ``--allow-code-change`` and records both code SHAs.
* Default off: without this tool ``student_run_case(dev_checkpoint=None)`` runs byte-identically.
* Nothing here reads ground truth into control; it only copies state that already exists.
"""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
import errno
import functools
import gc
import hashlib
import io
import json
import os
from pathlib import Path, PurePath
import platform
import random
import shutil
import subprocess
import sys
import threading
import time
import types
import zlib

import numpy as np

SCHEMA = 'ugrp.dev_pair_checkpoint.v1'
RESUMED_COHORT = 'v98-dev-resumed-diagnostic'
RESUMED_LABELS = {'run_status': 'DEV_RESUMED_DIAGNOSTIC', 'cohort_role': 'DEV_RESUMED_DIAGNOSTIC',
                  'tensorboard_cohort': RESUMED_COHORT, 'confirmation_sample': False, 'promotable': False,
                  'measured_sim_evidence': False, 'research_result': False, 'evidence': False, 'pooled': False}
EPS = 1e-9
_LOCK = type(threading.Lock())
_RLOCK = type(threading.RLock())
_LOAD = {'out': None}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, limit=None):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        left = limit
        while left is None or left > 0:
            chunk = stream.read(1 << 20 if left is None else min(1 << 20, left))
            if not chunk:
                break
            h.update(chunk)
            if left is not None:
                left -= len(chunk)
    if left not in (None, 0):
        raise ValueError(f'{path}: shorter than the recorded prefix')
    return h.hexdigest()


def git(*args, cwd=None):
    from harness import zone_pair_highpose_contract as contract
    return subprocess.check_output(['git', *args], cwd=cwd or contract.ROOT, text=True).strip()


def code_identity():
    return {'head': git('rev-parse', 'HEAD'),
            'dirty': bool(git('status', '--porcelain', '--untracked-files=all')),
            'branch': git('branch', '--show-current')}


def versions():
    import cloudpickle
    import mujoco
    return {'python': sys.version, 'platform': platform.platform(), 'mujoco': mujoco.__version__,
            'numpy': np.__version__, 'cloudpickle': cloudpickle.__version__,
            'PYTHONHASHSEED': os.environ.get('PYTHONHASHSEED')}


# ---------------------------------------------------------------------------------------------------------------
# Pickling
class Slot:
    """Placeholder for a resource recreated after load. Must not survive restore()."""
    def __init__(self, kind, key):
        self.kind, self.key = kind, key

    def __reduce__(self):
        raise TypeError('a recreate-on-load placeholder was pickled again')

    def __repr__(self):
        return f'Slot({self.kind!r}, {self.key!r})'


def _slot(kind, key):
    return Slot(kind, key)


def _fresh_lock():
    return threading.Lock()


def _fresh_rlock():
    return threading.RLock()


def _out_path(relative):
    if _LOAD['out'] is None:
        raise RuntimeError('checkpoint load without a target case directory')
    return _LOAD['out'] if relative == '.' else _LOAD['out'] / relative


MJV_STRUCTS = ('MjvOption', 'MjvCamera', 'MjvPerturb')


def _mjv_fields(obj):
    fields = {}
    for name in dir(obj):
        if name.startswith('_'):
            continue
        value = getattr(obj, name)
        if callable(value):
            continue
        fields[name] = np.array(value, copy=True) if isinstance(value, np.ndarray) else value
    return fields


def _mjv_struct(kind, fields):
    import mujoco
    obj = getattr(mujoco, kind)()
    for name, value in fields.items():
        if isinstance(value, np.ndarray):
            getattr(obj, name)[...] = value
        else:
            setattr(obj, name, value)
    if any(not np.array_equal(np.asarray(getattr(obj, k)), np.asarray(v)) for k, v in fields.items()):
        raise RuntimeError(f'{kind} field restore mismatch')
    return obj


def _new_plain(cls):
    return cls.__new__(cls)


def _set_plain_dict(obj, state):
    obj.__dict__.update(state)
    return obj


def _mujoco_view(array):
    seen = 0
    base = array
    while isinstance(base, np.ndarray) and base.base is not None and seen < 64:
        base, seen = base.base, seen + 1
    return type(base).__name__ == 'PyCapsule' and base is not array


class CheckpointPickler:
    """cloudpickle.Pickler with recreate-on-load reducers (subclassed lazily so cloudpickle stays optional)."""

    def __new__(cls, file, *, out, renderers, streams):
        import cloudpickle
        import mujoco

        class _Pickler(cloudpickle.Pickler):
            def reducer_override(self, obj):
                kind = type(obj)
                if kind is _LOCK:
                    if obj.locked():
                        raise RuntimeError('lock held at the checkpoint boundary')
                    return _fresh_lock, ()
                if kind is _RLOCK:
                    if not repr(obj).startswith('<unlocked'):
                        raise RuntimeError('RLock held at the checkpoint boundary')
                    return _fresh_rlock, ()
                if isinstance(obj, ThreadPoolExecutor):
                    return _slot, ('executor', 'render')
                if isinstance(obj, mujoco.Renderer):
                    key = renderer_keys.get(id(obj))
                    if key is None:
                        raise RuntimeError('unknown mujoco.Renderer in the object graph')
                    return _slot, ('renderer', key)
                if isinstance(obj, io.IOBase):
                    key = stream_keys.get(id(obj))
                    if key is None:
                        raise RuntimeError(f'unknown open file in the object graph: {obj!r}')
                    return _slot, ('stream', key)
                if kind.__module__.startswith('mujoco') and kind.__name__ in MJV_STRUCTS:
                    return _mjv_struct, (kind.__name__, _mjv_fields(obj))
                if not isinstance(obj, type) and hasattr(obj, '__dict__') and kind.__module__ != 'builtins':
                    own = {k for c in kind.__mro__[:-1] for k in vars(c)}
                    if '__getattr__' in own and not own & {'__reduce__', '__reduce_ex__', '__getstate__',
                                                           '__setstate__', '__getnewargs__', '__getnewargs_ex__',
                                                           '__slots__'}:
                        # Delegating __getattr__: default unpickling probes __setstate__ on the empty instance
                        # and recurses through it. Rebuild with an explicit state setter (same __dict__).
                        return _new_plain, (kind,), dict(vars(obj)), None, None, _set_plain_dict
                if isinstance(obj, Future):
                    raise RuntimeError('pending Future in the object graph')
                if isinstance(obj, PurePath) and obj.is_absolute():
                    try:
                        relative = Path(obj).relative_to(out_dir)
                    except ValueError:
                        pass
                    else:
                        return _out_path, (relative.as_posix(),)
                if kind is np.ndarray and _mujoco_view(obj):
                    raise RuntimeError(f'ndarray view into a MuJoCo buffer (shape {obj.shape}) would be copied')
                return super().reducer_override(obj)

        renderer_keys = {id(r): k for k, r in renderers.items() if r is not None}
        stream_keys = {id(f): k for k, f in streams.items()}
        out_dir = Path(out).absolute()
        return _Pickler(file, protocol=5)


def walk_graph(roots, visit, limit=5_000_000):
    """BFS over gc referents (Python objects only); visit(obj) for each, once."""
    seen, queue = set(), deque(roots)
    while queue:
        obj = queue.popleft()
        if id(obj) in seen or isinstance(obj, (type, types.ModuleType)):
            continue
        seen.add(id(obj))
        if len(seen) > limit:
            raise RuntimeError('object graph walk limit exceeded')
        visit(obj)
        if isinstance(obj, (str, bytes, int, float, bool, np.ndarray)) or obj is None:
            continue
        queue.extend(gc.get_referents(obj))
    return len(seen)


def module_table():
    """Repository modules loaded now (some by path via sys.path inserts, e.g. VIS3 / markerless_probe)."""
    from harness import zone_pair_highpose_contract as contract
    root = Path(contract.ROOT).resolve()
    table = {}
    for name, module in list(sys.modules.items()):
        file = getattr(module, '__file__', None)
        if file and Path(file).resolve().is_relative_to(root):
            table[name] = str(Path(file).resolve())
    return {'sys_path': list(sys.path), 'modules': table}


def load_module_table(table):
    """Recreate the import state a checkpoint's by-reference pickles need (before unpickling)."""
    import importlib
    import importlib.util
    missing = [p for p in table['sys_path'] if p not in sys.path]
    sys.path[0:0] = missing
    loaded = []
    for name, file in table['modules'].items():
        if name in sys.modules:
            continue
        try:
            importlib.import_module(name)
        except ImportError:
            spec = importlib.util.spec_from_file_location(name, file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        loaded.append(name)
    return {'sys_path_added': missing, 'modules_loaded': len(loaded)}


# ---------------------------------------------------------------------------------------------------------------
class DevCheckpoint:
    """Hook object for ``student_run_case(dev_checkpoint=...)``.

    Save mode: ``at_tick`` saves at the selected loop boundaries (top of tick i, before eval_sample/capture).
    Resume mode: ``restore`` replaces the fresh setup; ``at_tick`` only applies ``stop_at_sim_s``.
    """

    def __init__(self, *, checkpoint_dir=None, every_s=None, at_sim_s=(), after_carry_go_s=None,
                 stop_at_sim_s=None, resume=None):
        self.dir = None if checkpoint_dir is None else Path(checkpoint_dir)
        self.every_s, self.at_sim_s = every_s, sorted(float(t) for t in at_sim_s)
        self.after_carry_go_s, self.stop_at_sim_s = after_carry_go_s, stop_at_sim_s
        self.resume = resume            # dict: row (manifest), file, source_case_dir, labels
        self.saved, self.carry_go_seen, self.pending_go = [], 0, []
        self._next_every = None
        if self.resume is None and self.dir is None and stop_at_sim_s is None:
            raise ValueError('DevCheckpoint needs a checkpoint dir, a resume source or a stop time')

    @property
    def resuming(self):
        return self.resume is not None

    # -- trigger selection -------------------------------------------------------------------------------------
    def _carry_go_count(self, runtime):
        count = 0
        for session in getattr(getattr(runtime, 'team', None), 'sessions', None) or []:
            for endpoint in session['endpoints'].values():
                count += sum(1 for e in endpoint.events if e.get('event') == 'barrier_go' and e.get('barrier') == 'carry')
        return count

    def _triggers(self, now, start, runtime):
        reasons = []
        if self.every_s:
            if self._next_every is None:
                self._next_every = start + self.every_s
            if now >= self._next_every - EPS:
                reasons.append(f'every_{self.every_s:g}s')
                while self._next_every <= now + EPS:
                    self._next_every += self.every_s
        while self.at_sim_s and now >= self.at_sim_s[0] - EPS:
            reasons.append(f'at_sim_s_{self.at_sim_s.pop(0):g}')
        if self.after_carry_go_s is not None:
            count = self._carry_go_count(runtime)
            if count > self.carry_go_seen:
                self.pending_go.append(now + self.after_carry_go_s)
                self.carry_go_seen = count
            while self.pending_go and now >= self.pending_go[0] - EPS:
                self.pending_go.pop(0)
                reasons.append(f'carry_go_plus_{self.after_carry_go_s:g}s')
        return reasons

    def at_tick(self, i, *, backend, runtime, start, commands, result):
        now = backend.now
        if self.stop_at_sim_s is not None and now >= self.stop_at_sim_s - EPS:
            result['dev_stop'] = {'stop_at_sim_s': self.stop_at_sim_s, 'stopped_at_sim_s': now, 'tick': i,
                                  'note': 'DEV horizon stop before this tick; status is a dev diagnostic only'}
            return True
        if self.dir is not None and not self.resuming:
            reasons = self._triggers(now, start, runtime)
            if reasons:
                try:
                    self.save(i, backend=backend, runtime=runtime, start=start, commands=commands, result=result,
                              reasons=reasons)
                except Exception as exc:  # noqa: BLE001 - saving only reads state; a failed save never stops the run
                    result.setdefault('dev_checkpoint_errors', []).append(
                        {'tick': i, 'sim_s': now, 'type': type(exc).__name__, 'message': str(exc)[:500]})
        return False

    # -- save ----------------------------------------------------------------------------------------------------
    def save(self, i, *, backend, runtime, start, commands, result, reasons):
        t0 = time.perf_counter()
        out = Path(backend.out)
        world = backend.world
        if getattr(world, '_snapshot_broker', None) is not None:
            raise RuntimeError('snapshot render broker in use; checkpoint unsupported')
        streams = {}
        for relative, stream in backend.streams.items():
            stream.flush()
            streams[relative] = {'offset': stream.tell()}
        for relative, row in streams.items():
            row['prefix_sha256'] = sha256_file(out / relative, row['offset'])
        files = {}
        for path in sorted(out.rglob('*')):
            relative = path.relative_to(out).as_posix()
            if not path.is_file() or relative in streams or '/rgb/' in f'/{relative}':
                continue
            files[relative] = sha256_file(path)
        renderers = {'renderer': world.renderer, 'observer_renderer': world.observer_renderer}
        state = {'schema': SCHEMA, 'imports': module_table(), 'backend': backend, 'runtime': runtime,
                 'host': {'tick': i, 'start': start, 'commands': commands, 'result': result},
                 'rng': {'random': random.getstate(), 'np_legacy': np.random.get_state()}}
        buffer = io.BytesIO()
        CheckpointPickler(buffer, out=out, renderers=renderers, streams=backend.streams).dump(state)
        raw = buffer.getvalue()
        data = zlib.compress(raw, 1)
        self.dir.mkdir(parents=True, exist_ok=True)
        name = f'ckpt_{i:05d}_t{backend.now:09.3f}.pkl.zlib'
        target = self.dir / name
        with open(target, 'xb') as stream:
            stream.write(data)
        digest = sha256_bytes(data)
        row = {'schema': SCHEMA, 'file': name, 'sha256': digest, 'raw_sha256': sha256_bytes(raw),
               'bytes': len(data), 'raw_bytes': len(raw), 'tick': i, 'sim_s': backend.now,
               'check_sim_s': backend.now - start, 'start_sim_s': start, 'frame': backend.frame,
               'triggers': reasons, 'case_dir': str(out), 'streams': streams, 'files': files,
               'commands_issued': dict(commands), 'code': code_identity(), 'versions': versions(),
               'imports': state['imports'],
               'loadavg': list(os.getloadavg()), 'save_wall_s': round(time.perf_counter() - t0, 3),
               'boundary': 'top of tick i: before eval_sample/capture/step of tick i',
               'use': 'DEV diagnostics only; a resumed run is never evidence and never pooled'}
        with open(self.dir / 'manifest.jsonl', 'a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        (self.dir / (name + '.sha256')).write_text(f'{digest}  {name}\n')
        self.saved.append({k: row[k] for k in ('file', 'sha256', 'tick', 'sim_s', 'triggers', 'bytes')})
        result['dev_checkpoint_saving'] = {'dir': str(self.dir), 'manifest': 'manifest.jsonl',
                                           'count': len(self.saved), 'last': self.saved[-1]}

    # -- restore -------------------------------------------------------------------------------------------------
    def restore(self, out, result):
        row, path, source = self.resume['row'], Path(self.resume['file']), Path(self.resume['source_case_dir'])
        data = path.read_bytes()
        if sha256_bytes(data) != row['sha256']:
            raise ValueError('checkpoint sha256 differs from its manifest row')
        raw = zlib.decompress(data)
        if sha256_bytes(raw) != row['raw_sha256']:
            raise ValueError('checkpoint payload sha256 differs from its manifest row')
        out = Path(out)
        # Files the case wrote before this point (reset/scene/staging records) and every stream prefix.
        for relative, digest in row['files'].items():
            target = out / relative
            if target.exists():
                if sha256_file(target) != digest:
                    raise ValueError(f'{relative}: freshly written file differs from the checkpointed run')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
            if sha256_file(target) != digest:
                raise ValueError(f'{relative}: source file changed since the checkpoint')
        import pickle
        _LOAD['out'] = out.absolute()
        try:
            table = row.get('imports')
            if table is None:
                raise ValueError('checkpoint manifest row lacks its import table')
            self.import_report = load_module_table(table)
            state = pickle.loads(raw)
        finally:
            _LOAD['out'] = None
        if state.get('schema') != SCHEMA:
            raise ValueError('checkpoint schema mismatch')
        backend, runtime, host = state['backend'], state['runtime'], state['host']
        world = backend.world
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ugrp-mujoco-render')
        renderer, observer, thread_id = executor.submit(world._create_renderers).result(timeout=30.0)
        fresh = {('executor', 'render'): executor, ('renderer', 'renderer'): renderer,
                 ('renderer', 'observer_renderer'): observer}
        for owner in [world, *getattr(world, 'controllers', {}).values()]:
            for key, value in list(vars(owner).items()):
                if isinstance(value, Slot) and value.kind in ('executor', 'renderer'):
                    setattr(owner, key, fresh[(value.kind, value.key)])
        world._render_thread_id = thread_id
        world._frame_callback_thread_id = threading.get_ident()
        for relative, info in row['streams'].items():
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(source / relative, 'rb') as src, open(target, 'xb') as dst:
                dst.write(src.read(info['offset']))
            if sha256_file(target) != info['prefix_sha256']:
                raise ValueError(f'{relative}: stream prefix differs from the checkpoint record')
            if not isinstance(backend.streams.get(relative), Slot):
                raise ValueError(f'{relative}: stream missing from the restored backend')
            backend.streams[relative] = target.open('a', buffering=1)
        leftovers = []
        walk_graph([backend, runtime, host], lambda o: leftovers.append(repr(o)) if isinstance(o, Slot) else None)
        if leftovers:
            raise RuntimeError(f'unrestored placeholders after load: {leftovers[:5]}')
        random.setstate(state['rng']['random'])
        np.random.set_state(state['rng']['np_legacy'])
        saved = host['result']
        loadavg = result.get('loadavg_start')
        result.clear()
        result.update(saved)
        result.pop('dev_checkpoint_saving', None)
        result.update(RESUMED_LABELS)
        result['loadavg_start'] = loadavg
        result['loadavg_start_of_source_run'] = saved.get('loadavg_start')
        result['dev_resumed'] = self.resume['labels']
        return backend, runtime, host['start'], host['tick'], host['commands']


# ---------------------------------------------------------------------------------------------------------------
# CLI
def _manifest(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def find_checkpoint(path):
    path = Path(path).absolute()
    rows = [r for r in _manifest(path.parent / 'manifest.jsonl') if r['file'] == path.name]
    if len(rows) != 1:
        raise ValueError('checkpoint not registered exactly once in its manifest.jsonl')
    return rows[0]


def _require_dev_probe(argv):
    if '--stage-probe' not in ' '.join(argv) or 'dev-pilot' not in argv:
        raise ValueError('dev checkpoints are for DEV_PILOT stage probes only (--admission dev-pilot --stage-probe ...)')


def cmd_run(args, rest):
    """Continuous run through the unchanged runner main(), saving checkpoints (bytes otherwise unchanged)."""
    from scripts import run_pair_highpose as rph
    _require_dev_probe(rest)
    out = Path(rest[rest.index('--output') + 1])
    dc = DevCheckpoint(checkpoint_dir=out / 'checkpoints', every_s=args.every_s, at_sim_s=args.at_sim_s or (),
                       after_carry_go_s=args.after_carry_go_s, stop_at_sim_s=args.stop_at_sim_s)
    original = rph.student_run_case
    rph.student_run_case = functools.partial(original, dev_checkpoint=dc)
    try:
        code = rph.main(rest)
    finally:
        rph.student_run_case = original
    print(json.dumps({'checkpoints': dc.saved}, ensure_ascii=False, indent=1))
    return code


def cmd_resume(args):
    from harness import zone_pair_highpose_contract as contract
    from scripts import run_pair_highpose as rph
    from scripts.run_final_environment_checks import write, check_source
    from scripts.agent_lock import DEFAULT_ROOT
    from scripts.agent_sim_slots import require_sim_slot, sim_snapshot
    ckpt = Path(args.checkpoint).absolute()
    row = find_checkpoint(ckpt)
    source_case = Path(row['case_dir'])
    source_run = source_case.parent
    plan = json.loads((source_run / 'plan.json').read_text())
    bundle = json.loads((source_case / 'bundle.json').read_text())
    probe = (plan.get('stage_probe') or {}).get('stage')
    if plan.get('admission_mode') != contract.DEV_PILOT or probe is None:
        raise ValueError('resume is for DEV_PILOT stage probes only')
    now = code_identity()
    ckpt_code = row['code']['head']
    changed = now['head'] != ckpt_code
    if now['dirty']:
        raise ValueError('source is dirty; commit before a resumed run (its code SHA must be recorded)')
    if changed and not args.allow_code_change:
        raise ValueError(f'HEAD {now["head"][:12]} differs from the checkpoint code {ckpt_code[:12]}; '
                         'pass --allow-code-change (diagnosis only, recorded)')
    if not changed:
        check_source(ckpt_code)
    primary = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir')).parent
    output = Path(args.output)
    if not output.is_absolute() or not output.resolve().is_relative_to((primary / 'outputs').resolve()):
        raise ValueError('raw output must be absolute under primary outputs')
    if output.exists():
        raise FileExistsError(output)
    if shutil.disk_usage(primary).free < 10 * 1024**3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    branch = now['branch']
    require_sim_slot(DEFAULT_ROOT, slot=args.sim_slot, owner=args.lock_owner, branch=branch)
    labels = {'resumed_from': row['sha256'], 'checkpoint_file': str(ckpt), 'checkpoint_tick': row['tick'],
              'checkpoint_sim_s': row['sim_s'], 'checkpoint_check_sim_s': row['check_sim_s'],
              'source_run': str(source_run), 'code_sha_at_checkpoint': ckpt_code, 'code_sha_now': now['head'],
              'code_changed': changed, 'allow_code_change': bool(args.allow_code_change),
              'stop_at_sim_s': args.stop_at_sim_s, 'evidence': False, 'pooled': False,
              'rule': 'DEV diagnostic only: never evidence, never pooled; final validation stays a continuous run',
              'by_value_code_note': 'closures pickled by value (e.g. staging tick wrappers, cap_world_steps) keep '
                                    'the checkpoint code even when module code changed'}
    output.mkdir(parents=True)
    calibration = output / 'dev_pilot_calibration.json'
    shutil.copyfile(source_run / 'dev_pilot_calibration.json', calibration)
    if sha256_file(calibration) != plan['calibration_sha256']:
        raise ValueError('source calibration copy sha256 differs from the plan')
    host_start = sim_snapshot(DEFAULT_ROOT)
    write(output / 'plan.json', {**plan, **RESUMED_LABELS, 'dev_resumed': labels, 'execution_started': True,
                                 'host_start': host_start, 'sim_slot': args.sim_slot, 'lock_mode': 'sim_slot'})
    dc = DevCheckpoint(stop_at_sim_s=args.stop_at_sim_s,
                       resume={'row': row, 'file': ckpt, 'source_case_dir': source_case, 'labels': labels})
    case_dir = output / bundle['case']['id']
    result = rph.student_run_case(bundle, case_dir, seed=plan['seed'], backend_factory=None,
                                  calibration=calibration, calibration_sha=plan['calibration_sha256'],
                                  probe=probe, dev_checkpoint=dc)
    write(case_dir / 'dev_resumed.json', labels)
    write(output / 'result.json', {**RESUMED_LABELS, 'status': result['status'], 'dev_resumed': labels,
                                   'cases': [result], 'host_start': host_start, 'host_end': sim_snapshot(DEFAULT_ROOT),
                                   'physical_success': None})
    print(json.dumps({k: result.get(k) for k in ('status', 'check_sim_s', 'dev_stop', 'failure')}, ensure_ascii=False))
    return int(result['status'] == 'HOST_ERROR')


WALL_KEYS = ('wall',)


def _strip_wall(value):
    if isinstance(value, dict):
        return {k: _strip_wall(v) for k, v in value.items() if not any(w in k.lower() for w in WALL_KEYS)}
    if isinstance(value, list):
        return [_strip_wall(v) for v in value]
    return value


def _row_time(line):
    row = json.loads(line)
    for key in ('t', 'sim_time', 'sim_s'):
        if isinstance(row.get(key), (int, float)):
            return float(row[key])
    return None


def _list_prefix_diffs(cont, res, path, out, from_sim_s):
    """Every list in the resumed record must be a prefix of the continuous one (wall-time keys stripped)."""
    if isinstance(res, dict) and isinstance(cont, dict):
        for key in res:
            if key in cont and not any(w in key.lower() for w in WALL_KEYS):
                _list_prefix_diffs(cont[key], res[key], f'{path}/{key}', out, from_sim_s)
    elif isinstance(res, list) and isinstance(cont, list):
        rows = [r for r in res if isinstance(r, dict) and ('event' in r or 'sim_s' in r)]
        if rows:
            out['event_lists'] += 1
            after = sum(1 for r in res if isinstance(r, dict) and isinstance(r.get('sim_s'), (int, float))
                        and r['sim_s'] >= from_sim_s - EPS)
            out['event_rows_after_T'] += after
            if len(res) > len(cont):
                out['divergences'].append({'path': path, 'kind': 'resumed list longer', 'resumed': len(res),
                                           'continuous': len(cont)})
                return
            for index, (a, b) in enumerate(zip(cont, res)):
                if _strip_wall(a) != _strip_wall(b):
                    out['divergences'].append({'path': path, 'kind': 'row differs', 'index': index,
                                               'sim_s': b.get('sim_s') if isinstance(b, dict) else None})
                    return
        else:
            for index, (a, b) in enumerate(zip(cont, res)):
                _list_prefix_diffs(a, b, f'{path}[{index}]', out, from_sim_s)


def compare(continuous, resumed, from_sim_s, min_horizon_s=60.):
    """Bit-identity gate: resumed case dir vs the continuous case dir after SIM time T (from_sim_s)."""
    continuous, resumed = Path(continuous), Path(resumed)
    report = {'schema': SCHEMA + '.compare', 'continuous': str(continuous), 'resumed': str(resumed),
              'from_sim_s': from_sim_s, 'min_horizon_s': min_horizon_s, 'streams': {}, 'frames': {},
              'record': {}, 'divergences': []}
    last_t = None
    for path in sorted(resumed.rglob('*.jsonl')):
        relative = path.relative_to(resumed).as_posix()
        other = continuous / relative
        res = path.read_bytes()
        if not other.is_file():
            report['divergences'].append({'stream': relative, 'kind': 'missing in continuous run'})
            continue
        cont = other.read_bytes()[:len(res)]
        lines = res.splitlines(keepends=True)
        after = [ln for ln in lines if (_row_time(ln) or -1.) >= from_sim_s - EPS]
        entry = {'bytes_compared': len(res), 'rows': len(lines), 'rows_after_T': len(after),
                 'identical_prefix': cont == res, 'sha256_resumed': sha256_bytes(res),
                 'sha256_continuous_same_length_prefix': sha256_bytes(cont)}
        times = [t for t in map(_row_time, lines) if t is not None]
        if times:
            entry['last_t'] = max(times)
            last_t = entry['last_t'] if last_t is None else max(last_t, entry['last_t'])
        if cont != res:
            cl = cont.splitlines(keepends=True)
            index = next((k for k, (a, b) in enumerate(zip(cl, lines)) if a != b), min(len(cl), len(lines)))
            entry['first_divergent_row'] = index
            entry['first_divergent_t'] = _row_time(lines[index]) if index < len(lines) else None
            report['divergences'].append({'stream': relative, 'kind': 'bytes differ', 'row': index,
                                          't': entry['first_divergent_t']})
        report['streams'][relative] = entry
    for path in sorted(resumed.rglob('rgb/*')):
        relative = path.relative_to(resumed).as_posix()
        other = continuous / relative
        robot = relative.split('/')[1]
        frames = report['frames'].setdefault(robot, {'compared': 0, 'identical': 0, 'first_divergent': None})
        frames['compared'] += 1
        if other.is_file() and sha256_file(other) == sha256_file(path):
            frames['identical'] += 1
        elif frames['first_divergent'] is None:
            frames['first_divergent'] = relative
            report['divergences'].append({'frame': relative, 'kind': 'frame sha256 differs or missing'})
    rec = {'event_lists': 0, 'event_rows_after_T': 0, 'divergences': []}
    _list_prefix_diffs(json.loads((continuous / 'student_record.json').read_text()),
                       json.loads((resumed / 'student_record.json').read_text()), '', rec, from_sim_s)
    report['record'] = {k: rec[k] for k in ('event_lists', 'event_rows_after_T')}
    report['divergences'] += [{'record': d} for d in rec['divergences']]
    report['last_t'] = last_t
    report['horizon_s'] = None if last_t is None else last_t - from_sim_s
    report['frames_after_T'] = {r: v['compared'] for r, v in report['frames'].items()}
    report['bit_identical'] = (not report['divergences'] and report['horizon_s'] is not None
                               and report['horizon_s'] >= min_horizon_s - 1e-6
                               and all(v['compared'] > 0 for v in report['frames'].values()))
    return report


def cmd_compare(args):
    report = compare(args.continuous, args.resumed, args.from_sim_s, args.min_horizon_s)
    text = json.dumps(report, ensure_ascii=False, indent=1, allow_nan=False) + '\n'
    if args.report:
        Path(args.report).write_text(text)
    print(json.dumps({k: report[k] for k in ('bit_identical', 'horizon_s', 'frames_after_T', 'record')}
                     | {'divergences': report['divergences'][:10]}, ensure_ascii=False))
    return 0 if report['bit_identical'] else 1


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run', help='continuous DEV stage probe that saves checkpoints; other args go to '
                                     'scripts/run_pair_highpose.py unchanged')
    run.add_argument('--every-s', type=float, help='save every N SIM s after start')
    run.add_argument('--at-sim-s', type=float, action='append', help='save at the first tick >= this world SIM time')
    run.add_argument('--after-carry-go-s', type=float,
                     help='save this many SIM s after each new carry barrier GO (lands inside the carry leg)')
    run.add_argument('--stop-at-sim-s', type=float, help='DEV horizon: stop before the first tick >= this SIM time')
    resume = sub.add_parser('resume', help='resume a saved checkpoint into a new output directory')
    resume.add_argument('--checkpoint', required=True, type=Path)
    resume.add_argument('--output', required=True, type=Path)
    resume.add_argument('--lock-owner', required=True, choices=('codex', 'claude', 'kiro'))
    resume.add_argument('--sim-slot', required=True)
    resume.add_argument('--stop-at-sim-s', type=float, help='DEV horizon: stop before the first tick >= this SIM time')
    resume.add_argument('--allow-code-change', action='store_true',
                        help='resume with HEAD != checkpoint code SHA (diagnosis only; both SHAs recorded)')
    cmp_ = sub.add_parser('compare', help='bit-identity gate: resumed case dir vs continuous case dir after T')
    cmp_.add_argument('--continuous', required=True, type=Path, help='continuous case directory')
    cmp_.add_argument('--resumed', required=True, type=Path, help='resumed case directory')
    cmp_.add_argument('--from-sim-s', required=True, type=float, help='checkpoint SIM time T')
    cmp_.add_argument('--min-horizon-s', type=float, default=60.)
    cmp_.add_argument('--report', type=Path)
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args, rest = parser().parse_known_args(argv)
    if args.command == 'run':
        return cmd_run(args, rest)
    if rest:
        raise ValueError(f'unknown arguments: {rest}')
    return cmd_compare(args) if args.command == 'compare' else cmd_resume(args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(2)
