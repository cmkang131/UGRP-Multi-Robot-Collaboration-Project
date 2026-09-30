"""Finite offline mutation check. Restore each owned file even on failure.

No SIM/worker/model/host lock; pytest only runs the targeted fake regression.
Use in the dedicated integration worktree with no other edit in progress.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TEST = 'tests/test_zone_final_environment_runnable.py'
MUTATIONS = (
    ('map-file-hash', 'harness/zone_final_environment.py',
     "if sha(path) != row['sha256'] or digest(static) != row['static_map_sha256']:", 'if False:',
     'test_changed_map_parent_or_calibration_contract_is_refused[file]'),
    ('measured-calibration-hash', 'harness/zone_final_environment.py',
     'if sha(path) != expected_sha:', 'if False:', 'test_measurement_hash_gate_precedes_worker_or_pf'),
    ('runnable-registration', 'harness/zone_final_environment.py',
     "'runnable': check != 'p03'", "'runnable': False",
     'test_registered_maps_resolve_and_new_bundle_is_runnable_without_sealing'),
    ('cap-admission', 'scripts/run_final_environment_checks.py',
     'if cap != expected:', 'if False:', 'test_invalid_cap_is_rejected_before_backend'),
    ('owned-cleanup', 'scripts/run_final_environment_checks.py',
     '                backend.close()', '                pass  # mutant',
     'test_frame_failure_retains_host_error_and_closes_owned_world'),
    ('fresh-cohort-output', 'scripts/run_final_environment_checks.py',
     '    args.output.mkdir(parents=True)', '    args.output.mkdir()',
     'test_cli_creates_fresh_parent_and_preserves_case_denominator'),
    ('catalog-registration', 'sim/workflow_manager.py',
     '        data["workflows"].extend(extra.get("workflows", []))', '        pass  # mutant',
     'test_workflow_is_discoverable_and_plan_does_not_execute'),
    ('physics-cap', 'sim/final_environment_checks.py',
     'if self.deadline is None or t > self.deadline + 1e-8 or t < self.now - 1e-8:', 'if False:',
     'test_real_backend_advance_rejects_deadline_with_fake_world'),
    ('constructor-step-cap', 'sim/zone_final_v3_scene.py',
     'if float(world.data.time) + float(world.model.opt.timestep) > world._final_environment_deadline + 1e-8:',
     'if False:', 'test_world_step_cap_covers_constructor_and_can_advance_to_check_deadline'),
    ('v3-world-connection', 'sim/zone_final_v3_scene.py',
     'return scene.robot_transform(xml, hardware=world.physical_params,\n                                     calibrated_keys=world.calibration_parameters)',
     'return xml', 'test_world_factory_applies_final_scene_contact_and_v3_robot_hooks'),
    ('unmeasured-posture-fail-closed', 'harness/vision_pose_source_final.py',
     '            self._fail(now, str(error))', '            pass  # mutant',
     'test_final_provider_only_consumes_own_rgb_after_delay_and_uses_fixed_v3_camera'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    rows = []
    for name, relative, before, after, test in MUTATIONS:
        path = ROOT / relative
        raw = path.read_bytes()
        source = raw.decode()
        if source.count(before) != 1:
            raise RuntimeError(f'{name}: mutation target must occur exactly once')
        try:
            path.write_text(source.replace(before, after, 1))
            result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', f'{TEST}::{test}'],
                                    cwd=ROOT, text=True, capture_output=True,
                                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=180)
            rows.append({'mutation': name, 'path': relative, 'test': test,
                         'pytest_exit_code': result.returncode,
                         'killed': result.returncode == 1,
                         'output': result.stdout + result.stderr})
        finally:
            path.write_bytes(raw)
            if path.read_bytes() != raw:
                raise RuntimeError(f'{name}: original bytes were not restored')
    with args.output.open('x') as stream:
        stream.write(json.dumps(rows, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'killed': sum(r['killed'] for r in rows), 'total': len(rows),
                      'all_sources_restored': True}))
    return int(not all(row['killed'] for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
