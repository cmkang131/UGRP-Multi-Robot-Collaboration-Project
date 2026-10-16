"""Read-only reproduction against PR #234 c02db4d5; 14 failures are expected."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import types

for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS'):
    if os.environ.get(name) != '1':
        raise SystemExit(f'{name}=1 required')
import cv2
cv2.setNumThreads(0)
assert cv2.getNumThreads() == 1
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
BASE = 'c02db4d55510a5936dadebef6ef6ddf5dd5592fb'
for name in ('harness.owncam_drive_mem_v3', 'harness.m1_owncam_memory_v3'):
    path = name.replace('.', '/') + '.py'
    source = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT, text=True)
    module = types.ModuleType(name)
    module.__file__ = str(ROOT/path)
    sys.modules[name] = module
    parent, leaf = name.rsplit('.', 1)
    setattr(importlib.import_module(parent), leaf, module)
    exec(compile(source, f'{BASE}:{path}', 'exec'), module.__dict__)
import pytest
print('Baseline c02db4d5; numerical/OpenCV threads=1; expected 14 failures', flush=True)
raise SystemExit(pytest.main(['-q', '--basetemp=./.pytest_tmp',
                             'tests/test_owncam_memory_v3_review4.py', '-k', 'test_p1 or test_p2']))
