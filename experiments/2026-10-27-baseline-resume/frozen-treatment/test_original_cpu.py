"""Run only pinned zero-argument synthetic controller tests, no pytest hooks."""
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import time
import traceback

# Establishes CUDA hiding and a simulator import blocker before old imports.
from test_cpu import REF

path = Path(REF['aliases']['S']) / 'tests/test_pairact_r1_student.py'
spec = importlib.util.spec_from_file_location('pinned_original_controller_tests', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
rows = []
for name, fn in inspect.getmembers(module, inspect.isfunction):
    if not name.startswith('test_'):
        continue
    if inspect.signature(fn).parameters:
        raise ValueError('unexpected fixture: CPU direct harness must not guess inputs')
    start = time.monotonic()
    try:
        fn()
        rows.append(dict(test=name, status='PASS', wall_s=time.monotonic() - start))
    except Exception:
        rows.append(dict(test=name, status='FAIL', error=traceback.format_exc()))
result = dict(source=str(path), tests=rows, tests_run=len(rows), failures=sum(r['status'] != 'PASS' for r in rows),
              gpu_runs=0, model_forward_calls=0, simulator_modules=[m for m in sys.modules if m == 'mujoco' or m == 'warp'])
with Path(sys.argv[1]).open('x') as stream:
    json.dump(result, stream, indent=2)
print(json.dumps(dict(tests_run=result['tests_run'], failures=result['failures'])))
sys.exit(0 if not result['failures'] else 1)
