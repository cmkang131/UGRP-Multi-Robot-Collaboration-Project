"""P03-only numeric/fake-worker regressions under the existing shared lock."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.run_ci_tests import local_lock_root, run_locked

TESTS = (
    'tests/test_vision_loc_provider_lifecycle.py',
    'tests/test_zone_study_source_pinning.py',
    'tests/test_zone_pair_provider_init.py',
    'tests/test_zone_study_pair_delay.py',  # inspected/collected, deselected by the no-inference guard
    'tests/test_zone_pair_tag_boundary_matrix.py',
    'tests/test_vision_pose_source.py',
    'tests/test_pose_provider_contract.py',
    'tests/test_pose_provider_boundary.py',
)


def main():
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + str(Path(__file__).parent)
    command = [sys.executable, '-m', 'pytest', '-q', '-p', 'offline_guard', *TESTS,
               '-k', 'not geometry_scene_and_public_projection_bypass_marker_transforms', *sys.argv[1:]]
    return run_locked(command, env, local_lock_root())


if __name__ == '__main__':
    raise SystemExit(main())
