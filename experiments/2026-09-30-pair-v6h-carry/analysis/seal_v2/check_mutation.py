"""Synthetic mutation: remove acquisition-read checks without editing sources."""
import importlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import pytest


def main():
    gate = importlib.import_module('experiments.2026-09-30-pair-v6h-carry.analysis.apply_sealed_analysis')
    original = gate.AcquisitionReader.read
    try:
        gate.AcquisitionReader.read = gate.classifier.EvidenceReader.read
        result = pytest.main(['-q', '-p', 'tests.pose_provider_no_physics',
            str(ROOT/'tests/test_v6h_acquisition_reader.py'), '-k', 'every_consumed_input'])
    finally:
        gate.AcquisitionReader.read = original
    # Only assertion failures kill this mutant; collection/import errors do not.
    if result != pytest.ExitCode.TESTS_FAILED:
        raise SystemExit(f'acquisition-check-removal mutant survived or test error: {result}')
    print('MUTANT_KILLED: acquisition read checks removed; tests failed')


if __name__ == '__main__':
    main()
