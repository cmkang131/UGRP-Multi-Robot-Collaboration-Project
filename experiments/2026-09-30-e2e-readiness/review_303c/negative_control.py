"""Run current review regressions against exact older production readers."""
import os
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path('/private/tmp/review-303c-f5566289')
GIT = '/Users/changmin/projects/ugrp/.git'
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
os.environ['GIT_DIR'] = GIT
for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[variable] = '1'
for name in ('mujoco', 'torch', 'sim.multi_masterpi_production'):
    sys.modules[name] = None
import pytest

def old_module(sha, name, path):
    data = subprocess.check_output(['git', '--git-dir=' + GIT, 'show', sha + ':' + path])
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / path)
    exec(compile(data, module.__file__, 'exec'), module.__dict__)
    return module

class OlderReaders:
    def __init__(self, sha):
        self.sha = sha
    def pytest_collection_modifyitems(self, items):
        if self.sha == 'old-runner':
            target = Path('/private/tmp/review303c-old-runner/scripts/run_zone_study_integration.py')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(['git', '--git-dir=' + GIT, 'show',
                               'cbac1dfc:scripts/run_zone_study_integration.py']))
            for item in items:
                item.module.runner.ROOT = target.parents[1]
            return
        study = old_module(self.sha, 'review303c_old_study', 'scripts/tensorboard_tools/zone_study.py')
        if self.sha == '114349e0':
            contract = old_module(self.sha, 'review303c_old_contract', 'scripts/zone_study_evidence_contract.py')
            study.verify_identity_join = contract.verify_identity_join
        exporter = old_module(self.sha, 'review303c_old_export', 'scripts/tensorboard_tools/export.py')
        exporter.export_study = study.export_study
        for item in items:
            item.module.tb = exporter

sha = sys.argv[1]
raise SystemExit(pytest.main(['-q', *sys.argv[2:]], plugins=[OlderReaders(sha)]))
