"""Run selected fake/RGB tests under the shared lock, with a unique raw log."""
import os
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time

from scripts.run_ci_tests import local_lock_root, run_locked

ROOT = Path(__file__).resolve().parents[2]
RAW = Path('/Users/changmin/projects/ugrp/outputs/cap-t03-redgreen')
RAW.mkdir(parents=True, exist_ok=True)
out = Path(tempfile.mkdtemp(prefix='offline-', dir=RAW))
env = dict(os.environ, PYTHONPATH=f'{Path(__file__).parent}:{ROOT}',
           OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
           VECLIB_MAXIMUM_THREADS='1')
command = [sys.executable, '-m', 'pytest', '-p', 'offline_guard', '-q',
           '--junitxml', str(out/'junit.xml'), *sys.argv[1:]]
(out/'command.txt').write_text(repr(command)+'\n')
print(f'RAW={out}', flush=True)


def source_hashes():
    paths = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard',
                                     '--', 'harness', 'tests', 'scripts', 'configs', 'config'],
                                    cwd=ROOT, text=True).splitlines()
    return {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(set(paths))
            if (ROOT/p).is_file() and (ROOT/p).suffix in ('.py', '.json', '.jpg', '.png')}


before = source_hashes()
(out/'inputs-before.json').write_text(json.dumps(before, indent=2)+'\n')
# Wait for an existing owner; never clear its lock or terminate its process.
deadline = time.monotonic() + 1200
with (out/'pytest.log').open('w') as stream:
    saved = [os.dup(fd) for fd in (1, 2)]
    try:
        for fd in (1, 2):
            os.dup2(stream.fileno(), fd)
        while True:
            result = run_locked(command, env, local_lock_root())
            if result != 3 or time.monotonic() >= deadline:
                break
            time.sleep(2)
    finally:
        for fd, original in zip((1, 2), saved):
            os.dup2(original, fd)
            os.close(original)
(out/'exit_code.txt').write_text(str(result)+'\n')
after = source_hashes()
(out/'inputs-after.json').write_text(json.dumps(after, indent=2)+'\n')
if before != after:
    print('Source changed while waiting/running; this is not a final verification.', flush=True)
    result = 4
(out/'verified_exit_code.txt').write_text(str(result)+'\n')
print((out/'pytest.log').read_text()[-14000:], flush=True)
raise SystemExit(result)
