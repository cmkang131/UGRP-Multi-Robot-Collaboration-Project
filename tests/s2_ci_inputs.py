"""Portable recorded inputs for offline S2 contract tests, never runtime defaults."""
from pathlib import Path
import pytest

FIX = Path(__file__).resolve().parent / 'fixtures/s2_ci'


@pytest.fixture
def portable_s2_inputs(monkeypatch):
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
