"""Read-only reproduction of review 6 at 7400c426; expect two failures."""
import os
from pathlib import Path
import subprocess
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
BASE = '7400c4262156f85ccdee946d8d96c075e0cdaa79'
CAPS = {name: '1' for name in
        ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')}
if any(os.environ.get(name) != value for name, value in CAPS.items()):
    raise SystemExit('Start with all four numerical thread caps=1')
import cv2
cv2.setNumThreads(0)
assert cv2.getNumThreads() == 1
from harness import owncam_safety_v3 as safety

path = 'harness/owncam_safety_v3.py'
source = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT, text=True)
exec(compile(source, f'{BASE}:{path}', 'exec'), safety.__dict__)
import pytest
print(f'Baseline {BASE}; original safety module in memory; no checkout/index changes', flush=True)
with mock.patch.dict(os.environ, CAPS):
    code = pytest.main(['-q', '-s', '--basetemp=./.pytest_tmp',
                       'tests/test_owncam_memory_v3_review6.py',
                       '-k', 'resumed_initial_sweep_completes'])
raise SystemExit(code)
