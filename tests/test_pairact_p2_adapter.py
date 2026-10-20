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
    assert "DEPENDENCY_SHA = '01ed171fc93140683227072a10aecff55150b45f'" in text   # teacher -c (P3 collect admission)


def test_floor_candidate_only_adds_lower_mode():
    profiles = _profiles()
    floor, p2 = profiles('pairact_p2_r13_floor'), profiles('pairact_p2_r13')
    assert {k: v for k, v in floor.items() if k != 'carry_lower'} == p2
    assert floor['carry_lower'] == 'floor_contact_v1' and 'carry_lower' not in p2


# ------------------------------------------------ pairact P3 collect (adapter -c)

import subprocess

import pytest

BASE = '6843fcaa94785e46ee52ef1889e392ca988d604d'     # dsh/pairact-p2-carrypath-a


def test_p3_collect_candidate_is_p2_profile_unchanged():
    profiles = _profiles()
    assert profiles('pairact_p3_collect') == profiles('pairact_p2_r13')
    assert not any(k in profiles('pairact_p3_collect') for k in ('record_training', 'recording_proof', 'noise'))


def test_existing_candidates_keep_the_exact_recording_off_call():
    try:
        out = subprocess.run(['git', '-C', str(ROOT), 'diff', '-U0', BASE, '--', 'scripts/run_beampair1.py',
                              'harness/beampair_teacher.py'], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        pytest.skip(f'base commit unavailable: {error}')
    removed = sorted(l[1:].strip() for l in out.splitlines() if l.startswith('-') and not l.startswith('---'))
    assert removed == sorted([
        "DEPENDENCY_SHA = '59299f903f4a2f9a2eabe5ff0e442e0ce25e8266'",
        "report=runner.run(plan,out,cap_s=cap_s,record_training=False,noise=False,execution_host=host,**selected)"])
    text = (ROOT/'scripts/run_beampair1.py').read_text()
    assert ("                else:\n                    report=runner.run(plan,out,cap_s=cap_s,record_training=False,"
            "noise=False,execution_host=host,**selected)\n") in text
    assert "if candidate==COLLECT_CANDIDATE:" in text and "COLLECT_CANDIDATE='pairact_p3_collect'" in text


def _adapter_funcs():
    import ast
    tree = ast.parse((ROOT/'scripts/run_beampair1.py').read_text())
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('collect_probe', 'collect_proof')]
    import os
    ns = {'os': os}
    exec(compile(ast.Module(body=keep, type_ignores=[]), 'collect', 'exec'), ns)
    return ns


def test_collect_env_is_required_and_probe_flag_strict(monkeypatch):
    ns = _adapter_funcs()
    monkeypatch.delenv('PAIRACT_P3_COLLECT_PREREG', raising=False)
    with pytest.raises(ValueError, match='FROZEN'):
        ns['collect_proof']({}, {})
    monkeypatch.setenv('PAIRACT_P3_RECORDING_PROBE', 'yes')
    with pytest.raises(ValueError, match='0 or 1'):
        ns['collect_probe']()
    monkeypatch.setenv('PAIRACT_P3_RECORDING_PROBE', '1')
    assert ns['collect_probe']() is True
    monkeypatch.delenv('PAIRACT_P3_RECORDING_PROBE')
    assert ns['collect_probe']() is False
