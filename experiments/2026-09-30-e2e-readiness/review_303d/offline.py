import os,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();os.chdir(root);sys.path.insert(0,str(root))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
os.environ['GIT_DIR']='/Users/changmin/projects/ugrp/.git'
for v in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):os.environ[v]='1'
for m in ('mujoco','torch','sim.multi_masterpi_production'):sys.modules[m]=None
import pytest
raise SystemExit(pytest.main(['-q',*sys.argv[2:]]))
