"""Reproduce the P06 offline selection without importing physics or inference.

Run with the existing Python 3.12 environment from the repository. This driver
does not acquire a host lock, following main PR #328 (2026-09-30).
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[variable] = '1'
for module in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
    sys.modules[module] = None

import pytest  # noqa: E402

selected = json.loads(Path(__file__).with_name('redesign_test_selectors.json').read_text())
raise SystemExit(pytest.main(['-q', *selected, *sys.argv[1:]]))
