"""F312-1: verify that the regression detects a host exempted from boundary checks.

Run with the existing Python environment. All mutations are in memory; no
physics, inference, network, repository edits, or extraction directories.
"""
from contextlib import nullcontext
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
for name in ('mujoco', 'torch', 'torchvision'):
    sys.modules[name] = None


def main():
    spec = importlib.util.spec_from_file_location('eval_boundary_tests', ROOT / 'tests/test_zone_eval_top.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = module.RobotInputBoundaryTests
    check = case.assert_eval_only_uses
    rows = []
    for name, ignored, expected in (
        ('normal', (), 0),
        ('skip_p03_boundary', ('zone_study_provider_p03.py',), 2),
        ('skip_legacy_boundary', ('run_zone_study_integration.py',), 2),
        ('skip_both_boundaries', ('zone_study_provider_p03.py', 'run_zone_study_integration.py'), 4),
    ):
        def mutated(self, path):
            if path.name not in ignored:
                check(self, path)

        context = patch.object(case, 'assert_eval_only_uses', mutated) if ignored else nullcontext()
        with context:
            result = unittest.TextTestRunner(stream=io.StringIO()).run(
                case('test_each_host_rejects_evaluation_camera_use_in_control'))
        failures = [text for _, text in result.failures]
        assert not result.errors and not result.skipped, (name, result.errors, result.skipped)
        assert len(failures) == expected, (name, failures)
        assert all('AssertionError not raised' in text for text in failures), (name, failures)
        rows.append({'mutation': name, 'expected_assertion_failures': expected,
                     'observed_assertion_failures': len(failures), 'errors': 0,
                     'tracebacks': failures})
    print(json.dumps({'boundary_mutants_detected': 3, 'rows': rows}, indent=2))


if __name__ == '__main__':
    main()
