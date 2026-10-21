"""E2E-min PREREG_DRAFT: registered N and level keys stay aligned with the code and report_tables."""
from pathlib import Path
import re

from harness.e2e_min_handoff import LEVELS

DOC = (Path(__file__).resolve().parents[1] / 'experiments/2026-10-21-e2e-min/PREREG_DRAFT.md').read_text()


def test_registered_n_is_fixed_3_and_6():
    assert "**등록 N(고정):** E2E-1' 3, E2E-2 6" in DOC
    assert re.search(r"\| \*\*E2E-1'\*\* \(`E2E-1p`\).*\| smoke 1\(합산하지 않음\) \+ 본 3 \|", DOC)
    assert re.search(r"\| E2E-2 \(`E2E-2`\).*\| 6 \|", DOC)


def test_level_keys_and_host_error_rule():
    assert set(LEVELS) == {'E2E-1p', 'E2E-2'}
    assert 'HOST_ERROR는 재실행하지 않습니다' in DOC
    assert '"level":"E2E-1p"|"E2E-2"' in DOC
