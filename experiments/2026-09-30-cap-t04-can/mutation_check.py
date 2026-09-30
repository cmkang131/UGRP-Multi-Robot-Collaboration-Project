"""Remove T04 decision logic in isolated Python processes; never edit sources.

Run with the repository's existing Python environment, from the worktree root.
Output must be a new directory. Nonzero pytest is expected for each mutation;
an import/collection failure is NOT accepted as a killed behavioural mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TEST = 'tests/test_zone_own_executor_can.py'
MUTATIONS = (
    ('remove_floor_perception', 'harness.wrist_can',
     "module.floor_can = lambda *a, **k: module.CanView('unknown', 'removed')",
     'test_cylinder_center_from_own_jpeg'),
    ('remove_lift_evidence_gate', 'harness.zone_can_skill',
     "needle = \"self.proofs = self.proofs + 1 if seen.answer == 'yes' else 0\"\n"
     "assert source.count(needle) == 1\n"
     "exec(compile(source.replace(needle, 'self.proofs += 1'), module.__file__, 'exec'), module.__dict__)",
     'test_ungrasped_and_empty_gripper_never_reach_holding_or_release'),
    ('remove_release_evidence_gate', 'harness.zone_can_skill',
     "needle = 'self.proofs = self.proofs + 1 if valid else 0'\n"
     "assert source.count(needle) == 1\n"
     "exec(compile(source.replace(needle, 'self.proofs += 1'), module.__file__, 'exec'), module.__dict__)",
     'test_bad_release_views_cannot_turn_open_gripper_into_completion'),
    ('remove_own_camera_boundary', 'harness.wrist_can',
     "original = module.decode_own\n"
     "module.decode_own = lambda obs, **kw: original({**obs, 'camera':'robot_cam', 'robot_id':kw['robot_id']}, **kw)",
     'test_input_and_pose_refusal[top]'),
    ('restore_full_target_sweep_mismatch', 'harness.zone_can_skill',
     "needle = 'self.guard.transition_clear(self.servo, next_servo, pose, loaded=loaded)'\n"
     "assert source.count(needle) == 1\n"
     "exec(compile(source.replace(needle, 'self.guard.transition_clear(self.servo, target, pose, loaded=loaded)'), module.__file__, 'exec'), module.__dict__)",
     'tests/test_review_e2e_batch_i.py::test_t04_issued_arm_increment_passes_the_same_static_sweep'),
    ('remove_arm_sweep_gate', 'harness.zone_can_skill',
     "needle = 'self.guard.transition_clear(self.servo, next_servo, pose, loaded=loaded)'\n"
     "assert source.count(needle) == 1\n"
     "exec(compile(source.replace(needle, 'True'), module.__file__, 'exec'), module.__dict__)",
     'tests/test_review_e2e_batch_i.py::test_t04_issued_arm_increment_passes_the_same_static_sweep'),
    ('check_arm_endpoint_only', 'harness.zone_can_skill',
     "module._CanGuard.transition_samples = lambda self, current, target: iter((current, target))",
     'tests/test_zone_own_executor_can_sweep.py::test_clear_endpoints_do_not_bypass_blocked_interior'),
)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for name, module_name, mutation, test_name in MUTATIONS:
        node = test_name if test_name.startswith('tests/') else f'{TEST}::{test_name}'
        code = ("import importlib, pathlib, sys\n"
                "sys.path.insert(0, 'experiments/2026-09-30-cap-t04-can')\n"
                "import offline_guard\n"
                "sys.modules['mujoco'] = None\n"
                f"module = importlib.import_module({module_name!r})\n"
                "source = pathlib.Path(module.__file__).read_text()\n" + mutation +
                f"\nimport pytest\nsys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', '-p', 'offline_guard', {node!r}]))\n")
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, text=True,
                                capture_output=True, timeout=180)
        content = result.stdout + result.stderr
        path = output / f'{name}.log'
        path.write_text(content)
        killed = result.returncode == 1 and 'AssertionError' in content and 'FAILED' in content and 'ERROR collecting' not in content
        rows.append({'mutation': name, 'test': node, 'exit_code': result.returncode,
                     'killed_by_assertion': killed, 'log': str(path),
                     'log_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    record = {'schema':'ugrp.can_skill_mutation.v1', 'physics_runs':0, 'model_calls':0,
              'all_killed': all(row['killed_by_assertion'] for row in rows), 'mutations':rows}
    (output / 'mutation.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
    return 0 if record['all_killed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    raise SystemExit(run(parser.parse_args().output))
