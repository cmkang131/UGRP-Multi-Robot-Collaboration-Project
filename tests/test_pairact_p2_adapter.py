import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _profiles():
    tree = ast.parse((ROOT/'scripts/run_beampair1.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'profiles')
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'profiles', 'exec'), ns)
    return ns['profiles']


def test_p2_candidate_is_r13_plus_carry_only():
    profiles = _profiles()
    p2, r13 = profiles('pairact_p2_r13'), profiles('beamact5_r13')
    assert {k: v for k, v in p2.items() if k not in ('pair_carry', 'carry_cap_s')} == r13
    assert p2['pair_carry'] == 'pair_carry_gt_v1' and p2['carry_cap_s'] == 110.
    assert 'pair_carry' not in r13


def test_dependency_pin_is_p2_teacher():
    text = (ROOT/'harness/beampair_teacher.py').read_text()
    assert "DEPENDENCY_SHA = 'ccd33332743b7e1b5fa9ec0ef8555edbba966713'" in text
