"""Read-only reproduction against 2fadd08a; the selected eight tests must fail."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import types
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
BASE = '2fadd08a0a49d94af21f54275f60e07645fb6677'
CAPS = {k: '1' for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')}
if any(os.environ.get(k) != v for k, v in CAPS.items()):
    raise SystemExit('Start with all four numerical thread caps=1')
import cv2
cv2.setNumThreads(0)
assert cv2.getNumThreads() == 1
for name in ('harness.owncam_drive_mem_v3', 'harness.m1_owncam_memory_v3', 'scripts.run_m1_owncam_memory_v3'):
    path = name.replace('.', '/') + '.py'
    source = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT, text=True)
    module = types.ModuleType(name)
    module.__file__ = str(ROOT/path)
    sys.modules[name] = module
    parent, leaf = name.rsplit('.', 1)
    setattr(importlib.import_module(parent), leaf, module)
    exec(compile(source, f'{BASE}:{path}', 'exec'), module.__dict__)
import pytest
print('Baseline 2fadd08a; original runtime/runner in memory; no checkout or index changes', flush=True)
with mock.patch.dict(os.environ, CAPS):
    code = pytest.main(['-q', '-s', '--basetemp=./.pytest_tmp', 'tests/test_owncam_memory_v3_review5.py',
                       '-k', 'marginal or repeated_good or saved_s151 or times_out or blocks_same or rejects_same'])
raise SystemExit(code)
