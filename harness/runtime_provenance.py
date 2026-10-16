"""Opt-in Python audit provenance prototype; NOT a physics runner or sandbox.

Observed reads are added to, never subtracted from, a v2 static contract. The
isolated child permits read-only Python/stdlib cases. Native workers need an OS
tracer + immutable sandbox (docs/runtime_provenance.md), not extra AST heuristics.
"""
from __future__ import annotations

from collections.abc import Mapping
import atexit
import hashlib
import importlib.metadata
import importlib.machinery
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import threading
from types import ModuleType

SCHEMA = 'ugrp.execution_runtime_seal.v2'
PROFILE = 'python-audit-offline-v1'
EXIT_VIOLATION = 86
ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('harness/runtime_provenance.py', 'scripts/trace_execution_dependencies.py')
LIMITATIONS = [
    'Python audit events only; a reproducibility check, not a security sandbox',
    'Native I/O, C getenv, child workers and physics require an OS backend',
    'File metadata queries and concurrent filesystem races require an immutable sandbox',
    'Bootstrap Python/stdlib and preloaded native libraries are trusted',
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _used_path(path):
    """Absolutize without erasing symlink/.. traversal or the caller's spelling."""
    path = os.fsdecode(path)
    return path if os.path.isabs(path) else os.path.join(os.getcwd(), path)


def _path_identity(path):
    """Resolve components in filesystem order and record every traversed link.

    Do not normpath/abspath first: alias/.. means the target's parent. Expanding
    each link before processing the next component also captures links inside
    link targets, including links no longer present in the final real path.
    """
    used = _used_path(path)
    pending = used.split(os.sep)
    resolved = os.sep
    links = {}
    traversals = 0
    while pending:
        part = pending.pop(0)
        if part in ('', '.'):
            continue
        if part == '..':
            # Missing/non-directory prefix followed by .. cannot be represented
            # as an ordinary absent leaf. Reject instead of pinning another file.
            if not os.path.isdir(resolved):
                raise ValueError('unresolvable parent traversal: ' + used)
            resolved = os.path.dirname(resolved)
            continue
        candidate = os.path.join(resolved, part)
        if os.path.islink(candidate):
            traversals += 1
            if traversals > 40:
                raise ValueError('symlink chain too long or cyclic: ' + used)
            target = os.readlink(candidate)
            links[candidate] = target
            if os.path.isabs(target):
                resolved = os.sep
            pending = target.split(os.sep) + pending
        else:
            resolved = candidate
    # realpath is authoritative; the traversal above inventories bindings and
    # normalizes .. only after following links, not by lexical cancellation.
    real = os.path.realpath(used)
    if real != resolved:
        raise ValueError('path resolution disagrees: ' + used)
    return {'path_used': used, 'realpath': real, 'links': links}


def file_state(path):
    """Pin bytes and the used-to-real path binding, including symlink chains."""
    binding = _path_identity(path)
    real = Path(binding['realpath'])
    if not real.exists():
        return {**binding, 'sha256': None}
    if not real.is_file():
        raise ValueError('not a regular input file: ' + str(path))
    hasher = hashlib.sha256()
    with real.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return {**binding, 'sha256': hasher.hexdigest()}


def _output_artifacts(paths):
    """Reserve exact tool-owned leaf paths, never a filename pattern or subtree."""
    artifacts = []
    for path in paths:
        binding = _path_identity(path)
        if (not Path(binding['realpath']).parent.is_dir() or os.path.islink(path)
                or (os.path.lexists(path) and not os.path.isfile(path))):
            raise ValueError('tool output must be an absent or regular file: ' + str(path))
        artifacts.append(binding)
    return artifacts


def _output_paths(artifacts):
    return {artifact['realpath'] for artifact in artifacts}


def directory_state(path, output_artifacts=()):
    """Pin directory names/types/link bindings, not file contents or stat data."""
    binding = _path_identity(path)
    outputs = _output_paths(output_artifacts)
    try:
        with os.scandir(path) as entries:
            members = []
            for entry in entries:
                if os.path.join(binding['realpath'], os.fsdecode(entry.name)) in outputs:
                    continue
                kind = ('symlink' if entry.is_symlink() else
                        'directory' if entry.is_dir() else 'file' if entry.is_file() else 'other')
                members.append([entry.name, kind,
                                os.readlink(entry.path) if kind == 'symlink' else None])
        return {**binding, 'entries': sorted(members), 'error': None}
    except (FileNotFoundError, NotADirectoryError) as exc:
        return {**binding, 'entries': None, 'error': type(exc).__name__}


def identity():
    return {'python': sys.version, 'implementation': sys.implementation.name,
            'cache_tag': sys.implementation.cache_tag, 'platform': platform.platform(),
            'executable': file_state(sys.executable),
            'packages': sorted([d.metadata['Name'], d.version]
                               for d in importlib.metadata.distributions())}


def tool_identity():
    return {p: file_state(ROOT / p) for p in SOURCES}


def _environment(names):
    if not isinstance(names, list) or any(not isinstance(n, str) or not re.fullmatch(
            r'[A-Za-z_][A-Za-z_0-9]*', n) for n in names):
        raise ValueError('env_names must list non-secret setting names')
    # This tool is offline: no credentials are inherited or serialized, even as hashes.
    if any(re.search(r'KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|COOKIE|AUTH', n, re.I) for n in names):
        raise ValueError('credential-like environment names are not supported')
    if any(n.startswith(('PYTHON', 'LD_', 'DYLD_')) for n in names):
        raise ValueError('interpreter/loader startup environment is not supported')
    return {n: os.environ[n] for n in names if n in os.environ}


def _case(root, value):
    if not isinstance(value, dict) or set(value) != {'entry', 'args'}:
        raise ValueError('case needs entry and args')
    path = Path(value['entry'])
    if path.is_absolute() or '..' in path.parts or not str(path).endswith('.py'):
        raise ValueError('case entry must be a repository Python script')
    if not (root / path).resolve().is_relative_to(root) or not (root / path).is_file():
        raise ValueError('case entry is missing or outside the repository')
    if not isinstance(value['args'], list) or any(not isinstance(a, str) for a in value['args']):
        raise ValueError('case args must be strings')
    return {'entry': str(path), 'args': value['args']}


def _policy(value):
    value = value or {'environment': 'abort', 'identity': 'abort', 'reason': ''}
    if (set(value) != {'environment', 'identity', 'reason'}
            or any(value[k] not in ('abort', 'warn') for k in ('environment', 'identity'))
            or not isinstance(value['reason'], str)
            or ('warn' in value.values() and not value['reason'].strip())):
        raise ValueError('policy requires abort/warn and a reason for warnings')
    return dict(value)


def _child(root, case, env_names, seed, expected=None, policy=None, timeout=30,
           output_artifacts=()):
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    request = {'root': str(root), 'case': case, 'seed': seed, 'expected': expected,
               'policy': policy or _policy(None), 'output_artifacts': output_artifacts}
    # Report FD is opened by the trusted parent; policy code cannot mask a caught
    # violation because the hook writes the report and calls os._exit immediately.
    with tempfile.TemporaryFile() as report:
        try:
            result = subprocess.run(
                [sys.executable, '-I', '-S', '-B', str(Path(__file__).resolve()), str(report.fileno())],
                input=json.dumps(request), text=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, cwd=root,
                env=_environment(env_names), pass_fds=(report.fileno(),), timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {'status': 'HOST_ERROR', 'reason': 'trace-timeout'}
        report.seek(0)
        raw = report.read()
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        return {'status': 'HOST_ERROR', 'reason': 'missing-audit-report', 'exit_code': result.returncode}
    if result.returncode != (0 if value.get('status') == 'OK' else EXIT_VIOLATION):
        return {'status': 'HOST_ERROR', 'reason': 'audit-exit-mismatch'}
    return value


class TraceFailure(ValueError):
    """A failed case report is evidence, never a usable partial seal."""
    def __init__(self, case, report):
        self.report = {'case': case, **report}
        super().__init__('canonical trace failed: ' + str(report.get('reason')) + ': '
                         + str(report.get('detail')))


def trace_contract(static, *, expected_static_sha256, cases, root=ROOT,
                   env_names=None, policy=None, timeout=30, output_artifacts=()):
    """Execute canonical offline cases; do not turn failures into partial seals."""
    from harness.execution_dependency_contract import verify_contract
    root = Path(root).resolve()
    verify_contract(static, expected_sha256=expected_static_sha256, root=root)
    if not cases:
        raise ValueError('at least one canonical case is required')
    cases = [_case(root, c) for c in cases]
    if any(c['entry'] not in static['declaration']['entry_points'] for c in cases):
        raise ValueError('canonical entry must be declared in the static contract')
    env_names = sorted(set(env_names or []))
    _environment(env_names)
    policy = _policy(policy)
    artifacts = _output_artifacts(output_artifacts)
    initial_identity = identity()
    initial_tools = tool_identity()
    seed = [str(root / p) for p in static['source_sha256']]
    files, directories, environment, traces = {}, {}, {}, []
    for case in cases:
        result = _child(root, case, env_names, seed, policy=policy, timeout=timeout,
                        output_artifacts=artifacts)
        if result['status'] != 'OK':
            raise TraceFailure(case, result)
        for target, observed in ((files, result['files']), (directories, result['directories']),
                                 (environment, result['environment'])):
            for key, state in observed.items():
                if key in target and target[key] != state:
                    raise ValueError('canonical cases disagree on input: ' + key)
                target[key] = state
        traces.append({'case': case, 'events': result['events'],
                       'observed_files': result['observed_files'],
                       'observed_directories': sorted(result['directories'])})
    # A canonical run must not mutate its own registration, inputs or environment.
    verify_contract(static, expected_sha256=expected_static_sha256, root=root)
    if identity() != initial_identity or tool_identity() != initial_tools:
        raise ValueError('trace environment changed during capture')
    for path, state in files.items():
        if file_state(path) != state:
            raise ValueError('input changed during capture: ' + path)
    for path, state in directories.items():
        if directory_state(path, artifacts) != state:
            raise ValueError('directory changed during capture: ' + path)
    if _output_artifacts([a['path_used'] for a in artifacts]) != artifacts:
        raise ValueError('tool output binding changed during capture')
    body = {'schema': SCHEMA, 'profile': PROFILE, 'root': str(root), 'static': static,
            'cases': cases, 'files': files, 'directories': directories, 'environment': environment,
            'env_names': env_names, 'policy': policy, 'identity': initial_identity,
            'tools': initial_tools, 'traces': traces, 'limitations': LIMITATIONS,
            'output_artifacts': artifacts}
    return {**body, 'sha256': digest(body)}


def run_sealed(value, *, expected_sha256, root=ROOT, case_index=0, timeout=30):
    """Opt-in OFFLINE runner; no hook or registration changes in legacy runners."""
    from harness.execution_dependency_contract import verify_contract
    warnings = []
    try:
        if (not isinstance(value, dict) or value.get('schema') != SCHEMA or value.get('profile') != PROFILE
                or not re.fullmatch('[0-9a-f]{64}', expected_sha256)
                or value.get('sha256') != expected_sha256
                or digest({k: v for k, v in value.items() if k != 'sha256'}) != expected_sha256):
            raise ValueError('runtime seal digest/schema mismatch')
        root = Path(root).resolve()
        if str(root) != value['root']:
            raise ValueError('runtime seal is bound to the traced root')
        policy = _policy(value['policy'])
        if tool_identity() != value['tools']:
            raise ValueError('audit runner changed')
        if identity() != value['identity']:
            if policy['identity'] == 'abort':
                raise ValueError('interpreter/library identity drift')
            warnings.append('interpreter/library identity drift: ' + policy['reason'])
        verify_contract(value['static'], expected_sha256=value['static']['sha256'], root=root)
        artifacts = value.get('output_artifacts', [])
        if _output_artifacts([a['path_used'] for a in artifacts]) != artifacts:
            raise ValueError('sealed tool output binding drift')
        # Check the complete union, including unobserved static files and symlinks.
        for path, state in value['files'].items():
            if file_state(path) != state:
                raise ValueError('sealed file drift: ' + path)
        for path, state in value['directories'].items():
            if directory_state(path, artifacts) != state:
                raise ValueError('sealed directory drift: ' + path)
        if not isinstance(case_index, int) or not 0 <= case_index < len(value['cases']):
            raise ValueError('unsealed canonical case')
        case = _case(root, value['cases'][case_index])
        result = _child(root, case, value['env_names'], list(value['files']),
                        expected=value, policy=policy, timeout=timeout, output_artifacts=artifacts)
        result['warnings'] = warnings + result.get('warnings', [])
        return result
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {'status': 'HOST_ERROR', 'reason': 'seal-violation', 'detail': str(exc),
                'warnings': warnings}


class _Environment(Mapping):
    def __init__(self, guard, values, *, binary=False):
        self.guard, self.values, self.binary = guard, values, binary

    def __getitem__(self, key):
        name = os.fsdecode(key) if self.binary else key
        self.guard.env_read(name)
        value = self.values[name]
        return os.fsencode(value) if self.binary else value

    def __iter__(self):
        for key in self.values:
            self.guard.env_read(key)
            yield os.fsencode(key) if self.binary else key

    def __len__(self):
        # Even the size of the visible environment is an input.
        for key in self.values:
            self.guard.env_read(key)
        return len(self.values)

    def copy(self):
        """Return an independent dict through the same audited mapping reads."""
        return dict(self)


class _InputScandir:
    """Preserve scandir iteration/context/close while hiding reserved outputs."""
    def __init__(self, entries, visible):
        self.entries, self.visible = entries, visible

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            entry = next(self.entries)
            if self.visible(entry.name):
                return entry

    def close(self):
        self.entries.close()

    def __enter__(self):
        self.entries.__enter__()
        return self

    def __exit__(self, *args):
        return self.entries.__exit__(*args)


class _Audit:
    def __init__(self, request, fd):
        self.root = Path(request['root'])
        self.expected = request['expected']
        self.policy = request['policy']
        self.output_artifacts = request.get('output_artifacts', [])
        self.outputs = _output_paths(self.output_artifacts)
        self.fd = fd
        self.active = False
        self.local = threading.local()
        self.files, self.directories, self.environment, self.events = {}, {}, {}, {}
        self.observed = set()
        self.warnings = []
        self.values = dict(os.environ)
        self.stdlib = Path(os.__file__).resolve().parent

    def finish(self, status='OK', reason=None, detail=None):
        value = {'status': status, 'reason': reason, 'detail': detail,
                 'files': self.files, 'observed_files': sorted(self.observed),
                 'directories': self.directories,
                 'environment': self.environment, 'events': self.events, 'warnings': self.warnings}
        data = json.dumps(value).encode()
        while data:
            data = data[os.write(self.fd, data):]
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0 if status == 'OK' else EXIT_VIOLATION)

    def fail(self, detail):
        self.finish('HOST_ERROR', 'seal-violation', detail)

    def check_path(self, collection, path, state):
        """Match consumed identity, while requiring every used link to be sealed."""
        if self.expected:
            expected = self.expected[collection]
            payload = lambda s: {k: v for k, v in s.items() if k not in ('path_used', 'links')}
            known_links = {p: target for s in expected.values() for p, target in s['links'].items()}
            matched = any(payload(s) == payload(state) for s in expected.values())
            if (not matched or any(known_links.get(p) != target for p, target in state['links'].items())
                    or (path in expected and expected[path] != state)):
                noun = 'file read' if collection == 'files' else 'directory query'
                self.fail('unsealed or changed ' + noun + ': ' + path)
        observed = getattr(self, collection)
        if path in observed and observed[path] != state:
            self.fail('input changed within run: ' + path)
        observed[path] = state

    def read(self, path, *, observed=True):
        if isinstance(path, int):
            self.fail('untracked file descriptor read')
        path = _used_path(path)
        if self.outputs and _path_identity(path)['realpath'] in self.outputs:
            self.fail('tool output cannot be read as input: ' + path)
        state = file_state(path)
        real = Path(state['realpath'])
        if real.suffix == '.pyc' and real.is_relative_to(self.root) and state['sha256']:
            self.fail('repository bytecode cache unsupported; use a clean staged tree')
        self.check_path('files', path, state)
        if observed:
            self.observed.add(path)

    def list_directory(self, path):
        if isinstance(path, int):
            self.fail('untracked directory descriptor query')
        path = _used_path('.' if path is None else path)
        self.check_path('directories', path, directory_state(path, self.output_artifacts))

    def install_output_view(self):
        # The observed snapshot AND the consumer see the same input directory.
        # Otherwise len(listdir(...)) could change after the parent saves a seal.
        listdir, scandir = os.listdir, os.scandir

        def visible(path):
            parent = _path_identity('.' if path is None else path)['realpath']
            return lambda name: os.path.join(parent, os.fsdecode(name)) not in self.outputs

        def input_listdir(path='.'):
            entries = listdir(path)  # audit hook validates before returning names
            if not self.active or getattr(self.local, 'busy', False):
                return entries
            return list(filter(visible(path), entries))

        def input_scandir(path='.'):
            entries = scandir(path)
            if not self.active or getattr(self.local, 'busy', False):
                return entries
            return _InputScandir(entries, visible(path))

        os.listdir, os.scandir = input_listdir, input_scandir

    def env_read(self, name):
        state = {'present': name in self.values,
                 'sha256': digest(self.values[name]) if name in self.values else None}
        if self.expected:
            if name not in self.expected['environment']:
                self.fail('unsealed environment read: ' + str(name))
            if self.expected['environment'][name] != state:
                if self.policy['environment'] == 'abort':
                    self.fail('environment drift: ' + str(name))
                warning = 'environment drift: ' + str(name) + ': ' + self.policy['reason']
                if warning not in self.warnings:
                    self.warnings.append(warning)
        self.environment[name] = state

    def hook(self, event, args):
        if not self.active or getattr(self.local, 'busy', False):
            return
        self.local.busy = True
        try:
            self.events[event] = self.events.get(event, 0) + 1
            if (event.startswith(('subprocess.', 'ctypes.', 'socket.'))
                    or event in {'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn',
                                 'os.exec', 'os.spawn', 'os.putenv', 'os.unsetenv',
                                 'os.remove', 'os.rename', 'os.rmdir', 'os.mkdir', 'os.link',
                                 'os.symlink', 'os.chmod', 'os.truncate', 'os.utime',
                                 'os.chdir', 'os.fchdir', 'mmap.__new__', 'sys.addaudithook'}):
                self.fail('unsupported offline operation: ' + event)
            if event == 'open':
                path, mode, flags = args
                if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                    self.fail('offline trace is read-only')
                self.read(path)
            elif event in ('os.listdir', 'os.scandir'):
                self.list_directory(args[0])
            elif event == 'import':
                name, filename = args[:2]
                if name.split('.')[0] in {'ctypes', '_ctypes', 'mujoco', 'numpy'}:
                    self.fail('native package requires OS tracing: ' + name)
                if filename:
                    if any(str(filename).endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES):
                        if not Path(filename).resolve().is_relative_to(self.stdlib / 'lib-dynload'):
                            self.fail('non-stdlib native library requires OS tracing')
                    self.read(filename)
            elif event in ('compile', 'exec'):
                filename = args[1] if event == 'compile' else args[0].co_filename
                if filename and not str(filename).startswith('<'):
                    self.read(filename)
        except BaseException:
            self.fail('audit event could not be verified: ' + event)
        finally:
            self.local.busy = False


def _worker():
    request = json.load(sys.stdin)
    guard = _Audit(request, int(sys.argv[1]))
    # Bootstrap modules are trusted and explicitly inventoried before policy code.
    for module in list(sys.modules.values()):
        for attr in ('__file__', '__cached__'):
            path = getattr(module, attr, None)
            if path and Path(path).is_file():
                guard.read(path, observed=False)
    for path in request['seed']:
        guard.read(path, observed=False)
    for name in (request['expected'] or {}).get('environment', {}):
        guard.env_read(name)
    os.environ = _Environment(guard, guard.values)
    os.environb = _Environment(guard, guard.values, binary=True)
    if guard.outputs:
        guard.install_output_view()
    entry = guard.root / request['case']['entry']
    # Match CPython file-mode script resolution, including a symlinked script.
    sys.path[:0] = [str(entry.resolve().parent), str(guard.root)]
    sys.argv = [str(entry), *request['case']['args']]
    sys.addaudithook(guard.hook)
    guard.active = True
    sys.audit('ugrp.audit.ready')
    if guard.events.get('ugrp.audit.ready') != 1:
        guard.fail('audit hook was not installed')
    # Registered first -> called last, after the policy's own atexit callbacks.
    # Keep the hook active through shutdown instead of declaring success early.
    atexit.register(guard.finish)
    sys.unraisablehook = lambda _exc: guard.finish('HOST_ERROR', 'canonical-case-failed', 'unraisable error')
    threading.excepthook = lambda _exc: guard.finish('HOST_ERROR', 'canonical-case-failed', 'thread error')
    try:
        source = entry.read_bytes()
        # Like coverage.py / runpy: execute in a real __main__ module namespace.
        # This child never resumes a caller, so keep it installed through atexit
        # too (run_path would restore the worker module as soon as it returns).
        main = ModuleType('__main__')
        main.__file__ = str(entry)
        main.__package__ = main.__spec__ = main.__cached__ = None
        main.__loader__ = importlib.machinery.SourceFileLoader('__main__', str(entry))
        main.__builtins__ = sys.modules['builtins']
        sys.modules['__main__'] = main
        exec(compile(source, str(entry), 'exec'), main.__dict__)
    except SystemExit as exc:
        if exc.code not in (None, 0):
            guard.finish('HOST_ERROR', 'canonical-case-failed', 'nonzero SystemExit')
    except BaseException as exc:
        guard.finish('HOST_ERROR', 'canonical-case-failed', type(exc).__name__)


if __name__ == '__main__':
    _worker()
