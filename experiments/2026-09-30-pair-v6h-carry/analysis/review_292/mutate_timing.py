from pathlib import Path
import sys
import harness.zone_pair_executor as module
import pytest
path=Path(module.__file__)
source=path.read_text()
old='v6e_carry.timing_calibration(params, axis, self.policy.carry_fwd_gain)'
assert source.count(old)==1
exec(compile(source.replace(old,'params'), str(path), 'exec'), module.__dict__)
raise SystemExit(pytest.main(sys.argv[1:]))
