"""Run six review2 regressions against ac743938; read-only git, exit 1 expected."""
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
for leaf in ('owncam_pose_guard_v3', 'owncam_visibility_v3', 'owncam_memory_v3', 'm1_owncam_memory_v3'):
    path = f'harness/{leaf}.py'
    source = subprocess.check_output(['git', 'show', f'ac743938:{path}'], cwd=ROOT, text=True)
    name = f'harness.{leaf}'
    module = types.ModuleType(name)
    module.__file__ = str(ROOT/path)
    sys.modules[name] = module
    setattr(importlib.import_module('harness'), leaf, module)
    exec(compile(source, f'ac743938:{path}', 'exec'), module.__dict__)
import pytest
print('Baseline ac743938; numerical/OpenCV threads=1; expected six failures', flush=True)
raise SystemExit(pytest.main(['-q', '--basetemp=./.pytest_tmp', 'tests/test_owncam_memory_v3_review2.py',
                             '-k', 'test_p1 or test_p2']))
