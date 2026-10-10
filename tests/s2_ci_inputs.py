"""Portable recorded inputs for offline S2 contract tests, never runtime defaults."""
from pathlib import Path
import io
import json
import subprocess
import tarfile
import pytest

FIX = Path(__file__).resolve().parent / 'fixtures/s2_ci'


@pytest.fixture
def portable_s2_inputs(monkeypatch, tmp_path):
    # Local developer raw must not make a missing fixture silently pass CI.
    original_open = Path.open
    def repository_inputs_only(path, *args, **kwargs):
        if '/Users/changmin/projects/ugrp/outputs/' in str(path):
            raise AssertionError('offline test attempted developer raw: ' + str(path))
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', repository_inputs_only)
    from scripts import run_s2_v133_reproduction, run_s2_v133_baseline_v52
    from harness import zone_s2_landmarks_contract, zone_s2_side_scan_contract
    from harness import zone_s2_look_before_move_contract, zone_s2_goal_heading_contract
    from harness import zone_s2_staged_approach_contract, zone_s2_staging_only_contract
    for module in (run_s2_v133_reproduction, run_s2_v133_baseline_v52,
                   zone_s2_landmarks_contract, zone_s2_side_scan_contract,
                   zone_s2_look_before_move_contract, zone_s2_goal_heading_contract,
                   zone_s2_staged_approach_contract, zone_s2_staging_only_contract):
        original = module.PLAN
        plan = FIX / Path(original).name
        assert plan.is_file(), plan
        monkeypatch.setattr(module, 'PLAN',
                            str(plan.relative_to(module.ROOT)) if isinstance(original, str) else plan)

    # Historical v133 contract inputs describe the frozen checkout, not HEAD.
    # Materialize its actual Git blobs; keep the production hash check intact.
    baseline = json.loads((FIX / 'v133-bundle.json').read_text())
    source_root = zone_s2_landmarks_contract.ROOT
    original_require = zone_s2_landmarks_contract.require_execution
    frozen_root = tmp_path / 'frozen-v133'

    def require_with_recorded_sources(value):
        if (value.get('source_sha') != baseline['source_sha']
                or value.get('execution_bundle_id') != baseline['execution_bundle_id']):
            return original_require(value)
        if not frozen_root.exists():
            paths = sorted(baseline['source_sha256'])
            archive = subprocess.check_output(
                ['git', 'archive', baseline['source_sha'], '--', *paths], cwd=source_root)
            frozen_root.mkdir()
            with tarfile.open(fileobj=io.BytesIO(archive)) as files:
                files.extractall(frozen_root, filter='data')
        # Only the historical admission call sees the archived source tree.
        # Newly built option bundles still hash and validate current sources.
        with monkeypatch.context() as scope:
            scope.setattr(zone_s2_landmarks_contract, 'ROOT', frozen_root)
            scope.setattr(zone_s2_landmarks_contract, 'PLAN',
                          str(FIX / 'landmarks-physical-registration.json'))
            return original_require(value)

    monkeypatch.setattr(zone_s2_landmarks_contract, 'require_execution',
                        require_with_recorded_sources)
