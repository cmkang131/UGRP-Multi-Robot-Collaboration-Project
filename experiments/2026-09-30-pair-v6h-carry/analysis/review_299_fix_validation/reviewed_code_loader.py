"""Load reviewed #299 classifier in memory, exposing its six independent failures.

Select only the original R1/R2 tests; never overwrite the current classifier.
Run via scripts.run_ci_tests.run_locked on the shared Mac.
"""
import subprocess
import types

SOURCE_SHA = "c86d9bac62036904ecc641db5e59e79edb58dec2"
SOURCE_PATH = "experiments/2026-09-30-pair-v6h-carry/analysis/classify_placements.py"


def pytest_collection_modifyitems(items):
    for item in items:
        module = item.module
        if module.__name__.endswith("test_classify_review_299") and not getattr(module, "_reviewed_injected", False):
            old = types.ModuleType("reviewed_299_classifier")
            old.__file__ = module.cp.__file__
            source = subprocess.check_output(["git", "show", f"{SOURCE_SHA}:{SOURCE_PATH}"], cwd=module.ROOT, text=True)
            exec(compile(source, old.__file__, "exec"), old.__dict__)
            module.cp = old
            module._reviewed_injected = True
