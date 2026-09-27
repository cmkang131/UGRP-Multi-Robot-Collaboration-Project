"""Run only the round-5 interrupt counterexample against a historical Git blob.

From the repository root:
OMP_NUM_THREADS=1 python experiments/2026-09-26-sim-speed/review5_validation/check_baseline.py 78945a3c
The source is loaded in memory; neither checkout nor Git metadata is changed.
"""
from pathlib import Path
import subprocess
import sys
import types

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root))
import scripts

revision = sys.argv[1]
source = subprocess.run(['git', 'show', f'{revision}:scripts/sim_slots.py'], cwd=root,
                        capture_output=True, text=True, check=True).stdout
module = types.ModuleType('scripts.sim_slots')
module.__file__ = f'<{revision}:scripts/sim_slots.py>'
sys.modules[module.__name__] = module
scripts.sim_slots = module
exec(compile(source, module.__file__, 'exec'), module.__dict__)

import pytest
raise SystemExit(pytest.main([
    '-q', 'tests/test_sim_speed_review5.py', '-k', 'interrupt_owned_descendant',
    '--basetemp=./.pytest_tmp',
]))
