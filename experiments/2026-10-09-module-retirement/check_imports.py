"""Batch real imports with explicit no-execution boundaries; never starts a run.

Called via python -c / runpy below. A blocked CLI is NOT counted as an import pass.
The guards are local to this disposable verifier process, not production edits.
"""
from __future__ import annotations
import argparse
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('UGRP_CLEANUP_IMPORT_ROOT', HERE.parents[1]))
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'scripts/red_block')]
sys.dont_write_bytecode = True
os.environ['MUJOCO_GL'] = 'glfw'
os.environ['UGRP_REAL_TRACE_ENABLE'] = '0'
CACHE = Path(tempfile.mkdtemp(prefix='ugrp-retirement-import-'))
for variable in ('TORCH_HOME', 'HF_HOME', 'XDG_CACHE_HOME', 'MPLCONFIGDIR'):
    os.environ[variable] = str(CACHE / variable.lower())


class ExecutionBlocked(RuntimeError):
    pass


def blocked(*args, **kwargs):
    raise ExecutionBlocked('CLI/physics execution is outside this import-only audit')


def audit(event, args):
    if event == 'open':
        path, mode, flags = args
        cache_write = isinstance(path, (str, bytes)) and Path(os.fsdecode(path)).is_relative_to(CACHE)
        if isinstance(path, (str, bytes)):
            parts = Path(os.fsdecode(path)).parts
            if 'outputs' in parts:
                raise ExecutionBlocked('outputs access blocked')
        if not cache_write and ((isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))):
            raise ExecutionBlocked('file write blocked')
    if event == 'os.mkdir' and Path(args[0]).is_relative_to(CACHE):
        return
    if event in ('os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.system', 'os.posix_spawn',
                 'socket.connect', 'socket.bind', 'socket.getaddrinfo'):
        raise ExecutionBlocked(event + ' blocked')
    if event == 'subprocess.Popen':
        argv = args[1]
        if not (isinstance(argv, (list, tuple)) and argv and Path(argv[0]).name == 'git'
                and len(argv) > 1 and argv[1] in ('show', 'rev-parse', 'cat-file')):
            raise ExecutionBlocked('subprocess execution blocked')


def main():
    inventory = json.loads((HERE / 'inventory.json').read_text())
    paths = sorted(set(inventory['live_core']) | set(inventory['held_core']))
    retry = os.environ.get('UGRP_CLEANUP_IMPORT_RETRY') == '1'
    if retry:
        paths = [row['path'] for row in map(json.loads, (HERE / 'imports.jsonl').read_text().splitlines())
                 if row.get('error_type') == 'ModuleNotFoundError']
    # Import dependencies normally before enabling the hooks so their ordinary
    # library discovery is not confused with an application-side effect.
    for name in ('numpy', 'PIL.Image', 'cv2', 'mujoco', *(['torch'] if retry else [])):
        try:
            importlib.import_module(name)
        except ImportError:
            pass
    if 'mujoco' in sys.modules:
        for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_resetData'):
            setattr(sys.modules['mujoco'], name, blocked)
    argparse.ArgumentParser.parse_args = blocked
    argparse.ArgumentParser.parse_known_args = blocked
    signal.signal(signal.SIGALRM, lambda *_: blocked())
    # The result stream is opened before guards, but candidate code cannot open
    # any output. No production output path is accessed.
    report_name = 'imports-baseline.jsonl' if 'UGRP_CLEANUP_IMPORT_ROOT' in os.environ else 'imports.jsonl'
    if retry:
        report_name = 'imports-reference-act.jsonl'
    with (HERE / report_name).open('w') as output:
        sys.addaudithook(audit)
        for path in paths:
            name = path.removesuffix('/__init__.py').removesuffix('.py').replace('/', '.')
            row = {'path': path, 'module': name}
            signal.alarm(15)
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    module = importlib.import_module(name)
                if Path(module.__file__).resolve() != (ROOT / path).resolve():
                    raise RuntimeError('import resolved outside the audited checkout')
                row['status'] = 'pass'
            except BaseException as error:
                row['status'] = 'blocked' if isinstance(error, ExecutionBlocked) else 'error'
                row['error_type'] = type(error).__name__
                row['error'] = str(error)[:450]
            finally:
                signal.alarm(0)
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
            output.flush()
            if row['status'] != 'pass':
                print(row['status'], path, row['error_type'], flush=True)


if __name__ == '__main__':
    main()
