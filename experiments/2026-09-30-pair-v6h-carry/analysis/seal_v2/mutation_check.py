"""Remove acquisition admission in memory; the two review regressions must fail.

No repository edits/extraction or recorded evidence reads. Run with --output to
preserve the synthetic-only pytest log/JUnit and machine-readable receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
MODULE = 'experiments.2026-09-30-pair-v6h-carry.analysis.apply_sealed_analysis'
TARGET = ROOT / 'experiments/2026-09-30-pair-v6h-carry/analysis/apply_sealed_analysis.py'
TESTS = ['tests/test_review_seal_v6h1.py::test_missing_acquisition_inventory_must_block_pass',
         'tests/test_review_seal_v6h1.py::test_trace_edit_cannot_flip_failed_B_to_pass_with_same_pinned_inputs']


def worker(output):
    sys.path.insert(0, str(ROOT))
    import pytest
    source = TARGET.read_text()
    original = '        reader.load_inventory(inventory, inventory_pin)'
    assert source.count(original) == 1
    mutated = source.replace(original, '''        reader = classifier.EvidenceReader(Path(raw).resolve())
        reader.manifest = Path(manifest).resolve()''')

    class RemoveInventory:
        def pytest_collection_finish(self, session):
            module = importlib.import_module(MODULE)
            exec(compile(mutated, str(TARGET), 'exec'), module.__dict__)

    return pytest.main(['-q', '-p', 'tests.pose_provider_no_physics', '-p', 'tests.v6h_seal_offline_guard',
                       '--junitxml=' + str(output / 'mutation.xml'), *TESTS], plugins=[RemoveInventory()])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.worker:
        return worker(args.output)
    args.output.mkdir(parents=True, exist_ok=False)
    original = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                             '--output', str(args.output.resolve())], cwd=ROOT, capture_output=True, text=True)
    (args.output / 'mutation.log').write_text(result.stdout + result.stderr)
    cases = ET.parse(args.output / 'mutation.xml').getroot().findall('.//testcase')
    failures = [c for c in cases if c.find('failure') is not None]
    unchanged = original == hashlib.sha256(TARGET.read_bytes()).hexdigest()
    assert result.returncode == 1 and len(cases) == len(failures) == 2
    assert all(c.find('error') is None and c.find('skipped') is None for c in cases)
    # Both fail because the mutant returns an analysed report instead of None,
    # not a preparation/subprocess failure or an unrelated malformed schema.
    assert all('is None' in c.find('failure').get('message', '') for c in failures)
    assert unchanged
    receipt = {'mutation': 'remove inventory admission; replace AcquisitionReader with EvidenceReader',
               'source_sha256': original, 'source_unchanged': unchanged, 'expected_pytest_exit': 1,
               'pytest_exit': result.returncode, 'failed_regressions': [c.get('name') for c in failures],
               'raw_or_real_inventory_access': False, 'physics_or_render': False,
               'temporary_extraction_created': False, 'status': 'MUTATION_DETECTED'}
    (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
