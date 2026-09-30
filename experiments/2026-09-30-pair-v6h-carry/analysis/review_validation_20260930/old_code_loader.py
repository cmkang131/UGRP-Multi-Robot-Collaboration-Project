"""Pytest plugin: load only the starting classifier in memory for counterexamples.

Run under run_ci_tests.run_locked with this directory on PYTHONPATH and
-p old_code_loader, selecting the 17 tests listed in old_code_tests.txt.
Nonzero pytest exit is expected. No source file is overwritten.
"""
from pathlib import Path
import subprocess
import types

SOURCE_SHA = '76e0f9ce793f8cbbff2349b2be2bbaa359250a42'
SOURCE_PATH = 'experiments/2026-09-30-pair-v6h-carry/analysis/classify_placements.py'


def pytest_collection_modifyitems(items):
    for item in items:
        module = item.module
        if module.__name__.endswith('test_v6h_classify_placements') and not getattr(module, '_old_injected', False):
            old = types.ModuleType('v6h_old_snapshot')
            old.__file__ = module.cp.__file__
            source = subprocess.check_output(['git', 'show', f'{SOURCE_SHA}:{SOURCE_PATH}'],
                                             cwd=module.ROOT, text=True)
            exec(compile(source, old.__file__, 'exec'), old.__dict__)
            module.cp = old
            module._old_injected = True
