"""Shared fixtures. Only the pair LLM tests are touched here."""
import pytest


@pytest.fixture(autouse=True)
def _pair_llm_formal_flags(request, monkeypatch):
    """pair_llm tests that build a MEASURED_SIM bundle run on the formal controller path.

    #363's DEV-only switches default to ON; a non-DEV_PILOT, non-synthetic bundle is refused while any is on
    (``require_dev_only_flags``, review #371 P2). A test that needs a DEV switch sets it itself."""
    if not request.node.nodeid.split('::')[0].rsplit('/', 1)[-1].startswith('test_pair_llm_'):
        return
    from harness import zone_pair_highpose_contract as c
    monkeypatch.setattr(c, 'DEV_LIGHT', False)
    monkeypatch.setattr(c, 'PARTIAL_FIX', False)
    monkeypatch.setattr(c, 'COLLISION_GUARD_MODE', 'enforce')
