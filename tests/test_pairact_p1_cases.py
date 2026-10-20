"""pairact P1: arm cases derivation changes only the candidate field."""
import importlib.util
import json
from pathlib import Path

import pytest

_P = Path(__file__).resolve().parents[1]/'experiments/2026-10-21-pairact-p1/make_arm_cases.py'
_spec = importlib.util.spec_from_file_location('make_arm_cases', _P)
m = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(m)


def _doc():
    return [dict(plan={'seed': i, 'spawns': {}}, profile=None, candidate='beamact5_r13') for i in range(3)]


def test_only_candidate_changes_and_source_untouched(tmp_path):
    src = tmp_path/'src.json'; src.write_text(json.dumps(_doc())); before = src.read_bytes()
    m.main(src, tmp_path/'c1.json', 'pairact_p1c1')
    out = json.loads((tmp_path/'c1.json').read_text())
    assert [c['candidate'] for c in out] == ['pairact_p1c1']*3
    assert [c['plan'] for c in out] == [c['plan'] for c in _doc()]
    assert src.read_bytes() == before


def test_rejects_unknown_arm_and_existing_output(tmp_path):
    with pytest.raises(ValueError):
        m.derive(_doc(), 'beamact5_r14')
    src = tmp_path/'src.json'; src.write_text(json.dumps({'cases': _doc()}))
    (tmp_path/'x.json').write_text('{}')
    with pytest.raises(FileExistsError):
        m.main(src, tmp_path/'x.json', 'beamact5_r13')
