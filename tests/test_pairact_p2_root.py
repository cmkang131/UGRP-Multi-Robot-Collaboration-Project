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
    assert "ADAPTER_SHA = '6843fcaa94785e46ee52ef1889e392ca988d604d'" in text
    assert "TEACHER_SHA = '59299f903f4a2f9a2eabe5ff0e442e0ce25e8266'" in text


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


# ------------------------------------------------------------ P5 student eval

def _runner_module():
    import sys
    sys.path.insert(0, str(ROOT/'scripts'))
    spec = importlib.util.spec_from_file_location('p2runner', ROOT/'scripts/run_warp_flow_teacher.py')
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ModuleNotFoundError as error:
        pytest.skip(f'root runner imports unavailable here: {error}')
    return mod


CFG = {'mode': 'pairact_r1_student_eval_v1', 'python': '/venv/bin/python', 'source': '/src/student',
       'model': '/runs/ckpt', 'config': '/src/student/cfg.json', 'device': 'cuda'}


def test_student_eval_config_is_exact_absolute_and_pinned(tmp_path, monkeypatch):
    mod = _runner_module()
    assert mod.load_student_eval(None) is None
    path = tmp_path/'s.json'
    monkeypatch.setattr(mod, 'source_head', lambda p: mod.STUDENT_SHA)
    path.write_text(json.dumps(CFG))
    assert mod.load_student_eval(path) == CFG
    for bad in ({**CFG, 'gt_pose': True}, {**CFG, 'model': 'rel/ckpt'}, {**CFG, 'mode': 'x'}):
        path.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            mod.load_student_eval(path)
    path.write_text(json.dumps(CFG))
    monkeypatch.setattr(mod, 'source_head', lambda p: '0'*40)
    with pytest.raises(ValueError, match='pinned'):
        mod.load_student_eval(path)


def test_student_eval_default_off_and_injected_only_when_set():
    runner = (ROOT/'scripts/run_warp_flow_teacher.py').read_text()
    episode = (ROOT/'scripts/warp_flow_episode.py').read_text()
    assert "p.add_argument('--student-eval',type=Path" in runner and 'default OFF' in runner
    assert "student_eval=None):" in episode and 'bridge.student_eval = student_eval' in episode
    assert "if self.student_eval is not None:" in episode
    assert "STUDENT_SHA='3c9337d5f5c9deefd49139b26ae7117022e3d5cc'" in runner
