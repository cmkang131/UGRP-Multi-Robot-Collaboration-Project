"""Apply the same round-6 counterexample to an unchanged historical Git blob."""
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
    '-q', 'tests/test_sim_speed_review6.py', '-k', 'pid_reuse_at_last_membership',
    '--basetemp=./.pytest_tmp',
]))
