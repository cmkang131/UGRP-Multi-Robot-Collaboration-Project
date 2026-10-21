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


def test_cand2b_arm_is_registered(tmp_path):
    src = tmp_path/'src.json'; src.write_text(json.dumps(_doc()))
    m.main(src, tmp_path/'c2b.json', 'pairact_p1c2b')
    assert {c['candidate'] for c in json.loads((tmp_path/'c2b.json').read_text())} == {'pairact_p1c2b'}


_G = Path(__file__).resolve().parents[1]/'experiments/2026-10-21-pairact-p1/p1_gate.py'
_gs = importlib.util.spec_from_file_location('p1_gate', _G)
g = importlib.util.module_from_spec(_gs); _gs.loader.exec_module(g)


def test_d3_effective_denominator_threshold():
    assert g.threshold(40, []) == (40, 38)
    assert g.threshold(40, [37]) == (39, 38)
    assert g.threshold(40, [36, 37]) == (38, 37)
    assert g.threshold(40, [1, 2, 3, 4, 5]) == (35, 34)    # 33.25 -> 34
    assert g.indices(5, [3], [1]) == [0, 2, 4]
    with pytest.raises(ValueError):
        g.indices(5, [], [7])


def test_verdict_counts_missing_as_failure_and_reports_both_denominators():
    v = g.verdict([{'arm': 'r13', 'success_n': 37}, {'arm': 'c1', 'success_n': 38},
                   {'arm': 'c3', 'success_n': None}], 40, [37])
    assert (v['N_eff'], v['need']) == (39, 38)
    assert [(a['arm'], a['adopt'], a['nominal'], a['effective']) for a in v['arms']] == [
        ('r13', False, '37/40', '37/39'), ('c1', True, '38/40', '38/39'), ('c3', False, '0/40', '0/39')]


def test_run_requires_frozen_prereg_with_recorded_exclusions():
    doc = json.loads((_G.parent/'PAIRACT_P1_PREREG_DRAFT.json').read_text())
    assert doc['status'] != 'FROZEN'
    with pytest.raises(SystemExit):
        g.check_frozen(doc, 'tournament')
    doc['status'] = 'FROZEN'
    doc['static_exclusion']['tournament']['excluded_worlds'] = None   # c7089b68f recorded []; test the unfilled case
    with pytest.raises(SystemExit):                       # list not yet filled by the static check
        g.check_frozen(doc, 'tournament')
    doc['static_exclusion']['tournament']['excluded_worlds'] = []
    assert g.check_frozen(doc, 'tournament') == []
    assert [a['arm'] for a in doc['arms_registered_order']] == ['r13', 'c1', 'c2b', 'c3']
