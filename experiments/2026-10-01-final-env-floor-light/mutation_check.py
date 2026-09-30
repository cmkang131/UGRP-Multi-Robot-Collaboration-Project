"""Finite fake-only mutations of new v87 files; restore originals in finally.

Run only after other tests finish. No SIM, native imports, worker, host lock or
extracted checkout. The temporary Python cache directory is deleted on exit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TEST = 'tests/test_zone_final_environment_floor_light.py::'
ENV = 'harness/zone_final_environment_floor_light.py'
PHYS = 'sim/final_environment_floor_light.py'
RUN = 'scripts/run_final_environment_floor_light.py'
BACKEND_TEST = 'test_backend_installs_profile_before_world_audits_and_records_receipt'
MUTATIONS = (
    ('skip-profile-install', PHYS,
     '        self.scene = render_profile.install(self.scene, env.RENDER_PROFILE)',
     '        pass  # mutant', BACKEND_TEST + '[False]'),
    ('skip-compiled-profile-verification', PHYS,
     'render_profile.verify_model(self.world.model, env.RENDER_PROFILE)',
     'render_profile.audit_model(self.world.model)', BACKEND_TEST + '[True]'),
    ('drop-render-receipt', PHYS,
     "        applied['render_profile_applied'] = self.render_audit", '        pass  # mutant',
     BACKEND_TEST + '[False]'),
    ('skip-failed-constructor-cleanup', PHYS, '            self.close()', '            pass  # mutant',
     BACKEND_TEST + '[True]'),
    ('allow-physics-drift', ENV, '    if value != expected:', '    if False:',
     'test_changed_contract_rejected[physics]'),
    ('allow-dark-calibration-contract', ENV, '    if contract != expected:', '    if False:',
     'test_changed_contract_rejected[calibration]'),
    ('admit-p03', ENV, "    value['source_sha256'] =", "    value['runnable'] = True\n    value['source_sha256'] =",
     'test_v87_only_changes_render_and_version_provenance[p03-zone_wide_door_geometry_v3]'),
    ('dispatch-old-dark-backend', RUN, 'from sim.final_environment_floor_light import PhysicsBackend',
     'from sim.final_environment_checks import PhysicsBackend',
     'test_three_map_cli_schedule_caps_failure_and_no_overwrite[False-p01-30]'),
    ('shorten-calibration-to-p01', RUN,
     'bundles = [env.bundle(mid, check=args.check) for mid in selected]',
     "bundles = [env.bundle(mid, check='p01') for mid in selected]",
     'test_three_map_cli_schedule_caps_failure_and_no_overwrite[False-calibration-120]'),
    ('remove-workflow-registration', 'configs/simulation_workflows.d/final_environment_v87.json',
     '"zone-final-environment-floor-light-check"', '"unregistered-mutant"',
     'test_both_workflows_discoverable_new_plan_and_ci_collection'),
    ('remove-ci-collection', 'scripts/run_ci_tests.py',
     '    "tests/test_zone_final_environment_floor_light.py",\n', '',
     'test_both_workflows_discoverable_new_plan_and_ci_collection'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    records = []
    preserved = json.loads((ROOT / 'experiments/2026-10-01-final-env-floor-light/v84_preservation.json').read_text())
    for name, relative, before, after, test in MUTATIONS:
        assert relative not in preserved['files_sha256'], 'never mutate v84 or pinned files'
        path = ROOT / relative
        original = path.read_bytes()
        source = original.decode()
        assert source.count(before) == 1, name
        try:
            path.write_text(source.replace(before, after, 1))
            with tempfile.TemporaryDirectory(prefix='ugrp-floor-light-mutation-') as cache:
                result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', TEST + test],
                    cwd=ROOT, text=True, capture_output=True, timeout=300,
                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPYCACHEPREFIX': cache})
            records.append({'mutation': name, 'path': relative, 'test': TEST + test,
                            'exit_code': result.returncode, 'detected': result.returncode == 1,
                            'source_sha256': hashlib.sha256(original).hexdigest(),
                            'output_tail': (result.stdout + result.stderr)[-5000:]})
            print(name, result.returncode, flush=True)
        finally:
            path.write_bytes(original)
            assert path.read_bytes() == original, name
    args.output.write_text(json.dumps({'scope': 'fake/offline only', 'mutations': records,
                                      'all_sources_restored': True}, ensure_ascii=False, indent=2) + '\n')
    return int(not all(row['detected'] for row in records))


if __name__ == '__main__':
    raise SystemExit(main())
