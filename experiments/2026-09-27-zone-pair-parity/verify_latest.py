"""Run the pinned grasp-v5 real-input regressions without changing the checkout."""
import importlib
import subprocess
import sys
import tempfile
from pathlib import Path

import replay as r

sys.meta_path.insert(0,r.FrozenPairs(r.V5))
with tempfile.TemporaryDirectory(prefix='pair-parity-tests-') as folder:
    root=Path(folder)
    names=r.git('ls-tree','-r','--name-only',r.V5,'--','tests').splitlines()
    selected=[n for n in names if n in ('tests/test_zone_pair_v5.py','tests/test_zone_pair_grasp.py','tests/test_zone_pair_standoff.py','tests/test_zone_pair_executor.py')
              or n.startswith(('tests/fixtures/zone_pair_v5/','tests/fixtures/zone_pair_standoff/'))]
    for n in selected:
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(subprocess.check_output(['git','show',f'{r.V5}:{n}'],cwd=r.ROOT))
    tests=importlib.import_module('tests');tests.__path__=[str(root/'tests'),*tests.__path__]
    helper=importlib.import_module('tests.test_zone_pair_executor')
    helper.ROOT=r.ROOT
    import pytest
    code=pytest.main(['-q','-p','no:cacheprovider','--basetemp=./.pytest_tmp','-k','not registration',str(root/'tests/test_zone_pair_v5.py')])
    assert not any(x in sys.modules for x in ('mujoco','torch','tensorflow'))
    raise SystemExit(code)
