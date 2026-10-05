"""PR338 counterexample from batch K review 84f672ae; offline only.

K1 is now a required passing regression. PR339 cases remain on the review
branch. REVIEW_E2E_K_PR338_ROOT can select an independent candidate tree.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def candidate(number):
    root = Path(os.environ.get(f"REVIEW_E2E_K_PR{number}_ROOT", ROOT)).resolve()
    module = {338: "harness/zone_final_environment.py",
              339: "harness/zone_target_executor.py"}[number]
    if not (root / module).is_file():
        pytest.skip(f"PR #{number} tree not provided")
    return root


def python_in(root, source):
    # Do not export GIT_DIR/GIT_WORK_TREE: candidate tests can create their own
    # temporary repositories. Imports resolve only within the selected tree.
    env = {k: v for k, v in os.environ.items()
           if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "PYTEST_ADDOPTS"}}
    env.update(PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE="1")
    guard = "import sys\nfor m in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production'):\n sys.modules[m] = None\n"
    result = subprocess.run([sys.executable, "-B", "-c", guard + source],
                            cwd=root, env=env, text=True, capture_output=True, timeout=90)
    if result.returncode:
        pytest.fail(result.stdout + result.stderr)
    return json.loads(result.stdout)


def test_pr338_preserves_existing_ci_collection_check():
    result = python_in(candidate(338), """
import json
from tests.test_zone_final_env import test_ci_collects_this_file
try:
    test_ci_collects_this_file()
except AssertionError as error:
    print(json.dumps({'passed': False, 'error': str(error)}))
else:
    print(json.dumps({'passed': True}))
""")
    assert result["passed"], result


@pytest.mark.parametrize('path', [
    'tests/test_zone_final_env.py',
    'tests/test_zone_final_environment_runnable.py',
    'tests/test_review_e2e_batch_k.py',
])
def test_pr338_ci_collects_both_suites_and_counterexample_once(path):
    from scripts.run_ci_tests import TEST_PATTERNS, collect_test_files
    assert collect_test_files(ROOT, TEST_PATTERNS).count(path) == 1


@pytest.mark.parametrize('patterns,accepted', [
    (('tests/test_zone_final_env*.py',), True),
    (('tests/test_zone_final_env.py', 'tests/test_zone_final_env*.py'), True),
    (('tests/test_zone_final_environment_runnable.py',), False),
    (('tests/test_zone_final_env_missing.py',), False),
    ((), False),
])
def test_pr338_collection_check_uses_expanded_exact_paths(monkeypatch, patterns, accepted):
    from scripts import run_ci_tests
    from tests.test_zone_final_env import test_ci_collects_this_file
    monkeypatch.setattr(run_ci_tests, 'TEST_PATTERNS', patterns)
    if accepted:
        test_ci_collects_this_file()
    else:
        with pytest.raises(AssertionError):
            test_ci_collects_this_file()
