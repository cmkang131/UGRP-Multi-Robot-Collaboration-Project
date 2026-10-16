"""Audit historical v6e/v6h receipts, independently of later main sources."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SEAL = '5be4330eca9b23d2cbde3657dcbb215ee1923b25'
REGISTRATION = 'experiments/2026-09-30-pair-v6h-carry/analysis/seal_v2/prereg_v6h.json'


def successor_blob(path):
    """Read the recorded seal's Git object; never substitute working-tree bytes."""
    from scripts.zone_pair_registered_source import committed_blob
    return committed_blob(str(ROOT), SEAL, path)


def successor_pins(contract='v6_contract'):
    """Audit v6e at its commit; return sealed successor hashes for those paths.

    These are historical pins, not constraints on post-unblinding main sources.
    Callers hash successor_blob(), or an explicitly selected negative-control
    candidate. Neither registration may be rewritten.
    """
    from scripts.zone_pair_v6_contract import PREREG_V6E, verify_v6_historical
    verify_v6_historical(revision='v6e')
    old = json.loads(PREREG_V6E.read_bytes())[contract]['source_sha256']
    raw = (ROOT / REGISTRATION).read_bytes()
    assert raw == subprocess.check_output(['git', 'show', f'{SEAL}:{REGISTRATION}'], cwd=ROOT)
    active = json.loads(raw)['pin_sets']['analysis']['files']
    assert old.keys() <= active.keys()
    return {path: active[path]['sha256'] for path in old}
