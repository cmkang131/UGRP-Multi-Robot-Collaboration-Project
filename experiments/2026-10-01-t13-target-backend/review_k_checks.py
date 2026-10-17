"""Offline review-K verification; explicit test list, no host lock."""
from pathlib import Path
import hashlib
import json
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TESTS = [
    'tests/test_review_e2e_batch_k.py', 'tests/test_zone_target_review_k.py',
    'tests/test_zone_target_workflow.py', 'tests/test_zone_own_executor_target.py',
    'tests/test_zone_identity_jobs.py', 'tests/test_zone_own_executor_recovery.py',
    'tests/test_zone_own_executor_host.py', 'tests/test_zone_pair_registered_source.py',
    'tests/test_zone_study_source_pinning.py', 'tests/test_zone_own_executor_color_seals.py',
    'tests/test_review_325b.py', 'tests/test_seal_v2_review_301.py',
    'tests/test_zone_final_environment_runnable.py', 'tests/test_zone_final_env.py',
    'tests/test_vision_loc_provider_lifecycle.py', 'tests/test_ci_sharding.py',
    'tests/test_simulation_workflow_manager.py::WorkflowManagerTests::test_catalog_has_thirty_selectable_workflows_and_distinct_adapters',
    'tests/test_simulation_workflow_manager.py::WorkflowManagerTests::test_every_catalog_workflow_has_a_read_only_explicit_plan',
]

def main():
    out = Path(sys.argv[1]); out.mkdir(exist_ok=True, parents=True)
    cmd = [sys.executable, '-m', 'pytest', '-q', '-p', 'tests.pose_provider_no_physics',
           *TESTS, '--tb=short', '--junitxml=' + str(out/'junit.xml')]
    with (out/'pytest.log').open('w') as log:
        result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    record = {'command': cmd, 'exit_code': result.returncode, 'host_lock': False,
              'python': sys.version, 'platform': platform.platform(),
              'log_sha256': hashlib.sha256((out/'pytest.log').read_bytes()).hexdigest()}
    (out/'pytest-receipt.json').write_text(json.dumps(record, indent=2)+'\n')
    print((out/'pytest.log').read_text())
    return result.returncode

if __name__ == '__main__':
    raise SystemExit(main())
