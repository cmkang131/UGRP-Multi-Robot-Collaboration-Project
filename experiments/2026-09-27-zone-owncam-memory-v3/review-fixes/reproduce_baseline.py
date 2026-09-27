"""Read eebab596 runtime into this process, then run the four review regressions.

No checkout, index, git metadata, or runtime source writes. Exit 1 is expected
(nine assertion failures). Tests and stored own-camera fixtures stay current.
"""
import importlib
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import pytest

BASELINE = 'eebab596'
for leaf in ('owncam_memory_v3', 'owncam_drive_mem_v3', 'm1_owncam_memory_v3'):
    path = f'harness/{leaf}.py'
    source = subprocess.check_output(['git', 'show', f'{BASELINE}:{path}'], cwd=ROOT, text=True)
    name = f'harness.{leaf}'
    module = types.ModuleType(name)
    module.__file__ = str(ROOT/path)
    sys.modules[name] = module
    setattr(importlib.import_module('harness'), leaf, module)
    exec(compile(source, f'{BASELINE}:{path}', 'exec'), module.__dict__)

print(f'Baseline runtime: {BASELINE}; four review regressions; expected 9 failures', flush=True)
raise SystemExit(pytest.main(['-q', '--basetemp=./.pytest_tmp',
                             'tests/test_owncam_memory_v3_review.py', '-k', 'test_p1 or test_p2']))
