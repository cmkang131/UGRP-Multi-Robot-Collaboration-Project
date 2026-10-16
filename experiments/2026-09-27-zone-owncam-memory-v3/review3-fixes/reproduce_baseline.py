"""Run seven review3 regressions against b1eebc0e; read-only git, exit 1 expected."""
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
for name in ('harness.owncam_memory_v3', 'harness.owncam_drive_mem_v3',
             'harness.owncam_slot_inspection_v3', 'harness.m1_owncam_memory_v3',
             'scripts.run_m1_owncam_memory_v3'):
    path = name.replace('.', '/') + '.py'
    source = subprocess.check_output(['git', 'show', f'b1eebc0e:{path}'], cwd=ROOT, text=True)
    module = types.ModuleType(name)
    module.__file__ = str(ROOT/path)
    sys.modules[name] = module
    parent, leaf = name.rsplit('.', 1)
    setattr(importlib.import_module(parent), leaf, module)
    exec(compile(source, f'b1eebc0e:{path}', 'exec'), module.__dict__)
import pytest
print('Baseline b1eebc0e; numerical/OpenCV threads=1; expected seven failures', flush=True)
raise SystemExit(pytest.main(['-q', '--basetemp=./.pytest_tmp', 'tests/test_owncam_memory_v3_review3.py',
                             '-k', 'test_p1 or test_p2 or test_external_sim_limit']))
