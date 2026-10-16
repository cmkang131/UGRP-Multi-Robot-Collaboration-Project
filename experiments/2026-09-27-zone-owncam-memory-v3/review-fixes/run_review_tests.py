"""Single-thread pytest entry point for this offline review verification."""
import os
import runpy
import sys
from pathlib import Path

THREAD_VARS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')
if any(os.environ.get(k) != '1' for k in THREAD_VARS):
    raise SystemExit('Set all four numerical thread environment variables to 1')
import cv2
cv2.setNumThreads(0)  # GCD build: 0 disables parallel regions; positive 1 is unsupported.
assert cv2.getNumThreads() == 1
print('Numerical thread caps: 1; OpenCV threads: 1; pytest worker: main process', flush=True)
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
if sys.argv[1:] == ['--baseline']:
    runpy.run_path(str(Path(__file__).with_name('reproduce_baseline.py')), run_name='__main__')
else:
    import pytest
    if '--basetemp=./.pytest_tmp' not in sys.argv[1:]:
        raise SystemExit('Required: --basetemp=./.pytest_tmp')
    raise SystemExit(pytest.main(sys.argv[1:]))
