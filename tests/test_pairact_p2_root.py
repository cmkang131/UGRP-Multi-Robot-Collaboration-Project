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
    assert "ADAPTER_SHA = 'db4920b9a22f6a755538291a92adfb21a6687e42'" in text
    assert "TEACHER_SHA = 'ccd33332743b7e1b5fa9ec0ef8555edbba966713'" in text


def test_derive_rejects_other_cases_file():
    with pytest.raises(ValueError, match='hash mismatch'):
        p2.derive(b'[]')


def test_derive_changes_only_candidate(monkeypatch):
    cases = [{'plan': {'seed': 8420000 + i, 'scene_profile': 'walls_floor_contrast_v5_indigo110_s80'},
              'candidate': 'beamact5_r13'} for i in range(40)]
    raw = json.dumps(cases).encode()
    monkeypatch.setattr(p2, 'R13_CASES_SHA256', hashlib.sha256(raw).hexdigest())
    out = p2.derive(raw)
    assert [c['source_world_index'] for c in out] == [6, 10, 20]
    assert all(c['candidate'] == 'pairact_p2_r13' for c in out)
    assert [c['plan'] for c in out] == [cases[i]['plan'] for i in (6, 10, 20)]
