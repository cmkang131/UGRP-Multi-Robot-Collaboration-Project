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
    assert "DEPENDENCY_SHA = 'a3cb7ffdf4a31b32685be98f1eda178b4900730e'" in text   # teacher -c6 (-c5 + detour_v2 opt-in)


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
    """Existing candidates still call runner.run(plan,out,cap_s=cap_s,record_training=False,noise=False,
    execution_host=host,**selected); the collect candidate only overrides three keywords. One call site."""
    try:
        out = subprocess.run(['git', '-C', str(ROOT), 'diff', '-U0', BASE, '--', 'scripts/run_beampair1.py',
                              'harness/beampair_teacher.py'], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        pytest.fail(f'base commit {BASE} unavailable ({error}): git fetch origin {BASE} (required check, not skippable)')
    removed = sorted(l[1:].strip() for l in out.splitlines() if l.startswith('-') and not l.startswith('---'))
    assert removed == sorted([
        "DEPENDENCY_SHA = '59299f903f4a2f9a2eabe5ff0e442e0ce25e8266'",
        "report=runner.run(plan,out,cap_s=cap_s,record_training=False,noise=False,execution_host=host,**selected)"])
    text = (ROOT/'scripts/run_beampair1.py').read_text()
    assert text.count('runner.run(') == 1
    assert "run_kwargs=dict(record_training=False,noise=False,execution_host=host,**selected)" in text
    assert "report=runner.run(plan,out,cap_s=cap_s,**run_kwargs)" in text
    assert "if candidate in COLLECT_CANDIDATES:" in text and "COLLECT_CANDIDATE='pairact_p3_collect'" in text
    assert "COLLECT_CANDIDATES=(COLLECT_CANDIDATE,'pairact_p3_collect_detour')" in text


def test_run_kwargs_equal_the_old_calls():
    """The merged call passes exactly the old keyword sets (existing candidate / collect candidate)."""
    import textwrap
    src = (ROOT/'scripts/run_beampair1.py').read_text()
    block = src[src.index('                run_kwargs=dict('):src.index('                report=runner.run(plan,out,cap_s=cap_s,**run_kwargs)')]
    selected = {'teacher_profile': 'p'}
    for candidate, expect in (('pairact_p2_r13', dict(record_training=False, noise=False, execution_host='h', **selected)),
                              ('pairact_p3_collect', dict(record_training=True, noise=False, execution_host='h',
                                                          recording_proof='proof', recording_probe=False, **selected))):
        ns = dict(candidate=candidate, COLLECT_CANDIDATE='pairact_p3_collect', host='h', selected=selected,
                  COLLECT_CANDIDATES=('pairact_p3_collect', 'pairact_p3_collect_detour'),
                  collect_proof=lambda host, sel: 'proof', collect_probe=lambda: False)
        exec(textwrap.dedent(block), ns)
        assert ns['run_kwargs'] == expect


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


# ------------------------------------------- -c3 carry detour (teacher carry_route detour_v1)

def test_detour_candidate_only_adds_carry_route():
    profiles = _profiles()
    det, p2 = profiles('pairact_p2_r13_detour'), profiles('pairact_p2_r13')
    assert {k: v for k, v in det.items() if k != 'carry_route'} == p2
    assert det['carry_route'] == 'detour_v1' and 'carry_route' not in p2
    assert profiles('pairact_p3_collect_detour') == det
    for name in ('pairact_p2_r13', 'pairact_p2_r13_floor', 'pairact_p3_collect', 'beamact5_r13'):
        assert 'carry_route' not in profiles(name)


def test_detour_collect_records_like_collect_and_detour_does_not():
    import textwrap
    src = (ROOT/'scripts/run_beampair1.py').read_text()
    block = src[src.index('                run_kwargs=dict('):src.index('                report=runner.run(plan,out,cap_s=cap_s,**run_kwargs)')]
    selected = {'teacher_profile': 'p', 'carry_route': 'detour_v1'}
    rec = dict(record_training=True, noise=False, execution_host='h', recording_proof='proof', recording_probe=False,
               **selected)
    for candidate, expect in (('pairact_p2_r13_detour', dict(record_training=False, noise=False, execution_host='h',
                                                             **selected)),
                              ('pairact_p3_collect_detour', rec)):
        ns = dict(candidate=candidate, COLLECT_CANDIDATE='pairact_p3_collect', host='h', selected=selected,
                  COLLECT_CANDIDATES=('pairact_p3_collect', 'pairact_p3_collect_detour'),
                  collect_proof=lambda host, sel: 'proof', collect_probe=lambda: False)
        exec(textwrap.dedent(block), ns)
        assert ns['run_kwargs'] == expect


# ------------------------------------------- -c6 carry detour_v2 (teacher carry_route detour_v2)

def test_detour2_candidates_only_add_route_and_lower():
    from scripts.run_beampair1 import profiles, COLLECT_CANDIDATES
    d2, p2 = profiles('pairact_p2_r13_detour2'), profiles('pairact_p2_r13')
    assert {k: v for k, v in d2.items() if k != 'carry_route'} == p2 and d2['carry_route'] == 'detour_v2'
    d2f = profiles('pairact_p2_r13_detour2_floor')
    assert {k: v for k, v in d2f.items() if k != 'carry_lower'} == d2 and d2f['carry_lower'] == 'floor_contact_v1'
    assert profiles('pairact_p2_r13_detour')['carry_route'] == 'detour_v1'           # -c3 candidate unchanged
    assert profiles('pairact_p2_r13_floor') == {**p2, 'carry_lower': 'floor_contact_v1'}
    assert 'pairact_p2_r13_detour2' not in COLLECT_CANDIDATES and 'pairact_p2_r13_detour2_floor' not in COLLECT_CANDIDATES
