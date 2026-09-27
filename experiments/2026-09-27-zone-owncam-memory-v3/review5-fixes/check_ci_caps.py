"""Check runner tests under mocked CI caps=2 after single-thread library init."""
import os
from pathlib import Path
import sys
from unittest import mock

THREAD_VARS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')
if any(os.environ.get(k) != '1' for k in THREAD_VARS):
    raise SystemExit('Start with all four numerical thread caps set to 1')
import cv2
cv2.setNumThreads(0)
assert cv2.getNumThreads() == 1
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import pytest
print('Process/library caps=1; mock CI environment caps=2; runner tests must patch their own caps', flush=True)
with mock.patch.dict(os.environ, {name: '2' for name in THREAD_VARS}):
    code = pytest.main(['-q', '--basetemp=./.pytest_tmp',
                       'tests/test_owncam_memory.py::RunnerTests',
                       'tests/test_owncam_memory_v3_review3.py::test_external_sim_limit_persists_pending_slot_handoff',
                       'tests/test_owncam_memory_v3_review5.py::test_runner_records_matched_contract_and_thread_caps'])
assert all(os.environ[name] == '1' for name in THREAD_VARS)
raise SystemExit(code)
