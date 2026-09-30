"""Independent batch G counterexamples, pinned to the reviewed PR #325 bytes.

Offline only: read git blobs; no imports from a controller, simulator or model.
Run with pytest. Set REVIEW_E2E_G_PR325_TREE to an extracted/fixed candidate
root to check a successor. Fixes deliberately XPASS(strict), requiring review.
Missing git objects/files are errors, never expected failures.
PR #329 has no confirmed counterexample in this review.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = 'd7ee112e22018055ec08e1098c3f33a7a06cb420'
PR325 = 'be97d9dd53638a1efbda7627b420bd9b1cbd9880'
PR329 = '823a1ac6d2d62b7cd0e12b3bbc01dfbea0f5f3e5'
REGISTRATION = 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json'
CHANGED_PINNED_SOURCES = (
    'harness/owncam_delivery_shared.py',
    'harness/zone_own_deliver.py',
    'harness/zone_own_team_host.py',
    'harness/zone_own_executor.py',
    'harness/zone_own_status.py',
)


def _blob(revision, path):
    return subprocess.check_output(['git', 'show', f'{revision}:{path}'], cwd=ROOT)


def _candidate(path):
    tree = os.environ.get('REVIEW_E2E_G_PR325_TREE')
    return (Path(tree) / path).read_bytes() if tree else _blob(PR325, path)


def test_counterexample_baseline_and_unmodified_recovery_tree_match_v6e_pins():
    """The five mismatches are introduced by #325, not pre-existing on main."""
    record = _blob(BASE, REGISTRATION)
    pins = json.loads(record)['v6_contract']['source_sha256']
    assert _blob(PR325, REGISTRATION) == record == _blob(PR329, REGISTRATION)
    for path in CHANGED_PINNED_SOURCES:
        for revision in (BASE, PR329):
            assert hashlib.sha256(_blob(revision, path)).hexdigest() == pins[path]


@pytest.mark.parametrize('path', CHANGED_PINNED_SOURCES)
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason='G-325-1: T03 edits five sources pinned by the current v6e registration')
def test_pr325_preserves_current_v6e_source_bytes(path):
    """Expected: opt-in color support leaves the existing sealed source intact."""
    original = _blob(BASE, REGISTRATION)
    assert _candidate(REGISTRATION) == original, 'Do not repair the counterexample by rewriting the old seal'
    expected = json.loads(original)['v6_contract']['source_sha256'][path]
    actual = hashlib.sha256(_candidate(path)).hexdigest()
    assert actual == expected, f'{path}: v6e={expected}, candidate={actual}'
