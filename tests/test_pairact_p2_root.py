import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('p2cases', ROOT/'experiments/2026-10-21-pairact-p2/make_p2_cases.py')
p2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p2)


def test_pins_point_to_p2_trees():
    text = (ROOT/'scripts/warp_flow_episode.py').read_text()
    assert "ADAPTER_SHA = '76532d0dd6aa770cea19c65a734b893159d898de'" in text
    assert "TEACHER_SHA = '208e61490cfc19aef2a95954841e76a929fc0666'" in text


def test_derive_rejects_other_cases_file():
    with pytest.raises(ValueError, match='hash mismatch'):
        p2.derive(b'[]')


def test_derive_changes_only_candidate(monkeypatch):
    cases = [{'plan': {'seed': 8420000 + i, 'scene_profile': 'walls_floor_contrast_v5_indigo110_s80'},
              'candidate': 'beamact5_r13'} for i in range(40)]
    raw = json.dumps(cases).encode()
    monkeypatch.setattr(p2, 'R13_CASES_SHA256', hashlib.sha256(raw).hexdigest())
    out = p2.derive(raw)
    assert [c['source_world_index'] for c in out] == [1, 11, 17]
    assert all(c['candidate'] == 'pairact_p2_r13' for c in out)
    assert [c['plan'] for c in out] == [cases[i]['plan'] for i in (1, 11, 17)]


def test_smoke_worlds_are_fastest_r13_grasps():
    # SMOKE.md §2 rule on the committed attempt-1 funnel: sim 22.8 / 24.3 / 25.2.
    assert p2.select_worlds(p2.load_funnel()) == (1, 11, 17)


def test_select_worlds_tie_breaks_by_case_and_skips_failures():
    funnel = {'per_case': [
        {'case': 9, 'sim': 20.0, 'succ': True}, {'case': 4, 'sim': 20.0, 'succ': True},
        {'case': 2, 'sim': 10.0, 'succ': False}, {'case': 7, 'sim': 30.0, 'succ': True},
        {'case': 8, 'sim': 40.0, 'succ': True}]}
    assert p2.select_worlds(funnel) == (4, 9, 7)


def test_attempt2_agrees_on_the_same_three_worlds():
    funnel = json.loads((ROOT/'experiments/2026-10-21-pairact-p2/r13-funnel-attempt2.json').read_text())
    assert p2.select_worlds(funnel) == (1, 11, 17)
