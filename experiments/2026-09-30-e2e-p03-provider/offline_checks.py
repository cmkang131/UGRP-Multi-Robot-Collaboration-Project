"""P03 numeric/fake-worker and evaluation-boundary regressions; no host lock (#328)."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TESTS = (
    'tests/test_zone_eval_top.py::ProfileTests',
    'tests/test_zone_eval_top.py::BoundaryTests',
    'tests/test_zone_eval_top.py::RobotInputBoundaryTests',
    'tests/test_vision_loc_provider_lifecycle.py',
    'tests/test_vision_loc_p03_source_pinning.py',
    'tests/test_zone_pair_registered_source.py',
    'tests/test_zone_pair_door_relax.py',
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
    return subprocess.call(command, env=env, cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
