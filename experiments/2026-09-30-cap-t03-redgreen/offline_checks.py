"""Run selected fake/RGB tests without the host lock, with a unique raw log."""
import os
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
RAW = Path('/Users/changmin/projects/ugrp/outputs/cap-t03-redgreen')
RAW.mkdir(parents=True, exist_ok=True)
out = Path(tempfile.mkdtemp(prefix='offline-', dir=RAW))
env = dict(os.environ, PYTHONPATH=f'{Path(__file__).parent}:{ROOT}',
           OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
           VECLIB_MAXIMUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
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
with (out/'pytest.log').open('w') as stream:
    result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
(out/'exit_code.txt').write_text(str(result)+'\n')
after = source_hashes()
(out/'inputs-after.json').write_text(json.dumps(after, indent=2)+'\n')
if before != after:
    print('Source changed while waiting/running; this is not a final verification.', flush=True)
    result = 4
(out/'verified_exit_code.txt').write_text(str(result)+'\n')
print((out/'pytest.log').read_text()[-14000:], flush=True)
raise SystemExit(result)
